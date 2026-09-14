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

import base64
import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.authz.permissions import PROJECT_WRITE
from app.authz.service import has_permission
from app.authz.visibility import (
    RESOURCE_PROJECT,
    context_for_user,
    effective_visibility_clause,
)
from app.core.dates import iso_date, parse_date
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.models_base import NAMES_SEP, split_names, utcnow
from app.core.org_tree import DeptTree
from app.core.scope import MATCH_NOTHING, principal_from_user
from app.org import context as org_context
from app.projects.models import Project
from app.tickets.models import Ticket, api_page_id, api_page_id_expr
from app.trash import repository as trash_repo
from app.trash.models import TRASH_TICKET, TrashItem
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

# 한 쪽 기본 카드 수(§8.5 재검수). 예전 `BOARD_COLUMN_LIMIT` 는 "이 이상은 없다"는 상한—
# 열이 200장을 넘으면 201번째부터는 화면도 서버도 아예 안 낸다(D3). 지금은 "이 이상은
# 다음 쪽에 있다"로 바뀐다 — 커서를 따라가면 열 전체를 받는다. `MAX_COLUMN_PAGE_SIZE` 는
# 한 요청이 한 번에 실어 나르는 카드 수의 그릇 크기일 뿐, 열 전체 조회 상한이 아니다.
DEFAULT_COLUMN_PAGE_SIZE = 50
MAX_COLUMN_PAGE_SIZE = 200

# 어휘 밖 상태를 모으는 칸의 열쇠. 프런트(`screens/WorkBoard.jsx::UNCLASSIFIED`)와
# 글자까지 같아야 한다 — 다르면 "더 보기"가 엉뚱한 열을 요청한다.
UNCLASSIFIED_KEY = "__unclassified__"

# ── 범위(scope) 계약 (§8.1) ──────────────────────────────────────────────────
SCOPE_SPRINT = "sprint"
SCOPE_EXECUTION = "execution"
SCOPE_ALL = "all"
BOARD_SCOPES: tuple[str, ...] = (SCOPE_SPRINT, SCOPE_EXECUTION, SCOPE_ALL)


def resolve_board_scope(scope: str | None, sprint_id: str | None) -> str:
    """어느 범위로 보는가. **모르는 값은 예외**다 — 조용히 기본값으로 떨어지면 화면은
    좁혔다고 믿는데 서버는 전체(또는 반대로 실행분만)를 준 것이 된다.

      sprint     회차가 담긴 티켓만. `sprint_id` 가 있어야 한다
      execution  회차 미선택. 종료 상태(완료·취소, `workflow.TERMINAL_CATEGORIES`)를 뺀다
      all        완료·취소를 포함한 전부. 명시할 때만

    `scope` 를 안 주면 `sprint_id` 유무로 고른다 — 화면이 회차를 이미 골랐다면 그
    맥락에서는 "실행분만"이라는 개념 자체가 없다(회차 안에 완료된 일도 회의의 자료다).
    """
    resolved = scope or (SCOPE_SPRINT if sprint_id else SCOPE_EXECUTION)
    if resolved not in BOARD_SCOPES:
        raise ValidationAppError(f"모르는 scope 입니다: {resolved}")
    if resolved == SCOPE_SPRINT and not sprint_id:
        raise ValidationAppError("scope=sprint 에는 sprint_id 가 필요합니다.")
    return resolved


def _not_trashed_ticket_clause():
    """이 티켓이 휴지통에 없다 — **SQL 절**로 (§8.5).

    예전엔(`_drop_trashed`) 전량을 파이썬으로 끌어와 `trashed_page_ids()` 집합과
    대조했다. 쪽 단위로 받는 목록에서 그렇게 하면 이번 쪽에서 휴지통이라 걸러진 건수만큼
    `total`(SQL COUNT)과 실제로 받은 카드 수가 어긋난다 — 커서를 끝까지 따라가도 받은
    수가 `total` 에 못 미친다. `TrashItem` 은 API 가 부르는 이름(`api_page_id_expr`)으로
    조회 가능한 표라 여기서 NOT EXISTS 로 만든다 — 파이썬 집합을 다시 만들 필요가 없다.
    """
    return ~(
        select(TrashItem.id)
        .where(
            TrashItem.item_type == TRASH_TICKET,
            TrashItem.notion_page_id == api_page_id_expr(),
        )
        .correlate(Ticket)
        .exists()
    )


