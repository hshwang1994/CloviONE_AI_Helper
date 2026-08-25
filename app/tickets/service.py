"""사용자 셀프서비스 티켓 조회/편집 (내 티켓 / 미할당 / 팀 / 생성·편집).

이 모듈은 **소스를 모른다**. 티켓을 읽고 쓰는 일은 전부 TicketRepository(app/tickets/repository.py)
뒤에 있고, Notion 속성 이름·스키마·페이지네이션은 구현체(repository_notion.py) 안에만 있다.
여기 남는 것은 소스와 무관한 규칙뿐이다: 로그인 사용자 기준 필터, 담당자 이름/앱 user_id 해석,
소유권(IDOR) 검사, 감사 스냅샷, 휴지통.

보안(스펙 §12.3): 대상 notion_user_id 는 **세션 사용자에서만** 도출한다. 브라우저는 소스 user id 를
주지도 받지도 않는다 — 응답에는 해석된 user_id/이름만 싣는다.
"""

from __future__ import annotations

import json
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
    as_filter_values,
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


def assignee_token(db: Session, user: User) -> str:
    """이 사람을 **티켓 담당자로 가리키는 값** (D-285).

    티켓의 담당자 칸(`tickets.assignee_notion_ids`)은 이관해 온 행에 옛 소스의 user id 를
    담고 있다. 그래서 담당자 축 전체가 `user_notion_mappings` 에 verified 행이 있는
    사람만 가리킬 수 있었다.

    🔴 그 짝은 이제 **새로 만들 수 없다.** Notion 런타임을 걷어낸 뒤(S14 · D-284) 새
    계정에는 그 행이 영원히 안 생긴다. 그런데 담당자 축은 그 값이 없으면 조용히 닫힌다:

      · `/my-tickets` 가 영원히 비어 있다(그리고 「Notion 계정 미연결」이라고 말한다 —
        없어진 시스템의 이름으로).
      · 담당자 후보 목록에 그 사람이 안 나온다 → 아무도 그 사람에게 일을 줄 수 없다.
      · 팀 티켓의 담당자 조건으로 그 사람을 고를 수 없다.

    실측(2026-08-24 운영): 활성 15명 중 **2명**이 이 상태였고, 그중 하나는 그날 만든
    계정이다 — 앞으로 만드는 계정은 **전부** 이 상태로 태어난다.

    그래서 담당자를 가리키는 값을 「옛 짝이 있으면 그것, 없으면 **자기 user id**」로 정한다.
    이관해 온 행은 한 글자도 안 건드리고(옛 토큰이 그대로 산다), 새 행은 자체 id 로 선다.
    두 값이 겹칠 수는 없다 — 서로 다른 시스템이 발급한 UUID 다.

    ⚠️ 뒤늦게 verified 매핑을 붙이면 그 사람의 토큰이 바뀌므로, 그때는 이미 쌓인 행의
    토큰을 함께 옮겨야 한다. 축을 하나로 합치는 일(옛 토큰 → user id 데이터 이전)은
    Backlog **P-36** 이다.
    """
    return my_notion_id(db, user) or user.id


def _assignee_id_to_user(db: Session) -> dict[str, str]:
    """담당자 토큰 → 앱 user_id. 담당자 편집(해석/보존/역표시)에 쓴다.

    두 갈래를 함께 담는다: verified·active 매핑의 notion_user_id 와, **활성 사용자
    자신의 id**(`assignee_token` 참조). 후자를 빼면 자체 계정이 자기 티켓의 담당자로
    해석되지 않아 화면에서 이름이 사라진다.

    _load_name_map 은 표시용 이름(전 사용자 포함)이라 편집엔 못 쓴다 — 편집 후보/보존 판정은
    반드시 'active + 미보관' 으로만 한다(스펙 §12.3).
    """
    rows = db.execute(
        select(User.id, UserNotionMapping.notion_user_id)
        .outerjoin(
            UserNotionMapping,
            (UserNotionMapping.user_id == User.id)
            & (UserNotionMapping.status == STATUS_VERIFIED),
        )
        .where(User.active.is_(True), User.archived_at.is_(None))
    ).all()
    out: dict[str, str] = {}
    for uid, nid in rows:
        if nid:
            out.setdefault(nid, uid)
        out.setdefault(uid, uid)
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
        # `url` 은 여기 없다. 그 값은 전 건이 app.notion.com 을 가리키는데, 정본이 이
        # 서버로 넘어온 뒤로 그 주소가 여는 것은 우리가 더 이상 쓰지 않는 낡은 사본이다.
        # 사용자에게 「원본」이라고 내주면 오늘 고친 내용이 없는 쪽으로 보내는 셈이 된다.
        "tid": t.number,
        # 화면이 보여 주는 이름 (D-282). `tid` 는 옛 소스의 번호라 이름이 아니다 —
        # 화면이 그 앞에 접두사를 붙여 이름을 **만들어 내면** 그 문자열은 제품 어디에도
        # 없는 이름이 되고, 붙여 넣어도 아무 티켓이 안 열린다.
        "key": t.key,
        "title": t.title,
        "status": t.status,
        "due": t.due,
        "start": t.start,
        "category": t.category,
        "est_wd": t.est_wd,
        "act_wd": t.act_wd,
        "difficulty": t.difficulty,
        "priority": t.priority,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "project_ids": list(t.project_ids),
        # 해석된 Portal 프로젝트 id. 화면이 프로젝트로 이동할 때 쓰고, 범위 판정
        # (`_drop_out_of_scope`)이 SQL 과 **같은 축**을 쓰게 하는 값이다.
        "project_uid": t.project_uid,
        "assignee_names": [n for n in names if n],
        "assignee_user_ids": [u for u in uids if u],
        "project_names": pnames,
        "project": pnames[0] if pnames else "",
    }


def ticket_views(db: Session, tickets, *, with_names: bool = True) -> list[dict]:
    """DTO 목록 → API 응답 dict 목록. 스프린트의 담당자별 리스트도 이걸 써서 모양이 같다."""
    id_to_name = _load_name_map(db)[0] if with_names else {}
    id_to_user = _assignee_id_to_user(db) if with_names else {}
    return [ticket_view(t, id_to_name, id_to_user) for t in tickets]


