"""사용자 셀프서비스 티켓 조회/편집 (내 티켓 / 미할당 / 팀 / 생성·편집).

이 모듈은 **소스를 모른다**. 티켓을 읽고 쓰는 일은 전부 TicketRepository(app/tickets/repository.py)
뒤에 있고, Notion 속성 이름·스키마·페이지네이션은 구현체(repository_notion.py) 안에만 있다.
여기 남는 것은 소스와 무관한 규칙뿐이다: 로그인 사용자 기준 필터, 담당자 이름/앱 user_id 해석,
소유권(IDOR) 검사, 감사 스냅샷, 휴지통.

보안(스펙 §12.3): 대상 notion_user_id 는 **세션 사용자에서만** 도출한다. 브라우저는 소스 user id 를
주지도 받지도 않는다 — 응답에는 해석된 user_id/이름만 싣는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import people
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.models_base import utcnow
from app.core.notion_blocks import rendered_to_markdown
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.reports.service import STATUS_CANCELLED, STATUS_DONE, _load_name_map
from app.tickets import attachments as ticket_attachments
from app.tickets import comments
from app.tickets.repository import TicketDraft, TicketDTO, snapshot
from app.trash import repository as trash_repo
from app.trash import service as trash_service
from app.trash.models import TRASH_TICKET
from app.core.authz import MODERATOR_ROLES
from app.users.models import User

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


# ── 조회 ──────────────────────────────────────────────────────────────────────

def list_my_tickets(db: Session, outbound, settings, user: User, *, repo=None) -> dict:
    """로그인 사용자가 담당한 티켓 전부(마감 무관). 매핑이 없으면 {mapped: False}."""
    nid = my_notion_id(db, user)
    if not nid:
        return {"mapped": False, "tickets": []}
    result = _repo(settings, outbound, repo).list_by_assignee(db, assignee_id=nid)
    return {"mapped": True, "tickets": _drop_trashed(db, ticket_views(db, result.tickets))}


def list_unassigned_tickets(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None
) -> list[dict]:
    """담당자가 없는 티켓. 기본은 활성(완료·취소 제외)만 — 아직 사람이 필요한 일.
    담당자가 없으므로 이름 해석은 건너뛰고 프로젝트 이름만 붙는다(기존 동작과 동일)."""
    result = _repo(settings, outbound, repo).list_unassigned(db)
    tickets = result.tickets
    if active_only:
        tickets = tuple(t for t in tickets if (t.status or "") not in _TERMINAL)
    return _drop_trashed(db, ticket_views(db, tickets, with_names=False))


def list_team_tickets(
    db: Session, outbound, settings, *, active_only: bool = True, repo=None
) -> list[dict]:
    """팀 전체 티켓(다른 사람 것 포함) — 조회 전용 팀 보드용. 기본은 활성(완료·취소 제외).
    담당자 이름을 붙여 담당자별로 볼 수 있게 하고, 휴지통에 넣은 티켓은 숨긴다."""
    result = _repo(settings, outbound, repo).list_all(db)
    tickets = result.tickets
    if active_only:
        tickets = tuple(t for t in tickets if (t.status or "") not in _TERMINAL)
    return _drop_trashed(db, ticket_views(db, tickets))


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


def list_assignees(db: Session) -> list[dict]:
    """담당자로 배정 가능한 사람 목록 — active + verified 매핑 사용자.

    raw notion_user_id 는 응답에 넣지 않는다(브라우저 미노출, 스펙 §12.3). 편집 API 가 user_id 를
    받아 서버에서 소스 id 로 해석한다.

    **부서·직책·조직을 함께 싣는다**(사용자 지시 2026-08-04). 예전에는 {user_id, display_name}
    뿐이라 '김하나'가 둘이면 담당자 선택 목록에 같은 줄이 두 번 떴고, 어느 쪽이 내가 찾는
    사람인지 알 방법이 화면에 없었다. 신원 조각은 app/core/people.py 가 만든다.

    행 대신 User 객체를 부르는 이유: `department`/`title` 은 관계에서 이름을 꺼내는
    프로퍼티라 컬럼 select 로는 안 나온다. 관계가 lazy="joined" 라 질의 수는 그대로다.
    """
    users = db.execute(
        select(User)
        .join(UserNotionMapping, UserNotionMapping.user_id == User.id)
        .where(
            User.active.is_(True),
            User.archived_at.is_(None),
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
        )
        .order_by(User.display_name)
    ).scalars().all()
    org_names = people.org_name_map(db)
    return [people.identity(u, org_names) for u in users]


# ── 휴지통 ────────────────────────────────────────────────────────────────────

def trash_ticket(db: Session, outbound, settings, user: User, *, page_id: str, now, repo=None) -> dict:
    """티켓을 휴지통으로 보낸다(노션은 손대지 않음). 편집 권한이 있어야 한다(담당자/미할당/운영자군).
    보관기간이 지나면 백그라운드가 노션 원본을 보관처리한다. 복원 가능."""
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
    """티켓 여러 건을 휴지통으로 보낸다. 건별로 권한을 검사하고, 실패(권한 없음·이미 휴지통·없음)는
    건너뛰고 나머지는 계속한다(부분 성공). {trashed:[...], failed:[{id,error}]}."""
    from app.core.errors import AppError

    r = _repo(settings, outbound, repo)
    nid = my_notion_id(db, user)
    trashed: list[dict] = []
    failed: list[dict] = []
    for pid in page_ids:
        try:
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

    updated = r.update(db, page_id=page_id, changes=repo_changes, now=now or utcnow())
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
) -> dict:
    """현재 담당자를 읽고 `wanted` 로 맞춘다. 이미 같으면 소스를 부르지 않는다."""
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
    updated = r.update(
        db, page_id=page_id,
        changes={"assignee_notion_ids": people},
        now=now or utcnow(),
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
) -> dict:
    """담당자 한 명을 다른 사람으로 바꾼다 — **나머지 담당자는 그대로 둔다**.

    공동 담당 티켓에서 퇴사자만 빼고 후임을 넣는 것이 목적이라, 담당자 목록을 통째로
    덮어쓰지 않는다(덮어쓰면 같이 일하던 사람이 조용히 빠진다).
    `to_user_id` 가 None 이면 후임 없이 빼기만 한다(미할당 트리아지로 보낸다).
    """
    r = _repo(settings, outbound, repo)
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
    updated = r.update(
        db, page_id=page_id, changes={"assignee_notion_ids": people}, now=now or utcnow()
    )
    return {
        "changed": True,
        "before_user_ids": before,
        "after_user_ids": resolve_assignee_user_ids(db, updated.assignee_ids),
        "ticket": ticket_views(db, [updated])[0],
    }


def set_ticket_assignees(
    db: Session, outbound, settings, user: User, *, page_id: str,
    user_ids: list[str], now: datetime | None = None, repo=None,
) -> dict:
    """담당자를 주어진 목록 **그대로** 맞춘다(되돌리기용).

    되돌리기는 '옮기기 직전 구성으로 복원'이므로 차집합이 아니라 전체 지정이어야 한다 —
    그 사이 제3자가 담당자를 더했다면 그 변경도 함께 되돌아간다. 그것이 '되돌리기'의 뜻이고,
    무엇이 바뀌었는지는 응답의 before/after 로 그대로 드러난다.
    """
    r = _repo(settings, outbound, repo)
    return _apply_assignees(db, r, user, page_id=page_id, wanted=list(user_ids), now=now)


def claim_ticket(
    db: Session, outbound, settings, user: User, *, page_id: str,
    now: datetime | None = None, repo=None,
) -> dict:
    """미할당(또는 본인 담당) 티켓의 담당자에 '나'를 배정한다. 내 계정이 Notion 미연결이면 거절."""
    if not my_notion_id(db, user):
        raise ValidationAppError("내 계정이 Notion 사용자와 연결되어 있지 않아 담당자로 배정할 수 없습니다.")
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
    created = _repo(settings, outbound, repo).create(db, draft=draft, now=now or utcnow())
    return {"ticket": ticket_views(db, [created])[0], "after": snapshot(created)}


# ── 본문 편집 ─────────────────────────────────────────────────────────────────

def save_ticket_body(
    db: Session, outbound, settings, user: User, *, page_id: str, body_markdown: str,
    now: datetime | None = None, repo=None,
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
    current = r.get_live(db, page_id=page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))
    result = r.save_body(
        db, page_id=page_id, body_markdown=body_markdown, now=now or utcnow()
    )
    return {
        "body_markdown": result.body_markdown,
        "synced": result.synced,
        "body_sync_error": result.sync_error,
    }


# ── 댓글 ──────────────────────────────────────────────────────────────────────
#
# URL 은 page_id(딥링크 키)로 받고, 저장은 자체 UUID(ticket_cache.id)로 한다 — 그 해석만
# 저장소 seam 을 지난다. 응답은 늘 **목록 전체**다: 삭제·수정 뒤에 클라이언트가 자기 목록을
# 직접 기워 맞추면 툼스톤 규약이 두 곳(서버·클라)에 생겨 언젠가 갈라진다.

def list_ticket_comments(
    db: Session, outbound, settings, user: User, *, page_id: str, repo=None
) -> dict:
    uid = _repo(settings, outbound, repo).local_uid(db, page_id=page_id)
    return {"comments": comments.list_comments(db, ticket_uid=uid, me=user)}


def add_ticket_comment(
    db: Session, outbound, settings, user: User, *, page_id: str, body: str,
    now: datetime | None = None, repo=None,
) -> dict:
    stamp = now or utcnow()
    uid = _repo(settings, outbound, repo).ensure_local(db, page_id=page_id, now=stamp)
    created = comments.create_comment(
        db, ticket_uid=uid, author=user, body=body, now=stamp
    )
    return {
        "comment_id": created.id,
        "comments": comments.list_comments(db, ticket_uid=uid, me=user),
    }


def edit_ticket_comment(
    db: Session, user: User, *, comment_id: str, body: str, now: datetime | None = None
) -> dict:
    comment = comments.get_or_404(db, comment_id)
    comments.ensure_can_edit(comment, user)
    comments.update_comment(db, comment, body=body, now=now or utcnow())
    return {"comments": comments.list_comments(db, ticket_uid=comment.ticket_uid, me=user)}


def delete_ticket_comment(
    db: Session, user: User, *, comment_id: str, now: datetime | None = None
) -> dict:
    comment = comments.get_or_404(db, comment_id)
    comments.ensure_can_delete(comment, user)
    comments.soft_delete_comment(db, comment, now=now or utcnow())
    return {"comments": comments.list_comments(db, ticket_uid=comment.ticket_uid, me=user)}


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
    current = r.get_live(db, page_id=page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))
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
        ensure_can_edit(r.get_live(db, page_id=page_id), user, my_notion_id(db, user))
    ticket_attachments.remove_attachment(db, att)
    return {"attachments": ticket_attachments.attachment_views(db, ticket_uid=uid)}


def _page_id_for_uid(db: Session, ticket_uid: str) -> str | None:
    """자체 UUID → Notion page id. source='native' 티켓은 page id 가 없어 None 이다."""
    from app.tickets.models import TicketCache

    row = db.get(TicketCache, ticket_uid)
    return row.notion_page_id if row is not None else None
