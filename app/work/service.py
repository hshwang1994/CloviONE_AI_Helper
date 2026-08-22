"""Board · Backlog · Sprint — 그리고 **Drop 한 번이 하나의 트랜잭션**이라는 규칙.

## Drop 이 하는 일 다섯

칸반에서 카드를 옮기면 다섯 가지가 함께 일어나야 한다.

| | 왜 |
|---|---|
| Status 변경 | 사용자가 실제로 요청한 것 |
| Activity | "언제 누가 이걸 진행으로 옮겼나" 에 답한다 |
| Audit | 운영·보안이 보는 기록. Activity 와 다른 질문이다 |
| `updated_at` | 목록 정렬과 신선도 |
| Notification | 관찰자와 담당자가 안다 |

**하나라도 따로 커밋되면 어긋난다.** 상태만 바뀌고 활동이 안 남으면 사람이 "내가 안
옮겼는데" 를 증명할 방법이 없고, 알림만 가고 상태가 롤백되면 없는 변화를 통보한 것이
된다. 그래서 다섯을 한 요청 트랜잭션에 둔다 — `get_db` 가 마지막에 한 번 커밋한다.

## 상태는 왜 저장소 seam 을 지나는가

지금 티켓의 정본은 아직 외부 소스다(S14 가 걷어 낸다). 여기서 로컬 컬럼만 고치면
다음 동기화 회차가 **조용히 되돌린다** — 사용자는 옮겼다고 믿고, 다음 날 원래 열에
가 있는 카드를 본다. 그래서 상태 변경만은 `app/tickets/service.py::update_ticket` 을
지난다(범위·편집 권한·소스 반영이 전부 거기 한 곳이다).

반대로 스프린트·순서·활동·잠금은 **Portal 이 소유하는 축**이라 소스에 보내지 않는다.
동기화가 그 컬럼을 안 건드리는 것은 `document_cache.owner_kind` 와 같은 배치다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.visibility import (
    RESOURCE_PROJECT,
    context_for_user,
    effective_visibility_clause,
)
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.models_base import utcnow
from app.projects.models import Project
from app.tickets.models import Ticket
from app.trash import repository as trash_repo
from app.trash.models import TRASH_TICKET
from app.users.models import User
from app.work import activity, numbering, rank as rank_mod, relations, workflow
from app.work.models import (
    ACT_RANK,
    ACT_SPRINT,
    ACT_STATUS,
    SPRINT_ACTIVE,
    SPRINT_CLOSED,
    SPRINT_PLANNED,
    SPRINT_STATES,
    Sprint,
    TicketStatus,
    TicketWatcher,
)
from app.work.resolve import display_key

logger = logging.getLogger(__name__)

# 한 열에 싣는 카드 수. 칸반은 스크롤 목록이 아니라 한눈에 보는 판이라, 이 수를 넘으면
# 필터를 좁히라고 말하는 편이 정직하다 — 800장을 그려 놓고 브라우저를 세우지 않는다.
BOARD_COLUMN_LIMIT = 200


def number_if_possible(db: Session, ticket: Ticket, *, now: datetime | None = None) -> bool:
    """번호가 없고 프로젝트에 Key 가 있으면 번호를 준다. 아니면 아무것도 안 한다.

    **조용히 실패하는 것이 여기서는 옳다.** Project Key 20건은 아직 사용자 확인 전이고
    (D-197), 확정 전에는 프로젝트 대부분이 Key 를 갖지 않는다. 그때 티켓 생성을 막으면
    Key 확정이 끝날 때까지 제품이 멈춘다. 번호 없는 티켓은 옛 이름(`GIT-n`)으로 계속
    불린다 — 그것이 3층 식별자를 두는 이유다.
    """
    if ticket.seq is not None or not ticket.project_uid:
        return False
    project = db.get(Project, ticket.project_uid)
    if project is None or not project.code:
        return False
    ticket.seq = numbering.allocate(db, ticket.project_uid)
    db.flush()
    db.refresh(ticket)
    activity.record(
        db, ticket_id=ticket.id, kind=activity.ACT_FIELD, field="canonical_key",
        from_value=None, to_value=ticket.canonical_key, now=now or utcnow(),
    )
    return True


# ── 범위 ─────────────────────────────────────────────────────────────────────


def _visible_tickets_stmt(db: Session, user: User):
    """이 사람에게 보이는 티켓. **프로젝트 축 하나로만 판정한다** (D-194).

    티켓은 `app/authz/visibility.py` 의 자원 종류가 아니다 — 소속 프로젝트가 보이면
    보인다. 그래서 여기서 새 규칙을 만들지 않고 프로젝트 절을 그대로 접는다.

    프로젝트가 없는 티켓(Migration Exception)은 전역이 아닌 사람에게 **안 보인다**.
    `IN (…)` 이 NULL 을 고르지 못하기 때문이고, 그것이 D-197 이 말한 의도된 fail-closed 다.
    """
    ctx = context_for_user(db, user)
    stmt = select(Ticket)
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    if clause is None:
        return stmt
    return stmt.where(
        Ticket.project_uid.in_(select(Project.id).where(clause))
    )


def get_scoped_project_or_404(db: Session, project_id: str, user: User) -> Project:
    """프로젝트 하나 — **판·백로그와 같은 판정**을 지난다.

    `app/projects/service.py` 에도 같은 이름의 게이트가 있지만 그쪽은 `Principal` 을
    받는다. 여기서 그 함수를 부르려면 라우트마다 `Principal` 을 함께 만들어야 하고,
    그러면 게이트를 지나는 경로와 안 지나는 경로가 생긴다 — 판정 자체는 양쪽 다
    `effective_visibility_clause` 하나이므로(D-194) 갈라질 자리는 없다.
    """
    ctx = context_for_user(db, user)
    stmt = select(Project).where(Project.id == project_id)
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    if clause is not None:
        stmt = stmt.where(clause)
    project = db.execute(stmt).scalar_one_or_none()
    if project is None:
        raise NotFoundError("프로젝트를 찾을 수 없습니다.")
    return project


def _drop_trashed(db: Session, tickets: list[Ticket]) -> list[Ticket]:
    """휴지통 티켓은 판에서도 없는 것이다 (H2). 목록만 닫고 판을 열어 두면 의미가 없다."""
    trashed = trash_repo.trashed_page_ids(db, TRASH_TICKET)
    if not trashed:
        return tickets
    return [t for t in tickets if t.notion_page_id not in trashed]


def _card(ticket: Ticket) -> dict:
    """판에 그리는 카드 한 장. 목록 API 와 **다른 모양**인 이유는 목적이 다르기 때문이다.

    목록은 표라서 열이 많고, 판은 카드라서 한 장에 다섯 줄이 최대다. 같은 dict 를
    쓰면 판이 안 쓰는 필드까지 매번 실려 나간다.
    """
    return {
        "id": ticket.id,
        "page_id": ticket.notion_page_id,
        "key": display_key(ticket),
        "title": ticket.title,
        "status": ticket.status,
        "category": workflow.category_of(ticket.status),
        "priority": ticket.priority,
        "due": ticket.due_date,
        "est_wd": ticket.est_wd,
        "sprint_id": ticket.sprint_id,
        "rank": str(ticket.backlog_rank) if ticket.backlog_rank is not None else None,
        "version": ticket.version,
    }


def board(
    db: Session, user: User, *, project_id: str | None = None, sprint_id: str | None = None
) -> dict:
    """칸반 한 판. 열은 상태 어휘가 정하고 순서도 거기서 온다.

    모르는 상태(어휘에 없는 값)는 **버리지 않고 따로 모은다.** 버리면 그 티켓이 어느
    화면에도 안 나타나고, 안 나타나는 티켓은 아무도 못 고친다.
    """
    stmt = _visible_tickets_stmt(db, user)
    if project_id:
        stmt = stmt.where(Ticket.project_uid == project_id)
    if sprint_id:
        stmt = stmt.where(Ticket.sprint_id == sprint_id)
    stmt = stmt.where(Ticket.notion_missing_at.is_(None)).order_by(
        Ticket.backlog_rank.nulls_last(), Ticket.created_at
    )
    tickets = _drop_trashed(db, list(db.execute(stmt).scalars().all()))

    # 열은 **표에서 읽는다**(`ticket_statuses`). 어휘의 정본은 코드이고
    # (`app/work/workflow.py::STATUSES`) 이 표는 그 결과지만, 런타임이 읽는 것은 표다 —
    # S5 의 `effective_permissions` 가 `permissions` 표를 읽는 것과 같은 배치이고,
    # 둘이 갈라지지 않는 것은 `tests/unit/test_work_domain_seed.py` 가 맞물려 둔다.
    #
    # 코드 목록을 그대로 쓰면 이 표에 소비자가 없어진다 — 아무도 안 읽는 표는 시드가
    # 틀려도 아무 일이 안 일어나고, 그러면 시드를 맞물어 두는 시험도 헛돈다.
    status_rows = db.execute(
        select(TicketStatus).order_by(TicketStatus.sort_order, TicketStatus.key)
    ).scalars().all()

    by_status: dict[str, list[dict]] = {row.key: [] for row in status_rows}
    unknown: list[dict] = []
    for ticket in tickets:
        card = _card(ticket)
        bucket = by_status.get(ticket.status or "")
        (unknown if bucket is None else bucket).append(card)

    columns = [
        {
            "key": row.key,
            "label": row.label,
            "category": row.category,
            "total": len(by_status[row.key]),
            "cards": by_status[row.key][:BOARD_COLUMN_LIMIT],
        }
        for row in status_rows
    ]
    return {
        "columns": columns,
        "column_limit": BOARD_COLUMN_LIMIT,
        # 어휘 밖 상태. 비어 있으면 화면이 이 칸을 그리지 않는다.
        "unclassified": unknown[:BOARD_COLUMN_LIMIT],
        "unclassified_total": len(unknown),
    }


def backlog(db: Session, user: User, *, project_id: str | None = None) -> dict:
    """백로그 — **순서가 전부인 목록**.

    끝난 것은 안 싣는다. 백로그는 "다음에 무엇을 하는가" 라서 완료·취소가 섞이면
    스크롤 대부분이 지나간 일이 된다.
    """
    stmt = _visible_tickets_stmt(db, user)
    if project_id:
        stmt = stmt.where(Ticket.project_uid == project_id)
    stmt = stmt.where(Ticket.notion_missing_at.is_(None)).order_by(
        Ticket.backlog_rank.nulls_last(), Ticket.created_at
    )
    tickets = [
        t for t in _drop_trashed(db, list(db.execute(stmt).scalars().all()))
        if not workflow.is_terminal(t.status)
    ]
    return {"items": [_card(t) for t in tickets], "total": len(tickets)}


# ── Drop ─────────────────────────────────────────────────────────────────────


def load_ticket_in_scope_or_404(db: Session, ticket_id: str, user: User) -> Ticket:
    """옮길 티켓 하나. 범위 밖이면 **404** — 있다는 사실도 알리지 않는다.

    조건을 **조회 자체에 붙인다.** `db.get(Ticket, id)` 로 꺼내 놓고 나중에 판정하면
    새로 생긴 경로가 그 판정을 빠뜨릴 자리가 생긴다 — 이 저장소가 네 번 반복한 실수의
    모양이다(`scripts/check_scope_gates.py` 서문).
    """
    stmt = _visible_tickets_stmt(db, user).where(Ticket.id == ticket_id)
    ticket = db.execute(stmt).scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("티켓을 찾을 수 없습니다.")
    if ticket.notion_page_id in trash_repo.trashed_page_ids(db, TRASH_TICKET):
        raise NotFoundError("티켓을 찾을 수 없습니다.")
    return ticket


def get_scoped_sprint_or_404(db: Session, sprint_id: str, user: User) -> Sprint:
    """스프린트 하나 — **목록과 같은 판정**을 지난다.

    목록만 좁히고 단건·쓰기를 열어 두면 목록을 좁힌 의미가 없다. 프로젝트 스프린트는
    그 프로젝트가 보이는 사람에게만 보이고, 팀 전체 스프린트(`project_id IS NULL`)는
    조직 안에서 열려 있다.
    """
    ctx = context_for_user(db, user)
    stmt = select(Sprint).where(Sprint.id == sprint_id)
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    if clause is not None:
        stmt = stmt.where(
            Sprint.project_id.is_(None)
            | Sprint.project_id.in_(select(Project.id).where(clause))
        )
    sprint = db.execute(stmt).scalar_one_or_none()
    if sprint is None:
        raise NotFoundError("스프린트를 찾을 수 없습니다.")
    return sprint


def _ensure_version(ticket: Ticket, base_version: int | None) -> None:
    """그 사이 누가 먼저 옮겼는가.

    `base_version` 이 없으면(구버전 클라이언트) 예전대로 동작한다 — 새 계약을 강제해
    기존 경로를 깨뜨리지 않는다(`_ensure_body_not_changed` 와 같은 규약).
    """
    if base_version is None:
        return
    if int(base_version) != int(ticket.version):
        raise ConflictError(
            "다른 사람이 먼저 이 티켓을 옮겼습니다. 새로고침한 뒤 다시 시도해 주세요."
        )


def _notify_move(
    db: Session, ticket: Ticket, *, actor: User, to_status: str, now: datetime
) -> None:
    """관찰자에게 알린다. **실패해도 이동은 남는다** — 배정 알림과 같은 규약."""
    try:
        from app.notifications.service import notify_user

        watchers = db.execute(
            select(TicketWatcher.user_id).where(TicketWatcher.ticket_id == ticket.id)
        ).scalars().all()
        label = display_key(ticket) or "티켓"
        for uid in {u for u in watchers if u and u != actor.id}:
            notify_user(
                db, uid, type_="ticket_status_changed",
                title=f"{label} 상태 변경: {to_status}",
                body=(ticket.title or "")[:200],
                related=("ticket", ticket.notion_page_id), now=now,
            )
    except Exception:  # noqa: BLE001 — 알림이 이동을 막으면 안 된다
        logger.exception("티켓 상태 알림에 실패했다 (ticket_id=%s)", ticket.id)


def move(
    db: Session,
    outbound,
    settings,
    user: User,
    *,
    ticket_id: str,
    to_status: str | None = None,
    sprint_id: str | None = None,
    set_sprint: bool = False,
    before_id: str | None = None,
    after_id: str | None = None,
    reorder: bool = False,
    base_version: int | None = None,
    now: datetime | None = None,
    repo=None,
    request=None,
) -> dict:
    """카드를 옮긴다 — **상태 · 활동 · 감사 · `updated_at` · 알림이 한 트랜잭션**이다.

    셋 다 선택이다: 상태만 바꿀 수도, 순서만 바꿀 수도, 스프린트만 옮길 수도 있다.
    아무것도 안 바뀌면 거절한다 — 빈 요청이 버전을 올리면 다른 사람의 편집이 헛
    충돌한다.
    """
    stamp = now or utcnow()
    ticket = load_ticket_in_scope_or_404(db, ticket_id, user)
    _ensure_version(ticket, base_version)

    if not (to_status or set_sprint or reorder):
        raise ValidationAppError("옮길 내용이 없습니다.")

    from_status = ticket.status
    if to_status:
        target = workflow.validate_transition(from_status, to_status)
        if target != from_status:
            # 소스까지 반영하는 유일한 경로. 범위·편집 권한 판정도 여기 한 곳이다.
            from app.tickets import service as tickets_service

            tickets_service.update_ticket(
                db, outbound, settings, user,
                page_id=ticket.notion_page_id, changes={"status": target},
                now=stamp, repo=repo,
            )
            db.refresh(ticket)
            activity.record(
                db, ticket_id=ticket.id, kind=ACT_STATUS, actor_id=user.id,
                field="status", from_value=from_status, to_value=target, now=stamp,
            )

    if set_sprint:
        before_sprint = ticket.sprint_id
        if sprint_id:
            sprint = db.get(Sprint, sprint_id)
            if sprint is None:
                raise NotFoundError("스프린트를 찾을 수 없습니다.")
            if sprint.project_id and sprint.project_id != ticket.project_uid:
                raise ValidationAppError("다른 프로젝트의 스프린트에는 넣을 수 없습니다.")
        ticket.sprint_id = sprint_id or None
        activity.record(
            db, ticket_id=ticket.id, kind=ACT_SPRINT, actor_id=user.id, field="sprint_id",
            from_value=before_sprint, to_value=ticket.sprint_id, now=stamp,
        )

    if reorder:
        before_rank = ticket.backlog_rank
        ticket.backlog_rank = rank_mod.place(
            db, project_id=ticket.project_uid, before_id=before_id, after_id=after_id
        )
        activity.record(
            db, ticket_id=ticket.id, kind=ACT_RANK, actor_id=user.id, field="backlog_rank",
            from_value=str(before_rank) if before_rank is not None else None,
            to_value=str(ticket.backlog_rank), now=stamp,
        )

    ticket.version = int(ticket.version) + 1
    ticket.updated_at = stamp
    db.flush()

    if request is not None:
        from app.core.audit import record_audit_from_request

        record_audit_from_request(
            request, db, action="ticket.board_move", object_type="ticket",
            object_id=ticket.id,
            before={"status": from_status, "version": int(ticket.version) - 1},
            after={
                "status": ticket.status, "sprint_id": ticket.sprint_id,
                "rank": str(ticket.backlog_rank) if ticket.backlog_rank is not None else None,
                "version": int(ticket.version),
            },
        )

    if to_status and to_status != from_status:
        _notify_move(db, ticket, actor=user, to_status=to_status, now=stamp)

    return {"ticket": _card(ticket)}


# ── Sprint ───────────────────────────────────────────────────────────────────


def _sprint_view(sprint: Sprint) -> dict:
    return {
        "id": sprint.id,
        "name": sprint.name,
        "project_id": sprint.project_id,
        "starts_on": sprint.starts_on,
        "ends_on": sprint.ends_on,
        "state": sprint.state,
        "goal": sprint.goal,
    }


def list_sprints(db: Session, user: User, *, project_id: str | None = None) -> list[dict]:
    """스프린트 목록. 프로젝트 스프린트는 그 프로젝트가 보이는 사람에게만 보인다."""
    ctx = context_for_user(db, user)
    stmt = select(Sprint)
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    if clause is not None:
        stmt = stmt.where(
            Sprint.project_id.is_(None)
            | Sprint.project_id.in_(select(Project.id).where(clause))
        )
    if project_id:
        stmt = stmt.where(Sprint.project_id == project_id)
    rows = db.execute(stmt.order_by(Sprint.starts_on.desc(), Sprint.name)).scalars().all()
    return [_sprint_view(s) for s in rows]


def create_sprint(
    db: Session,
    user: User,
    *,
    name: str,
    starts_on: str,
    ends_on: str,
    project_id: str | None = None,
    goal: str | None = None,
    now: datetime | None = None,
) -> dict:
    """스프린트 한 회차. 시작 상태는 `planned` 다 — **여는 것은 별도 동작**이다.

    만들자마자 열면 다음 회차를 미리 계획해 둘 수 없다. 「이번」이 무엇인지가 계획의
    핵심이라 그 전환을 사람이 눌러야 한다.
    """
    label = (name or "").strip()
    if not label:
        raise ValidationAppError("스프린트 이름을 입력해 주세요.")
    if not (starts_on and ends_on) or starts_on >= ends_on:
        raise ValidationAppError("스프린트 기간은 시작일이 종료일보다 앞이어야 합니다.")
    if project_id is not None:
        # 남의 팀 프로젝트에 회차를 만들 수 있으면, 그 팀의 백로그에 내 회차가 나타난다.
        get_scoped_project_or_404(db, project_id, user)

    row = Sprint(
        name=label, project_id=project_id, starts_on=starts_on, ends_on=ends_on,
        state=SPRINT_PLANNED, goal=(goal or None),
        created_at=now or utcnow(), updated_at=now or utcnow(),
    )
    db.add(row)
    db.flush()
    return _sprint_view(row)


def set_sprint_state(
    db: Session, user: User, *, sprint_id: str, state: str, now: datetime | None = None
) -> dict:
    """회차를 연다/닫는다. **한 프로젝트에 열린 회차는 하나**뿐이다.

    둘이면 「이번 스프린트」에 답이 둘이 되고 번다운이 두 개가 된다. 부분 유니크
    인덱스가 막지만, 여기서 먼저 읽을 수 있는 말로 거절한다 — 제약 이름만 보고
    무엇이 문제인지 아는 사람은 없다.
    """
    if state not in SPRINT_STATES:
        raise ValidationAppError(f"모르는 스프린트 상태입니다: {state}")
    sprint = get_scoped_sprint_or_404(db, sprint_id, user)
    if state == SPRINT_ACTIVE and sprint.state != SPRINT_ACTIVE:
        conflict = db.execute(
            select(Sprint).where(
                Sprint.state == SPRINT_ACTIVE,
                Sprint.org_id == sprint.org_id,
                (
                    Sprint.project_id == sprint.project_id
                    if sprint.project_id is not None
                    else Sprint.project_id.is_(None)
                ),
            )
        ).scalars().first()
        if conflict is not None:
            raise ConflictError(
                f"이미 «{conflict.name}» 회차가 열려 있습니다. 먼저 닫아 주세요."
            )
    sprint.state = state
    sprint.updated_at = now or utcnow()
    db.flush()
    return _sprint_view(sprint)


def sprint_scope(db: Session, sprint_id: str, user: User) -> dict:
    """이 회차에 담긴 일의 크기. 번다운의 입력이다.

    난이도·예상WD·실제WD 를 유지한 이유가 여기 있다(§5.2) — 버리면 이 계산이 죽는다.

    **집계도 범위를 지난다.** 숫자만 돌려주니 안전해 보이지만, 남의 팀 회차의 티켓 수와
    공수를 읽을 수 있으면 그것으로 그 팀의 상태를 읽는다.
    """
    get_scoped_sprint_or_404(db, sprint_id, user)
    tickets = db.execute(
        select(Ticket).where(Ticket.sprint_id == sprint_id)
    ).scalars().all()
    planned = sum(float(t.est_wd or 0) for t in tickets)
    done = sum(
        float(t.est_wd or 0) for t in tickets if workflow.category_of(t.status) == "DONE"
    )
    return {
        "sprint_id": sprint_id,
        "tickets": len(tickets),
        "planned_wd": round(planned, 2),
        "done_wd": round(done, 2),
        "remaining_wd": round(planned - done, 2),
    }


# ── 관계 · 관찰자 ────────────────────────────────────────────────────────────


def ticket_detail_extras(db: Session, ticket: Ticket) -> dict:
    """상세 화면이 새로 얻는 것 — 이름 세 층 · 관계 · 활동."""
    return {
        "key": display_key(ticket),
        "canonical_key": ticket.canonical_key,
        "legacy_key": ticket.legacy_key,
        "version": ticket.version,
        "sprint_id": ticket.sprint_id,
        "relations": relations.for_ticket(db, ticket.id),
        "activities": activity.timeline(db, ticket.id),
    }


def watch(
    db: Session, *, ticket_id: str, user_id: str, watching: bool,
    now: datetime | None = None,
) -> bool:
    """관찰자를 켜고 끈다. 이미 그 상태면 아무것도 안 한다(재실행 안전)."""
    existing = db.get(TicketWatcher, {"ticket_id": ticket_id, "user_id": user_id})
    if watching and existing is None:
        db.add(
            TicketWatcher(
                ticket_id=ticket_id, user_id=user_id, created_at=now or utcnow()
            )
        )
        db.flush()
        return True
    if not watching and existing is not None:
        db.delete(existing)
        db.flush()
        return True
    return False


def close_sprint_and_carry_over(
    db: Session, user: User, *, sprint_id: str, target_sprint_id: str | None,
    now: datetime | None = None,
) -> dict:
    """회차를 닫고 **안 끝난 일을 다음 회차로 옮긴다.**

    안 옮기면 그 티켓들은 어느 회차에도 없는 상태가 되고, 다음 계획 회의에서 목록을
    손으로 다시 만들게 된다 — 그러면 몇 건은 반드시 빠진다.
    """
    sprint = get_scoped_sprint_or_404(db, sprint_id, user)
    if target_sprint_id is not None:
        # 옮길 곳도 범위 안이어야 한다. 한쪽만 보면 안 끝난 일을 남의 팀 회차로 밀어
        # 넣을 수 있고, 그 순간 그 티켓들은 **내 범위에서 사라진다**.
        get_scoped_sprint_or_404(db, target_sprint_id, user)

    stamp = now or utcnow()
    carried = 0
    for ticket in db.execute(
        select(Ticket).where(Ticket.sprint_id == sprint_id)
    ).scalars().all():
        if workflow.is_terminal(ticket.status):
            continue
        before = ticket.sprint_id
        ticket.sprint_id = target_sprint_id
        activity.record(
            db, ticket_id=ticket.id, kind=ACT_SPRINT, field="sprint_id",
            from_value=before, to_value=target_sprint_id, now=stamp,
        )
        carried += 1
    sprint.state = SPRINT_CLOSED
    sprint.updated_at = stamp
    db.flush()
    return {"sprint_id": sprint_id, "carried_over": carried}


def rank_of(value: Decimal | None) -> str | None:
    """소수 순위를 문자열로. JSON 이 float 로 바꾸면 자리수를 잃는다."""
    return str(value) if value is not None else None