def _project_visibility(db: Session, viewer, scope=None) -> "ProjectVisibility | None":
    """이 사람이 볼 수 있는 프로젝트 — **티켓 범위 판정의 단 하나의 입력** (0060).

    `None` 은 제한 없음(전역)이다. 빈 집합은 아무것도 안 보인다(fail-closed) — 둘을 같은
    값으로 표현하면 범위 계산이 빈 답을 낸 순간 조용히 전 포탈이 열린다.

    두 표현을 함께 만든다(`ProjectVisibility` docstring 참조): 미러 경로는 Portal id 로,
    실시간 폴백 경로는 외부 page id 로 맞춘다. 한 함수가 둘 다 만들므로 갈라질 자리가 없다.

    조회 범위(`visibility`)를 쓴다. 상위 부서 사람이 하위 팀 프로젝트의 티켓을 보는 것은
    협업이고, 그 프로젝트를 **옮기거나 지우는** 것만 관리 범위가 필요하다.

    `scope` 를 주면 그것으로 **더 좁힌다**(넓히지 못한다 — 부르는 쪽이 이미 그 사람의 조회
    범위 안에서 고른 값이어야 한다). 스프린트가 "이 부서의 회의" 로 화면 Context 를 좁힐 때
    쓴다 — 그때도 판정 함수는 이 하나뿐이라 규칙이 갈라지지 않는다.
    """
    if viewer is None:
        return None
    from app.authz.visibility import context_for_user, visible_project_ids
    from app.projects.models import Project
    from app.tickets.repository import ProjectVisibility

    ctx = context_for_user(db, viewer, scope=scope)
    if ctx.scope.is_global:
        return None
    rows = db.execute(
        visible_project_ids(ctx).add_columns(Project.notion_page_id)
    ).all()
    return ProjectVisibility(
        uids=frozenset(r[0] for r in rows),
        page_ids=frozenset(r[1] for r in rows if r[1]),
    )


def _project_in_scope(project_uid, external_ids, visible) -> bool:
    """이 티켓의 프로젝트가 범위 안인가 — **판정 문장은 여기 하나뿐이다**.

    미러에서 읽었으면 해석된 Portal id 로 본다(SQL 절과 같은 축). 실시간 폴백은 Portal
    짝을 아직 모르므로 외부 relation id 로 본다. 외부 relation 이 정확히 하나가 아니면
    소속을 판정할 수 없고, 판정할 수 없으면 닫는다(0060).

    ⚠️ 미러 경로에서 외부 id 로 되돌아가지 않는다. Portal 전용 프로젝트(Notion 짝 없음)의
    티켓은 외부 id 가 아예 없어서, 되돌아가는 순간 그 티켓들이 **전원에게서** 사라진다.
    """
    if project_uid:
        return project_uid in visible.uids
    ids = tuple(external_ids or ())
    return len(ids) == 1 and ids[0] in visible.page_ids


def _view_in_scope(view: dict, visible) -> bool:
    return _project_in_scope(view.get("project_uid"), view.get("project_ids"), visible)


def drop_out_of_scope_dtos(db: Session, dtos, viewer, scope=None) -> list:
    """DTO 목록에서 범위 밖 티켓을 뺀다 (스프린트·리포트 집계용).

    화면용 view 가 아니라 DTO 를 다루는 경로(집계)가 따로 있어서, 판정 규칙이 두 벌이 되지
    않게 여기 한 곳에 둔다 — 화면 목록은 좁혀 놓고 집계가 전 포탈이면 **담당자별 생산성이
    숫자로 새어 나간다**(그게 스프린트 요약에서 실제로 일어나던 일이다).

    소속을 판정할 수 없는 티켓(프로젝트 0개·2개 이상)은 어느 집계에도 안 들어간다 —
    아무 팀의 성과도 아니고, 그 상태 자체가 고쳐야 할 정합성 오류다.
    """
    if viewer is None:
        return list(dtos)
    visible = _project_visibility(db, viewer, scope)
    if visible is None:
        return list(dtos)
    return [
        d for d in dtos
        if _project_in_scope(
            getattr(d, "project_uid", None), getattr(d, "project_ids", ()), visible
        )
    ]


def ensure_in_scope(db: Session, page_id: str, viewer: "User | None") -> None:
    """범위 밖 티켓은 **없는 것으로 취급한다** (1순위 유출 #2).

    `GET /api/tickets/{page_id}` 는 로그인만 하면 **id 하나로** 본문·댓글·첨부 원본
    바이트까지 내줬다 — 목록에서 가려 둔 것이 단건에서 새는 전형적인 IDOR 다.

    **403 이 아니라 404.** 403 은 "그 id 는 존재하지만 너는 못 본다" 를 알려 주므로 id 를
    찍어 보며 포탈 전체 티켓의 존재를 열거할 수 있다(저장소 규칙 — `core/scope.py`
    모듈 docstring, 채팅 이미지 서빙, `get_scoped_user_or_404` 가 같은 관용).

    ## 판정은 **프로젝트**가 한다 (0060 에서 바뀐 규칙)

    예전에는 담당자로 판정하면서, 담당자를 앱 사용자로 해석하지 못하는 티켓은
    **그냥 통과시켰다** — "그런 티켓은 미할당 버킷에 있으니 막으면 목록과 단건이 다른 말을
    한다" 는 이유였다. 그 예외가 이 앱의 가장 큰 우회 경로였다: 운영 실측으로 티켓의
    21.5% 가 그 상태였고, 그 티켓들은 **로그인한 누구나** id 하나로 본문·댓글·첨부를 열고
    편집·claim 까지 할 수 있었다.

    이제 소속은 담당자가 아니라 프로젝트이므로 그 예외가 필요 없다. 목록도 단건도 같은
    조건(`project_link='ok'` + 프로젝트가 범위 안)을 본다.

    행이 없으면 통과시킨다. 판정할 근거가 없는 것이지 범위 밖인 것이 아니다
    (막 만든 티켓이 자기 눈에 안 보이면 그것도 고장이다).

    ## 🔴 **두 축으로 찾는다** (S14)

    `page_id` 는 이관해 온 티켓에서는 `notion_page_id` 이고, 자체 DB 에서 만든 티켓에서는
    **행의 uuid** 다(`app/tickets/repository_native.py` 의 식별자 규약).

    한 축만 보면 조용히 열린다: 자체 DB 티켓은 `notion_page_id` 가 NULL 이라 조회가 아무
    행도 못 찾고, 바로 위 「행이 없으면 통과」에 걸려 **범위 문을 통째로 지나간다.**
    0060 이 담당자 축을 버리고 닫은 그 구멍이 새 티켓에서 다시 열리는 것이고, 증상은
    「어떤 티켓만 아무에게나 보인다」라 아무도 신고하지 않는다.
    """
    if viewer is None:
        return
    from app.tickets.models import PROJECT_LINK_OK   # 지연 import(순환 참조)

    visible = _project_visibility(db, viewer)
    if visible is None:
        return
    found = ticket_row_for(db, page_id)
    if found is None:
        return
    project_uid, link = found.project_uid, found.project_link
    if link == PROJECT_LINK_OK and project_uid in visible.uids:
        return
    raise NotFoundError("티켓을 찾을 수 없습니다.")



