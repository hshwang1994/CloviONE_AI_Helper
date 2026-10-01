"""조직 정합성 진단 — **판정할 수 없는 데이터를 사람에게 보여 준다** (0060, 계획 3.2).

## 왜 이 화면이 필요한가

이 앱의 접근 모델은 "소속을 모르면 닫는다"(fail-closed)다. 그 규칙 하나만 두면 안전하기는 한데
**아무도 원인을 못 찾는다** — 증상이 "권한이 없습니다" 가 아니라 "목록이 비어 있음" 이기 때문이다.
닫는 규칙과 그 대상을 드러내는 화면은 한 배포에 함께 있어야 한다.

## 구조 (계획 3.2)

검사 하나(`Check`)는 **행을 가진 표 하나**를 본다: 사람 · 티켓 · 프로젝트 · 지식 공간 · 회차. 화면은
그 표를 기준으로 탭을 나눈다(`TABS`). 검사마다 **전량 목록**을 만들고, 요약(`report`)은 건수만,
목록(`list_items`)은 검색 · 정렬 · 페이지를 준다. 예전에는 한 응답이 검사 아홉 개를 50건 표본씩
실어서 51번째 행부터는 볼 길이 없었다.

## 자동으로 고치지 않는다

세는 것과 고치는 것을 섞지 않는다. "부서를 모르니 조직 직속으로 하자" 같은 추측은 언제나 넓히는
쪽으로 틀리고, 틀린 것을 아무도 신고하지 않는다. 사람이 목록을 보고 지정한다. 일괄 작업은 **이미
있는 쓰기 경로**만 부른다(소속 지정 · 티켓 프로젝트 지정 · 회차에서 빼기) — 감사와 알림이 갈라지지 않게.
나머지 행은 대상 화면으로 가는 링크를 준다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import ownership
from app.core.errors import NotFoundError, ValidationAppError
from app.core.models_base import split_names
from app.core.org_tree import DeptTree
from app.core.search_text import fold
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import (
    PROJECT_LINK_AMBIGUOUS,
    PROJECT_LINK_MISSING,
    PROJECT_LINK_OK,
    PROJECT_LINK_UNRESOLVED,
    TicketCache,
    api_page_id,
)
from app.users.models import (
    ADMIN_SCOPE_DEPT,
    ADMIN_SCOPE_GLOBAL,
    ADMIN_SCOPE_ORG,
    MEMBERSHIP_ORGANIZATION,
    MEMBERSHIP_UNASSIGNED,
    ROLE_ADMIN,
    ROLE_SYSTEM_ADMIN,
    User,
)

# 요약(`report`)이 검사마다 함께 싣는 표본. 목록은 `list_items` 가 페이지로 준다.
SAMPLE_LIMIT = 50

TAB_PEOPLE = "people"
TAB_TICKETS = "tickets"
TAB_RESOURCES = "resources"
TAB_SPRINTS = "sprints"

TABS: tuple[tuple[str, str], ...] = (
    (TAB_PEOPLE, "사람"),
    (TAB_TICKETS, "티켓"),
    (TAB_RESOURCES, "프로젝트와 문서 공간"),
    (TAB_SPRINTS, "회차"),
)

# 일괄 작업의 이름. 화면이 이 이름으로 단추를 고른다(`frontend/src/screens/integrity/checks.js`).
# 각 작업은 **이미 있는 쓰기 경로**를 부른다(`app/integrity/router.py`) - 감사와 알림이 갈라지지 않게.
FIX_MEMBERSHIP = "membership"                  # 사용자 편집과 같은 소속 규칙
FIX_TICKET_PROJECT = "ticket_project"          # 티켓 편집(`tickets.service.update_ticket`)
FIX_REMOVE_FROM_SPRINT = "remove_from_sprint"  # 보드 이동(`work.service.move`)
FIX_SPACE_OWNER = "space_owner"                # 공간 수정(`knowledge.service.update_space`)
FIX_PROJECT_DEPARTMENT = "project_department"  # 프로젝트 수정(`projects.service.update_project`)
FIX_SPRINT_TEAM = "sprint_team"                # 회차 수정(`work.service.update_sprint`)


@dataclass(frozen=True)
class Check:
    key: str
    tab: str
    kind: str
    title: str
    why: str
    remedy: str
    items: Callable[[Session], list[dict]]
    fixes: tuple[str, ...] = ()
    # 「문제 종류」 칸에 서는 짧은 이름(D-530) - `title` 은 문장이라 필터 칸에서 여섯 글자 뒤로 잘렸다. 화면은 칸과 메뉴에 이것을,
    # 고른 검사의 머리에 `title` 을 쓴다.
    short: str = ""


def _search_text(*parts) -> str:
    return fold(" ".join(str(p) for p in parts if p))


def _live_tickets():
    """정리 대상이 되는 티켓 - 휴지통과 옛 소스에서 사라진 행은 뺀다(계획 2.6).

    두 행은 티켓 화면에서 열리지 않는다. 세면 이 화면이 가리키는 곳에 고칠 대상이 없고, 건수는
    어떤 조치로도 줄지 않는다. 휴지통 판정은 보드, 진행률, 리포트와 같은 절이다.
    """
    from app.tickets.query import not_trashed_clause

    return (TicketCache.notion_missing_at.is_(None), not_trashed_clause())


def _unassigned_membership_filter():
    """「소속이 지정되지 않은 사용자」의 정의 — **세는 쪽과 고치는 쪽이 같은 문장을 쓴다.**

    정의가 두 벌이면 화면이 세어 준 목록과 버튼이 고치는 목록이 갈라진다. 조직 트리의 「미지정」
    수(`app/org/tree.py`)도 이 정의를 쓴다(`app/users/service.py::unassigned_membership_clause`).
    """
    from app.users.service import unassigned_membership_clause

    return unassigned_membership_clause(active_only=True)


def _inactive_department_ids(db: Session) -> set[str]:
    return set(db.execute(select(Department.id).where(Department.active.is_(False))).scalars())


def _dept_names(db: Session) -> dict[str, str]:
    return dict(db.execute(select(Department.id, Department.name)).all())


def _user_row(u: User, *, reason: str, department: str | None = None) -> dict:
    return {
        "id": u.id, "title": u.display_name, "display_name": u.display_name, "email": u.email,
        "role": u.role, "department": department, "link": f"#/users/{u.id}", "reason": reason,
        "_search": _search_text(u.display_name, u.email),
    }


# ── 사람 ──────────────────────────────────────────────────────────────────────


def _users_without_membership(db: Session) -> list[dict]:
    rows = db.execute(
        select(User).where(*_unassigned_membership_filter()).order_by(User.display_name, User.id)
    ).scalars()
    return [_user_row(u, reason="부서도 조직 직속도 지정되지 않았습니다.") for u in rows]


def _users_on_inactive_department(db: Session) -> list[dict]:
    inactive = _inactive_department_ids(db)
    if not inactive:
        return []
    names = _dept_names(db)
    rows = db.execute(
        select(User).where(
            User.active.is_(True), User.archived_at.is_(None), User.department_id.in_(inactive),
        ).order_by(User.display_name, User.id)
    ).scalars()
    return [
        _user_row(u, reason=f"비활성 부서({names.get(u.department_id, '?')})에 속해 있습니다.",
                  department=names.get(u.department_id))
        for u in rows
    ]


# ── 티켓 ──────────────────────────────────────────────────────────────────────


def _ticket_row(t: TicketCache, *, reason: str, **extra) -> dict:
    page_id = api_page_id(t)
    key = t.canonical_key or (str(t.notion_ticket_number) if t.notion_ticket_number else None)
    return {
        "id": page_id, "uid": t.id, "key": key, "number": t.notion_ticket_number,
        "title": t.title or "(제목 없음)", "status": t.status,
        "link": f"#/tickets/{page_id}", "reason": reason,
        "_search": _search_text(t.title, key),
        **extra,
    }


def _tickets_without_one_project(db: Session) -> list[dict]:
    reason = {
        PROJECT_LINK_MISSING: "프로젝트가 연결되지 않았습니다.",
        PROJECT_LINK_AMBIGUOUS: "프로젝트가 둘 이상 연결됐습니다.",
        PROJECT_LINK_UNRESOLVED: "연결된 프로젝트를 찾을 수 없습니다.",
    }
    rows = db.execute(
        select(TicketCache)
        .where(TicketCache.project_link != PROJECT_LINK_OK, *_live_tickets())
        .order_by(TicketCache.notion_ticket_number.desc().nullslast(), TicketCache.id)
    ).scalars()
    return [
        _ticket_row(t, reason=reason.get(t.project_link, t.project_link), state=t.project_link)
        for t in rows
    ]


def _known_assignee_tokens(db: Session) -> set[str]:
    """담당자 토큰으로 **아는 값** — verified 매핑의 옛 id 와 모든 계정의 자기 id(D-285)."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    known = set(
        db.execute(
            select(UserNotionMapping.notion_user_id).where(
                UserNotionMapping.status == STATUS_VERIFIED,
                UserNotionMapping.notion_user_id.is_not(None),
            )
        ).scalars()
    )
    known.update(db.execute(select(User.id)).scalars())
    return known