def _assignee_sql_clause(assignee_token: str | None):
    """담당자 한 명 — **SQL 절**로. `assignee_notion_ids` 는 앞뒤로 구분자(`NAMES_SEP`)를
    두른 문자열이다(`join_names`) — 그래서 짧은 토큰이 더 긴 토큰 안에 우연히 끼어드는
    부분 일치 오탐이 없다. `%`·`_`·`\\` 는 LIKE 메타문자라 이스케이프한다."""
    if not assignee_token:
        return None
    escaped = (
        assignee_token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return Ticket.assignee_notion_ids.like(
        f"%{NAMES_SEP}{escaped}{NAMES_SEP}%", escape="\\"
    )


def _ilike_escape(text: str) -> str:
    """검색어를 LIKE 패턴 자리에 안전하게 넣는다. 사용자가 적은 글자라 `%`·`_` 가
    실제로 들어올 수 있다(담당자 토큰과 달리 이건 **사람이 타이핑한 값**이다)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _team_projects_clause(team_id: str):
    """이 팀의 일 — **프로젝트의 `dept_id` 가 정확히 그 팀**인 티켓 (D-482).

    티켓에는 부서 칸이 없고 티켓의 팀은 `project.dept_id` 한 단계다. 하위 팀·상위 본부·
    조직 공통 프로젝트의 티켓은 이 팀의 일이 아니다 — 회차에 담을 수 있는 자격
    (`ensure_eligible`)과 같은 정의라, 백로그에 보이는 티켓은 전부 담을 수 있고 담을 수
    없는 티켓은 백로그에 안 보인다.
    """
    return Ticket.project_uid.in_(select(Project.id).where(Project.dept_id == team_id))


def _board_scope_stmt(
    db: Session,
    user: User,
    *,
    project_id: str | None,
    sprint_id: str | None,
    scope: str,
    assignee_token: str | None = None,
    blocked_only: bool = False,
    team_id: str | None = None,
    q: str | None = None,
    priority: str | None = None,
    difficulty: str | None = None,
    signal: str | None = None,
    today: date | None = None,
):
    """판·백로그가 공유하는 **한 조건**(§8.5). 첫 쪽과 다음 쪽이 같은 조건을 본다 —
    안 그러면 이번 쪽에서 본 카드가 다음 쪽에서 다른 조건에 걸려 새거나 겹친다.

    범위(가시성) 절이 **무엇보다도 먼저** 걸린다(D-202). 커서·상한은 이 위에 얹힐 뿐,
    이 절을 지나지 않은 행은 어느 쪽에도 새어 나오지 않는다.

    회차를 골랐으면 그 회차에 담긴 티켓이 판이다(회차 게이트는 `board()` 가 먼저 지난다).
    회차 없이 팀만 골랐으면 그 팀의 실행분 — 팀 절은 백로그와 같은 정의다.
    """
    stmt = _visible_tickets_stmt(db, user)
    if project_id:
        stmt = stmt.where(Ticket.project_uid == project_id)
    if sprint_id:
        stmt = stmt.where(Ticket.sprint_id == sprint_id)
    elif team_id:
        stmt = stmt.where(_team_projects_clause(team_id))
    stmt = stmt.where(
        Ticket.notion_missing_at.is_(None),
        _not_trashed_ticket_clause(),
    )
    if scope == SCOPE_EXECUTION:
        cat = workflow.category_sql(Ticket.status)
        # 어휘 밖 상태(`category` 가 `None`)는 실행분에 남는다 — 종료라고 알려진 것만 뺀다.
        stmt = stmt.where(cat.is_(None) | cat.notin_(workflow.TERMINAL_CATEGORIES))
    assignee_clause = _assignee_sql_clause(assignee_token)
    if assignee_clause is not None:
        stmt = stmt.where(assignee_clause)
    return _apply_shared_filters(
        stmt, q=q, priority=priority, difficulty=difficulty,
        signal=signal, blocked_only=blocked_only, today=today,
    )


def _encode_rank_cursor(rank: Decimal | None, row_id: str) -> str:
    """열/백로그 한 쪽의 마지막 행 — **불투명 문자열**로. 화면은 내용을 몰라도 된다."""
    payload = f"{'' if rank is None else str(rank)}|{row_id}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_rank_cursor(cursor: str) -> tuple[Decimal | None, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        rank_part, row_id = raw.split("|", 1)
        return (Decimal(rank_part) if rank_part else None, row_id)
    except Exception as exc:  # noqa: BLE001 — 형식이 뭐든 "잘못된 커서"로 뭉친다
        raise ValidationAppError("잘못된 커서입니다.") from exc


def _rank_keyset_page(
    db: Session, stmt, rank_col, *, cursor: str | None, limit: int
) -> tuple[list[Ticket], str | None]:
    """`rank_col` NULLS LAST, `Ticket.id` 순으로 커서 다음 `limit` 건 + 「더 있다」.

    `offset` 대신 keyset 을 쓴다(D-202 옆 §8.5) — 순위가 바뀔 수 있는 목록에서 `offset`
    은 그 사이 옮겨진 카드를 건너뛰거나 두 번 돌려주는데, 그 어긋남은 오류를 안 낸다.
    `limit`+1 을 직접 받아 다음 쪽 유무를 본다 — 별도 COUNT 와 비교하면 그 사이 자료가
    바뀌었을 때 어긋날 수 있다.
    """
    q = stmt.order_by(rank_col.nulls_last(), Ticket.id.asc())
    if cursor:
        last_rank, last_id = _decode_rank_cursor(cursor)
        if last_rank is not None:
            q = q.where(
                (rank_col > last_rank)
                | ((rank_col == last_rank) & (Ticket.id > last_id))
                | rank_col.is_(None)
            )
        else:
            q = q.where(rank_col.is_(None), Ticket.id > last_id)
    rows = list(db.execute(q.limit(limit + 1)).scalars().all())
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_rank_cursor(getattr(page[-1], rank_col.key), page[-1].id) if has_more and page else None
    return page, next_cursor


def number_if_possible(db: Session, ticket: Ticket, *, now: datetime | None = None) -> bool:
    """번호가 없고 프로젝트에 코드가 있으면 번호를 준다. 아니면 아무것도 안 한다.

    **조용히 실패하는 것이 여기서는 옳다.** 코드는 이제 프로젝트를 만들 때 서버가 함께
    붙이므로(D-282) 코드 없는 프로젝트는 사실상 이관 중간 상태 하나뿐이다. 그래도
    막지 않는 이유는 같다: 여기서 예외를 던지면 그 한 상태 때문에 티켓 생성이 통째로
    멈춘다. 번호 없는 티켓은 화면에서 **제목으로** 불린다
    (`app/work/resolve.py::display_key` 가 `None` 을 돌려주는 그 상태다).
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


def _visible_tickets_stmt(db: Session, user: User, *, scope=None):
    """이 사람에게 보이는 티켓. **프로젝트 축 하나로만 판정한다** (D-194).

    티켓은 `app/authz/visibility.py` 의 자원 종류가 아니다 — 소속 프로젝트가 보이면
    보인다. 그래서 여기서 새 규칙을 만들지 않고 프로젝트 절을 그대로 접는다.

    프로젝트가 없는 티켓(Migration Exception)은 전역이 아닌 사람에게 **안 보인다**.
    `IN (…)` 이 NULL 을 고르지 못하기 때문이고, 그것이 D-197 이 말한 의도된 fail-closed 다.

    `scope` 는 **좁히기만 한다**. 부서(팀) 필터가 고른 범위를 여기로 넘긴다 — 티켓에는
    부서 칸이 없고(`app/tickets/models.py` 가 그 칸을 일부러 없앴다) 티켓의 팀은
    `project.dept_id` 한 단계이므로, 판정 함수를 새로 만들지 않고 같은 프로젝트 절에
    좁힌 Scope 를 넣는다. 넓히지는 못한다 — 부르는 쪽이 이미 그 사람의 조회 범위 안에서
    고른 값이어야 한다(`org_context.filter_scope` 가 그것을 보장한다).
    """
    ctx = context_for_user(db, user, scope=scope)
    stmt = select(Ticket)
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    if clause is None:
        return stmt
    return stmt.where(
        Ticket.project_uid.in_(select(Project.id).where(clause))
    )


#: 신호 필터의 어휘. 화면과 서버가 같은 말을 쓴다 — 「차단과 이슈만」 하나로 뭉쳐 있던
#: `blocked_only` 는 지연만 보는 길을 안 줬다(그리고 이름과 뜻도 어긋나 있었다:
#: 그 깃발 하나가 차단 **또는** 이슈를 뜻했다).
SIGNAL_BLOCKED = "blocked"
SIGNAL_OVERDUE = "overdue"
SIGNAL_ISSUE = "issue"
SIGNALS: tuple[str, ...] = (SIGNAL_BLOCKED, SIGNAL_OVERDUE, SIGNAL_ISSUE)


def _signal_clause(signal: str | None, *, today: date | None):
    """신호 하나를 SQL 절로. 모르는 이름은 조용히 무시하지 않고 **거절한다** —
    오타 하나가 「필터를 걸었는데 전부 나온다」로 조용히 지나가면 안 된다."""
    if not signal:
        return None
    if signal not in SIGNALS:
        raise ValidationAppError("모르는 신호입니다.")
    if signal == SIGNAL_BLOCKED:
        return Ticket.blocked_flag.is_(True)
    if signal == SIGNAL_ISSUE:
        return Ticket.issue_flag.is_(True)
    # 지연은 오늘이 며칠인가에 달린 값이라 서버가 준 `today` 없이는 판정하지 않는다.
    if today is None:
        return None
    cat = workflow.category_sql(Ticket.status)
    return (
        Ticket.due_date.is_not(None)
        & (Ticket.due_date < today)
        & (cat.is_(None) | cat.notin_(workflow.TERMINAL_CATEGORIES))
    )


def _apply_shared_filters(
    stmt,
    *,
    q: str | None = None,
    priority: str | None = None,
    difficulty: str | None = None,
    signal: str | None = None,
    blocked_only: bool = False,
    today: date | None = None,
):
    """판과 백로그가 **같은 말로 좁힌다**.

    예전에는 검색·우선순위·난이도가 백로그에만 있었다. 백로그에서 검색어를 넣고 칸반
    탭으로 옮기면 그 조건이 조용히 사라졌고, 사용자는 자기가 무엇을 지웠는지 몰랐다.
    두 목록이 같은 티켓을 다른 질문으로 볼 뿐이므로 **좁히는 말은 하나여야 한다.**
    """
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if difficulty:
        stmt = stmt.where(Ticket.difficulty == difficulty)
    needle = (q or "").strip()
    if needle:
        # 제목과 이름(`ABC-12`) 둘 다 본다 — 사람들은 티켓을 번호로 기억한다.
        pattern = f"%{_ilike_escape(needle)}%"
        stmt = stmt.where(
            Ticket.title.ilike(pattern, escape="\\")
            | Ticket.canonical_key.ilike(pattern, escape="\\")
        )
    clause = _signal_clause(signal, today=today)
    if clause is not None:
        stmt = stmt.where(clause)
    elif blocked_only:
        # 하위호환. 옛 화면과 저장된 링크가 아직 이 이름을 쓴다.
        stmt = stmt.where(Ticket.blocked_flag.is_(True) | Ticket.issue_flag.is_(True))
    return stmt


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
    """휴지통 티켓은 판에서도 없는 것이다 (H2). 목록만 닫고 판을 열어 두면 의미가 없다.

    비교는 **API 가 부르는 이름**으로 한다(`api_page_id`). 휴지통은 그 이름으로 항목을
    적어 두므로(`trash_ticket(page_id=...)`), 여기서 `notion_page_id` 만 보면 자체 DB 에서
    만든 티켓은 `None` 과 비교하게 되고 **버린 티켓이 판에 계속 남는다.**
    """
    trashed = trash_repo.trashed_page_ids(db, TRASH_TICKET)
    if not trashed:
        return tickets
    return [t for t in tickets if api_page_id(t) not in trashed]


def _card(ticket: Ticket, *, names: dict[str, str] | None = None) -> dict:
    """판에 그리는 카드 한 장. 목록 API 와 **다른 모양**인 이유는 목적이 다르기 때문이다.

    목록은 표라서 열이 많고, 판은 카드라서 한 장에 다섯 줄이 최대다. 같은 dict 를
    쓰면 판이 안 쓰는 필드까지 매번 실려 나간다.

    ## 무엇이 늘었나 (지시 5 · D-349)

    신호 둘(`issue` · `blocked`)과 사람(`assignee_*`)과 프로젝트 이름이다. 셋 다 카드가
    **실제로 그리는 것**이라, 없으면 화면이 카드마다 상세를 다시 부르거나(N+1) 아예
    안 그린다. `지연` 은 여기 없다 — 오늘이 며칠인지에 달린 값이라 화면이 그 자리에서
    판정한다(`frontend/src/lib/ticketSignals.js`).

    `names` 는 담당자 토큰 → **사람 조각** 맵이다(`_people`). 카드마다 조회하면 판 한
    장에 질의가 이백 번 난다 — 부르는 쪽이 한 번 만들어 넘긴다.
    """
    tokens = [t for t in split_names(ticket.assignee_notion_ids) if t]
    people = [(names or {}).get(t) for t in tokens]
    people = [p for p in people if p]
    project_names = [n for n in split_names(ticket.project_names) if n]
    return {
        "id": ticket.id,
        "page_id": api_page_id(ticket),
        "key": display_key(ticket),
        "title": ticket.title,
        "status": ticket.status,
        # 「상태가 어느 갈래인가」다(OPEN · IN_PROGRESS · DONE · CANCELED). 이름이
        # `category` 였는데 티켓에는 **같은 이름의 자기 필드**가 따로 있어(사람이 적는
        # 분류) 빠른 수정 모달이 이 값을 그 칸에 그대로 넣을 뻔했다. 이름을 갈라 둔다.
        "status_category": workflow.category_of(ticket.status),
        "priority": ticket.priority,
        "difficulty": ticket.difficulty,
        "due": iso_date(ticket.due_date),
        "est_wd": ticket.est_wd,
        # 아래 넷은 **빠른 수정**이 여는 폼이 그리는 값이다(지시 5). 없으면 모달이 이미
        # 있는 값을 빈칸으로 보여 주고, 사용자는 자기가 안 지운 값이 지워졌다고 읽는다.
        "act_wd": ticket.act_wd,
        "start": iso_date(ticket.start_date),
        "category": ticket.category,
        "sprint_id": ticket.sprint_id,
        "rank": str(ticket.backlog_rank) if ticket.backlog_rank is not None else None,
        "board_rank": str(ticket.board_rank) if ticket.board_rank is not None else None,
        "version": ticket.version,
        # 여러 프로젝트가 걸린 판에서는 카드가 자기 프로젝트를 말해야 한다(지시 §2.4).
        "project_uid": ticket.project_uid,
        "project": project_names[0] if project_names else "",
        # 담당자는 **토큰이 아니라 사람**으로 나간다. 원본 소스 id 는 절대 안 싣는다(§12.3).
        # 카드가 얼굴을 그려야 해서(지시 6) 이름만으로는 모자란다 — 이름을 씨앗으로 쓰면
        # 개명한 사람의 기본 아바타가 바뀌고, 동명이인은 같은 얼굴을 받는다.
        "assignees": people,
        "assignee_names": [p["display_name"] for p in people if p.get("display_name")],
        "assignee_user_ids": [p["user_id"] for p in people if p.get("user_id")],
        # 해석 못 한 담당자가 몇인가. 이름이 빈 카드를 「담당자 없음」으로 읽지 않게 한다.
        "assignee_tokens": len(tokens),
        # Signal — 상태와 직교하는 축 (D-349).
        "issue": bool(ticket.issue_flag),
        "blocked": bool(ticket.blocked_flag),
        "blocked_reason": ticket.blocked_reason,
    }


def _people(db: Session) -> dict[str, dict]:
    """담당자 토큰 → 카드가 그릴 사람 조각. **한 번만 만든다.**

    카드마다 조회하면 판 한 장에 질의가 이백 번 난다. 여기서는 두 번이다 — 활성 사용자
    해석표 한 번(`load_display_maps`)과 아바타 한 번(`avatar_map`).

    조각에 `user_id` 를 넣는 이유는 아바타 때문이다(지시 6). 기본 아바타의 씨앗은
    **UUID** 라, 이름을 씨앗으로 쓰면 개명한 사람의 얼굴이 바뀌고 동명이인이 같은 얼굴을
    받는다. 소스 토큰은 안 나간다(§12.3) — 나가는 것은 앱 user_id 다.
    """
    from app.core.people import avatar_map
    from app.reports.service import load_display_maps

    maps = load_display_maps(db)
    avatars = avatar_map(db, list(maps.id_to_user.values()))
    out: dict[str, dict] = {}
    for token, user_id in maps.id_to_user.items():
        art = avatars.get(user_id) or {}
        out[token] = {
            "user_id": user_id,
            "display_name": maps.id_to_name.get(token, ""),
            "avatar_url": art.get("url"),
            "avatar_default_key": art.get("default_key"),
        }
    return out


def board(
    db: Session,
    user: User,
    *,
    project_id: str | None = None,
    sprint_id: str | None = None,
    scope: str | None = None,
    assignee_token: str | None = None,
    blocked_only: bool = False,
    team_id: str | None = None,
    q: str | None = None,
    priority: str | None = None,
    difficulty: str | None = None,
    signal: str | None = None,
    column_page_size: int = DEFAULT_COLUMN_PAGE_SIZE,
    today: date | None = None,
) -> dict:
    """칸반 한 판. 열은 상태 어휘가 정하고 순서도 거기서 온다.

    모르는 상태(어휘에 없는 값)는 **버리지 않고 따로 모은다.** 버리면 그 티켓이 어느
    화면에도 안 나타나고, 안 나타나는 티켓은 아무도 못 고친다.

    ## 열이 셋으로 갈린다 (지시 5 · D-349)

    여섯이 전부 열이 되면 판이 화면 폭을 넘고, 매일 보는 넷이 매일 안 보는 둘 때문에
    좁아진다. 어느 상태가 어디에 서는가는 어휘가 안다(`workflow.board_placement`) —
    화면이 상태 이름을 적어 열을 고르면 어휘가 바뀐 날 그 화면만 옛 목록으로 남는다.

      column     기본 실행 열 (계획 · 진행 중 · 검증 · 완료)
      collapsed  접힌 칸 (보류). 펴면 보인다
      hidden     기본 판에서 숨는다 (취소). Filter 로만 본다

    **신호 때문에 카드를 다른 열로 옮기지 않는다.** 차단된 진행 중 티켓은 진행 중 열에
    있고 카드가 신호를 단다 — 옮기면 「지금 무엇이 진행 중인가」에 답이 둘이 된다.

    ## 범위 (§8.1 재검수)

    회차 미선택 기본은 `execution` 이다 — 완료·취소가 실행 판을 덮던 A1 이 그 fallback
    때문이었다. `scope="all"` 을 명시할 때만 종료 상태까지 본다.

    ## 열은 **한 쪽만** 낸다 (§8.5 재검수)

    옛 `BOARD_COLUMN_LIMIT` 는 200건에서 자르고 그 뒤를 아예 안 냈다. 지금은 각 열의
    첫 쪽(`column_page_size`, 기본 50)과 `next_cursor` 를 낸다 — 나머지는
    `GET /api/work/board/columns/{status_key}` 가 **같은 조건**으로 이어 준다.

    ## 요약은 SQL 이 센다

    옛 구현은 전량을 파이썬으로 끌어와 세었다(`scope=all` 이면 1,148행). 지금은
    `total`·`by_status`·신호 셋 전부 `GROUP BY`/`FILTER` 로 낸다 — 자르기 전에 센다는
    성질은 그대로이면서 메모리에서 행이 사라진다.
    """
    resolved_scope = resolve_board_scope(scope, sprint_id)
    _ensure_sprint_on_team(db, user, sprint_id=sprint_id, team_id=team_id)
    page_size = max(1, min(column_page_size or DEFAULT_COLUMN_PAGE_SIZE, MAX_COLUMN_PAGE_SIZE))
    base_stmt = _board_scope_stmt(
        db, user, project_id=project_id, sprint_id=sprint_id, scope=resolved_scope,
        assignee_token=assignee_token, blocked_only=blocked_only, team_id=team_id,
        q=q, priority=priority, difficulty=difficulty, signal=signal, today=today,
    )

    # 열은 **표에서 읽는다**(`ticket_statuses`). 어휘의 정본은 코드이고
    # (`app/work/workflow.py::STATUSES`) 이 표는 그 결과지만, 런타임이 읽는 것은 표다.
    # 코드 목록을 그대로 쓰면 이 표에 소비자가 없어진다 — 아무도 안 읽는 표는 시드가
    # 틀려도 아무 일이 안 일어나고, 그러면 시드를 맞물어 두는 시험도 헛돈다.
    status_rows = db.execute(
        select(TicketStatus).order_by(TicketStatus.sort_order, TicketStatus.key)
    ).scalars().all()
    known_keys = [row.key for row in status_rows]

    names = _people(db)
    columns = []
    for row in status_rows:
        page, next_cursor = _rank_keyset_page(
            db, base_stmt.where(Ticket.status == row.key), Ticket.board_rank,
            cursor=None, limit=page_size,
        )
        columns.append({
            "key": row.key,
            "label": row.label,
            "category": row.category,
            # 화면이 열 이름을 적어 자리를 고르지 않게 한다.
            "placement": workflow.board_placement(row.key),
            "cards": [_card(t, names=names) for t in page],
            "total": 0,  # 아래 SQL 집계로 채운다 — 잘리기 전 값이다.
            "next_cursor": next_cursor,
        })

    unclassified_stmt = (
        base_stmt.where(Ticket.status.is_(None) | Ticket.status.notin_(known_keys))
        if known_keys else base_stmt
    )
    unknown_page, unknown_next = _rank_keyset_page(
        db, unclassified_stmt, Ticket.board_rank, cursor=None, limit=page_size,
    )

    base_sq = base_stmt.subquery()
    total = db.execute(select(func.count()).select_from(base_sq)).scalar_one()
    status_counts = dict(
        db.execute(select(base_sq.c.status, func.count()).group_by(base_sq.c.status)).all()
    )
    for col in columns:
        col["total"] = status_counts.get(col["key"], 0)
    unclassified_total = sum(n for key, n in status_counts.items() if key not in known_keys)

    count_cols = [
        func.count().filter(base_sq.c.blocked_flag.is_(True)),
        func.count().filter(base_sq.c.issue_flag.is_(True)),
    ]
    if today is not None:
        cat_case = workflow.category_sql(base_sq.c.status)
        overdue_expr = (
            base_sq.c.due_date.is_not(None)
            & (base_sq.c.due_date < today)
            & (cat_case.is_(None) | cat_case.notin_(workflow.TERMINAL_CATEGORIES))
        )
        count_cols.append(func.count().filter(overdue_expr))
    signal_row = db.execute(select(*count_cols)).one()
    signals = {
        "blocked": signal_row[0],
        "issue": signal_row[1],
        "overdue": signal_row[2] if today is not None else 0,
    }

    return {
        "scope": resolved_scope,
        "column_page_size": page_size,
        "columns": columns,
        # 판 전체의 판독 줄. **자르기 전에** 센다.
        "summary": {
            "total": total,
            "by_status": {key: status_counts.get(key, 0) for key in known_keys},
            "signals": signals,
        },
        # 어휘 밖 상태. 비어 있으면 화면이 이 칸을 그리지 않는다.
        "unclassified": [_card(t, names=names) for t in unknown_page],
        "unclassified_next_cursor": unknown_next,
        "unclassified_total": unclassified_total,
    }


def board_column(
    db: Session,
    user: User,
    *,
    status_key: str,
    project_id: str | None = None,
    sprint_id: str | None = None,
    scope: str | None = None,
    assignee_token: str | None = None,
    blocked_only: bool = False,
    team_id: str | None = None,
    q: str | None = None,
    priority: str | None = None,
    difficulty: str | None = None,
    signal: str | None = None,
    today: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_COLUMN_PAGE_SIZE,
) -> dict:
    """판의 열 하나 — **다음 쪽**(§8.5). `board()` 와 **글자까지 같은 조건**을 받아야
    한다 — 조건이 어긋나면 이 쪽에서 board() 가 안 보여준 카드가 새거나, board() 가
    보여준 카드가 이 쪽에서 다시 나와 중복된다.

    범위(가시성) 절은 `_board_scope_stmt` 안에서 **상한(limit)보다 먼저** 걸린다
    (D-202) — 다음 쪽 요청도 그 순서를 지킨다.
    """
    resolved_scope = resolve_board_scope(scope, sprint_id)
    _ensure_sprint_on_team(db, user, sprint_id=sprint_id, team_id=team_id)
    page_size = max(1, min(limit or DEFAULT_COLUMN_PAGE_SIZE, MAX_COLUMN_PAGE_SIZE))
    base_stmt = _board_scope_stmt(
        db, user, project_id=project_id, sprint_id=sprint_id, scope=resolved_scope,
        assignee_token=assignee_token, blocked_only=blocked_only, team_id=team_id,
        q=q, priority=priority, difficulty=difficulty, signal=signal, today=today,
    )
    known_keys = [key for key in db.execute(select(TicketStatus.key)).scalars().all()]
    if status_key == UNCLASSIFIED_KEY:
        col_stmt = (
            base_stmt.where(Ticket.status.is_(None) | Ticket.status.notin_(known_keys))
            if known_keys else base_stmt
        )
    elif status_key in known_keys:
        col_stmt = base_stmt.where(Ticket.status == status_key)
    else:
        raise NotFoundError("모르는 열입니다.")

    page, next_cursor = _rank_keyset_page(db, col_stmt, Ticket.board_rank, cursor=cursor, limit=page_size)
    total = db.execute(select(func.count()).select_from(col_stmt.subquery())).scalar_one()
    names = _people(db)
    return {"cards": [_card(t, names=names) for t in page], "total": total, "next_cursor": next_cursor}


def _backlog_scope_stmt(
    db: Session,
    user: User,
    *,
    project_id: str | None = None,
    q: str | None = None,
    assignee_token: str | None = None,
    priority: str | None = None,
    difficulty: str | None = None,
    exclude_ticket_id: str | None = None,
    team_id: str | None = None,
    signal: str | None = None,
    blocked_only: bool = False,
    today: date | None = None,
):
    """백로그의 **한 조건** — 목록(`backlog`)과 위치 이동(`_backlog_position_rank`)이
    같은 조건을 봐야 한다. 조건이 어긋나면 "지금 화면에 보이는 백로그"와 "맨 위로/맨
    아래로가 계산한 백로그"가 다른 집합이 되고, 그 어긋남은 카드 순서가 화면마다
    다르게 보이는 것으로만 드러난다(오류가 안 난다).
    """
    stmt = _visible_tickets_stmt(db, user)
    if team_id:
        stmt = stmt.where(_team_projects_clause(team_id))
    if project_id:
        stmt = stmt.where(Ticket.project_uid == project_id)
    cat = workflow.category_sql(Ticket.status)
    stmt = stmt.where(
        Ticket.notion_missing_at.is_(None),
        # 회차에 담기지 않은 것만. 이 한 줄이 「백로그」의 정의다.
        Ticket.sprint_id.is_(None),
        _not_trashed_ticket_clause(),
        # 끝난 것은 안 싣는다 — `workflow.is_terminal` 과 같은 판정을 SQL 로.
        cat.is_(None) | cat.notin_(workflow.TERMINAL_CATEGORIES),
    )
    if exclude_ticket_id:
        stmt = stmt.where(Ticket.id != exclude_ticket_id)
    assignee_clause = _assignee_sql_clause(assignee_token)
    if assignee_clause is not None:
        stmt = stmt.where(assignee_clause)
    return _apply_shared_filters(
        stmt, q=q, priority=priority, difficulty=difficulty,
        signal=signal, blocked_only=blocked_only, today=today,
    )


def backlog(
    db: Session,
    user: User,
    *,
    project_id: str | None = None,
    q: str | None = None,
    assignee_token: str | None = None,
    priority: str | None = None,
    difficulty: str | None = None,
    team_id: str | None = None,
    signal: str | None = None,
    blocked_only: bool = False,
    today: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_COLUMN_PAGE_SIZE,
) -> dict:
    """백로그 — **아직 어느 회차에도 안 담긴 일**. 서버 커서 페이징(§8.5) — 181행을
    한 번에 받던 것을 `backlog_rank` 순으로 쪽 낸다.

    ## 「백로그」는 상태가 아니라 위치다 (D-349)

    별도 Status 를 만들지 않는다. `sprint_id IS NULL` 인 활성 티켓이 백로그다 — 상태를
    손으로 「계획」으로 바꾸는 것이 편입이 아니고, 편입은 `move(set_sprint=...)` 라는
    **명시적 동작**이다(지시 §2.3).

    예전에는 이 목록이 회차에 담긴 티켓까지 함께 실었다. 그러면 같은 티켓이 판에도 있고
    백로그에도 있어서, 「다음에 무엇을 할까」를 고르는 화면이 이미 이번 주에 하기로 한
    일로 절반이 찬다.

    끝난 것은 안 싣는다. 백로그는 "다음에 무엇을 하는가" 라서 완료·취소가 섞이면
    스크롤 대부분이 지나간 일이 된다.
    """
    page_size = max(1, min(limit or DEFAULT_COLUMN_PAGE_SIZE, MAX_COLUMN_PAGE_SIZE))
    stmt = _backlog_scope_stmt(
        db, user, project_id=project_id, q=q, assignee_token=assignee_token,
        priority=priority, difficulty=difficulty, team_id=team_id,
        signal=signal, blocked_only=blocked_only, today=today,
    )
    page, next_cursor = _rank_keyset_page(db, stmt, Ticket.backlog_rank, cursor=cursor, limit=page_size)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    names = _people(db)
    return {
        "items": [_card(t, names=names) for t in page],
        "total": total,
        "next_cursor": next_cursor,
    }


def backlog_position_rank(
    db: Session,
    user: User,
    *,
    ticket_id: str,
    position: str,
    project_id: str | None = None,
    q: str | None = None,
    assignee_token: str | None = None,
    priority: str | None = None,
    difficulty: str | None = None,
    team_id: str | None = None,
    signal: str | None = None,
    blocked_only: bool = False,
    today: date | None = None,
) -> Decimal:
    """「맨 위로 / 맨 아래로」의 목표 순위 값 (§8.5).

    `before_id`/`after_id`(`rank.place`)는 그 카드가 **화면에 있어야** 쓸 수 있다 —
    181행 중 맨 아래로 보내려는 카드의 새 이웃(현재 맨 끝 카드)이 아직 안 받아 온
    쪽에 있을 수 있다. 여기서는 카드 자체를 끌어오지 않고 `backlog_rank` 값만
    다시 조회해 그 사이 값을 계산한다 — **지금 화면과 같은 조건**(`_backlog_scope_stmt`)
    으로, 옮기는 카드 자신은 이웃 후보에서 뺀다.

    `rank.place()` 를 안 쓰는 이유: 그 함수는 이웃을 **옮기는 카드의 project_uid** 로
    좁힌다(단일 프로젝트 화면의 드래그를 겨눈 설계다). 이 화면은 프로젝트를 안 좁히면
    여러 프로젝트가 섞인 채로 `backlog_rank` 하나로 정렬되므로, "맨 위/맨 아래"는 그
    화면이 보는 전체 순서 기준이어야 한다 — 옮기는 카드의 프로젝트로 좁히면 안 된다.
    드래그 경로도 이제 같은 원칙이다(`_place_by_neighbours` — 이웃을 가시성 범위로 읽는다).
    """
    if position not in ("top", "bottom"):
        raise ValidationAppError(f"모르는 위치입니다: {position}")
    stmt = _backlog_scope_stmt(
        db, user, project_id=project_id, q=q, assignee_token=assignee_token,
        priority=priority, difficulty=difficulty, exclude_ticket_id=ticket_id,
        team_id=team_id, signal=signal, blocked_only=blocked_only, today=today,
    )
    sq = stmt.subquery()
    # 전체 순위를 파이썬으로 끌어오지 않는다 — 필요한 것은 양 끝 값 둘뿐이다.
    # MIN/MAX 는 NULL 을 무시하므로, 순위 없는 행이 섞여 있어도 「맨 아래」가
    # 값 있는 마지막 카드의 **뒤**로 간다(옛 전량 로드는 NULLS LAST 의 마지막 행이
    # NULL 이라 이 경우 STEP 근처로 떨어졌다 — 자리 겹침 후보였다).
    low, high = db.execute(
        select(func.min(sq.c.backlog_rank), func.max(sq.c.backlog_rank))
    ).one()
    if position == "top":
        return rank_mod.between(None, Decimal(low) if low is not None else None)
    return rank_mod.between(Decimal(high) if high is not None else None, None)


# ── Drop ─────────────────────────────────────────────────────────────────────


def _neighbour_ranks(
    db: Session, user: User, *, before_id: str | None, after_id: str | None, field: str,
) -> tuple[Decimal | None, Decimal | None]:
    """드롭 위치 두 이웃의 순위 — **요청자 가시성 범위**에서 읽는다.

    rank 는 이미 전역 수직선이다(`_rank_keyset_page` 가 프로젝트 파티션 없이 값으로만
    정렬한다). 두 이웃 사이의 중점은 숫자 순서가 부분집합에서 보존되므로 어떤 필터
    투영(전체 판·프로젝트 판·백로그)에서도 정확히 그 사이에 선다.

    🔴 옛 경로(`rank.neighbours`)는 이웃을 **옮기는 카드의 project_uid** 로 좁혔다 —
    단일 프로젝트 화면의 드래그를 겨눈 설계라, 프로젝트를 안 좁힌 판·백로그에서 타
    프로젝트 카드 옆에 놓으면 이웃이 (None, None) 이 되어 카드가 맨 뒤로 떨어졌다.
    놓은 자리와 무관하게, 오류 한 줄 없이.

    이웃 id 는 클라이언트 입력이다 — 가시성 절로 읽으므로 범위 밖 티켓의 순위를 탐침할
    수 없고, 범위 밖·미존재 id 는 None(이웃 없음 → 맨 뒤 폴백)으로 떨어진다. 실패의
    모양이 미존재와 같아 존재 여부도 새지 않는다.
    """
    def _rank_of(ticket_id: str | None) -> Decimal | None:
        if not ticket_id:
            return None
        row = db.execute(
            _visible_tickets_stmt(db, user).where(Ticket.id == ticket_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        value = getattr(row, field)
        return Decimal(value) if value is not None else None

    return _rank_of(before_id), _rank_of(after_id)


def _place_by_neighbours(
    db: Session, user: User, *, ticket: Ticket,
    before_id: str | None, after_id: str | None, field: str,
) -> Decimal:
    """드롭 위치의 순위 값 — `rank.place()` 와 같은 흐름, 이웃 조회만 가시성 범위다.

    재조정(rebalance)은 여전히 **옮기는 카드의 프로젝트 단위**다. 이웃이 같은 프로젝트면
    재조정 뒤 다시 읽은 값으로 정확히 앉고, 타 프로젝트 이웃이면 재조정이 그 값을 못
    바꾸므로 깊은 자릿수를 그대로 수용한다 — `_PRECISION`(200자리) 아래에서 정확성은
    유지되고, 같은 틈에 수십 번 연속 꽂는 병리적 경우에만 자릿수가 자란다.
    """
    low, high = _neighbour_ranks(db, user, before_id=before_id, after_id=after_id, field=field)
    if low is None and high is None:
        # 이웃이 하나도 없다 — 빈 칸에 놓았거나 이웃이 아직 순위를 못 받았다.
        # `rank.place()` 의 같은 갈래와 같은 이유로 맨 뒤에 붙인다.
        return rank_mod.append_rank(db, project_id=ticket.project_uid, field=field)
    value = rank_mod.between(low, high)
    if not rank_mod.needs_rebalance(value):
        return value
    rank_mod.rebalance(db, project_id=ticket.project_uid, field=field)
    low, high = _neighbour_ranks(db, user, before_id=before_id, after_id=after_id, field=field)
    if low is None and high is None:
        return rank_mod.append_rank(db, project_id=ticket.project_uid, field=field)
    return rank_mod.between(low, high)


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
    if api_page_id(ticket) in trash_repo.trashed_page_ids(db, TRASH_TICKET):
        raise NotFoundError("티켓을 찾을 수 없습니다.")
    return ticket


# ── 회차의 세 문 (D-482) ──────────────────────────────────────────────────────
#
# 회차에는 서로 다른 질문이 셋 있고, 셋이 각자 함수다. 한 함수에 섞으면 한쪽을 고칠 때
# 다른 쪽이 조용히 넓어진다.
#
#   조회   sprint_visibility_clause   자기 팀과 그 아래 ∪ 관리 범위 (프로젝트 줄기와 다르다)
#   편성   ensure_sprint_manageable   관리 범위가 그 팀을 덮는가 — 보이는데 못 고치면 403
#   담기   ensure_eligible           티켓의 팀(프로젝트의 dept_id) == 회차의 팀, 열린 회차만

SPRINT_NOT_FOUND = "스프린트를 찾을 수 없습니다."
SPRINT_FORBIDDEN = "이 팀의 회차를 편성할 권한이 없습니다."


def _principal(db: Session, user: User):
    return principal_from_user(db, user, DeptTree.load(db))


def sprint_visibility_clause(principal):
    """회차 조회 절 — `None` 은 제한 없음(전역), 그 밖에는 WHERE 에 붙일 절이다.

    볼 수 있는 팀은 `org_context.sprint_team_ids` 가 정한다(자기 부서와 그 아래 ∪ 관리
    범위 ∪ 조직 직속이면 조직의 모든 팀). 팀 미정(`department_id IS NULL`) 회차는 조직
    범위·전역 범위에만 보인다 — 팀 사용자의 주기가 아니다.

    목록·단건·회의·이웃·판·집계가 **전부 이 절 하나**를 쓴다. 한 곳이 다른 절을 쓰면
    목록에 없는 회차가 「다음 회차」 단추로 새거나 그 반대가 된다.
    """
    teams = org_context.sprint_team_ids(principal)
    if teams is None:
        return None
    parts = []
    if teams:
        parts.append(Sprint.department_id.in_(tuple(sorted(teams))))
    vis = principal.visibility
    if vis.is_org and vis.org_id:
        parts.append(Sprint.department_id.is_(None) & (Sprint.org_id == vis.org_id))
    if not parts:
        return MATCH_NOTHING
    return or_(*parts)


def _visible_sprints_stmt(db: Session, user: User, principal=None):
    principal = principal if principal is not None else _principal(db, user)
    stmt = select(Sprint)
    clause = sprint_visibility_clause(principal)
    return stmt if clause is None else stmt.where(clause)


def get_scoped_sprint_or_404(db: Session, sprint_id: str, user: User) -> Sprint:
    """스프린트 하나 — **목록과 같은 판정**을 지난다.

    목록만 좁히고 단건·쓰기를 열어 두면 목록을 좁힌 의미가 없다. 범위 밖 회차는 없는
    회차와 **똑같이 404** 다 — 403 은 그 id 가 존재한다는 사실을 알려 주고, 그러면 id 를
    찍어 보며 남의 팀 회차를 열거할 수 있다.
    """
    sprint = db.execute(
        _visible_sprints_stmt(db, user).where(Sprint.id == sprint_id)
    ).scalar_one_or_none()
    if sprint is None:
        raise NotFoundError(SPRINT_NOT_FOUND)
    return sprint


def ensure_team_manageable(db: Session, user: User, department_id: str | None, *, org_id=None):
    """이 팀의 회차를 **편성**할 수 있는가 — 관리 범위가 그 팀을 덮어야 한다 (403).

    조회와 다른 문이다. A 본부 사람은 A-1 회차를 보지만 A-1 을 관리하지 않으면 못 연다.
    팀 미정 회차(`department_id` 없음)는 조직·전역 관리자만 만진다 — 팀을 정해 주는 사람이다.
    """
    principal = _principal(db, user)
    if department_id is None:
        if not org_context.can_manage_unassigned_sprints(principal, org_id):
            raise ForbiddenError("팀 미정 회차는 조직 관리자만 편성할 수 있습니다.")
        return principal
    managed = org_context.manageable_team_ids(principal)
    if managed is not None and department_id not in managed:
        raise ForbiddenError(SPRINT_FORBIDDEN)
    return principal


def ensure_sprint_manageable(db: Session, user: User, sprint: Sprint):
    """`ensure_team_manageable` 의 회차판. 부르는 쪽은 이미 회차 조회 문을 지났다."""
    return ensure_team_manageable(db, user, sprint.department_id, org_id=sprint.org_id)


def ensure_planning_role(db: Session, user: User) -> None:
    """회차에 담고 빼는 것은 편성이다 — 역할 게이트도 회차 쓰기와 같은 `PROJECT_WRITE` 다.

    판의 상태·순서 이동은 티켓 편집 권한(전원)이지만, 어느 회차에 무엇이 들어가는가는
    팀의 계획이라 운영군이 정한다. 화면이 단추를 감추는 것은 안내이고 문은 여기다.
    """
    if not has_permission(db, user, PROJECT_WRITE):
        raise ForbiddenError("회차에 담거나 빼는 일은 운영 권한이 있어야 할 수 있습니다.")


def ensure_sprint_open(sprint: Sprint, *, what: str) -> None:
    """닫힌 회차는 **과거 기록**이다 — 담기·빼기·순서·상태 변경 어느 것도 안 된다."""
    if sprint.state == SPRINT_CLOSED:
        raise ValidationAppError(f"닫힌 회차의 티켓은 {what} 수 없습니다. 닫힌 회차는 기록으로만 남습니다.")


def ensure_eligible(db: Session, sprint: Sprint, ticket: Ticket) -> None:
    """이 티켓을 이 회차에 담을 수 있는가 — **정확 일치**다.

    티켓의 팀은 프로젝트의 `dept_id` 한 단계이고, 회차의 팀과 같아야 한다. 상위 본부·
    하위 팀·형제 팀의 프로젝트 티켓도, 조직 공통(`dept_id` 없음) 프로젝트의 티켓도 안
    된다 — 그 티켓은 그 팀의 백로그에 없고, 백로그에 없는 것이 담기면 회의에서 「우리
    일이 아닌데 왜 여기 있지」가 된다. 프로젝트에 부서를 지정하면 그 팀의 일이 된다.
    """
    if sprint.department_id is None:
        raise ValidationAppError("팀이 정해지지 않은 회차에는 티켓을 담을 수 없습니다. 먼저 회차의 팀을 정해 주세요.")
    project = db.get(Project, ticket.project_uid) if ticket.project_uid else None
    if project is None or project.dept_id != sprint.department_id:
        raise ValidationAppError("이 티켓은 다른 팀의 일이라 이 회차에 담을 수 없습니다. 같은 팀 프로젝트의 티켓만 담을 수 있습니다.")


def _ensure_sprint_on_team(
    db: Session, user: User, *, sprint_id: str | None, team_id: str | None
) -> Sprint | None:
    """판이 고른 회차는 보여야 하고, 팀도 골랐다면 그 팀의 회차여야 한다 (422)."""
    if not sprint_id:
        return None
    sprint = get_scoped_sprint_or_404(db, sprint_id, user)
    if team_id and sprint.department_id != team_id:
        raise ValidationAppError("고른 회차가 이 팀의 회차가 아닙니다.")
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
                related=("ticket", api_page_id(ticket)), now=now,
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
    # 판에서 옮겼는가, 백로그에서 옮겼는가. 두 목록의 순서는 다른 컬럼이다.
    on_board: bool = False,
    # 화면에 없는 카드 기준 이동(§8.5) — before_id/after_id 대신 쓴다. 백로그에서만
    # 뜻이 있다("맨 위/맨 아래"는 판의 열에는 없는 개념이다 — 열은 상태가 자리를 정한다).
    to_position: str | None = None,
    position_project_id: str | None = None,
    position_q: str | None = None,
    position_assignee_token: str | None = None,
    position_priority: str | None = None,
    position_difficulty: str | None = None,
    position_team_id: str | None = None,
    position_signal: str | None = None,
    position_today: date | None = None,
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
    from app.tickets import service as tickets_service

    stamp = now or utcnow()
    ticket = load_ticket_in_scope_or_404(db, ticket_id, user)
    _ensure_version(ticket, base_version)

    if not (to_status or set_sprint or reorder):
        raise ValidationAppError("옮길 내용이 없습니다.")
    # 세 종류 전부 티켓 편집 문을 지난다 — 상태는 `update_ticket` 안에서 한 번 더 지나지만,
    # 순서·회차만 옮기는 요청이 그 문을 건너뛰면 읽기 전용 역할(감사자)이 판을 만진다.
    tickets_service.ensure_can_edit(ticket, user, None)
    # 지금 담긴 회차. 클라이언트가 준 id 가 아니라 티켓의 값이라 조회 문을 안 지난다.
    current_sprint = db.get(Sprint, ticket.sprint_id) if ticket.sprint_id else None
    changed = False

    from_status = ticket.status
    if to_status:
        target = workflow.validate_transition(from_status, to_status)
        if target != from_status:
            # 소스까지 반영하는 유일한 경로. 범위·편집 권한 판정도 여기 한 곳이다
            # (닫힌 회차의 티켓은 그 안에서 422 로 막힌다).
            tickets_service.update_ticket(
                db, outbound, settings, user,
                page_id=api_page_id(ticket), changes={"status": target},
                now=stamp, repo=repo,
            )
            db.refresh(ticket)
            activity.record(
                db, ticket_id=ticket.id, kind=ACT_STATUS, actor_id=user.id,
                field="status", from_value=from_status, to_value=target, now=stamp,
            )
            changed = True

    if set_sprint:
        # 담고 빼는 것은 **편성**이다 — 역할(`PROJECT_WRITE`)과 관리 범위(그 회차의 팀)를
        # 둘 다 본다. 화면이 단추를 감추는 것은 안내이고 문은 여기다.
        ensure_planning_role(db, user)
        before_sprint = ticket.sprint_id
        target_sprint = None
        if sprint_id:
            # 담는 쪽 문도 회차 게이트를 지난다(위 「문이 둘이다」와 같은 이유). 범위 밖
            # 회차는 404 다 — 400 으로 거절하면 그 응답 자체가 「그 id 의 회차가 있다」를
            # 알려 주는 오라클이 되어, id 를 찍어 남의 팀 회차를 열거할 수 있다.
            target_sprint = get_scoped_sprint_or_404(db, sprint_id, user)
            ensure_sprint_manageable(db, user, target_sprint)
            ensure_sprint_open(target_sprint, what="담을")
            if before_sprint and before_sprint != target_sprint.id:
                # 🔴 다른 회차에 든 티켓을 조용히 옮기지 않는다. 옮기면 원래 회차의 범위가
                # 아무 기록 없이 줄고, 그 회의는 「어디 갔지」로 시작한다. 먼저 빼고 담는다.
                held = current_sprint.name if current_sprint is not None else "다른"
                raise ConflictError(
                    f"이 티켓은 이미 «{held}» 회차에 담겨 있습니다. 먼저 그 회차에서 뺀 뒤 담아 주세요."
                )
            ensure_eligible(db, target_sprint, ticket)
        if before_sprint and (target_sprint is None or target_sprint.id != before_sprint):
            # 빼는 쪽도 편성이다 — 지금 담긴 회차를 관리할 수 있어야 하고, 닫힌 회차의
            # membership 은 기록이라 못 뺀다.
            if current_sprint is not None:
                ensure_sprint_manageable(db, user, current_sprint)
                ensure_sprint_open(current_sprint, what="뺄")
        new_sprint_id = target_sprint.id if target_sprint is not None else None
        if new_sprint_id != before_sprint:
            ticket.sprint_id = new_sprint_id
            activity.record(
                db, ticket_id=ticket.id, kind=ACT_SPRINT, actor_id=user.id, field="sprint_id",
                from_value=before_sprint, to_value=ticket.sprint_id, now=stamp,
            )
            changed = True

    if reorder:
        # 닫힌 회차의 판은 기록이다 — 순서도 안 바꾼다.
        if on_board and current_sprint is not None:
            ensure_sprint_open(current_sprint, what="옮길")
        # **어느 목록의 순서인가.** 판과 백로그는 다른 줄이라 한 컬럼으로 두면 카드를
        # 판에서 옮긴 순간 백로그 순서가 함께 흐트러진다 — 그 흐트러짐은 오류를 안 내고
        # 다음 계획 회의에서야 보인다.
        field = "board_rank" if on_board else "backlog_rank"
        before_rank = getattr(ticket, field)
        if to_position and not on_board:
            placed = backlog_position_rank(
                db, user, ticket_id=ticket.id, position=to_position,
                project_id=position_project_id, q=position_q,
                assignee_token=position_assignee_token,
                priority=position_priority, difficulty=position_difficulty,
                team_id=position_team_id, signal=position_signal,
                today=position_today,
            )
        else:
            # 이웃은 가시성 범위 전역으로 읽는다 — 프로젝트가 섞인 판·백로그에서 놓은
            # 자리가 그대로 순위가 된다(`_place_by_neighbours` 의 🔴 주석).
            placed = _place_by_neighbours(
                db, user, ticket=ticket, before_id=before_id, after_id=after_id,
                field=field,
            )
        setattr(ticket, field, placed)
        activity.record(
            db, ticket_id=ticket.id, kind=ACT_RANK, actor_id=user.id, field=field,
            from_value=str(before_rank) if before_rank is not None else None,
            to_value=str(placed), now=stamp,
        )
        changed = True

    if not changed:
        # 같은 회차에 다시 담기 같은 no-op — 버전을 올리면 다른 사람의 편집이 헛 충돌한다.
        return {"ticket": _card(ticket)}

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


def _sprint_view(sprint: Sprint, *, today: date | None = None) -> dict:
    return {
        "id": sprint.id,
        "name": sprint.name,
        # 이 회차를 운영하는 팀(`org_units.id`). `None` 은 팀 미정(레거시)이다 — 화면은
        # 이 값을 팀 후보 목록에서 이름·경로로 옮긴다. `project_id` 는 더 이상 없다(D-482).
        "department_id": sprint.department_id,
        # 화면은 'YYYY-MM-DD' 문자열을 읽는다. 컬럼은 `date` 다 (S7 · P-14a).
        "starts_on": iso_date(sprint.starts_on),
        "ends_on": iso_date(sprint.ends_on),
        "state": sprint.state,
        "goal": sprint.goal,
        # 오늘이 이 회차에 걸려 있는가(§8.3) — 작업 보드가 진입 시 자동으로 고르는
        # 회차가 이 값이다. `today` 를 안 주면(마이그레이션·단위 시험 등) 판정하지
        # 않는다 — 모르면서 `False` 로 답하면 "활성 회차가 없다"는 다른 사실이 된다.
        "active": (
            sprint.state == SPRINT_ACTIVE
            and sprint.starts_on <= today <= sprint.ends_on
        ) if today is not None else None,
    }


#: 회차 목록·이웃의 정렬 열쇠. 이름 사전순은 「9-10」이 「9-2」보다 앞에 서서 버렸다 —
#: 같은 시작일이면 나중에 만든 것이 앞이고, 그것도 같으면 id 로 고정된다(안정 정렬).
def _sprint_order_desc():
    return (Sprint.starts_on.desc(), Sprint.created_at.desc(), Sprint.id.desc())


def _same_team_clause(sprint: Sprint):
    """같은 팀의 회차 — 팀 미정끼리는 같은 조직의 팀 미정끼리다."""
    if sprint.department_id is not None:
        return Sprint.department_id == sprint.department_id
    return Sprint.department_id.is_(None) & (Sprint.org_id == sprint.org_id)


def list_sprints(
    db: Session, user: User, *, department_id: str | None = None, today: date | None = None
) -> list[dict]:
    """회차 목록 — **팀별**이다.

    `department_id` 를 주면 그 팀의 회차만(범위 밖 팀은 404), `"none"` 이면 팀 미정
    회차만, 안 주면 볼 수 있는 회차 전부다. 어느 경우든 조회 절은 하나
    (`sprint_visibility_clause`)다.
    """
    principal = _principal(db, user)
    stmt = _visible_sprints_stmt(db, user, principal)
    if department_id == "none":
        stmt = stmt.where(Sprint.department_id.is_(None))
    elif department_id:
        teams = org_context.sprint_team_ids(principal)
        if teams is not None and department_id not in teams:
            raise NotFoundError("팀을 찾을 수 없습니다.")
        stmt = stmt.where(Sprint.department_id == department_id)
    rows = db.execute(stmt.order_by(*_sprint_order_desc())).scalars().all()
    return [_sprint_view(s, today=today) for s in rows]


def _ensure_name_free(db: Session, *, org_id, department_id, name: str, except_id=None) -> None:
    """이름은 팀 안에서 유일하다. 제약 이름(`uq_sprints_name`)만 보고 무엇이 문제인지
    아는 사람은 없으므로 여기서 먼저 사람의 말로 거절한다."""
    stmt = select(Sprint.id).where(Sprint.org_id == org_id, Sprint.name == name)
    stmt = stmt.where(
        Sprint.department_id == department_id if department_id is not None
        else Sprint.department_id.is_(None)
    )
    if except_id:
        stmt = stmt.where(Sprint.id != except_id)
    if db.execute(stmt).first() is not None:
        raise ConflictError("이 팀에 같은 이름의 회차가 이미 있습니다.")


def _ensure_no_other_active(db: Session, sprint: Sprint) -> None:
    """활성 회차는 **팀당 하나**다. 둘이면 「이번 회차」에 답이 둘이 되고 번다운이 둘이 된다."""
    conflict = db.execute(
        select(Sprint).where(
            Sprint.state == SPRINT_ACTIVE, Sprint.id != sprint.id, _same_team_clause(sprint),
        )
    ).scalars().first()
    if conflict is not None:
        raise ConflictError(f"이미 «{conflict.name}» 회차가 열려 있습니다. 먼저 닫아 주세요.")


def create_sprint(
    db: Session,
    user: User,
    *,
    name: str,
    starts_on: str,
    ends_on: str,
    department_id: str,
    goal: str | None = None,
    now: datetime | None = None,
) -> dict:
    """회차 하나 — **팀의 회차**다. 시작 상태는 `planned` 다 — **여는 것은 별도 동작**이다.

    만들자마자 열면 다음 회차를 미리 계획해 둘 수 없다. 「이번」이 무엇인지가 계획의
    핵심이라 그 전환을 사람이 눌러야 한다.

    팀은 보이는 팀이어야 하고(아니면 없는 팀과 같은 404) 관리 범위 안이어야 한다(403).
    프로젝트가 아직 없는 새 팀도 회차를 먼저 만들 수 있다 — 그런 제한은 없다.
    """
    label = (name or "").strip()
    if not label:
        raise ValidationAppError("회차 이름을 입력해 주세요.")
    if not department_id:
        raise ValidationAppError("회차를 운영할 팀을 골라 주세요.")
    # 여기서 한 번 날짜로 읽는다 — 못 읽는 값을 그대로 두면 DB 가 거절하고,
    # 그 실패는 422 가 아니라 500 이 된다 (S7 · P-14a).
    first, last = parse_date(starts_on), parse_date(ends_on)
    # 못 읽는 날짜와 거꾸로 된 기간은 다른 잘못이다 — 2월 31일을 적은 사람에게 「시작일이
    # 종료일보다 앞이어야」라고 답하면 무엇을 고쳐야 하는지 모른다.
    if first is None or last is None:
        raise ValidationAppError("회차 기간은 달력에 있는 날짜(YYYY-MM-DD)여야 합니다.")
    if first >= last:
        raise ValidationAppError("회차 기간은 시작일이 종료일보다 앞이어야 합니다.")
    team = org_context.team_context(db, user, department_id)   # 범위 밖 팀은 404
    ensure_team_manageable(db, user, department_id)
    org_id = team["principal"].tree.org_of(department_id)
    _ensure_name_free(db, org_id=org_id, department_id=department_id, name=label)

    row = Sprint(
        name=label, department_id=department_id, org_id=org_id,
        starts_on=first, ends_on=last, state=SPRINT_PLANNED, goal=(goal or None),
        created_at=now or utcnow(), updated_at=now or utcnow(),
    )
    db.add(row)
    db.flush()
    return _sprint_view(row)


def set_sprint_state(
    db: Session, user: User, *, sprint_id: str, state: str, now: datetime | None = None
) -> dict:
    """회차를 연다/되돌린다. **한 팀에 열린 회차는 하나**뿐이다.

    둘이면 「이번 스프린트」에 답이 둘이 되고 번다운이 두 개가 된다. 부분 유니크
    인덱스가 막지만, 여기서 먼저 읽을 수 있는 말로 거절한다 — 제약 이름만 보고
    무엇이 문제인지 아는 사람은 없다. 팀이 다르면 같은 기간에 나란히 연다.
    """
    if state not in SPRINT_STATES:
        raise ValidationAppError(f"모르는 스프린트 상태입니다: {state}")
    sprint = get_scoped_sprint_or_404(db, sprint_id, user)
    ensure_sprint_manageable(db, user, sprint)
    # closed 는 종착이다 — 번다운·이월 기록이 닫힌 시점 기준으로 서 있고, 다시 열면
    # 그 기록이 전부 거짓이 된다. 같은 상태로의 재설정은 재실행 안전으로 남긴다.
    if sprint.state == SPRINT_CLOSED and state != SPRINT_CLOSED:
        raise ConflictError("이미 닫은 회차는 다시 열 수 없습니다. 새 회차를 만들어 주세요.")
    # 닫기는 `/close` 한 곳이다 — 여기로 닫으면 이월 없이 닫혀 안 끝난 티켓이 붕 뜬다.
    if state == SPRINT_CLOSED and sprint.state != SPRINT_CLOSED:
        raise ValidationAppError(
            "회차를 닫으려면 「회차 닫기」를 써 주세요. 안 끝난 티켓을 보낼 곳을 함께 정해야 합니다."
        )
    if state == SPRINT_ACTIVE and sprint.state != SPRINT_ACTIVE:
        if sprint.department_id is None:
            raise ValidationAppError("팀이 정해지지 않은 회차는 열 수 없습니다. 먼저 회차의 팀을 정해 주세요.")
        _ensure_no_other_active(db, sprint)
    sprint.state = state
    sprint.updated_at = now or utcnow()
    db.flush()
    return _sprint_view(sprint)


def update_sprint(
    db: Session, user: User, *, sprint_id: str, changes: dict, now: datetime | None = None
) -> dict:
    """이름·기간·목표를 고친다. **보낸 칸만** 바뀐다(라우터가 `exclude_unset` 으로 거른다).

    닫은 회차는 **이름만** 고친다 — 기간·목표는 그 회차의 기록이고, 지난 기록을 다시
    쓰면 회의록과 번다운이 거짓이 된다. 오타는 기록이 아니라 실수라 이름은 남긴다.

    `department_id` 는 팀 미정(레거시) 회차에 팀을 **정해 주는** 칸이다. 이미 팀이 있는
    회차의 팀은 못 바꾼다 — 담긴 티켓의 자격(같은 팀)이 통째로 깨진다.
    """
    sprint = get_scoped_sprint_or_404(db, sprint_id, user)
    ensure_sprint_manageable(db, user, sprint)
    if sprint.state == SPRINT_CLOSED and any(
        k in changes for k in ("starts_on", "ends_on", "goal", "department_id")
    ):
        raise ValidationAppError("닫은 회차는 이름만 고칠 수 있습니다. 기간과 목표는 기록으로 남습니다.")
    team_after = sprint.department_id
    if "department_id" in changes:
        target = changes.get("department_id") or None
        if sprint.department_id is not None:
            if target != sprint.department_id:
                raise ValidationAppError("회차의 팀은 바꿀 수 없습니다. 팀이 다르면 새 회차를 만들어 주세요.")
        elif target is None:
            raise ValidationAppError("회차의 팀을 골라 주세요.")
        else:
            team = org_context.team_context(db, user, target)   # 범위 밖 팀은 404
            ensure_team_manageable(db, user, target)
            if team["principal"].tree.org_of(target) != sprint.org_id:
                raise ValidationAppError("다른 조직의 팀에는 이 회차를 둘 수 없습니다.")
            team_after = target
    if "name" in changes:
        label = (changes.get("name") or "").strip()
        if not label:
            raise ValidationAppError("회차 이름을 입력해 주세요.")
        if label != sprint.name or team_after != sprint.department_id:
            _ensure_name_free(
                db, org_id=sprint.org_id, department_id=team_after, name=label, except_id=sprint.id,
            )
        sprint.name = label
    elif team_after != sprint.department_id:
        _ensure_name_free(
            db, org_id=sprint.org_id, department_id=team_after, name=sprint.name, except_id=sprint.id,
        )
    if team_after != sprint.department_id:
        sprint.department_id = team_after
        if sprint.state == SPRINT_ACTIVE:
            _ensure_no_other_active(db, sprint)
    if "starts_on" in changes or "ends_on" in changes:
        first = parse_date(changes["starts_on"]) if "starts_on" in changes else sprint.starts_on
        last = parse_date(changes["ends_on"]) if "ends_on" in changes else sprint.ends_on
        # create 와 같은 규칙 — 반쪽만 보내도 합성해서 다시 검증한다.
        if first is None or last is None:
            raise ValidationAppError("회차 기간은 달력에 있는 날짜(YYYY-MM-DD)여야 합니다.")
        if first >= last:
            raise ValidationAppError("회차 기간은 시작일이 종료일보다 앞이어야 합니다.")
        sprint.starts_on = first
        sprint.ends_on = last
    if "goal" in changes:
        sprint.goal = changes.get("goal") or None
    sprint.updated_at = now or utcnow()
    db.flush()
    return _sprint_view(sprint)


def delete_sprint(
    db: Session, user: User, *, sprint_id: str, now: datetime | None = None
) -> dict:
    """**planned 회차만** 지운다 — 잘못 만든 회차를 정리하는 길이다.

    active 는 닫기(이월)로 정리하고, closed 는 기록이라 남긴다. 담긴 티켓은 삭제
    금지 사유가 아니라 **명시적으로 백로그로 뺀다** — FK 의 `SET NULL` 에 맡기면
    티켓 타임라인에 「왜 회차에서 빠졌는지」가 조용히 빈다(활동 한 줄을 남긴다).
    회의록은 FK CASCADE 로 함께 사라진다 — 연 적 없는 회차의 회의록은 사실상 없다.
    """
    sprint = get_scoped_sprint_or_404(db, sprint_id, user)
    ensure_sprint_manageable(db, user, sprint)
    if sprint.state == SPRINT_ACTIVE:
        raise ValidationAppError("진행 중인 회차는 삭제할 수 없습니다. 먼저 「회차 닫기」로 닫아 주세요.")
    if sprint.state == SPRINT_CLOSED:
        raise ValidationAppError("닫은 회차는 기록으로 남습니다. 삭제할 수 없습니다.")
    stamp = now or utcnow()
    detached = 0
    for ticket in db.execute(
        select(Ticket).where(Ticket.sprint_id == sprint.id)
    ).scalars().all():
        ticket.sprint_id = None
        activity.record(
            db, ticket_id=ticket.id, kind=ACT_SPRINT, actor_id=user.id, field="sprint_id",
            from_value=sprint.id, to_value=None, now=stamp,
        )
        detached += 1
    name = sprint.name
    db.delete(sprint)
    db.flush()
    return {"deleted": True, "name": name, "detached": detached}


def sprint_scope(db: Session, sprint_id: str, user: User) -> dict:
    """이 회차에 담긴 일의 크기. 번다운의 입력이다.

    난이도·예상WD·실제WD 를 유지한 이유가 여기 있다(§5.2) — 버리면 이 계산이 죽는다.

    **집계도 범위를 지난다.** 숫자만 돌려주니 안전해 보이지만, 남의 팀 회차의 티켓 수와
    공수를 읽을 수 있으면 그것으로 그 팀의 상태를 읽는다.
    """
    get_scoped_sprint_or_404(db, sprint_id, user)
    # 🔴 문이 둘이다 — 회차가 보인다고 그 안의 티켓이 다 보이는 것은 아니다. 회의·판과
    # 같은 티켓 절을 한 번 더 지난다(숫자만 돌려줘도 남의 프로젝트 공수는 유출이다).
    tickets = db.execute(
        _visible_tickets_stmt(db, user).where(Ticket.sprint_id == sprint_id)
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
    """상세 화면이 새로 얻는 것 — 이름 · 관계 · 활동."""
    return {
        "key": display_key(ticket),
        "canonical_key": ticket.canonical_key,
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
    ensure_sprint_manageable(db, user, sprint)
    # 닫기는 되돌릴 수 없다(이월이 실제로 티켓을 옮긴다) — 전제부터 확인한다.
    if sprint.state == SPRINT_CLOSED:
        raise ConflictError("이미 닫은 회차입니다.")
    if sprint.state == SPRINT_PLANNED:
        raise ValidationAppError(
            "아직 열지 않은 회차는 닫을 수 없습니다. 잘못 만든 회차라면 삭제할 수 있습니다."
        )
    if target_sprint_id is not None:
        if target_sprint_id == sprint_id:
            raise ValidationAppError(
                "지금 닫는 회차로는 이월할 수 없습니다. 다른 회차를 골라 주세요."
            )
        # 옮길 곳도 범위 안이어야 한다. 한쪽만 보면 안 끝난 일을 남의 팀 회차로 밀어
        # 넣을 수 있고, 그 순간 그 티켓들은 **내 범위에서 사라진다**.
        target = get_scoped_sprint_or_404(db, target_sprint_id, user)
        if target.state == SPRINT_CLOSED:
            raise ValidationAppError("이미 닫힌 회차로는 이월할 수 없습니다.")
        # 담기(`move`)·생성이 지키는 불변식과 같다 — 같은 팀의 열린 회차로만 보낸다.
        # 대상이 없으면(`None`) 안 끝난 티켓은 백로그로 돌아간다 — 다음 회차가 아직
        # 없어도 닫을 수 있고, 그것이 기본값이다.
        if target.department_id != sprint.department_id or target.org_id != sprint.org_id:
            raise ValidationAppError("다른 팀의 회차로는 이월할 수 없습니다. 같은 팀의 열린 회차만 고를 수 있습니다.")

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