def ticket_row_for(db: Session, page_id: str | None):
    """API 가 부르는 `page_id` → 우리 표의 행. **두 축을 이 함수 하나가 안다** (S14).

    `page_id` 는 이관해 온 티켓에서는 `notion_page_id` 이고, 자체 DB 에서 만든 티켓에서는
    **행의 uuid** 다(`app/tickets/repository_native.py` 의 식별자 규약). 그 사실을 아는
    자리가 여러 곳이 되면 한 곳이 빠지고, 빠진 곳은 오류를 안 낸다 — 그냥 「행이 없다」로
    읽혀서 범위 판정이 통과하거나 낙관적 잠금이 안 걸리거나 알림이 안 간다.

    `OR` 하나로 묻지 않고 두 번 묻는 이유: 두 컬럼이 우연히 같은 문자열을 담는 날
    `OR` 는 두 행을 돌려주고 `scalar_one_or_none()` 이 500 을 낸다. 순서가 있는 두 조회는
    그때도 한 행을 고르고, 그 순서가 저장소 구현체와 같다.
    """
    if not page_id:
        return None
    from app.tickets.models import TicketCache

    row = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == page_id)
    ).scalar_one_or_none()
    if row is not None:
        return row
    return db.get(TicketCache, page_id)


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


# ── 서버 필터 조립 ────────────────────────────────────────────────────────────
#
# 화면이 고른 조건과 앱이 반드시 거는 조건을 **한 벌로 합쳐서** 저장소에 넘긴다. 합치지 않고
# 일부를 파이썬 뒤처리로 남기면 페이지네이션이 그 뒤처리 **앞에서** 일어나고, 그 순간
# "20건을 달랬는데 13건이 왔다" + "total 이 사용자가 세는 수와 다르다" 가 동시에 난다.

def _assignee_token_for_user(db: Session, user_id: str) -> str | None:
    """앱 user_id → 담당자 토큰(`assignee_token` 참조). 활성 사용자가 아니면 None.

    브라우저는 소스 user id 를 주지도 받지도 않는다(§12.3) — 담당자 필터도 앱 user_id 로만
    받고 여기서 한 번 해석한다. 옛 짝이 있으면 그 값이, 없으면 자기 id 가 토큰이다.

    🔴 **`users.id` 로만 찾는다.** 옛 토큰을 그대로 넣어도 통하게 하면 계약이 두 벌이 되고,
    그 순간 브라우저가 소스 id 를 말할 수 있는 길이 생긴다(§12.3). 활성 사용자가 아니면
    `None` 이고, 부르는 쪽은 그때 목록을 **닫는다**(전체를 열지 않는다).
    """
    row = db.execute(
        select(User.id, UserNotionMapping.notion_user_id)
        .outerjoin(
            UserNotionMapping,
            (UserNotionMapping.user_id == User.id)
            & (UserNotionMapping.status == STATUS_VERIFIED),
        )
        .where(
            User.id == user_id,
            User.active.is_(True),
            User.archived_at.is_(None),
        )
    ).first()
    if row is None:
        return None
    uid, nid = row
    return nid or uid


def build_filters(
    db: Session,
    query=None,
    *,
    now: datetime | None = None,
    active_only: bool = False,
    viewer=None,
    assignee_id: str | None = None,
    allow_assignee_filter: bool = True,
    scope=None,
) -> TicketFilters:
    """화면 질의(`schemas.TicketListQuery`) + 앱이 거는 조건 → `TicketFilters` 한 벌.

    `query` 가 없으면(내부 호출) 앱이 거는 조건만 남는다.

    `allow_assignee_filter=False` 는 담당자 필터가 **뜻이 없는 화면**용이다(내 티켓은 담당자가
    언제나 세션 사용자고, 미할당은 정의상 담당자가 없다). 그런 화면에서 이 조건을 그대로
    걸면 언제나 빈 목록이 나가는데, 그건 "필터가 안 먹는다" 가 아니라 "티켓이 없다" 로
    보여서 원인을 못 찾는다.
    """
    # 범위(프로젝트)와 화면이 고른 담당자는 **서로 다른 축**이다. 둘 다 AND 로 걸린다.
    allowed_projects = _project_visibility(db, viewer, scope)
    picked_assignee = assignee_id
    close_everything = False
    if (allow_assignee_filter and query is not None
            and as_filter_values(getattr(query, "assignee_user_id", None))
            and assignee_id is None):
        resolved: list[str] = []
        for uid in as_filter_values(query.assignee_user_id):
            token = _assignee_token_for_user(db, uid)
            if token is not None:
                resolved.append(token)
        if not resolved:
            # 가리킬 수 없는 사람으로 거르면 걸릴 티켓이 없다. 조건을 조용히 버리면 **필터 없는
            # 전체 목록**이 나가는데, 그건 사용자가 알아챌 수 없는 방향의 오류다 — 닫는다.
            close_everything = True
        else:
            picked_assignee = resolved[0] if len(resolved) == 1 else tuple(resolved)
    if close_everything:
        from app.tickets.repository import ProjectVisibility

        allowed_projects = ProjectVisibility(uids=frozenset(), page_ids=frozenset())
    from app.tickets.query import SORT_KEYS

    raw_sort = getattr(query, "sort", None) or "created_at"
    sort_key = raw_sort if raw_sort in SORT_KEYS else "created_at"
    sort_dir = "asc" if getattr(query, "order", None) == "asc" else "desc"
    if query is None:
        sort_key = None
        sort_dir = "desc"
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
        sort_key=sort_key,
        sort_dir=sort_dir,
        created_from=getattr(query, "created_from", None),
        created_to=getattr(query, "created_to", None),
        est_wd_min=getattr(query, "est_wd_min", None),
        est_wd_max=getattr(query, "est_wd_max", None),
        act_wd_min=getattr(query, "act_wd_min", None),
        act_wd_max=getattr(query, "act_wd_max", None),
        exclude_statuses=frozenset(_TERMINAL) if active_only else frozenset(),
        # 휴지통은 목록에서 숨긴다(H2). 파이썬 `_drop_trashed` 도 그대로 남겨 둔다 —
        # 범위와 같은 이유로 두 그물이 겹치는 편이 낫다.
        exclude_page_ids=frozenset(trash_repo.trashed_page_ids(db, TRASH_TICKET)),
        project_any_of=allowed_projects,
    )


# ── 조회 ──────────────────────────────────────────────────────────────────────

def _total(result, views: list[dict]) -> int:
    """저장소가 센 값(필터 뒤·자르기 전). 안 세는 구현체면 페이지 길이로 떨어진다."""
    return result.total if result.total is not None else len(views)


def list_my_tickets(
    db: Session, outbound, settings, user: User, *, repo=None,
    filters: TicketFilters | None = None, page: PageSpec | None = None,
) -> dict:
    """로그인 사용자가 담당한 티켓(마감 무관).

    `total` 은 **필터 뒤·페이지 자르기 전** 건수다. 화면이 "N건 중 1-20" 을 쓸 수 있어야 한다.

    여기 「연결된 계정이 없어 답할 수 없다」는 갈래가 있었다(`mapped: False`). 사람마다
    가리킬 값이 언제나 있으므로(`assignee_token`) 그 상태는 이제 존재하지 않는다 —
    0건은 사고가 아니라 사실이고, 그때는 빈 목록이 정답이다.
    """
    result = _repo(settings, outbound, repo).list_by_assignee(
        db, assignee_id=assignee_token(db, user), filters=filters, page=page
    )
    views = _drop_trashed(db, ticket_views(db, result.tickets))
    return {"tickets": views, "total": _total(result, views)}