def _tickets_with_unmapped_assignees(db: Session) -> list[dict]:
    """담당자가 적혀 있는데 포털 계정으로 해석되지 않는 티켓. **미할당이 아니다**(0060)."""
    known = _known_assignee_tokens(db)
    out = []
    for t in db.execute(
        select(TicketCache).where(
            TicketCache.assignee_notion_ids.is_not(None),
            TicketCache.assignee_notion_ids != "",
            *_live_tickets(),
        ).order_by(TicketCache.notion_ticket_number.desc().nullslast(), TicketCache.id)
    ).scalars():
        if not (set(split_names(t.assignee_notion_ids)) & known):
            out.append(_ticket_row(t, reason="담당자 값이 이 포털의 어느 계정과도 맞지 않습니다."))
    return out


def _closed_account_tokens(db: Session) -> dict[str, dict[str, str]]:
    """담당자 토큰 → 그 토큰이 가리키는 **닫힌 계정**(보관 · 비활성)의 이름과 상태(D-285 두 축)."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    rows = db.execute(
        select(User.id, User.display_name, User.archived_at, UserNotionMapping.notion_user_id)
        .outerjoin(
            UserNotionMapping,
            (UserNotionMapping.user_id == User.id)
            & (UserNotionMapping.status == STATUS_VERIFIED),
        )
        .where(or_(User.active.is_(False), User.archived_at.is_not(None)))
    ).all()
    out: dict[str, dict[str, str]] = {}
    for uid, name, archived_at, nid in rows:
        who = {"name": name, "state": "보관" if archived_at is not None else "비활성"}
        out.setdefault(uid, who)
        if nid:
            out.setdefault(nid, who)
    return out


def _tickets_assigned_to_closed_accounts(db: Session) -> list[dict]:
    """보관 · 비활성 계정이 담당으로 남은 **남은 일**. 끝난 일은 넘길 것이 없어서 안 센다.

    누구에게 넘길지는 사람이 정한다 — 티켓 상세의 담당자 칸과 오프보딩 화면(퇴사자 일괄 인계)이
    그 자리다. 행마다 오프보딩 링크를 함께 준다.
    """
    from app.tickets.service import _TERMINAL

    closed = _closed_account_tokens(db)
    out: list[dict] = []
    if not closed:
        return out
    for t in db.execute(
        select(TicketCache)
        .where(
            TicketCache.assignee_notion_ids.is_not(None),
            TicketCache.assignee_notion_ids != "",
            *_live_tickets(),
            TicketCache.completed_at.is_(None),
            or_(TicketCache.status.is_(None), TicketCache.status.not_in(tuple(sorted(_TERMINAL)))),
        )
        .order_by(TicketCache.notion_ticket_number.desc().nullslast(), TicketCache.id)
    ).scalars():
        labels: list[str] = []
        for token in split_names(t.assignee_notion_ids):
            who = closed.get(token)
            if who is None:
                continue
            label = f"{who['name']}({who['state']})"
            if label not in labels:
                labels.append(label)
        if labels:
            out.append(_ticket_row(
                t, reason=f"담당자 {', '.join(labels)} 님의 계정이 닫혀 있습니다.",
                assignees=", ".join(labels),
            ))
    return out


def _open_sprint_tickets_off_team(db: Session) -> list[dict]:
    """열린 회차에 담긴 **다른 팀의 티켓** (D-482). 닫힌 회차는 기록이라 세지 않는다."""
    from app.work.models import SPRINT_CLOSED, Sprint

    rows = db.execute(
        select(TicketCache, Sprint, Project)
        .join(Sprint, Sprint.id == TicketCache.sprint_id)
        .outerjoin(Project, Project.id == TicketCache.project_uid)
        .where(
            Sprint.state != SPRINT_CLOSED,
            Sprint.department_id.is_not(None),
            or_(Project.id.is_(None), Project.dept_id.is_(None),
                Project.dept_id != Sprint.department_id),
            *_live_tickets(),
        )
        .order_by(Sprint.name, TicketCache.seq, TicketCache.id)
    ).all()
    return [
        _ticket_row(
            t, reason=f"회차({s.name})의 팀과 티켓 프로젝트의 부서가 다릅니다.",
            ticket_id=t.id, page_id=api_page_id(t), sprint_id=s.id, sprint=s.name,
            project_id=p.id if p is not None else None,
            project_dept_id=p.dept_id if p is not None else None,
            sprint_dept_id=s.department_id,
        )
        for t, s, p in rows
    ]


# ── 프로젝트와 문서 공간 ─────────────────────────────────────────────────────


def _project_row(p: Project, *, reason: str, department: str | None = None) -> dict:
    return {
        "id": p.id, "title": p.name, "name": p.name, "code": p.code, "department": department,
        "link": f"#/projects/{p.id}", "reason": reason, "_search": _search_text(p.name, p.code),
    }


def _projects_without_scope(db: Session) -> list[dict]:
    """조직이 없는 프로젝트. **제품이 만들 수 없는** 옛 데이터다(`create_project` 는 늘 조직을 넣는다).
    `0033` 이 기본 조직으로 채웠고, 이 검사는 감시로 남는다."""
    rows = db.execute(
        select(Project).where(
            Project.archived_at.is_(None),
            or_(Project.org_id.is_(None), Project.org_id == ""),
        ).order_by(Project.name, Project.id)
    ).scalars()
    return [_project_row(p, reason="조직이 지정되지 않았습니다.") for p in rows]


def _projects_on_inactive_department(db: Session) -> list[dict]:
    inactive = _inactive_department_ids(db)
    if not inactive:
        return []
    names = _dept_names(db)
    rows = db.execute(
        select(Project).where(Project.archived_at.is_(None), Project.dept_id.in_(inactive))
        .order_by(Project.name, Project.id)
    ).scalars()
    return [
        _project_row(p, reason=f"비활성 부서({names.get(p.dept_id, '?')})에 속해 있습니다.",
                     department=names.get(p.dept_id))
        for p in rows
    ]


def _space_row(s, *, reason: str, docs: int) -> dict:
    return {
        "id": s.id, "title": s.name, "name": s.name, "doc_count": docs,
        "link": f"#/knowledge?space={s.id}", "reason": reason, "_search": _search_text(s.name),
    }


def _doc_counts(db: Session) -> dict[str, int]:
    from app.knowledge.models import Document

    return dict(
        db.execute(
            select(Document.space_id, func.count())
            .where(Document.archived.is_(False))
            .group_by(Document.space_id)
        ).all()
    )


def _spaces_without_ownership(db: Session) -> list[dict]:
    """소속이 지정되지 않은 **지식 공간** (S14, D-245). 문서의 가시성은 자기 공간이 정한다."""
    from app.knowledge.models import KnowledgeSpace

    counts = _doc_counts(db)
    rows = db.execute(
        select(KnowledgeSpace)
        .where(KnowledgeSpace.owner_kind == ownership.OWNER_UNSET, KnowledgeSpace.archived.is_(False))
        .order_by(KnowledgeSpace.name, KnowledgeSpace.id)
    ).scalars()
    return [
        _space_row(s, reason=f"문서 {int(counts.get(s.id, 0))}건이 닫혀 있습니다.", docs=int(counts.get(s.id, 0)))
        for s in rows
    ]


def _spaces_on_inactive_department(db: Session) -> list[dict]:
    from app.knowledge.models import KnowledgeSpace

    inactive = _inactive_department_ids(db)
    if not inactive:
        return []
    names = _dept_names(db)
    counts = _doc_counts(db)
    rows = db.execute(
        select(KnowledgeSpace)
        .where(KnowledgeSpace.archived.is_(False), KnowledgeSpace.owner_dept_id.in_(inactive))
        .order_by(KnowledgeSpace.name, KnowledgeSpace.id)
    ).scalars()
    return [
        _space_row(s, reason=f"비활성 부서({names.get(s.owner_dept_id, '?')})의 공간입니다.",
                   docs=int(counts.get(s.id, 0)))
        for s in rows
    ]


# ── 회차 ──────────────────────────────────────────────────────────────────────


def _sprints_without_team(db: Session) -> list[dict]:
    """팀이 정해지지 않은 **열린** 회차 (D-482). 닫힌 회차는 팀을 고칠 수 없고(`update_sprint` 가 막는다)
    기록일 뿐이라 세지 않는다 - 세면 이 건수는 어떤 조치로도 0 이 되지 않는다. 닫힌 수는 참고로 따로 준다."""
    from app.work.models import SPRINT_CLOSED, Sprint

    rows = db.execute(
        select(Sprint).where(Sprint.department_id.is_(None), Sprint.state != SPRINT_CLOSED)
        .order_by(Sprint.starts_on.desc(), Sprint.name, Sprint.id)
    ).scalars()
    return [
        {
            "id": s.id, "title": s.name, "name": s.name, "state": s.state, "org_id": s.org_id,
            "starts_on": s.starts_on.isoformat() if s.starts_on else None,
            "ends_on": s.ends_on.isoformat() if s.ends_on else None,
            # 링크가 없다. 작업 보드는 팀의 회차만 보여 주므로 팀 없는 회차는 어느 판에도 안 뜬다.
            # 그 자리가 없어서 이 화면이 팀 지정(`FIX_SPRINT_TEAM`)을 직접 준다.
            "link": None, "reason": "팀이 정해지지 않았습니다.",
            "_search": _search_text(s.name),
        }
        for s in rows
    ]


def _closed_sprints_without_team(db: Session) -> int:
    from app.work.models import SPRINT_CLOSED, Sprint

    return int(db.execute(
        select(func.count()).select_from(Sprint).where(
            Sprint.department_id.is_(None), Sprint.state == SPRINT_CLOSED,
        )
    ).scalar_one())


CHECKS: tuple[Check, ...] = (
    Check("users_without_membership", TAB_PEOPLE, "user", "소속이 지정되지 않은 사용자",
          "부서도 조직 직속도 지정되지 않았습니다. 이 계정은 조직 데이터(프로젝트, 티켓, 문서)를 아무것도 볼 수 없습니다.",
          "부서를 지정하거나, 부서 없이 조직 전체를 보는 자리라면 '조직 직속'으로 지정하세요.",
          _users_without_membership, (FIX_MEMBERSHIP,), short="소속 없음"),
    Check("users_on_inactive_department", TAB_PEOPLE, "user", "비활성 부서에 속한 사용자",
          "비활성 부서는 새로 고를 수 없을 뿐 기존 연결은 그대로 동작합니다. 조직 개편 때 이 사람들이 잊히기 쉽습니다.",
          "활성 부서로 옮기거나, 부서를 다시 활성화하세요.",
          _users_on_inactive_department, (FIX_MEMBERSHIP,), short="비활성 부서 소속"),
    Check("tickets_without_one_project", TAB_TICKETS, "ticket", "프로젝트가 정확히 하나가 아닌 티켓",
          "티켓의 조직 소속은 프로젝트가 정합니다. 프로젝트가 없거나 둘 이상이면 전체 관리자 외에는 아무에게도 보이지 않습니다.",
          "프로젝트를 정확히 하나로 지정하세요. 서버가 임의로 하나를 고르지 않습니다.",
          _tickets_without_one_project, (FIX_TICKET_PROJECT,), short="프로젝트 지정 오류"),
    Check("tickets_with_unmapped_assignees", TAB_TICKETS, "ticket", "담당자를 포털 계정으로 연결하지 못한 티켓",
          "이관해 온 담당자 값이 이 포털의 계정 어느 것과도 맞지 않습니다. '내 티켓'과 담당자별 집계에 잡히지 않습니다.",
          "티켓 상세에서 담당자를 지금 있는 계정으로 다시 지정하세요.",
          _tickets_with_unmapped_assignees, short="담당자 미연결"),
    Check("tickets_assigned_to_closed_accounts", TAB_TICKETS, "ticket", "닫힌 계정이 담당인 티켓",
          "담당자가 보관되었거나 비활성인 계정입니다. 이 일은 어느 대기열에서도 눈에 띄지 않습니다. 끝난 티켓은 세지 않습니다.",
          "퇴사한 사람의 일은 오프보딩 화면에서 한 번에 넘기고, 한 건씩은 티켓 상세에서 담당자를 다시 지정하세요.",
          _tickets_assigned_to_closed_accounts, short="닫힌 계정 담당"),
    Check("open_sprint_tickets_off_team", TAB_TICKETS, "ticket", "열린 회차에 담긴 다른 팀의 티켓",
          "회차에는 같은 팀 프로젝트의 티켓만 담깁니다. 팀이 어긋난 티켓은 그 팀의 회의에서 우리 일이 아닌 항목으로 보입니다.",
          "회차에서 빼거나, 프로젝트의 부서를 회차의 팀에 맞추세요.",
          _open_sprint_tickets_off_team, (FIX_REMOVE_FROM_SPRINT,), short="다른 팀 회차"),
    Check("projects_without_scope", TAB_RESOURCES, "project", "조직이 지정되지 않은 프로젝트",
          "조직이 없으면 소속을 판정할 수 없어 전체 관리자만 볼 수 있고, 그 프로젝트의 티켓도 함께 닫힙니다.",
          "업그레이드가 기본 조직으로 채웁니다. 그 뒤에도 남으면 데이터를 직접 확인해야 합니다.",
          _projects_without_scope, short="조직 없음"),
    Check("projects_on_inactive_department", TAB_RESOURCES, "project", "비활성 부서의 프로젝트",
          "비활성 부서는 새로 고를 수 없을 뿐 기존 연결은 그대로 동작합니다. 조직 개편 때 잊히기 쉽습니다.",
          "부서를 활성 부서로 바꾸세요. 열린 회차에 담긴 티켓이 있는 프로젝트는 먼저 회차에서 빼야 합니다.",
          _projects_on_inactive_department, (FIX_PROJECT_DEPARTMENT,), short="비활성 부서 프로젝트"),
    Check("spaces_without_ownership", TAB_RESOURCES, "space", "소속이 지정되지 않은 지식 공간",
          "이 공간이 어느 부서나 프로젝트 것인지 알 수 없어, 전체 관리자 외에는 이 공간의 문서가 보이지 않습니다.",
          "소속을 부서나 조직 공통으로 지정하세요. 문서 화면에는 공간의 소속을 고치는 자리가 없어 여기서 지정합니다.",
          _spaces_without_ownership, (FIX_SPACE_OWNER,), short="공간 소속 없음"),
    Check("spaces_on_inactive_department", TAB_RESOURCES, "space", "비활성 부서의 지식 공간",
          "비활성 부서의 공간은 그대로 보이지만 조직 개편 때 잊히기 쉽습니다.",
          "소속을 활성 부서나 조직 공통으로 바꾸세요.",
          _spaces_on_inactive_department, (FIX_SPACE_OWNER,), short="비활성 부서 공간"),
    Check("sprints_without_team", TAB_SPRINTS, "sprint", "팀이 정해지지 않은 열린 회차",
          "회차는 팀이 운영하는 주기입니다. 팀이 없으면 팀 사용자에게 보이지 않고 티켓을 담거나 회차를 열 수 없습니다.",
          "회차를 운영할 팀을 지정하세요. 팀이 없는 회차는 작업 보드에 뜨지 않아 여기서 지정합니다.",
          _sprints_without_team, (FIX_SPRINT_TEAM,), short="팀 없는 회차"),
)
CHECK_BY_KEY = {c.key: c for c in CHECKS}


def _public(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def _admin_scope_overview(db: Session) -> dict:
    """조직/부서 관리자 현황 — 참고 정보다(할 일이 아니다)."""
    rows = list(
        db.execute(
            select(User).where(
                User.role.in_([ROLE_ADMIN, ROLE_SYSTEM_ADMIN]),
                User.active.is_(True),
                User.archived_at.is_(None),
            )
        ).scalars()
    )
    by_scope = {ADMIN_SCOPE_GLOBAL: 0, ADMIN_SCOPE_ORG: 0, ADMIN_SCOPE_DEPT: 0}
    for u in rows:
        by_scope[u.admin_scope] = by_scope.get(u.admin_scope, 0) + 1
    return {"total": len(rows), "by_scope": by_scope}


def report(db: Session) -> dict:
    """요약 한 벌 — 검사마다 건수, 탭마다 합계, 관리자 범위 현황. **아무 데이터도 바꾸지 않는다.**

    검사마다 표본(`items`, 앞 50건)을 함께 싣는다 - 목록 화면은 `list_items` 로 페이지를 받는다.
    """
    findings = []
    tab_counts = {key: 0 for key, _ in TABS}
    for check in CHECKS:
        items = check.items(db)
        tab_counts[check.tab] += len(items)
        findings.append({
            "key": check.key, "tab": check.tab, "kind": check.kind, "title": check.title, "short": check.short or check.title,
            "why": check.why, "remedy": check.remedy, "count": len(items),
            "fixes": list(check.fixes), "fixable_here": bool(check.fixes),
            "items": [_public(i) for i in items[:SAMPLE_LIMIT]],
        })
    total = sum(f["count"] for f in findings)
    return {
        "findings": findings,
        "total_issues": total,
        "tabs": [{"key": key, "label": label, "count": tab_counts[key]} for key, label in TABS],
        "notes": {"closed_sprints_without_team": _closed_sprints_without_team(db)},
        "admins": _admin_scope_overview(db),
    }


SORT_KEYS = ("title", "reason")


def list_items(
    db: Session, key: str, *, q: str | None = None, sort: str | None = None,
    order: str | None = None, offset: int = 0, limit: int = 50,
) -> dict:
    """검사 하나의 목록 — 검색 · 정렬 · 페이지. 모르는 검사는 404, 모르는 정렬 키는 기본 정렬이다."""
    check = CHECK_BY_KEY.get(key)
    if check is None:
        raise NotFoundError("알 수 없는 정합성 검사입니다.")
    items = check.items(db)
    needle = fold(q or "").strip()
    if needle:
        items = [i for i in items if needle in i.get("_search", "")]
    if sort in SORT_KEYS:
        items = sorted(items, key=lambda i: (fold(str(i.get(sort) or "")), str(i.get("id"))),
                       reverse=(order == "desc"))
    total = len(items)
    page = items[offset: offset + limit]
    return {"items": [_public(i) for i in page], "total": total, "kind": check.kind, "fixes": list(check.fixes)}


def list_admins(db: Session, *, q: str | None = None, offset: int = 0, limit: int = 50) -> dict:
    """관리자 범위 현황의 목록(참고 탭). 50명에서 잘리지 않는다."""
    tree = DeptTree.load(db)
    stmt = select(User).where(
        User.role.in_([ROLE_ADMIN, ROLE_SYSTEM_ADMIN]),
        User.active.is_(True),
        User.archived_at.is_(None),
    ).order_by(User.display_name, User.id)
    rows = list(db.execute(stmt).scalars())
    needle = fold(q or "").strip()
    if needle:
        rows = [u for u in rows if needle in _search_text(u.display_name, u.email)]
    total = len(rows)
    page = rows[offset: offset + limit]
    return {
        "total": total,
        "items": [
            {
                "id": u.id, "display_name": u.display_name, "email": u.email, "role": u.role,
                "admin_scope": u.admin_scope,
                "scope_path": [
                    {"id": n.id, "name": n.name}
                    for n in tree.path(u.scope_dept_id or u.department_id)
                ] if u.admin_scope == ADMIN_SCOPE_DEPT else [],
            }
            for u in page
        ],
    }


# ── 일괄 작업 ─────────────────────────────────────────────────────────────────


def _skip_reason(user: User | None) -> str:
    """왜 이 id 는 못 고쳤는가. **건너뛴 사실을 말하지 않으면 아무도 모른다.**"""
    if user is None:
        return "이 계정을 찾을 수 없습니다."
    if user.archived_at is not None:
        return "보관된 계정입니다. 보관을 해제한 뒤에 소속을 지정할 수 있습니다."
    if not user.active:
        return "비활성 계정입니다. 계정을 다시 활성화한 뒤에 소속을 지정할 수 있습니다."
    if not user.department_id and user.membership_kind == MEMBERSHIP_ORGANIZATION:
        return "이미 조직 직속으로 지정된 계정입니다. 소속을 바꾸려면 사용자 화면에서 편집하세요."
    return "이미 활성 부서에 속한 계정입니다. 소속을 바꾸려면 사용자 화면에서 편집하세요."


def assign_membership(
    db: Session, *, user_ids: list[str], department_id: str | None, organization_direct: bool,
) -> dict:
    """소속 미지정 사용자 **또는 비활성 부서에 남은 사용자**에게 소속을 지정한다.

    `{"changed": n, "skipped": [...]}` 를 돌려준다. 부서와 조직 직속 중 **하나만** 받는다.
    대상은 이 화면이 세어 준 사람들(사람 탭의 두 검사)로만 좁힌다 - id 목록만 손대서 이미 활성 부서에
    속한 사람의 부서를 덮어쓰지 못하게. 부서는 사용자 편집과 같은 함수(`resolve_assignable`)가 검사한다.
    """
    from app.org.service import resolve_assignable

    if bool(department_id) == bool(organization_direct):
        raise ValidationAppError("부서 지정과 조직 직속 중 하나만 고르세요.")
    if not user_ids:
        return {"changed": 0, "skipped": []}
    dept = resolve_assignable(db, Department, department_id) if department_id else None

    wanted = list(dict.fromkeys(user_ids))
    known = {u.id: u for u in db.execute(select(User).where(User.id.in_(wanted))).scalars()}
    inactive = _inactive_department_ids(db)
    eligible_stmt = select(User).where(User.id.in_(wanted), *_unassigned_membership_filter())
    eligible = {u.id: u for u in db.execute(eligible_stmt).scalars()}
    if inactive:
        for u in db.execute(
            select(User).where(
                User.id.in_(wanted), User.active.is_(True), User.archived_at.is_(None),
                User.department_id.in_(inactive),
            )
        ).scalars():
            eligible[u.id] = u
    changed = 0
    skipped: list[dict] = []
    for user_id in wanted:
        user = eligible.get(user_id)
        if user is None:
            other = known.get(user_id)
            skipped.append({
                "user_id": user_id,
                "display_name": other.display_name if other is not None else None,
                "reason": _skip_reason(other),
            })
            continue
        if dept is not None:
            user.department_ref = dept
            user.membership_kind = "department"
        else:
            user.department_ref = None
            user.membership_kind = MEMBERSHIP_ORGANIZATION
        changed += 1
    return {"changed": changed, "skipped": skipped}


def listed(db: Session, key: str, ids: list[str]) -> tuple[list[dict], list[dict]]:
    """일괄 작업이 받은 id 중 **그 검사가 지금 세는 것만** 고른다(입력 순서 유지, 중복 제거).

    화면이 본 목록과 요청 사이에 다른 사람이 고쳤을 수 있고, id 목록만 손대서 멀쩡한 행을
    바꿀 수도 있다. 목록 밖 id 는 사유와 함께 돌려준다. 건너뛴 사실을 말하지 않으면 아무도 모른다.
    """
    by_id = {i["id"]: i for i in CHECK_BY_KEY[key].items(db)}
    ok, skipped = [], []
    for item_id in dict.fromkeys(ids):
        item = by_id.get(item_id)
        if item is None:
            skipped.append({"id": item_id, "title": None,
                            "reason": "이 목록에 없는 항목입니다. 이미 정리됐을 수 있습니다."})
        else:
            ok.append(_public(item))
    return ok, skipped


__all__ = [
    "CHECKS", "SAMPLE_LIMIT", "TABS", "report", "list_items", "list_admins",
    "assign_membership", "listed", "MEMBERSHIP_UNASSIGNED",
]
