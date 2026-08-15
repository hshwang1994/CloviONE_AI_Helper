"""사용자 셀프서비스 티켓 조회/편집 (내 티켓 / 미할당 / 팀 / 생성·편집).

이 모듈은 **소스를 모른다**. 티켓을 읽고 쓰는 일은 전부 TicketRepository(app/tickets/repository.py)
뒤에 있고, Notion 속성 이름·스키마·페이지네이션은 구현체(repository_notion.py) 안에만 있다.
여기 남는 것은 소스와 무관한 규칙뿐이다: 로그인 사용자 기준 필터, 담당자 이름/앱 user_id 해석,
소유권(IDOR) 검사, 감사 스냅샷, 휴지통.

보안(스펙 §12.3): 대상 notion_user_id 는 **세션 사용자에서만** 도출한다. 브라우저는 소스 user id 를
주지도 받지도 않는다 — 응답에는 해석된 user_id/이름만 싣는다.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import people
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.core.models_base import utcnow
from app.core.notion_blocks import rendered_to_markdown
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.reports.service import STATUS_CANCELLED, STATUS_DONE, _load_name_map
from app.tickets import attachments as ticket_attachments
from app.tickets import comments
from app.tickets.repository import (
    PageSpec,
    TicketDraft,
    TicketDTO,
    TicketFilters,
    snapshot,
)
from app.trash import repository as trash_repo
from app.trash import service as trash_service
from app.trash.models import TRASH_TICKET
from app.core.authz import MODERATOR_ROLES
from app.users.models import User

logger = logging.getLogger("app.tickets")

# 완료·취소는 '끝난' 티켓 — 미할당 목록의 기본에서 뺀다(진행/계획/이슈/검증만 담당자 필요).
_TERMINAL = {STATUS_DONE, STATUS_CANCELLED}



def _repo(settings, outbound, repo=None, *, use_cache: bool | None = None):
    """저장소를 얻는다. 라우터는 app.state.repositories.tickets 를 넘기고, 앱 없이 부르는
    유닛 테스트 경로에서는 설정대로 새로 만든다(선택 로직 자체는 source_registry 한 곳뿐)."""
    if repo is not None:
        return repo
    from app.core.source_registry import build_ticket_repository

    built = build_ticket_repository(settings, outbound)
    if use_cache is not None:
        built.use_cache = use_cache
    return built


def my_notion_id(db: Session, user: User) -> str | None:
    """로그인 사용자의 verified Notion user id(정방향). 매핑이 없거나 미검증이면 None.

    reports 의 _load_name_map 은 역방향(notion id → 이름)이라 여기엔 못 쓴다 — 정방향 전용.
    """
    row = db.execute(
        select(UserNotionMapping.notion_user_id).where(
            UserNotionMapping.user_id == user.id,
            UserNotionMapping.status == STATUS_VERIFIED,
        )
    ).first()
    return row[0] if row and row[0] else None


def _verified_id_to_user(db: Session) -> dict[str, str]:
    """verified·active 매핑의 notion_user_id → 앱 user_id. 담당자 편집(해석/보존/역표시)에 쓴다.

    _load_name_map 은 표시용 이름(전 사용자 포함)이라 편집엔 못 쓴다 — 편집 후보/보존 판정은
    반드시 'verified + active' 로만 한다(스펙 §12.3).
    """
    rows = db.execute(
        select(UserNotionMapping.notion_user_id, User.id)
        .join(User, User.id == UserNotionMapping.user_id)
        .where(
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
            User.active.is_(True),
            User.archived_at.is_(None),
        )
    ).all()
    out: dict[str, str] = {}
    for nid, uid in rows:
        out.setdefault(nid, uid)
    return out


def ticket_view(t: TicketDTO, id_to_name: dict[str, str], id_to_user: dict[str, str]) -> dict:
    """티켓 한 건의 API 응답 dict.

    `id` 는 계속 Notion page id 다 — 딥링크·휴지통·감사가 전부 이 값을 키로 쓴다. 자체 UUID 는
    `uid` 로 따로 싣는다(소스 전환 뒤 내부 참조가 옮겨 갈 자리). raw 소스 user id 는 절대
    싣지 않는다(§12.3) — 이름/앱 user_id 로 해석한 결과만 나간다.
    """
    names = [id_to_name.get(a) for a in t.assignee_ids]
    uids = [id_to_user.get(a) for a in t.assignee_ids]
    pnames = list(t.project_names)
    return {
        "id": t.page_id,
        "uid": t.uid,
        "url": t.url,
        "tid": t.number,
        "title": t.title,
        "status": t.status,
        "due": t.due,
        "start": t.start,
        "category": t.category,
        "est_wd": t.est_wd,
        "act_wd": t.act_wd,
        "difficulty": t.difficulty,
        "priority": t.priority,
        "project_ids": list(t.project_ids),
        "assignee_names": [n for n in names if n],
        "assignee_user_ids": [u for u in uids if u],
        "project_names": pnames,
        "project": pnames[0] if pnames else "",
    }


def ticket_views(db: Session, tickets, *, with_names: bool = True) -> list[dict]:
    """DTO 목록 → API 응답 dict 목록. 스프린트의 담당자별 리스트도 이걸 써서 모양이 같다."""
    id_to_name = _load_name_map(db)[0] if with_names else {}
    id_to_user = _verified_id_to_user(db) if with_names else {}
    return [ticket_view(t, id_to_name, id_to_user) for t in tickets]


def drop_out_of_scope_dtos(db: Session, dtos, viewer) -> list:
    """DTO 목록에서 범위 밖 티켓을 뺀다 (스프린트·리포트 집계용).

    화면용 view 가 아니라 DTO 를 다루는 경로(집계)가 따로 있어서, 판정 규칙이 두 벌이 되지
    않게 여기 한 곳에 둔다 — 화면 목록은 좁혀 놓고 집계가 전 포탈이면 **담당자별 생산성이
    숫자로 새어 나간다**(그게 스프린트 요약에서 실제로 일어나던 일이다).

    담당자를 해석할 수 없는 티켓은 부서 집계에서 뺀다. 그건 미할당 트리아지의 몫이고,
    아무 팀의 성과도 아니다.
    """
    if viewer is None:
        return list(dtos)
    from app.core.scope import any_assignee_visible, build_scope, visible_user_ids

    # UA-02: 예전엔 `scope.is_dept`일 때만 걸러 org 범위 뷰어는 그대로 통과했다.
    # `visible_user_ids`가 전역일 때만 `None`(무제한)을 주므로 그 판정 하나로 충분하다.
    scope = build_scope(db, viewer)
    id_to_user = _verified_id_to_user(db)
    visible = visible_user_ids(db, scope)
    return [
        d for d in dtos
        if any_assignee_visible(
            [id_to_user.get(n) for n in (getattr(d, "assignee_ids", ()) or ())], visible
        )
    ]


def ensure_in_scope(db: Session, page_id: str, viewer: "User | None") -> None:
    """범위 밖 티켓은 **없는 것으로 취급한다** (1순위 유출 #2).

    `GET /api/tickets/{page_id}` 는 로그인만 하면 **id 하나로** 본문·댓글·첨부 원본
    바이트까지 내줬다 — 목록에서 가려 둔 것이 단건에서 새는 전형적인 IDOR 다.

    **403 이 아니라 404.** 403 은 "그 id 는 존재하지만 너는 못 본다" 를 알려 주므로 id 를
    찍어 보며 포탈 전체 티켓의 존재를 열거할 수 있다(저장소 규칙 — `core/scope.py`
    모듈 docstring, 채팅 이미지 서빙, `get_scoped_user_or_404` 가 같은 관용).

    ## 담당자를 해석할 수 없는 티켓은 **통과시킨다**

    그런 티켓은 미할당 트리아지(포탈 전용 버킷)에 나온다. 여기서 막으면 **목록에는 보이는데
    누르면 없다고 하는** 화면이 된다 — 그건 보안이 아니라 고장이다. 목록과 단건이 같은 말을
    해야 한다.

    캐시에 행이 없어도 통과시킨다. 판정할 근거가 없는 것이지 범위 밖인 것이 아니다
    (동기화 직전에 만든 티켓이 자기 눈에 안 보이면 그것도 고장이다).
    """
    if viewer is None:
        return
    from app.core.scope import any_assignee_visible, build_scope, visible_user_ids
    from app.tickets.models import TicketCache, split_names   # 지연 import(순환 참조)

    scope = build_scope(db, viewer)
    # RBAC 재감사(2026-08-16)로 발견: `not scope.is_dept`는 org 범위(admin_scope='org')를
    # global과 똑같이 취급해 이 함수가 지키는 모든 경로(단건 조회 + 위 호출부 주석이 명시한
    # 6곳 이상의 쓰기 — 상태변경·댓글·첨부·배정 등)에서 조직 관리자가 다른 조직 티켓에
    # 그대로 닿았다. 진짜 무제한은 global뿐이다.
    if scope.is_global:
        return
    row = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == page_id)
    ).scalar_one_or_none()
    if row is None:
        return
    id_to_user = _verified_id_to_user(db)
    owners = [id_to_user.get(n) for n in split_names(row.assignee_notion_ids)]
    owners = [o for o in owners if o]
    if not owners:
        return   # 앱이 담당자를 모르는 티켓 = 포탈 전용 버킷 — 막지 않는다
    if not any_assignee_visible(owners, visible_user_ids(db, scope)):
        raise NotFoundError("티켓을 찾을 수 없습니다.")


def ensure_not_trashed(db: Session, page_id: str) -> None:
    """휴지통에 있는 티켓은 **없는 것으로 취급한다** (H2).

    `_drop_trashed` 는 목록 세 곳에만 걸려 있었다. 그래서 휴지통에 넣은 티켓이:
      * 상세로는 **정상적으로 열리고**(`GET /api/tickets/{page_id}`),
      * `can_edit` 도 계산돼 **수정·본문 저장·댓글·첨부가 그대로 됐다**,
      * 검색과 ⌘K 에도 보관기간(기본 7일) 내내 계속 나왔다.
    사용자에게는 "지웠는데 아직 열리고 고쳐진다" 이고, 그렇게 고친 내용은 보관기간이 끝나면
    티켓과 함께 사라진다. 게시판은 이걸 제대로 한다(`_board_rows` 가 `deleted_at IS NULL` 로
    거르고 첨부도 부모가 지워지면 404) — 티켓·문서만 빠져 있었다.

    **403 이 아니라 404** 다. 저장소 규칙이 그렇고(채팅 이미지 서빙·`get_scoped_user_or_404`),
    이유도 같다: 403 은 "있지만 당신은 안 된다" 라서 존재를 알려 준다. 휴지통 항목은
    그 사용자에게 없는 것이 맞다.

    복원 경로(`app/trash/service.py`)는 이 함수를 지나지 않는다 — 거기서는 휴지통에 있는
    것이 정상이고, 오히려 없으면 오류다.
    """
    if page_id in trash_repo.trashed_page_ids(db, TRASH_TICKET):
        raise NotFoundError("티켓을 찾을 수 없습니다.")


def ensure_ticket_visible(db: Session, page_id: str, user: "User | None") -> None:
    """이 사람에게 이 티켓이 **'있는' 것인가** — 휴지통(H2) + 범위(§0-A) 판정 한 벌.

    둘은 늘 함께 다닌다. 따로 부르면 한쪽만 붙은 경로가 생기고, 그게 §0-A 가 네 번 반복해서
    잡아낸 실수의 모양이다("목록에는 걸었는데 쓰기에는 안 걸었다"). 댓글 경로 전체가 이
    함수 하나만 지나게 해서 **판정을 빠뜨릴 자리를 코드에서 없앤다**.

    순서가 의미 있다: 휴지통이 먼저다. 지운 티켓은 범위와 무관하게 그 사람에게 없다.
    """
    ensure_not_trashed(db, page_id)
    ensure_in_scope(db, page_id, user)


def _drop_trashed(db: Session, rows: list[dict]) -> list[dict]:
    """휴지통에 들어간 티켓(노션 page id 기준)은 목록에서 숨긴다 — 보관기간 동안은 노션엔 남아 있다."""
    trashed = trash_repo.trashed_page_ids(db, TRASH_TICKET)
    if not trashed:
        return rows
    return [t for t in rows if t.get("id") not in trashed]


def sync_indicator(db: Session, settings=None, outbound=None, *, repo=None) -> dict | None:
    """로컬 미러로 답한 경우의 신선도 블록. 실시간으로 답했으면 None.

    실시간 응답에는 이 키 자체를 넣지 않는다 — '미러가 얼마나 낡았나'는 미러로 답할 때만
    뜻이 있는 값이고, 실시간 경로의 기존 응답 계약(골든)을 건드리지 않기 위해서다.
    """
    status = _repo(settings, outbound, repo).sync_state(db)
    if status is None:
        return None
    return {
        "status": status.status,
        "last_run_at": status.last_run_at,
        "last_success_at": status.last_success_at,
        "ticket_count": status.ticket_count,
        "truncated": status.truncated,
        "error": status.error,
    }


# ── 서버 필터 조립 ────────────────────────────────────────────────────────────
#
# 화면이 고른 조건과 앱이 반드시 거는 조건을 **한 벌로 합쳐서** 저장소에 넘긴다. 합치지 않고
# 일부를 파이썬 뒤처리로 남기면 페이지네이션이 그 뒤처리 **앞에서** 일어나고, 그 순간
# "20건을 달랬는데 13건이 왔다" + "total 이 사용자가 세는 수와 다르다" 가 동시에 난다.

def _notion_id_for_user(db: Session, user_id: str) -> str | None:
    """앱 user_id → verified·active 소스 user id. 없으면 None.

    브라우저는 소스 user id 를 주지도 받지도 않는다(§12.3) — 담당자 필터도 앱 user_id 로만
    받고 여기서 한 번 해석한다.
    """
    for nid, uid in _verified_id_to_user(db).items():
        if uid == user_id:
            return nid
    return None


def _scope_assignee_ids(db: Session, viewer) -> frozenset[str] | None:
    """범위 판정을 **질의 조건**으로 옮긴 값 — 범위 안 사람들의 소스 user id 집합.

    규칙은 `_drop_out_of_scope` 와 **같은 것 하나**다(`core/scope.py::any_assignee_visible`):
    담당자 중 한 명이라도 범위 안이면 보인다. 전역·조직 범위면 None(제한 없음)이라
    오늘까지의 동작과 같다.

    왜 SQL 쪽으로 옮기는가: 범위를 파이썬 뒤처리로만 두면 페이지를 자른 **뒤에** 걸리게 되어
    남의 팀 티켓이 자리만 차지하고 빠진 페이지가 나간다(20건 요청에 3건 응답). 그렇다고
    파이썬 그물을 떼지는 않는다 — `_drop_out_of_scope` 는 그대로 남겨 두 그물이 겹치게 한다.
    여기가 넓게 틀리면 그물이 잡고(닫히는 방향), 그때 total 이 페이지 합보다 커지는 것이
    **틀렸다는 신호**가 된다.
    """
    if viewer is None:
        return None
    from app.core.scope import build_scope, visible_user_ids

    scope = build_scope(db, viewer)
    # RBAC 재감사(2026-08-16): ensure_in_scope와 같은 자리에서 같은 이유로 정정 — org
    # 범위를 global처럼 무제한 취급하면 목록 SQL 필터가 이 함수가 존재하는 이유(페이지네이션
    # 뒤가 아니라 SQL 단에서 거르기)를 org 관리자에게만 건너뛰게 된다.
    if scope.is_global:
        return None
    visible = visible_user_ids(db, scope) or frozenset()
    return frozenset(
        nid for nid, uid in _verified_id_to_user(db).items() if uid in visible
    )


def build_filters(
    db: Session,
    query=None,
    *,
    now: datetime | None = None,
    active_only: bool = False,
    viewer=None,
    assignee_id: str | None = None,
    allow_assignee_filter: bool = True,
) -> TicketFilters:
    """화면 질의(`schemas.TicketListQuery`) + 앱이 거는 조건 → `TicketFilters` 한 벌.

    `query` 가 없으면(내부 호출) 앱이 거는 조건만 남는다.

    `allow_assignee_filter=False` 는 담당자 필터가 **뜻이 없는 화면**용이다(내 티켓은 담당자가
    언제나 세션 사용자고, 미할당은 정의상 담당자가 없다). 그런 화면에서 이 조건을 그대로
    걸면 언제나 빈 목록이 나가는데, 그건 "필터가 안 먹는다" 가 아니라 "티켓이 없다" 로
    보여서 원인을 못 찾는다.
    """
    # 담당자에 걸리는 조건은 둘 다 여기로 모인다: 범위(집합 중 하나) + 화면이 고른 사람.
    # 둘은 AND 이고, 한쪽이 '아무도 아님' 이면 결과는 비는 것이 맞다.
    allowed_assignees = _scope_assignee_ids(db, viewer)
    picked_assignee = assignee_id
    if (allow_assignee_filter and query is not None
            and query.assignee_user_id and assignee_id is None):
        resolved = _notion_id_for_user(db, query.assignee_user_id)
        if resolved is None:
            # 매핑이 없는 사람으로 거르면 걸릴 티켓이 없다. 조건을 조용히 버리면 **필터 없는
            # 전체 목록**이 나가는데, 그건 사용자가 알아챌 수 없는 방향의 오류다 — 닫는다.
            allowed_assignees = frozenset()
        else:
            picked_assignee = resolved
    return TicketFilters(
        status=getattr(query, "status", None),
        priority=getattr(query, "priority", None),
        difficulty=getattr(query, "difficulty", None),
        project_id=getattr(query, "project_id", None),
        category=getattr(query, "category", None),
        search=getattr(query, "q", None),
        due_bucket=getattr(query, "due", None),
        today=now.date().isoformat() if now is not None else None,
        assignee_id=picked_assignee,
        exclude_statuses=frozenset(_TERMINAL) if active_only else frozenset(),
        # 휴지통은 목록에서 숨긴다(H2). 파이썬 `_drop_trashed` 도 그대로 남겨 둔다 —
        # 범위와 같은 이유로 두 그물이 겹치는 편이 낫다.
        exclude_page_ids=frozenset(trash_repo.trashed_page_ids(db, TRASH_TICKET)),
        assignee_any_of=allowed_assignees,
    )


# ── 조회 ──────────────────────────────────────────────────────────────────────

def _total(result, views: list[dict]) -> int:
    """저장소가 센 값(필터 뒤·자르기 전). 안 세는 구현체면 페이지 길이로 떨어진다."""
    return result.total if result.total is not None else len(views)


def list_my_tickets(
    db: Session, outbound, settings, user: User, *, repo=None,
    filters: TicketFilters | None = None, page: PageSpec | None = None,
) -> dict:
    """로그인 사용자가 담당한 티켓(마감 무관). 매핑이 없으면 {mapped: False}.

    `total` 은 **필터 뒤·페이지 자르기 전** 건수다. 화면이 "N건 중 1-20" 을 쓸 수 있어야 한다.
    """
    nid = my_notion_id(db, user)
    if not nid:
        return {"mapped": False, "tickets": [], "total": 0}
    result = _repo(settings, outbound, repo).list_by_assignee(
        db, assignee_id=nid, filters=filters, page=page
    )
    views = _drop_trashed(db, ticket_views(db, result.tickets))
    return {"mapped": True, "tickets": views, "total": _total(result, views)}


def list_unassigned_page(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None,
    filters: TicketFilters | None = None, page: PageSpec | None = None,
) -> dict:
    """미할당 트리아지 한 페이지 — {"tickets": [...], "total": n}."""
    result = _repo(settings, outbound, repo).list_unassigned(db, filters=filters, page=page)
    tickets = result.tickets
    if active_only:
        tickets = tuple(t for t in tickets if (t.status or "") not in _TERMINAL)
    views = _drop_trashed(db, ticket_views(db, tickets, with_names=False))
    return {"tickets": views, "total": _total(result, views)}


def list_unassigned_tickets(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None
) -> list[dict]:
    """담당자가 없는 티켓 **전부**. 기본은 활성(완료·취소 제외)만 — 아직 사람이 필요한 일.
    담당자가 없으므로 이름 해석은 건너뛰고 프로젝트 이름만 붙는다(기존 동작과 동일).

    페이지를 안 받는다 — 스프린트·어시스턴트가 집계에 쓰는 경로라 전량이 맞다.
    화면(라우터)은 `list_unassigned_page` 를 쓴다.
    """
    return list_unassigned_page(
        db, outbound, settings, active_only=active_only, repo=repo
    )["tickets"]


def list_team_page(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None, viewer=None,
    filters: TicketFilters | None = None, page: PageSpec | None = None,
) -> dict:
    """팀 티켓 한 페이지 — {"tickets": [...], "total": n}. 판정은 `list_team_tickets` 참조."""
    result = _repo(settings, outbound, repo).list_all(db, filters=filters, page=page)
    tickets = result.tickets
    if active_only:
        tickets = tuple(t for t in tickets if (t.status or "") not in _TERMINAL)
    views = _drop_out_of_scope(db, _drop_trashed(db, ticket_views(db, tickets)), viewer)
    return {"tickets": views, "total": _total(result, views)}


def list_team_tickets(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None, viewer=None
) -> list[dict]:
    """**보는 사람의 팀** 티켓 — 조회 전용 팀 보드용. 기본은 활성(완료·취소 제외).
    담당자 이름을 붙여 담당자별로 볼 수 있게 하고, 휴지통에 넣은 티켓은 숨긴다.

    ## 예전에는 포탈 전체였다 (1순위 유출 #1)

    `repo.list_all(db)` 를 그대로 돌려줬다 — 화면 이름은 '팀 티켓' 인데 **다른 팀 사람의
    티켓이 담당자 이름과 함께 전부** 보였다. 사용자 지시("팀 티켓 등은 기본적으로 본인이
    속한 팀 정보를 봐야 한다")와 정면으로 어긋난다.

    판정은 `core/scope.py` 가 이미 종결한 규칙 그대로다 — 담당자 중 **한 명이라도** 범위
    안이면 보인다. 스칼라 하나로 정하면 두 팀이 함께 맡은 티켓이 한쪽에서 통째로 사라지고,
    그 팀은 자기 팀이 그 일을 하고 있다는 사실 자체를 못 본다.

    담당자를 앱 사용자로 해석할 수 없는 티켓은 부서 화면에 안 나온다 — 그건 미할당
    트리아지가 담당하고, 그 버킷은 **앱이 담당자를 모르는 티켓 전부**를 담는다.

    `viewer` 가 없으면 좁히지 않는다(리포트·집계 등 내부 호출부의 기존 계약을 지킨다).

    페이지를 안 받는다 — 스프린트·어시스턴트가 집계에 쓰는 경로라 전량이 맞다.
    화면(라우터)은 `list_team_page` 를 쓴다.
    """
    return list_team_page(
        db, outbound, settings, active_only=active_only, repo=repo, viewer=viewer
    )["tickets"]


def _drop_out_of_scope(db: Session, views: list[dict], viewer) -> list[dict]:
    """범위 밖 티켓을 뺀다. 담당자 해석은 `ticket_views` 가 이미 붙여 준 값을 쓴다."""
    if viewer is None:
        return views
    from app.core.scope import any_assignee_visible, build_scope, visible_user_ids

    scope = build_scope(db, viewer)
    # RBAC 재감사(2026-08-16): 위 ensure_in_scope/_scope_assignee_ids와 같은 정정 — 이 함수는
    # 팀 티켓 목록·스프린트/어시스턴트 집계가 쓴다(위 docstring), org 범위를 무제한 취급하면
    # 그 경로들이 다른 조직 티켓까지 그대로 낸다.
    if scope.is_global:
        return views
    visible = visible_user_ids(db, scope)
    return [
        v for v in views
        if any_assignee_visible(v.get("assignee_user_ids") or [], visible)
    ]


def list_period_tickets(
    db: Session, outbound, settings, *, start: str, end: str, repo=None
) -> list[TicketDTO]:
    """마감일이 [start, end) 인 티켓 DTO 목록(리포트·스프린트 집계 코어가 쓴다)."""
    return list(
        _repo(settings, outbound, repo).list_for_period(db, start=start, end=end).tickets
    )


def ticket_detail(
    db: Session, outbound, settings, user: User, *, page_id: str, repo=None
) -> dict:
    """티켓 단건 상세(속성 + 본문 블록). 우리 화면에서 읽고, 원본 열기로 노션에 갈 수 있다.
    상세는 늘 실시간이다(온디맨드 1건이라 캐시 이득이 없다).
    본문 블록은 장애 격리 — 실패해도 속성은 보여준다(§17.4)."""
    ensure_not_trashed(db, page_id)   # H2 — 지운 티켓이 상세로 열리면 안 된다
    ensure_in_scope(db, page_id, user)   # 1순위 유출 #2 — 범위 밖은 404
    r = _repo(settings, outbound, repo)
    dto = r.get(db, page_id=page_id)
    ticket = ticket_views(db, [dto])[0]
    # 우리가 가진 첨부. 미러 행이 아직 없으면(=uid 없음) 첨부도 있을 수 없으니 빈 목록이다 —
    # 여기서 ensure_local 을 부르면 **읽기 한 번이 쓰기가 된다**(캐시 행 생성).
    uid = r.local_uid(db, page_id=page_id)
    attachment_list = ticket_attachments.attachment_views(db, ticket_uid=uid) if uid else []
    # 화면이 '눌러 봐야 거절당하는 버튼'을 안 그리게 한다. 판정 자체는 쓰기 경로가 다시 하므로
    # (ensure_can_edit) 이 값은 표시용이지 접근 통제가 아니다 — 클라이언트를 신뢰하지 않는다.
    try:
        ensure_can_edit(dto, user, my_notion_id(db, user))
        can_edit = True
    except ForbiddenError:
        can_edit = False
    blocks, blocks_error = None, None
    try:
        blocks = r.body_blocks(db, page_id=page_id)
    except Exception as exc:  # noqa: BLE001 — 본문만 격리 실패, 속성은 계속 보여준다
        blocks_error = "본문을 불러오지 못했습니다. 원본에서 확인해 주세요."
        _ = exc
    return {
        "ticket": ticket,
        "blocks": blocks,
        "blocks_error": blocks_error,
        # 편집기를 여는 데 쓰는 마크다운. 우리 정본이 있으면 그것, 없으면 방금 읽은 소스 본문을
        # 같은 규칙으로 되읽은 값이다 — 이걸 안 주면 프런트가 마크다운 변환기를 한 벌 더 갖거나
        # 편집기가 빈 채로 열려 '저장'이 기존 본문 삭제가 된다.
        "body_markdown": _detail_body_markdown(dto, blocks, blocks_error),
        # 편집 시작 시점의 지문 (Z2). 저장할 때 그대로 돌려보내면 그 사이 누가 먼저
        # 저장한 경우 409 로 막힌다 — 안 보내면 예전처럼 덮어쓴다.
        "body_version": body_version(_detail_body_markdown(dto, blocks, blocks_error)),
        # 위 본문이 **우리 정본**인가, 아니면 소스에서 되읽은 근사치인가.
        # 근사치일 때 편집기에서 저장하면 굵게·링크 같은 인라인 서식과 이미지·표 블록이
        # 사라지고 글자만 남는다(우리 본문 파이프라인은 평문 마크다운이다). 화면이 그때만
        # 경고하려면 이 구분이 필요하다 — 항상 경고하면 사용자가 경고를 읽지 않게 된다.
        "body_is_local": dto.body_markdown is not None,
        # 정본은 저장됐는데 소스에 못 밀어 넣은 상태면 그 이유. 화면이 배너로 보여준다.
        "body_sync_error": dto.body_sync_error,
        # 포털에서 붙인 파일(§4). 본문 안의 Notion 이미지는 blocks 쪽에 kind="image" 로 온다.
        "attachments": attachment_list,
        "can_edit": can_edit,
    }


def _detail_body_markdown(dto: TicketDTO, blocks, blocks_error) -> str | None:
    """편집기 초기값. 본문을 못 읽었으면 None — 모르는 것을 빈 문자열로 내려보내면 안 된다."""
    if dto.body_markdown is not None:
        return dto.body_markdown
    if blocks_error is not None or blocks is None:
        return None
    return rendered_to_markdown(blocks)


def ticket_meta(outbound, settings, db: Session | None = None, *, repo=None) -> dict:
    """편집 드롭다운용 허용 옵션(진행상태·우선순위·난이도).

    db 를 주면 로컬 메타 캐시를 먼저 본다(폼이 소스 왕복 없이 즉시 뜬다). db 없이 부르면
    실시간 스키마 조회로 떨어진다 — 앱 없이 부르는 유닛 테스트용 경로다.
    """
    meta = _repo(settings, outbound, repo, use_cache=(db is not None)).meta(db)
    return {
        "statuses": list(meta.statuses),
        "priorities": list(meta.priorities),
        "difficulties": list(meta.difficulties),
    }


def list_projects(outbound, settings, db: Session | None = None, *, repo=None) -> list[dict]:
    """새 티켓 폼의 프로젝트 드롭다운용 [{id, name}]. db 를 주면 메타 캐시 우선."""
    r = _repo(settings, outbound, repo, use_cache=(db is not None))
    return [{"id": p.id, "name": p.name} for p in r.projects(db)]


def list_assignees(db: Session, *, org_id: str | None = None) -> list[dict]:
    """담당자로 배정 가능한 사람 목록 — active + verified 매핑 사용자.

    raw notion_user_id 는 응답에 넣지 않는다(브라우저 미노출, 스펙 §12.3). 편집 API 가 user_id 를
    받아 서버에서 소스 id 로 해석한다.

    **부서·직책·조직을 함께 싣는다**(사용자 지시 2026-08-04). 예전에는 {user_id, display_name}
    뿐이라 '김하나'가 둘이면 담당자 선택 목록에 같은 줄이 두 번 떴고, 어느 쪽이 내가 찾는
    사람인지 알 방법이 화면에 없었다. 신원 조각은 app/core/people.py 가 만든다.

    행 대신 User 객체를 부르는 이유: `department`/`title` 은 관계에서 이름을 꺼내는
    프로퍼티라 컬럼 select 로는 안 나온다. 관계가 lazy="joined" 라 질의 수는 그대로다.
    """
    stmt = (
        select(User)
        .join(UserNotionMapping, UserNotionMapping.user_id == User.id)
        .where(
            User.active.is_(True),
            User.archived_at.is_(None),
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
        )
    )
    # 조직 밖 사람은 담당자 후보가 아니다 (1순위 유출 #7). 이 목록은 이름·부서·직책·조직을
    # 그대로 실어 주므로(사용자 지시로 그렇게 만들었다) **조직도 열거**가 된다 — 검색이
    # 사용자 종류를 역할로 막는 결정을 이 목록이 옆문으로 무효화하고 있었다.
    if org_id:
        stmt = stmt.where(User.org_id == org_id)
    users = db.execute(stmt.order_by(User.display_name)).scalars().all()
    org_names = people.org_name_map(db)
    return [people.identity(u, org_names) for u in users]


# ── 강제 재동기화 (C7) ────────────────────────────────────────────────────────

def can_trigger_sync(user: User) -> bool:
    """지금 당장 동기화를 돌릴 수 있는 사람 — 운영자군.

    `team_docs.service.can_trigger_sync`, `ensure_can_edit` 와 **같은 기준**
    (`MODERATOR_ROLES`)이다. 기준을 여기서 새로 정의하지 않는다 — "운영자"의 뜻이 화면마다
    갈라지면 어떤 콘솔에서는 되는데 다른 콘솔에서는 막히는 혼란이 생긴다.
    """
    return user.role in MODERATOR_ROLES


# ── 휴지통 ────────────────────────────────────────────────────────────────────

def trash_ticket(db: Session, outbound, settings, user: User, *, page_id: str, now, repo=None) -> dict:
    """티켓을 휴지통으로 보낸다(노션은 손대지 않음). 편집 권한이 있어야 한다(담당자/미할당/운영자군).
    보관기간이 지나면 백그라운드가 노션 원본을 보관처리한다. 복원 가능."""
    ensure_not_trashed(db, page_id)   # H2 — 휴지통 항목은 없는 것으로 본다
    ensure_in_scope(db, page_id, user)   # 쓰기도 범위 밖은 404 (3순위 IDOR)
    current = _repo(settings, outbound, repo).get_live(db, page_id=page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))
    item = trash_service.move_to_trash(
        db, item_type=TRASH_TICKET, notion_page_id=page_id,
        title=current.title or "(제목 없음)", url=current.url,
        user=user, now=now,
    )
    return {"title": item.title, "url": item.url}


def trash_tickets_bulk(
    db: Session, outbound, settings, user: User, *, page_ids: list[str], now, repo=None
) -> dict:
    """티켓 여러 건을 휴지통으로 보낸다. 건별로 검사하고, 실패(범위 밖·권한 없음·이미 휴지통·
    없음)는 건너뛰고 나머지는 계속한다(부분 성공). {trashed:[...], failed:[{id,error}]}.

    ⚠️ **범위와 권한은 다른 축이다.** 예전에는 이 루프가 `ensure_can_edit` 만 지났는데, 그건
    `MODERATOR_ROLES` 를 **무조건** 통과시키고 미할당 티켓은 누구나 통과시킨다 — 즉 다른
    부서의 운영자가 page_id 목록만 던지면 범위 밖 티켓을 통째로 휴지통에 넣을 수 있었다.
    단건 경로(`trash_ticket`)는 `ensure_in_scope` 를 지나는데 **일괄만 안 지났다.**
    휴지통 모듈에서 정확히 같은 것("단건만 막으면 소용없다")을 겪고도 여기서 반복했다.
    """
    from app.core.errors import AppError

    r = _repo(settings, outbound, repo)
    nid = my_notion_id(db, user)
    trashed: list[dict] = []
    failed: list[dict] = []
    for pid in page_ids:
        try:
            # 단건과 **같은 문**을 지난다. 범위 밖은 404 라 '없는 것' 과 구별되지 않는다.
            ensure_in_scope(db, pid, user)
            current = r.get_live(db, page_id=pid)
            ensure_can_edit(current, user, nid)
            trash_service.move_to_trash(
                db, item_type=TRASH_TICKET, notion_page_id=pid,
                title=current.title or "(제목 없음)", url=current.url,
                user=user, now=now,
            )
            trashed.append({"id": pid, "title": current.title or "(제목 없음)"})
        except AppError as exc:
            failed.append({"id": pid, "error": exc.message})
    return {"trashed": trashed, "failed": failed}


# ── 수동 편집(쓰기) ────────────────────────────────────────────────────────────

def ensure_can_edit(ticket: TicketDTO, user: User, my_notion_id_value: str | None) -> None:
    """소유권 검증(스펙 §25.5·IDOR). 운영/관리자군은 우회, 그 외는 본인 담당 또는 미할당만.

    소스에서 **방금 읽은** '현재' 티켓의 담당자로 판정한다(프런트가 준 값도, 캐시 값도 아니다).
    """
    # 운영/관리자군(MODERATOR_ROLES)은 소유권을 우회해 아무 티켓이나 편집할 수 있다.
    # 그 외(user/auditor)는 본인 담당이거나 미할당인 티켓만 편집할 수 있다(IDOR 차단).
    if user.role in MODERATOR_ROLES:
        return
    assignees = ticket.assignee_ids
    if not assignees:
        return  # 미할당 — 담당자가 필요한 일이므로 누구나 손댈 수 있다(배정 포함)
    if my_notion_id_value and my_notion_id_value in assignees:
        return  # 본인 담당
    raise ForbiddenError("이 티켓을 편집할 권한이 없습니다(담당자 또는 미할당 티켓만 편집할 수 있습니다).")


def _resolve_assignee_ids(db: Session, user_ids: list[str]) -> list[str]:
    """앱 user_id 목록 → 소스 user_id 목록(verified·active 매핑만). 하나라도 해석 불가면 거절.

    브라우저는 절대 소스 id 를 주지 않는다 — 항상 서버에서 매핑으로 해석한다(스펙 §12.3).
    """
    if not user_ids:
        return []
    rows = db.execute(
        select(User.id, UserNotionMapping.notion_user_id)
        .join(UserNotionMapping, UserNotionMapping.user_id == User.id)
        .where(
            User.id.in_(user_ids),
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
            User.active.is_(True),
            User.archived_at.is_(None),
        )
    ).all()
    found = {uid: nid for uid, nid in rows}
    missing = [uid for uid in user_ids if uid not in found]
    if missing:
        raise ValidationAppError("담당자로 지정할 수 없는 사용자가 있습니다(Notion 계정 미연결).")
    seen: set[str] = set()
    out: list[str] = []
    for uid in user_ids:
        nid = found[uid]
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def _build_assignee_people(db: Session, current_assignees, user_ids: list[str]) -> list[str]:
    """새 담당자(people) 소스 id 목록을 만든다.

    앱에 연결되지 않은(verified 매핑이 없는) 기존 담당자는 **보존**하고, 앱 사용자 담당자만
    user_ids 로 교체한다 — 이렇게 하면 편집 화면(앱 사용자 체크박스)으로 손대지 않은 외부/미연결
    담당자를 조용히 지우지 않는다.
    """
    mapped_ids = set(_verified_id_to_user(db))
    preserved = [nid for nid in current_assignees if nid not in mapped_ids]
    resolved = _resolve_assignee_ids(db, user_ids)
    merged: list[str] = []
    seen: set[str] = set()
    for nid in preserved + resolved:
        if nid not in seen:
            seen.add(nid)
            merged.append(nid)
    return merged


def _notify_assignees_added(
    db: Session, *, page_id: str, number, title: str | None, actor: User,
    before: list[str], after: list[str], now: datetime,
) -> None:
    """담당자로 **새로 들어온 사람**에게만 알린다 (X9 + N2).

    감사 확인: 누가 나에게 티켓을 배정해도 앱이 안 알려 줬다. 담당자는 `/my-tickets` 를
    스스로 열어야 자기 일이 늘어난 걸 알았다.

    ## 누구에게 (한 번에 여러 명이 바뀐다)

    담당자 교체 한 번에 **빠진 사람, 들어온 사람, 그대로인 사람**이 동시에 생긴다.
    셋 중 알림을 받는 것은 **들어온 사람뿐**이다.

      * **그대로인 사람**: 그에게는 아무 일도 일어나지 않았다. 공동 담당 티켓에 사람이
        한 명 추가될 때마다 기존 담당자 전원이 알림을 받으면 그건 통보가 아니라 소음이고,
        소음이 몇 번 반복되면 사람들은 배지 자체를 무시한다.
      * **빠진 사람**: 알 필요가 있는 사건이지만 **배정과 다른 사건**이다. 같은 유형으로
        보내면 (1) 제목이 "배정"인데 내용은 해제라 읽는 사람이 헷갈리고, (2) 사용자가
        설정에서 '티켓 배정'을 끄는 순간 켠 적도 없는 해제 통보까지 같이 꺼진다.
        해제 통보는 자기 유형(`ticket_unassigned`)을 갖고 따로 들어와야 하고, 그건 이번
        다섯 종에 없다 — 그래서 여기서는 **일부러** 보내지 않는다.
      * **나 자신**: 내가 한 배정은 내가 이미 안다. 빼지 않으면 '내가 맡기'를 누를 때마다
        배지가 켜져서, 배지가 늘 켜져 있는 상태가 기본값이 된다.

    ## 실패해도 티켓 편집은 남는다

    `notify_user` 가 터져도 이 함수 밖으로 나가지 않는다(댓글 알림과 같은 규약). 다만
    조용히 삼키지도 않는다 — 원인을 로그에 남긴다.
    """
    try:
        added = [uid for uid in after if uid not in before and uid != actor.id]
        if not added:
            return

        from app.notifications.service import notify_user

        label = f"GIT-{number}" if number else "티켓"
        for uid in added:
            notify_user(
                db, uid, type_="ticket_assigned",
                title=f"{label} 담당자로 지정: {actor.display_name}",
                body=(title or "")[:200],
                related=("ticket", page_id), now=now,
            )
    except Exception:  # noqa: BLE001 — 알림이 티켓 편집을 막으면 안 된다
        logger.exception("티켓 배정 알림에 실패했다 (page_id=%s)", page_id)


def update_ticket(
    db: Session, outbound, settings, user: User, *, page_id: str, changes: dict,
    now: datetime | None = None, repo=None,
) -> dict:
    """티켓 속성을 수동 편집한다(소유권·스키마 검증 후 소스 반영). 감사용 before/after 포함.

    changes 는 이미 exclude_unset 된 dict(보낸 필드만). 담당자만 여기서 앱 user_id → 소스 id 로
    해석하고, 값 검증·속성 매핑은 저장소 구현체가 실제 스키마로 한다. 성공하면 저장소가 같은
    요청 안에서 캐시 행까지 고친다 — 방금 고친 값이 목록에 바로 보인다.
    """
    if not changes:
        raise ValidationAppError("변경할 내용이 없습니다.")
    r = _repo(settings, outbound, repo)
    ensure_not_trashed(db, page_id)   # H2 — 휴지통 항목은 없는 것으로 본다
    ensure_in_scope(db, page_id, user)   # 쓰기도 범위 밖은 404 (3순위 IDOR)
    current = r.get_live(db, page_id=page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))

    repo_changes = dict(changes)
    if "assignee_user_ids" in repo_changes:
        repo_changes["assignee_notion_ids"] = _build_assignee_people(
            db, current.assignee_ids, repo_changes.pop("assignee_user_ids") or []
        )
    # API 이름 → 저장소 도메인 키. 두 이름이 다른 것은 API 쪽이 '무엇을 보내는지'(project_id,
    # start_date)를, 저장소 쪽이 '어느 속성인지'(project, start)를 말하기 때문이다.
    if "project_id" in repo_changes:
        pid = (repo_changes.pop("project_id") or "").strip()
        repo_changes["project"] = [pid] if pid else []   # 빈 값 = 프로젝트 연결 해제
    if "start_date" in repo_changes:
        repo_changes["start"] = repo_changes.pop("start_date")

    stamp = now or utcnow()
    updated = r.update(db, page_id=page_id, changes=repo_changes, now=stamp)
    if "assignee_notion_ids" in repo_changes:
        # 담당자를 건드린 편집에서만 본다. 마감일만 고친 저장이 배정 알림을 만들면 안 된다.
        _notify_assignees_added(
            db, page_id=page_id, number=updated.number, title=updated.title, actor=user,
            before=resolve_assignee_user_ids(db, current.assignee_ids),
            after=resolve_assignee_user_ids(db, updated.assignee_ids),
            now=stamp,
        )
    return {
        "ticket": ticket_views(db, [updated])[0],
        "before": snapshot(current),
        "after": snapshot(updated),
    }


# ── 담당자 재배정(오프보딩) ───────────────────────────────────────────────────
#
# 오프보딩은 티켓 담당자를 **되돌릴 수 있게** 옮겨야 한다. 그러려면 옮기기 직전의 담당자
# 구성을 앱 user_id 로 남겨야 하는데, `update_ticket` 은 감사 스냅샷을 raw 소스 id 로만
# 돌려주므로 부르는 쪽이 매핑을 한 벌 더 갖게 된다. 여기 두 함수가 그 해석을 대신하고,
# 소스 왕복도 건당 한 번으로 줄인다(`update_ticket` 을 그대로 쓰면 get_live 가 두 번 돈다).

def resolve_assignee_user_ids(db: Session, assignee_source_ids) -> list[str]:
    """소스 담당자 id → 앱 user_id 목록(해석되는 것만, 순서 보존·중복 제거).

    해석되지 않는 담당자(앱에 없는 외부 사용자)는 여기서 **사라진다**. 그래도 되는 이유는
    쓰기 경로(`_build_assignee_people`)가 그런 담당자를 언제나 보존하기 때문이다 — 즉
    "앱이 아는 담당자 집합"만 재배정의 대상이고, 나머지는 우리가 건드리지 않는다.
    """
    id_to_user = _verified_id_to_user(db)
    out: list[str] = []
    for nid in assignee_source_ids:
        uid = id_to_user.get(nid)
        if uid and uid not in out:
            out.append(uid)
    return out


def _apply_assignees(
    db: Session, r, user: User, *, page_id: str, wanted: list[str], now: datetime | None,
    notify: bool = True,
) -> dict:
    """현재 담당자를 읽고 `wanted` 로 맞춘다. 이미 같으면 소스를 부르지 않는다."""
    ensure_not_trashed(db, page_id)   # H2 — 휴지통 항목은 없는 것으로 본다
    current = r.get_live(db, page_id=page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))
    before = resolve_assignee_user_ids(db, current.assignee_ids)
    if before == wanted:
        return {
            "changed": False,
            "before_user_ids": before,
            "after_user_ids": before,
            "ticket": ticket_views(db, [current])[0],
        }
    people = _build_assignee_people(db, current.assignee_ids, wanted)
    stamp = now or utcnow()
    updated = r.update(
        db, page_id=page_id,
        changes={"assignee_notion_ids": people},
        now=stamp,
    )
    if notify:
        _notify_assignees_added(
            db, page_id=page_id, number=updated.number, title=updated.title, actor=user,
            before=before, after=resolve_assignee_user_ids(db, updated.assignee_ids),
            now=stamp,
        )
    return {
        "changed": True,
        "before_user_ids": before,
        "after_user_ids": resolve_assignee_user_ids(db, updated.assignee_ids),
        "ticket": ticket_views(db, [updated])[0],
    }


def replace_ticket_assignee(
    db: Session, outbound, settings, user: User, *, page_id: str,
    from_user_id: str, to_user_id: str | None, now: datetime | None = None, repo=None,
    notify: bool = True,
) -> dict:
    """담당자 한 명을 다른 사람으로 바꾼다 — **나머지 담당자는 그대로 둔다**.

    공동 담당 티켓에서 퇴사자만 빼고 후임을 넣는 것이 목적이라, 담당자 목록을 통째로
    덮어쓰지 않는다(덮어쓰면 같이 일하던 사람이 조용히 빠진다).
    `to_user_id` 가 None 이면 후임 없이 빼기만 한다(미할당 트리아지로 보낸다).

    `notify=False` 는 **건별 배정 알림을 끄는 스위치**다. 오프보딩이 그것을 쓴다: 100건을
    한 번에 넘기면 후임의 배지에 알림 100건이 꽂히는데, 그건 통보가 아니라 사고다.
    오프보딩은 대신 **요약 한 건**(`offboarding_handover`)을 보낸다.
    """
    r = _repo(settings, outbound, repo)
    ensure_not_trashed(db, page_id)   # H2 — 휴지통 항목은 없는 것으로 본다
    ensure_in_scope(db, page_id, user)   # 쓰기도 범위 밖은 404 (3순위 IDOR)
    current = r.get_live(db, page_id=page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))
    before = resolve_assignee_user_ids(db, current.assignee_ids)
    wanted = [uid for uid in before if uid != from_user_id]
    if to_user_id and to_user_id not in wanted:
        wanted.append(to_user_id)
    if before == wanted:
        return {
            "changed": False, "before_user_ids": before, "after_user_ids": before,
            "ticket": ticket_views(db, [current])[0],
        }
    people = _build_assignee_people(db, current.assignee_ids, wanted)
    stamp = now or utcnow()
    updated = r.update(
        db, page_id=page_id, changes={"assignee_notion_ids": people}, now=stamp
    )
    after = resolve_assignee_user_ids(db, updated.assignee_ids)
    if notify:
        _notify_assignees_added(
            db, page_id=page_id, number=updated.number, title=updated.title, actor=user,
            before=before, after=after, now=stamp,
        )
    return {
        "changed": True,
        "before_user_ids": before,
        "after_user_ids": after,
        "ticket": ticket_views(db, [updated])[0],
    }


def set_ticket_assignees(
    db: Session, outbound, settings, user: User, *, page_id: str,
    user_ids: list[str], now: datetime | None = None, repo=None,
    notify: bool = True,
) -> dict:
    """담당자를 주어진 목록 **그대로** 맞춘다(되돌리기용).

    되돌리기는 '옮기기 직전 구성으로 복원'이므로 차집합이 아니라 전체 지정이어야 한다 —
    그 사이 제3자가 담당자를 더했다면 그 변경도 함께 되돌아간다. 그것이 '되돌리기'의 뜻이고,
    무엇이 바뀌었는지는 응답의 before/after 로 그대로 드러난다.

    `notify=False` 의 뜻은 `replace_ticket_assignee` 와 같다(오프보딩 되돌리기가 쓴다).
    """
    r = _repo(settings, outbound, repo)
    return _apply_assignees(
        db, r, user, page_id=page_id, wanted=list(user_ids), now=now, notify=notify
    )


def claim_ticket(
    db: Session, outbound, settings, user: User, *, page_id: str,
    now: datetime | None = None, repo=None,
) -> dict:
    """미할당(또는 본인 담당) 티켓의 담당자에 '나'를 배정한다. 내 계정이 Notion 미연결이면 거절.

    🔴 **한 번에 한 사람만 진행한다** (Z1). 담당자를 읽고 쓰는 사이에 Notion 왕복이 두 번
    (0.5~3초) 들어간다. 트리아지 화면에서 두 사람이 같은 티켓을 거의 동시에 누르면 둘 다
    빈 담당자를 읽고 각자 자기를 써서, **뒤에 쓴 사람이 앞사람을 덮어쓰는데 둘 다 성공 토스트를
    본다.** 앞사람은 자기 티켓이라고 믿고 일을 시작한다.

    잠금의 한계와 `--workers 1` 전제는 `app/tickets/claim_lock.py` 에 적었다.
    """
    if not my_notion_id(db, user):
        raise ValidationAppError("내 계정이 Notion 사용자와 연결되어 있지 않아 담당자로 배정할 수 없습니다.")
    from app.tickets.claim_lock import claim_guard

    with claim_guard(page_id):
        return update_ticket(
            db, outbound, settings, user, page_id=page_id,
            changes={"assignee_user_ids": [user.id]}, now=now, repo=repo,
        )


def create_ticket(
    db: Session, outbound, settings, user: User, *, payload,
    now: datetime | None = None, repo=None,
) -> dict:
    """새 티켓을 만든다(제목 필수). 담당자는 user_id→소스 id 로 해석하고, 나머지 검증(상태·
    우선순위·난이도 옵션, 프로젝트 필수)은 저장소 구현체가 실제 스키마로 한다.

    생성 직후 저장소가 캐시에 그 티켓을 써 넣으므로 다음 목록 조회에서 바로 보인다.
    """
    draft = TicketDraft(
        title=payload.title,
        status=payload.status,
        priority=payload.priority,
        difficulty=payload.difficulty,
        est_wd=payload.est_wd,
        due_date=payload.due_date,
        project_id=payload.project_id,
        description_markdown=payload.description,
        assignee_ids=tuple(_resolve_assignee_ids(db, payload.assignee_user_ids or [])),
    )
    stamp = now or utcnow()
    created = _repo(settings, outbound, repo).create(db, draft=draft, now=stamp)
    # 생성과 동시에 남에게 배정하는 것도 배정이다. 여기가 빠지면 "남이 나에게 일을 만든"
    # 경우만 조용해지는데, 그게 배정 알림이 가장 필요한 자리 중 하나다.
    _notify_assignees_added(
        db, page_id=created.page_id, number=created.number, title=created.title,
        actor=user, before=[],
        after=resolve_assignee_user_ids(db, created.assignee_ids), now=stamp,
    )
    return {"ticket": ticket_views(db, [created])[0], "after": snapshot(created)}


# ── 본문 편집 ─────────────────────────────────────────────────────────────────

def body_version(text: str | None) -> str:
    """본문의 지문 (Z2). 편집을 시작할 때 받은 값을 저장할 때 그대로 돌려보낸다.

    타임스탬프가 아니라 **내용의 해시**를 쓰는 이유: 타임스탬프는 내용이 안 바뀐 저장(공백
    정리 등)에도 달라져 헛 충돌을 만들고, 반대로 같은 초에 두 번 저장되면 못 잡는다.
    해시는 **정말로 내용이 달라졌을 때만** 다르다.
    """
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _ensure_body_not_changed(db: Session, *, page_id: str, base_version: str | None) -> None:
    """그 사이 누가 먼저 저장했으면 막는다 (Z2).

    예전에는 조건 없이 덮어썼다. 미할당 티켓은 **아무나 편집 가능**하므로 두 사람이 동시에
    본문을 쓰면 나중 사람이 앞사람 글을 통째로 지운다 — 그리고 **양쪽 다 성공 토스트를 본다.**
    사람이 이미 한 일을 파괴하는 부류라 그 어떤 성능 문제보다 아프다.

    `base_version` 이 없으면(구버전 클라이언트·CLI) 예전대로 동작한다 — 새 계약을 강제해
    기존 경로를 깨뜨리지 않는다.
    """
    if not base_version:
        return
    from app.tickets.models import TicketCache

    row = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == page_id)
    ).scalar_one_or_none()
    if row is None:
        return
    if row.body_markdown is None:
        # 🔴 여기서 막으면 **본문이 있는 티켓은 첫 저장이 무조건 실패**한다.
        #
        # 화면이 편집을 시작할 때 받는 지문은 `_detail_body_markdown` 이 만든다. 로컬 본문이
        # 없으면 그 함수는 **Notion 블록을 렌더한 글**로 지문을 만든다. 반면 여기서는 로컬
        # 컬럼만 본다. 그래서 두 지문이 hash(Notion 본문) vs hash("") 로 항상 어긋나고,
        # 아무도 저장하지 않았는데 "다른 사람이 먼저 저장했습니다" 가 나온다.
        #
        # 정본이 없다는 것은 **포털을 통해 잃을 글이 아직 없다**는 뜻이다. 이 잠금이 지키려는
        # 것은 "사람이 포털에서 쓴 글을 나중 사람이 덮어쓰는 것" 이고, 그런 글이 아직 없다.
        # 앞사람의 첫 저장이 정본을 만들어 놓으므로 **뒷사람은 그다음부터 정상적으로 걸린다.**
        # 잃는 것은 '둘 다 첫 저장' 인 한순간뿐인데, 그건 매 저장마다 소스 본문을 다시 읽어야만
        # 알 수 있고(왕복 한 번 더) 지금 겪는 "영영 저장 못 함" 보다 훨씬 작은 문제다.
        return
    if body_version(row.body_markdown) != base_version:
        raise ConflictError(
            "다른 사람이 먼저 저장했습니다. 새로고침해 최신 내용을 확인한 뒤 다시 저장해 주세요."
        )


def save_ticket_body(
    db: Session, outbound, settings, user: User, *, page_id: str, body_markdown: str,
    now: datetime | None = None, repo=None, base_version: str | None = None,
) -> dict:
    """티켓 본문을 저장한다. 편집 권한은 속성 편집과 **같은 규칙**(담당자/미할당/운영자군).

    저장 순서(정본 먼저 → 소스 push)는 저장소 구현체가 지킨다. 여기서 중요한 것은 소스 push
    실패를 **오류로 바꾸지 않는 것**이다 — 오류로 던지면 요청 트랜잭션이 롤백되어 방금 저장한
    사용자 텍스트까지 사라지고, 순서를 지킨 의미가 사라진다. 대신 `synced=False` 를 그대로
    응답에 실어 화면이 "저장됨 · 원본 동기화 실패"를 보여주게 한다.

    다만 바로 아래 `get_live` 는 정본을 쓰기 **전에** 소스를 부른다. 소유권은 프런트가 준 값도
    캐시 값도 아닌 '지금 소스의 담당자'로 판정해야 하기 때문이다(IDOR). 그래서 소스가 아예
    닿지 않는 순간에는 저장이 시작되지도 못하고 요청이 실패한다 — 아무것도 저장되지 않지만
    '저장했다'고 하지도 않는다. 이 함수가 지키는 것은 '소스가 살아서 거절한 경우'다.
    """
    r = _repo(settings, outbound, repo)
    ensure_not_trashed(db, page_id)   # H2 — 휴지통 항목은 없는 것으로 본다
    ensure_in_scope(db, page_id, user)   # 쓰기도 범위 밖은 404 (3순위 IDOR)
    current = r.get_live(db, page_id=page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))
    _ensure_body_not_changed(db, page_id=page_id, base_version=base_version)
    result = r.save_body(
        db, page_id=page_id, body_markdown=body_markdown, now=now or utcnow()
    )
    return {
        "body_markdown": result.body_markdown,
        "body_version": body_version(result.body_markdown),
        "synced": result.synced,
        "body_sync_error": result.sync_error,
    }


# ── 댓글 ──────────────────────────────────────────────────────────────────────
#
# URL 은 page_id(딥링크 키)로 받고, 저장은 자체 UUID(ticket_cache.id)로 한다 — 그 해석만
# 저장소 seam 을 지난다. 응답은 늘 **목록 전체**다: 삭제·수정 뒤에 클라이언트가 자기 목록을
# 직접 기워 맞추면 툼스톤 규약이 두 곳(서버·클라)에 생겨 언젠가 갈라진다.
#
# 그 "응답은 늘 목록 전체" 때문에 **쓰기 경로의 범위 판정이 조회 판정이기도 하다**: 판정 없이
# 삭제를 한 번 던지면 그 티켓의 댓글 전체가 응답으로 돌아온다(지운 댓글만 툼스톤이고 나머지는
# 본문 그대로다). 그래서 아래 네 함수가 전부 `ensure_ticket_visible` 한 곳을 지난다.


def ensure_comment_ticket_visible(db: Session, ticket_uid: str, user: "User | None") -> None:
    """댓글이 매달린 티켓이 이 사람에게 보이는가 — **목록과 똑같은 판정**(§0-A).

    수정·삭제는 comment_id 만 받는다. 그래서 `comments.ensure_can_edit/ensure_can_delete` 만
    지났는데, 그건 **작성자/모더레이터 판정이지 범위 판정이 아니다** — 남의 부서 관리자가
    comment_id 하나로 범위 밖 티켓의 논의를 지울 수 있었고, 내가 쓴 댓글이 붙은 티켓이 나중에
    남의 부서로 배정돼도 계속 고칠 수 있었다(첨부에서 같은 순서로 이미 일어난 일이다 →
    router.py::_ensure_attachment_ticket_visible). 목록만 닫고 쓰기를 열어 두면 목록을 닫은
    의미가 없다.

    ⚠️ **page id 가 없는 티켓(source='native')은 통과시킨다.** 판정할 근거가 없는 것이지 범위
    밖인 것이 아니다 — `ensure_in_scope` 가 캐시 행이 없을 때, 그리고 담당자를 앱 사용자로
    해석할 수 없을 때 통과시키는 것과 같은 이유다. 그 결합(미할당 트리아지에 뜨는 티켓의
    댓글은 지울 수 있어야 한다)은 `ensure_in_scope` 가 갖고 있고 여기서 다시 쓰지 않는다.
    """
    page_id = _page_id_for_uid(db, ticket_uid)
    if page_id is None:
        return
    ensure_ticket_visible(db, page_id, user)


def list_ticket_comments(
    db: Session, outbound, settings, user: User, *, page_id: str, repo=None
) -> dict:
    # 상세와 **같은 규칙**이어야 한다. 상세만 막고 댓글을 열어 두면 id 하나로 논의 전체가
    # 새는데, 그건 상세가 새는 것과 다르지 않다.
    ensure_ticket_visible(db, page_id, user)
    uid = _repo(settings, outbound, repo).local_uid(db, page_id=page_id)
    return comments.list_comments(db, ticket_uid=uid, me=user)


def add_ticket_comment(
    db: Session, outbound, settings, user: User, *, page_id: str, body: str,
    now: datetime | None = None, repo=None,
) -> dict:
    stamp = now or utcnow()
    # H2 — 휴지통 티켓에는 댓글을 달 수 없다. 여기가 특히 중요한 이유: `ensure_local` 은
    # 미러 행이 없으면 **만든다**. 막지 않으면 지운 티켓에 댓글을 다는 순간 그 티켓의
    # 캐시 행이 되살아나고, 보관기간이 끝나면 댓글과 함께 다시 사라진다.
    # 범위 밖도 404 다 (3순위 IDOR).
    ensure_ticket_visible(db, page_id, user)
    uid = _repo(settings, outbound, repo).ensure_local(db, page_id=page_id, now=stamp)
    created = comments.create_comment(
        db, ticket_uid=uid, author=user, body=body, now=stamp
    )
    _notify_ticket_comment(db, page_id=page_id, uid=uid, author=user, now=stamp)
    return {
        "comment_id": created.id,
        **comments.list_comments(db, ticket_uid=uid, me=user),
    }


def _notify_ticket_comment(db: Session, *, page_id: str, uid: str, author: User, now) -> None:
    """내 티켓에 댓글이 달리면 알린다 (N2).

    `app/tickets/` 와 `app/board/` 전체에 `notify` 문자열이 **0건**이었다. 만들어지는 알림
    14종이 전부 관리·운영 이벤트 아니면 채팅이고, **사람이 실제로 협업하는 두 축(티켓·게시판)이
    통째로 조용했다.** 담당자는 `/my-tickets` 를 스스로 열어야 논의가 있었다는 걸 안다.

    ## 누구에게

    담당자 전원(작성자 자신은 뺀다 — 내가 쓴 것을 나에게 알리면 배지가 늘 켜져 있다).
    담당자를 해석하지 못하면 조용히 넘어간다 — 알림 하나 때문에 댓글 저장을 실패시키지 않는다.

    ## 실패해도 댓글은 남는다

    `notify_user` 가 터져도 이 함수 밖으로 나가지 않는다. 알림은 본 작업(댓글)보다 약한
    관심사이고, 그 반대로 만들면 알림 표 하나가 협업을 멈춘다.
    """
    from app.tickets.models import TicketCache

    try:
        row = db.execute(
            select(TicketCache).where(TicketCache.notion_page_id == page_id)
        ).scalar_one_or_none()
        if row is None:
            return
        id_to_user = _verified_id_to_user(db)
        targets = {
            id_to_user.get(n)
            for n in split_names(row.assignee_notion_ids or "")
            if id_to_user.get(n)
        }
        targets.discard(author.id)
        if not targets:
            return

        from app.notifications.service import notify_user

        label = f"GIT-{row.notion_ticket_number}" if row.notion_ticket_number else "티켓"
        for uid_ in targets:
            notify_user(
                db, uid_, type_="ticket_comment",
                title=f"{label}에 새 댓글: {author.display_name}",
                body=(row.title or "")[:200],
                related=("ticket", page_id), now=now,
            )
    except Exception:  # noqa: BLE001 — 알림이 댓글 저장을 막으면 안 된다
        logger.exception("티켓 댓글 알림에 실패했다 (page_id=%s)", page_id)


def edit_ticket_comment(
    db: Session, user: User, *, comment_id: str, body: str, now: datetime | None = None
) -> dict:
    # 범위 판정이 권한 판정보다 **먼저**다. 순서가 뒤집히면 범위 밖 댓글에 403 이 나가고,
    # 403 은 "그 id 는 존재한다"를 알려 준다 — 그걸 세면 남의 부서 논의의 존재를 열거할 수 있다.
    comment = comments.get_or_404(db, comment_id)
    ensure_comment_ticket_visible(db, comment.ticket_uid, user)
    comments.ensure_can_edit(comment, user)
    comments.update_comment(db, comment, body=body, now=now or utcnow())
    return comments.list_comments(db, ticket_uid=comment.ticket_uid, me=user)


def delete_ticket_comment(
    db: Session, user: User, *, comment_id: str, now: datetime | None = None
) -> dict:
    # 범위 밖은 404 — 모더레이션 권한(운영자·관리자)은 **자기 범위 안에서만** 있다.
    comment = comments.get_or_404(db, comment_id)
    ensure_comment_ticket_visible(db, comment.ticket_uid, user)
    comments.ensure_can_delete(comment, user)
    comments.soft_delete_comment(db, comment, now=now or utcnow())
    return comments.list_comments(db, ticket_uid=comment.ticket_uid, me=user)


# ── 첨부 (지시서 §4) ──────────────────────────────────────────────────────────

def add_ticket_attachment(
    db: Session, outbound, settings, user: User, *, page_id: str, data_dir,
    filename: str, content: bytes, now: datetime | None = None, repo=None,
) -> dict:
    """티켓에 파일을 붙인다. **편집 권한이 필요하다** — 남의 담당 티켓에 파일을 붙이는 것은
    티켓을 고치는 일이다. 권한 판정은 방금 소스에서 읽은 '현재' 담당자로 한다(ensure_can_edit).
    """
    stamp = now or utcnow()
    r = _repo(settings, outbound, repo)
    ensure_not_trashed(db, page_id)   # H2 — 휴지통 항목은 없는 것으로 본다
    current = r.get_live(db, page_id=page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))
    ensure_not_trashed(db, page_id)   # H2 — 첨부도 같은 이유
    ensure_in_scope(db, page_id, user)   # 쓰기도 범위 밖은 404 (3순위 IDOR)
    uid = r.ensure_local(db, page_id=page_id, now=stamp)
    att = ticket_attachments.add_attachment(
        db, data_dir, ticket_uid=uid, uploader=user,
        filename=filename, content=content, now=stamp,
    )
    return {
        "attachment_id": att.id,
        "attachments": ticket_attachments.attachment_views(db, ticket_uid=uid),
    }


def delete_ticket_attachment(
    db: Session, outbound, settings, user: User, *, attachment_id: str, repo=None
) -> dict:
    """첨부를 뗀다. 올린 사람 본인이거나 티켓을 편집할 수 있는 사람.

    없는 첨부는 404 다 — 403 은 "그런 첨부가 있긴 하다"를 알려 준다.
    """
    att = ticket_attachments.get_attachment(db, attachment_id)
    if att is None:
        raise NotFoundError("첨부를 찾을 수 없습니다.")
    uid = att.ticket_uid
    if att.uploaded_by_user_id != user.id:
        page_id = _page_id_for_uid(db, uid)
        if page_id is None:
            raise NotFoundError("첨부를 찾을 수 없습니다.")
        r = _repo(settings, outbound, repo)
        ensure_not_trashed(db, page_id)   # H2
        ensure_in_scope(db, page_id, user)   # 쓰기도 범위 밖은 404 (3순위 IDOR)
        ensure_can_edit(r.get_live(db, page_id=page_id), user, my_notion_id(db, user))
    ticket_attachments.remove_attachment(db, att)
    return {"attachments": ticket_attachments.attachment_views(db, ticket_uid=uid)}


def _page_id_for_uid(db: Session, ticket_uid: str) -> str | None:
    """자체 UUID → Notion page id. source='native' 티켓은 page id 가 없어 None 이다."""
    from app.tickets.models import TicketCache

    row = db.get(TicketCache, ticket_uid)
    return row.notion_page_id if row is not None else None