def list_unassigned_page(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None, viewer=None,
    filters: TicketFilters | None = None, page: PageSpec | None = None, scope=None,
) -> dict:
    """미할당 트리아지 한 페이지 — {"tickets": [...], "total": n}.

    **범위가 걸린다** (0060). 예전에는 이 함수에 `viewer` 인자 자체가 없어 로그인한 누구나
    전 포털의 미할당 티켓을 봤다 — 형제 함수 `list_team_page` 는 두 겹으로 범위를 걸고
    있었는데 여기만 아무 것도 없었다. 미할당 티켓은 **누구나 편집·claim 할 수 있으므로**
    (`ensure_can_edit`) 그건 읽기 유출을 넘어 쓰기 경계 문제였다.

    범위 판정은 팀 티켓과 **같은 것 하나**(`_project_visibility`)다.
    """
    result = _repo(settings, outbound, repo).list_unassigned(db, filters=filters, page=page)
    tickets = result.tickets
    if active_only:
        tickets = tuple(t for t in tickets if (t.status or "") not in _TERMINAL)
    views = _drop_out_of_scope(
        db, _drop_trashed(db, ticket_views(db, tickets, with_names=False)), viewer, scope
    )
    return {"tickets": views, "total": _total(result, views)}


def list_unassigned_tickets(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None, viewer=None,
    scope=None,
) -> list[dict]:
    """담당자가 없는 티켓 **전부**(범위 안). 기본은 활성(완료·취소 제외)만.
    담당자가 없으므로 이름 해석은 건너뛰고 프로젝트 이름만 붙는다.

    페이지를 안 받는다 — 스프린트·어시스턴트가 집계에 쓰는 경로라 전량이 맞다.
    화면(라우터)은 `list_unassigned_page` 를 쓴다.

    `viewer` 는 **반드시 넘겨야 한다.** 예전에는 스프린트가 "배분 대상은 좁히지 않는다" 며
    일부러 안 넘겼는데, 그 결과 스프린트 화면이 전 포털 미할당을 그대로 보여 주는 우회
    경로가 됐다. 회의에서 배분하려면 그 팀이 **볼 수 있는** 일이어야 한다.
    """
    return list_unassigned_page(
        db, outbound, settings, active_only=active_only, repo=repo, viewer=viewer, scope=scope
    )["tickets"]


def list_team_page(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None, viewer=None,
    filters: TicketFilters | None = None, page: PageSpec | None = None, scope=None,
) -> dict:
    """팀 티켓 한 페이지 — {"tickets": [...], "total": n}. 판정은 `list_team_tickets` 참조."""
    result = _repo(settings, outbound, repo).list_all(db, filters=filters, page=page)
    tickets = result.tickets
    if active_only:
        tickets = tuple(t for t in tickets if (t.status or "") not in _TERMINAL)
    views = _drop_out_of_scope(db, _drop_trashed(db, ticket_views(db, tickets)), viewer, scope)
    return {"tickets": views, "total": _total(result, views)}


def list_team_tickets(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None, viewer=None,
    scope=None,
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
        db, outbound, settings, active_only=active_only, repo=repo, viewer=viewer, scope=scope
    )["tickets"]


def _drop_out_of_scope(db: Session, views: list[dict], viewer, scope=None) -> list[dict]:
    """범위 밖 티켓을 뺀다 — **SQL 그물 뒤의 두 번째 그물**.

    `build_filters` 가 이미 같은 조건을 SQL 로 걸었다(그래야 페이지를 자르기 **전에** 걸린다).
    그런데도 파이썬 그물을 남겨 두는 이유는 두 그물이 겹치게 하기 위해서다: SQL 쪽이 넓게
    틀리면 여기서 잡히고(닫히는 방향), 그때 total 이 페이지 합보다 커지는 것이 **틀렸다는
    신호**가 된다. 판정 입력은 둘 다 `_project_visibility` 하나다.
    """
    if viewer is None:
        return views
    visible = _project_visibility(db, viewer, scope)
    if visible is None:
        return views
    return [v for v in views if _view_in_scope(v, visible)]


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
        ensure_can_edit(dto, user, assignee_token(db, user))
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
        # `body_is_local` 과 `body_sync_error` 는 여기 없다. 둘 다 「정본이 두 곳에
        # 있다」는 전제에서 나온 값이었는데 정본이 이 서버 하나가 됐다. 밀어 넣을 원본이
        # 없으므로 저장은 언제나 무손실이고, 어긋날 짝이 없으므로 어긋난 이유도 없다.
        # 포털에서 붙인 파일(§4). 본문 안의 이미지는 blocks 쪽에 kind="image" 로 온다.
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


def list_projects(db: Session, viewer: User) -> list[dict]:
    """새 티켓 폼의 프로젝트 드롭다운 — **이 사람이 볼 수 있는 Portal 프로젝트**.

    예전에는 외부 소스(Notion)의 relation 목록을 그대로 내려 줬다. 두 가지가 잘못이었다:
      * **범위가 없다.** 다른 부서의 프로젝트 이름이 전부 드롭다운에 떴다.
      * **외부 키를 브라우저에 내보낸다.** 그러면 소스가 바뀌는 날 프런트도 함께 바뀌고,
        무엇보다 그 id 로는 권한을 검증할 수 없다(Portal 이 소유를 모른다).

    `dept_path` 는 그 프로젝트의 소속 **경로**다 — 화면이 "이 티켓이 어디로 공유되는가" 를
    사용자에게 보여 줄 수 있어야 한다(§13).

    ⚠️ 경로를 **서버가** 만든다. 예전에는 `dept_id` 만 주고 "화면이 조직 트리에서 만든다"
    고 적어 뒀는데, 조직 트리 API(`/api/admin/departments`)는 관리자 전용이라 일반
    사용자의 화면에서는 언제나 빈 값이었다 — 그래서 부서 프로젝트를 골라도 공유 범위가
    늘 "조직 전체 공통" 이라고 표시됐다. 정확히 반대로 안내한 셈이다.
    """
    from app.authz.visibility import (
        RESOURCE_PROJECT,
        context_for_user,
        effective_visibility_clause,
    )
    from app.core.org_tree import DeptTree
    from app.projects.models import Project

    ctx = context_for_user(db, viewer)
    tree = DeptTree.load(db)
    stmt = select(Project).where(Project.archived_at.is_(None))
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    if clause is not None:
        stmt = stmt.where(clause)
    rows = db.execute(stmt.order_by(Project.name.asc(), Project.id.asc())).scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "code": p.code,
            "dept_id": p.dept_id,
            "dept_path": [
                {"id": n.id, "name": n.name} for n in tree.path(p.dept_id)
            ] if p.dept_id else [],
            "org_id": p.org_id,
            # 어느 프로젝트에나 티켓을 만들 수 있다. 예전에는 외부 짝이 있어야 했고
            # (소스에 relation 을 걸어야 티켓이 생겼다) 그래서 이 칸이 있었는데, S14 뒤로
            # 티켓의 정본이 이 서버라 짝이 없어도 만들어진다. 칸 자체는 남긴다 — 화면이
            # 이미 읽고 있고, 없애면 프런트가 `undefined` 를 거짓으로 읽어 버튼이 사라진다.
            "can_create_ticket": True,
        }
        for p in rows
    ]


def list_assignees(
    db: Session, *, org_id: str | None = None, project_id: str | None = None,
) -> list[dict]:
    """담당자로 배정 가능한 사람 목록 — **활성 사용자 전원**.

    예전에는 여기에 `user_notion_mappings` 의 verified 행이 있는 사람만 나왔다. 그 짝은
    이제 새로 만들 수 없으므로(S14 가 Notion 런타임을 걷었다) 그 조건은 **새 계정을
    영원히 후보에서 빼는** 조건이 된다 — 누구도 그 사람에게 일을 줄 수 없다. 가리키는
    값은 `assignee_token` 이 언제나 만들어 낸다(D-285).

    ## `project_id` 를 주면 **그 프로젝트에 닿을 수 있는 사람만** (0060)

    담당자와 프로젝트 ACL 이 어긋나면 안 된다: A-2 사람을 A-1 프로젝트 티켓의 담당자로
    배정하면 그 사람은 **자기가 담당한 티켓을 못 여는** 상태가 된다(목록에도 안 뜬다).
    화면에서 고를 수 없게 막는 편이 그 상태를 만들고 나서 설명하는 것보다 낫다.

    판정은 화면 판정과 **같은 표**(`app/authz/visibility.py`)를 쓴다. 사람마다 질의를
    돌리지 않는다 — 범위 계산은 부서 트리 하나로 끝나므로 트리를 한 번 읽어 전원을
    메모리에서 판정한다.

    raw notion_user_id 는 응답에 넣지 않는다(브라우저 미노출, 스펙 §12.3). 편집 API 가 user_id 를
    받아 서버에서 담당자 토큰으로 해석한다.

    **부서·직책·조직을 함께 싣는다**(사용자 지시 2026-08-04). 예전에는 {user_id, display_name}
    뿐이라 '김하나'가 둘이면 담당자 선택 목록에 같은 줄이 두 번 떴고, 어느 쪽이 내가 찾는
    사람인지 알 방법이 화면에 없었다. 신원 조각은 app/core/people.py 가 만든다.

    행 대신 User 객체를 부르는 이유: `department`/`title` 은 관계에서 이름을 꺼내는
    프로퍼티라 컬럼 select 로는 안 나온다. 관계가 lazy="joined" 라 질의 수는 그대로다.
    """
    stmt = select(User).where(User.active.is_(True), User.archived_at.is_(None))
    # 조직 밖 사람은 담당자 후보가 아니다 (1순위 유출 #7). 이 목록은 이름·부서·직책·조직을
    # 그대로 실어 주므로(사용자 지시로 그렇게 만들었다) **조직도 열거**가 된다 — 검색이
    # 사용자 종류를 역할로 막는 결정을 이 목록이 옆문으로 무효화하고 있었다.
    if org_id:
        stmt = stmt.where(User.org_id == org_id)
    users = db.execute(stmt.order_by(User.display_name)).scalars().all()
    if project_id:
        users = _users_who_can_reach_project(db, users, project_id)
    from app.core.org_tree import DeptTree

    org_names = people.org_name_map(db)
    # 조직 경로까지 싣는다 — 담당자 선택기에서 동명이인을 이름만으로 고르면 안 된다.
    tree = DeptTree.load(db)
    return [people.identity(u, org_names, None, tree) for u in users]


def _users_who_can_reach_project(db: Session, users: list[User], project_id: str) -> list[User]:
    """이 프로젝트를 **볼 수 있는** 사람만 남긴다. 프로젝트가 없으면 빈 목록(fail-closed).

    판정은 화면이 쓰는 그 함수(`app/authz/visibility.py`)가 한다 — 사람마다 다시 적으면
    「담당자 후보로는 떴는데 그 사람은 그 프로젝트를 못 본다」가 된다.
    """
    from app.authz.visibility import users_who_can_view_project
    from app.projects.models import Project

    return users_who_can_view_project(db, users, db.get(Project, project_id))


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
    ensure_can_edit(current, user, assignee_token(db, user))
    item = trash_service.move_to_trash(
        db, item_type=TRASH_TICKET, notion_page_id=page_id,
        title=current.title or "(제목 없음)", url=current.url,
        user=user, now=now,
    )
    # `url` 은 안 돌려준다 — 옛 Notion 주소라 화면이 그것으로 링크를 만들면 낡은 사본을 연다.
    return {"title": item.title}


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
    nid = assignee_token(db, user)
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

def ensure_can_edit(ticket: TicketDTO, user: User, my_token: str | None) -> None:
    """소유권 검증(스펙 §25.5·IDOR). 운영/관리자군은 우회, 그 외는 본인 담당 또는 미할당만.

    소스에서 **방금 읽은** '현재' 티켓의 담당자로 판정한다(프런트가 준 값도, 캐시 값도 아니다).

    ## 이 함수는 범위를 보지 않는다 — 그건 앞 문이 이미 했다

    호출부는 전부 `ensure_in_scope` 를 먼저 지난다(쓰기 경로 여덟 곳). 즉 여기 도달했다는
    것은 **그 티켓의 프로젝트가 이 사람 범위 안**이라는 뜻이고, 여기서는 그 안에서 누가
    손댈 수 있는가만 정한다. 두 축(범위·소유권)을 한 함수에 섞으면 한쪽을 고칠 때 다른
    쪽이 조용히 넓어진다.

    아래 "미할당은 누구나" 예외가 예전에는 위험했다 — 범위 판정이 담당자 축이었고, 담당자를
    해석 못 하는 티켓(운영 실측 21.5%)을 `ensure_in_scope` 가 **통과시켰기** 때문에 사실상
    전 포털 대상 무제한 편집이었다. 0060 에서 범위가 프로젝트 축으로 바뀌면서 그 통과 예외가
    사라졌고, 이제 이 예외는 "내가 볼 수 있는 프로젝트의, 주인 없는 일" 로 정확히 좁혀진다.
    """
    # 운영/관리자군(MODERATOR_ROLES)은 소유권을 우회해 아무 티켓이나 편집할 수 있다.
    # 그 외(user/auditor)는 본인 담당이거나 미할당인 티켓만 편집할 수 있다(IDOR 차단).
    if user.role in MODERATOR_ROLES:
        return
    assignees = ticket.assignee_ids
    if not assignees:
        return  # 미할당 — 담당자가 필요한 일이므로 (범위 안이면) 누구나 손댈 수 있다
    if my_token and my_token in assignees:
        return  # 본인 담당
    raise ForbiddenError("이 티켓을 편집할 권한이 없습니다(담당자 또는 미할당 티켓만 편집할 수 있습니다).")


def _resolve_assignee_ids(db: Session, user_ids: list[str]) -> list[str]:
    """앱 user_id 목록 → 담당자 토큰 목록. 하나라도 해석 불가면 거절.

    브라우저는 절대 소스 id 를 주지 않는다 — 항상 서버에서 해석한다(스펙 §12.3).
    거절하는 것은 **활성 사용자가 아닌 id** 뿐이다(`assignee_token` 참조).
    """
    if not user_ids:
        return []
    rows = db.execute(
        select(User.id, UserNotionMapping.notion_user_id)
        .outerjoin(
            UserNotionMapping,
            (UserNotionMapping.user_id == User.id)
            & (UserNotionMapping.status == STATUS_VERIFIED),
        )
        .where(
            User.id.in_(user_ids),
            User.active.is_(True),
            User.archived_at.is_(None),
        )
    ).all()
    found = {uid: (nid or uid) for uid, nid in rows}
    missing = [uid for uid in user_ids if uid not in found]
    if missing:
        raise ValidationAppError("담당자로 지정할 수 없는 사용자가 있습니다(활성 계정이 아닙니다).")
    seen: set[str] = set()
    out: list[str] = []
    for uid in user_ids:
        nid = found[uid]
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def _build_assignee_people(db: Session, current_assignees, user_ids: list[str]) -> list[str]:
    """새 담당자 토큰 목록을 만든다.

    앱 사용자로 해석되지 않는 기존 담당자(퇴사자·외부 사람의 옛 토큰)는 **보존**하고, 앱
    사용자 담당자만 user_ids 로 교체한다 — 이렇게 하면 편집 화면(앱 사용자 체크박스)으로
    손대지 않은 담당자를 조용히 지우지 않는다.
    """
    mapped_ids = set(_assignee_id_to_user(db))
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
    db: Session, *, page_id: str, key: str | None, title: str | None, actor: User,
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

        # 알림에 쓰는 이름은 `<PROJECT_CODE>-<SEQ>` 다 (D-282). 예전에는 채번 숫자에
        # `GIT-` 을 붙였는데 그 접두사는 옛 정책의 것이고 이관하지 않았다(D-283) — 그대로
        # 두면 알림에 뜬 이름을 검색창에 쳐도 그 티켓이 안 나온다.
        label = key or "티켓"
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
    ensure_can_edit(current, user, assignee_token(db, user))

    repo_changes = dict(changes)
    if "assignee_user_ids" in repo_changes:
        repo_changes["assignee_notion_ids"] = _build_assignee_people(
            db, current.assignee_ids, repo_changes.pop("assignee_user_ids") or []
        )
    # API 이름 → 저장소 도메인 키. 두 이름이 다른 것은 API 쪽이 '무엇을 보내는지'(project_id,
    # start_date)를, 저장소 쪽이 '어느 속성인지'(project, start)를 말하기 때문이다.
    if "project_id" in repo_changes:
        # 프로젝트는 **뗄 수 없다** (0060). 예전에는 빈 값이 '연결 해제' 였는데, 티켓의 조직
        # 소속을 프로젝트가 정하는 이상 그건 그 티켓을 어느 범위에도 안 잡히는 유령으로
        # 만드는 동작이다. 옮기는 것은 되고(아래 검증을 지난 프로젝트로), 없애는 것은 안 된다.
        pid = (repo_changes.pop("project_id") or "").strip()
        if not pid:
            raise ValidationAppError(
                "티켓에서 프로젝트를 뗄 수 없습니다. 다른 프로젝트로 옮길 수는 있습니다."
            )
        # 옮기는 대상도 **내가 쓸 수 있는 프로젝트**여야 한다 — 아니면 내 티켓을 남의 부서로
        # 밀어 넣고 그 순간 되돌릴 수도 없게 된다(읽기 유출보다 나쁘다).
        repo_changes["project"] = [_resolve_writable_project(db, user, pid)]
    if "start_date" in repo_changes:
        repo_changes["start"] = repo_changes.pop("start_date")

    stamp = now or utcnow()
    updated = r.update(db, page_id=page_id, changes=repo_changes, now=stamp)
    if "assignee_notion_ids" in repo_changes:
        # 담당자를 건드린 편집에서만 본다. 마감일만 고친 저장이 배정 알림을 만들면 안 된다.
        _notify_assignees_added(
            db, page_id=page_id, key=updated.key, title=updated.title, actor=user,
            before=resolve_assignee_user_ids(db, current.assignee_ids),
            after=resolve_assignee_user_ids(db, updated.assignee_ids),
            now=stamp,
        )
    return {
        "ticket": ticket_views(db, [updated])[0],
        "before": snapshot(current),
        "after": snapshot(updated),
    }


# ── 활동 이력 ─────────────────────────────────────────────────────────────────
#
# 상태·담당자·마감이 바뀔 때마다 감사 로그에 before/after 가 쌓인다. 그런데 **티켓 화면에는
# 그것이 없었다** — 「이 티켓이 왜 지금 이 상태인가」에 답하는 유일한 기록인데, 보려면
# 관리자 콘솔의 감사 화면을 열어야 했고 그 화면은 일반 사용자가 못 연다. 그 사이 상세
# 화면의 아래쪽 40% 는 비어 있었다(S18 실측, 2560 폭).
#
# 감사 행을 **그대로** 내보내지 않는다. 그 행에는 클라이언트 IP·요청 id 처럼 운영자만 볼
# 것이 함께 들어 있고, 그것을 티켓 열람자 전원에게 열면 감사 화면의 권한 경계를 이 경로가
# 우회하는 것이 된다. 아래 세 가지를 지킨다:
#
#   1. **읽기 권한을 먼저 본다.** 티켓 상세와 같은 판정(`ensure_in_scope`)이라 범위 밖은
#      404 다 — 「이력이 없다」가 아니라 「그 티켓이 없다」로 답한다.
#   2. **화이트리스트로 검열한다.** 사용자에게 보이는 속성 다섯만 나간다.
#   3. **바뀐 것만 말한다.** before 와 after 가 같은 칸은 싣지 않는다 — 저장 한 번에 아홉
#      칸이 전부 나열되면 무엇이 바뀌었는지가 오히려 안 보인다.

# 사용자에게 보이는 이름. 감사 스냅샷의 키(`repository.snapshot`)와 짝이다.
HISTORY_FIELDS: dict[str, str] = {
    "status": "상태",
    "priority": "우선순위",
    "due": "마감",
    "assignees": "담당자",
    "difficulty": "난이도",
    "est_wd": "예상 WD",
}
# 이 티켓에 달리는 감사 동작 중 **사람이 한 일**만 이력에 싣는다.
HISTORY_ACTIONS: dict[str, str] = {
    "ticket.create": "만들었습니다",
    "ticket.update": "속성을 고쳤습니다",
    "ticket.claim": "담당자로 자신을 지정했습니다",
    "ticket.body_update": "본문을 고쳤습니다",
    "ticket.trash": "휴지통으로 옮겼습니다",
}
HISTORY_LIMIT = 50


def _history_value(field: str, raw, names: dict[str, str]) -> str:
    if field == "assignees":
        ids = raw or []
        if not isinstance(ids, list):
            return str(raw)
        if not ids:
            return "없음"
        return ", ".join(names.get(str(i), "알 수 없는 사용자") for i in ids)
    if raw in (None, "", []):
        return "없음"
    return str(raw)


def ticket_history(db: Session, user: User, *, page_id: str, limit: int = HISTORY_LIMIT) -> dict:
    """이 티켓에 무슨 일이 있었는가 — 감사 기록의 **사용자에게 보이는 부분**만.

    돌려주는 것은 `{"items": [...]}` 하나다. 각 항목은 언제·누가·무엇을 했고, 속성이
    바뀐 경우 어느 칸이 무엇에서 무엇으로 갔는지를 담는다.
    """
    from app.audit.models import AuditLog  # noqa: PLC0415 — 순환 import 를 만들지 않는다

    ensure_not_trashed(db, page_id)
    ensure_in_scope(db, page_id, user)

    rows = db.execute(
        select(AuditLog)
        .where(AuditLog.object_type == "notion_task", AuditLog.object_id == page_id,
               AuditLog.result == "success")
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(max(1, min(limit, HISTORY_LIMIT)))
    ).scalars().all()

    # 이름은 한 번에 모아 읽는다 — 행마다 조회하면 이력 50줄이 질의 50번이 된다.
    wanted: set[str] = set()
    for row in rows:
        if row.user_id:
            wanted.add(row.user_id)
        for side in (row.before_json, row.after_json):
            payload = _history_payload(side)
            for uid in (payload.get("assignees") or []):
                if isinstance(uid, str):
                    wanted.add(uid)
    names: dict[str, str] = {}
    if wanted:
        names = {
            u.id: u.display_name
            for u in db.execute(select(User).where(User.id.in_(list(wanted)))).scalars().all()
        }

    items = []
    for row in rows:
        before = _history_payload(row.before_json)
        after = _history_payload(row.after_json)
        changes = []
        for field, label in HISTORY_FIELDS.items():
            if field not in before and field not in after:
                continue
            old, new = before.get(field), after.get(field)
            if old == new:
                continue
            changes.append({
                "field": field, "label": label,
                "from": _history_value(field, old, names),
                "to": _history_value(field, new, names),
            })
        items.append({
            "id": row.id,
            "at": row.created_at.isoformat(),
            "actor": names.get(row.user_id or "", "알 수 없는 사용자"),
            "action": row.action,
            # 모르는 동작도 **버리지 않는다** — 이력에서 줄이 조용히 사라지면 사람은
            # 그 사이에 아무 일도 없었다고 읽는다.
            "summary": HISTORY_ACTIONS.get(row.action, "기록이 남았습니다"),
            "changes": changes,
        })
    return {"items": items}


def _history_payload(raw) -> dict:
    """감사 스냅샷 칸. `JsonText` 는 문자열로 돌려주므로 여기서 한 번 푼다."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
    id_to_user = _assignee_id_to_user(db)
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
    ensure_can_edit(current, user, assignee_token(db, user))
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
            db, page_id=page_id, key=updated.key, title=updated.title, actor=user,
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
    ensure_can_edit(current, user, assignee_token(db, user))
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
            db, page_id=page_id, key=updated.key, title=updated.title, actor=user,
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
    """미할당(또는 본인 담당) 티켓의 담당자에 '나'를 배정한다.

    🔴 **한 번에 한 사람만 진행한다** (Z1). 담당자를 읽고 쓰는 사이에 Notion 왕복이 두 번
    (0.5~3초) 들어간다. 트리아지 화면에서 두 사람이 같은 티켓을 거의 동시에 누르면 둘 다
    빈 담당자를 읽고 각자 자기를 써서, **뒤에 쓴 사람이 앞사람을 덮어쓰는데 둘 다 성공 토스트를
    본다.** 앞사람은 자기 티켓이라고 믿고 일을 시작한다.

    잠금의 한계는 `app/tickets/claim_lock.py` 에 적었다.
    """
    from app.tickets.claim_lock import claim_guard

    with claim_guard(db, page_id):
        return update_ticket(
            db, outbound, settings, user, page_id=page_id,
            changes={"assignee_user_ids": [user.id]}, now=now, repo=repo,
        )


def _resolve_writable_project(db: Session, user: User, project_id: str) -> str:
    """Portal 프로젝트 id → 외부 소스 relation id. 범위 밖이거나 없으면 404.

    **없는 프로젝트와 범위 밖 프로젝트를 같은 404 로** 답한다. 갈리면 응답만 보고 "그
    프로젝트는 존재한다" 를 알 수 있고, id 를 찍어 보며 조직의 프로젝트 목록을 열거할 수
    있다(`app/core/scope.py` 모듈 docstring 의 규칙).
    """
    from app.authz.visibility import (
        RESOURCE_PROJECT,
        context_for_user,
        effective_visibility_clause,
    )
    from app.projects.models import Project

    ctx = context_for_user(db, user)
    stmt = select(Project).where(Project.id == project_id)
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    if clause is not None:
        stmt = stmt.where(clause)
    project = db.execute(stmt).scalar_one_or_none()
    if project is None:
        raise NotFoundError("프로젝트를 찾을 수 없습니다.")
    if project.archived_at is not None:
        raise ValidationAppError("보관된 프로젝트에는 새 티켓을 만들 수 없습니다.")
    # 외부 짝(`notion_page_id`)이 있으면 그 값을, 없으면 **우리 id** 를 돌려준다 (S14).
    #
    # 예전에는 짝이 없는 프로젝트에서 티켓 생성을 막았다. 그때는 그것이 옳았다 — 티켓
    # 본체가 외부 소스에 살아서 relation 을 걸 자리가 없었고, 조용히 프로젝트 없이
    # 만들면 그 티켓이 유령이 됐다.
    #
    # 자체 DB 가 정본이 된 뒤에는 그 근거가 없다. 그리고 **막아 두면 새 정책과 정면으로
    # 부딪힌다**: Cutover 이후에 만드는 프로젝트에는 `notion_page_id` 가 영원히 없으므로,
    # 그 프로젝트에서는 티켓을 하나도 못 만들게 된다.
    #
    # 저장소 구현체는 두 모양을 다 받는다(`repository_native._resolve_project`).
    return project.notion_page_id or project.id


def create_ticket(
    db: Session, outbound, settings, user: User, *, payload,
    now: datetime | None = None, repo=None,
) -> dict:
    """새 티켓을 만든다. **프로젝트가 필수**이고, 그 프로젝트가 이 사람 범위 안이어야 한다.

    담당자는 user_id→소스 id 로 해석하고, 나머지 검증(상태·우선순위·난이도 옵션)은 저장소
    구현체가 실제 스키마로 한다.

    `payload.project_id` 는 **Portal 프로젝트 id** 다. 여기서 두 가지를 한다:
      1. 그 프로젝트를 이 사람이 쓸 수 있는가 — 없거나 범위 밖이면 404(존재를 알리지 않는다)
      2. 외부 소스에 쓸 relation id 로 번역 — 브라우저는 외부 키를 모른 채로 끝난다

    생성 직후 저장소가 캐시에 그 티켓을 써 넣으므로 다음 목록 조회에서 바로 보인다.
    """
    external_project_id = _resolve_writable_project(db, user, payload.project_id)
    draft = TicketDraft(
        title=payload.title,
        status=payload.status,
        priority=payload.priority,
        difficulty=payload.difficulty,
        est_wd=payload.est_wd,
        due_date=payload.due_date,
        project_id=external_project_id,
        description_markdown=payload.description,
        assignee_ids=tuple(_resolve_assignee_ids(db, payload.assignee_user_ids or [])),
    )
    stamp = now or utcnow()
    created = _repo(settings, outbound, repo).create(db, draft=draft, now=stamp)
    # 번호는 **로컬 행이 생긴 뒤에** 붙인다 (S6 · D-196). 저장소가 캐시 행을 써 넣은
    # 다음이라야 그 행에 `seq` 를 줄 수 있고, 채번과 티켓 삽입이 같은 트랜잭션에 있어야
    # 롤백될 때 번호도 함께 돌아간다.
    _number_new_ticket(db, page_id=created.page_id, actor=user, now=stamp)
    # 생성과 동시에 남에게 배정하는 것도 배정이다. 여기가 빠지면 "남이 나에게 일을 만든"
    # 경우만 조용해지는데, 그게 배정 알림이 가장 필요한 자리 중 하나다.
    _notify_assignees_added(
        db, page_id=created.page_id, key=created.key, title=created.title,
        actor=user, before=[],
        after=resolve_assignee_user_ids(db, created.assignee_ids), now=stamp,
    )
    return {"ticket": ticket_views(db, [created])[0], "after": snapshot(created)}


def _number_new_ticket(db: Session, *, page_id: str | None, actor: User, now: datetime) -> None:
    """새 티켓에 번호와 첫 활동을 남긴다 (S6).

    **프로젝트에 코드가 없으면 번호를 안 준다.** 그 상태에서 번호를 요구하면 티켓 생성이
    통째로 막힌다 — 번호 없는 티켓은 화면에서 제목으로 불린다(`work/resolve.display_key`).

    **행을 두 축으로 찾는다 (S14).** `page_id` 는 이관해 온 티켓에서는 `notion_page_id`
    이고 자체 DB 에서 만든 티켓에서는 행의 uuid 다. 한 축만 보면 자체 DB 티켓에서 이
    함수가 조용히 아무 일도 안 하고, 그러면 그 티켓만 **생성 활동이 없는 채로** 남는다 —
    번호는 저장소 구현체가 이미 붙였으므로 오류도 안 난다.
    """
    if not page_id:
        return
    from app.work import activity as work_activity
    from app.work import service as work_service

    row = ticket_row_for(db, page_id)
    if row is None:
        return
    work_activity.record(
        db, ticket_id=row.id, kind=work_activity.ACT_CREATED, actor_id=actor.id,
        to_value=row.status, now=now,
    )
    work_service.number_if_possible(db, row, now=now)


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
    row = ticket_row_for(db, page_id)
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

    밀어 넣을 소스가 없으므로 저장은 이 서버의 티켓 표 하나에서 끝난다. 예전에 이 자리에
    있던 「push 실패를 오류로 바꾸지 않는다」와 그것을 나르던 `synced=False` 는 정본이 두
    곳에 있을 때만 뜻이 있던 규칙이라 함께 걷었다.

    다만 바로 아래 `get_live` 는 정본을 쓰기 **전에** 소스를 부른다. 소유권은 프런트가 준 값도
    캐시 값도 아닌 '지금 소스의 담당자'로 판정해야 하기 때문이다(IDOR). 그래서 소스가 아예
    닿지 않는 순간에는 저장이 시작되지도 못하고 요청이 실패한다 — 아무것도 저장되지 않지만
    '저장했다'고 하지도 않는다. 이 함수가 지키는 것은 '소스가 살아서 거절한 경우'다.
    """
    r = _repo(settings, outbound, repo)
    ensure_not_trashed(db, page_id)   # H2 — 휴지통 항목은 없는 것으로 본다
    ensure_in_scope(db, page_id, user)   # 쓰기도 범위 밖은 404 (3순위 IDOR)
    current = r.get_live(db, page_id=page_id)
    ensure_can_edit(current, user, assignee_token(db, user))
    _ensure_body_not_changed(db, page_id=page_id, base_version=base_version)
    result = r.save_body(
        db, page_id=page_id, body_markdown=body_markdown, now=now or utcnow()
    )
    return {
        "body_markdown": result.body_markdown,
        "body_version": body_version(result.body_markdown),
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
    try:
        row = ticket_row_for(db, page_id)
        if row is None:
            return
        id_to_user = _assignee_id_to_user(db)
        targets = {
            id_to_user.get(n)
            for n in split_names(row.assignee_notion_ids or "")
            if id_to_user.get(n)
        }
        targets.discard(author.id)
        if not targets:
            return

        from app.notifications.service import notify_user

        label = row.canonical_key or "티켓"
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
    ensure_can_edit(current, user, assignee_token(db, user))
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
        ensure_can_edit(r.get_live(db, page_id=page_id), user, assignee_token(db, user))
    ticket_attachments.remove_attachment(db, att)
    return {"attachments": ticket_attachments.attachment_views(db, ticket_uid=uid)}


def _page_id_for_uid(db: Session, ticket_uid: str) -> str | None:
    """자체 UUID → **API 가 부르는 `page_id`**. `ticket_row_for` 의 정확한 역함수다.

    이관해 온 티켓에서는 `notion_page_id`, 자체 DB 에서 만든 티켓에서는 행의 uuid 다.
    여기서 `notion_page_id` 만 돌려주면 자체 티켓이 `None` 이 되고, 이 값을 받는 쪽은
    「티켓을 못 찾았다」로 읽는다 — 범위 판정이 통과하거나 알림이 안 간다.
    """
    from app.tickets.models import TicketCache

    row = db.get(TicketCache, ticket_uid)
    return (row.notion_page_id or row.id) if row is not None else None
