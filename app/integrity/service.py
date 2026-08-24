"""조직 정합성 진단 — **판정할 수 없는 데이터를 사람에게 보여 준다** (0060).

## 왜 이 화면이 필요한가

이 앱의 접근 모델은 "소속을 모르면 닫는다"(fail-closed)로 바뀌었다. 그 규칙 하나만 두면
안전하기는 한데 **아무도 원인을 못 찾는다** — 증상이 "권한이 없습니다" 가 아니라 "목록이
비어 있음" 이기 때문이다. 닫는 규칙과 그 대상을 드러내는 화면은 한 배포에 함께 있어야 한다.

그래서 여기서 딱 두 가지만 한다:

  1. **소속을 판정할 수 없는 것들을 센다** — 사용자·티켓·문서·프로젝트
  2. 그중 Portal 이 고칠 수 있는 것은 **일괄 지정** 액션을 준다

## 자동으로 고치지 않는다

세는 것과 고치는 것을 섞지 않는다. "부서를 모르니 조직 직속으로 하자", "프로젝트 이름이
비슷하니 이걸로 하자" 같은 추측은 언제나 넓히는 쪽으로 틀리고, 틀린 것을 아무도 신고하지
않는다(화면이 잘 보이니까). 사람이 목록을 보고 지정한다.

이관해 온 티켓이 달고 있는 옛 소스의 relation 목록은 여기서 못 고친다 — **무엇을 어디서
고쳐야 하는지**를 말해 주는 것까지가 이 화면의 몫이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import ownership
from app.core.errors import NotFoundError, ValidationAppError
from app.core.models_base import split_names
from app.core.org_tree import DeptTree
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

# 목록으로 보여 줄 표본 상한. 전량을 내리면 큰 설치에서 응답이 수 MB 가 되고, 화면은 그걸
# 다 그리지도 못한다. **총 건수는 따로 센다** — 표본이 잘렸다고 숫자까지 잘리면 그 화면은
# "몇 건인지 모르겠다" 를 말하게 된다.
SAMPLE_LIMIT = 50


@dataclass(frozen=True)
class Finding:
    """한 종류의 정합성 문제.

    `fixable_here` 는 "Portal 이 이 화면에서 고칠 수 있는가" 다. 외부 소스가 정본인 것은
    False 이고, 그때 `remedy` 가 어디서 고쳐야 하는지를 말한다.
    """

    key: str
    title: str
    why: str
    remedy: str
    count: int
    items: list[dict]
    fixable_here: bool = False


def _sample(rows) -> list[dict]:
    return list(rows)[:SAMPLE_LIMIT]


def _users_without_membership(db: Session) -> Finding:
    stmt = (
        select(User)
        .where(
            User.active.is_(True),
            User.archived_at.is_(None),
            or_(User.department_id.is_(None), User.department_id == ""),
            User.membership_kind != MEMBERSHIP_ORGANIZATION,
        )
        .order_by(User.display_name)
    )
    rows = list(db.execute(stmt).scalars())
    return Finding(
        key="users_without_membership",
        title="소속이 지정되지 않은 사용자",
        why=(
            "부서도 조직 직속도 지정되지 않았습니다. 이 계정은 조직 데이터(프로젝트, 티켓, 문서)를 "
            "아무것도 볼 수 없습니다. 부서 미지정과 조직 직속은 서로 다른 사실이라 서버가 "
            "추측하지 않습니다."
        ),
        remedy="부서를 지정하거나, 부서 없이 조직 전체를 보는 자리라면 '조직 직속'으로 지정하세요.",
        count=len(rows),
        items=_sample(
            {"id": u.id, "display_name": u.display_name, "email": u.email, "role": u.role}
            for u in rows
        ),
        fixable_here=True,
    )


def _tickets_without_one_project(db: Session) -> Finding:
    counts = dict(
        db.execute(
            select(TicketCache.project_link, func.count())
            .where(TicketCache.project_link != PROJECT_LINK_OK)
            .group_by(TicketCache.project_link)
        ).all()
    )
    rows = list(
        db.execute(
            select(TicketCache)
            .where(TicketCache.project_link != PROJECT_LINK_OK)
            .order_by(TicketCache.notion_ticket_number.desc().nullslast())
            .limit(SAMPLE_LIMIT)
        ).scalars()
    )
    reason = {
        PROJECT_LINK_MISSING: "프로젝트가 연결되지 않음",
        PROJECT_LINK_AMBIGUOUS: "프로젝트가 2개 이상 연결됨",
        PROJECT_LINK_UNRESOLVED: "연결된 프로젝트를 찾을 수 없음(이관 전이거나 삭제됨)",
    }
    return Finding(
        key="tickets_without_one_project",
        title="프로젝트가 정확히 하나가 아닌 티켓",
        why=(
            "티켓의 조직 소속은 프로젝트가 정합니다. 프로젝트가 없거나 둘 이상이면 어느 부서 "
            "것인지 판정할 수 없어, 전체 관리자 외에는 아무에게도 보이지 않습니다. "
            "임의로 하나를 고르지 않습니다. 잘못 고르면 그 티켓이 다른 부서로 새고 아무도 "
            "그 사실을 알아채지 못합니다."
        ),
        remedy=(
            "티켓 상세 화면에서 그 티켓의 프로젝트를 정확히 하나로 지정하세요. "
            "프로젝트를 찾을 수 없는 티켓은 먼저 그 프로젝트를 만들어야 합니다."
        ),
        count=sum(counts.values()),
        items=_sample(
            {
                "id": api_page_id(t),
                "number": t.notion_ticket_number,
                "title": t.title,
                "state": t.project_link,
                "reason": reason.get(t.project_link, t.project_link),
            }
            for t in rows
        ),
    )


def _tickets_with_unmapped_assignees(db: Session) -> Finding:
    """담당자가 적혀 있는데 포털 계정으로 해석되지 않는 티켓.

    **미할당이 아니다.** 0060 이전에는 이 둘을 한 목록에 섞었고(둘 다 "담당자를 모른다"),
    그 결과 배정 대기와 데이터 정합성 문제가 같은 화면에 쌓여 어느 쪽도 처리되지 않았다.
    """
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    known = set(
        db.execute(
            select(UserNotionMapping.notion_user_id).where(
                UserNotionMapping.status == STATUS_VERIFIED,
                UserNotionMapping.notion_user_id.is_not(None),
            )
        ).scalars()
    )
    rows = [
        t
        for t in db.execute(
            select(TicketCache).where(
                TicketCache.assignee_notion_ids.is_not(None),
                TicketCache.assignee_notion_ids != "",
            )
        ).scalars()
        if not (set(split_names(t.assignee_notion_ids)) & known)
    ]
    return Finding(
        key="tickets_with_unmapped_assignees",
        title="담당자를 포털 계정으로 연결하지 못한 티켓",
        why=(
            "원본에 담당자가 있지만 그 사람이 포털 계정과 연결되어 있지 않습니다. 티켓 자체는 "
            "프로젝트 범위에서 정상적으로 보이지만, '내 티켓'과 담당자별 집계에는 잡히지 않습니다."
        ),
        remedy="사용자와 권한 > Notion 사용자 연결에서 그 사람의 계정을 연결하세요.",
        count=len(rows),
        items=_sample(
            {"id": api_page_id(t), "number": t.notion_ticket_number, "title": t.title}
            for t in rows
        ),
    )


def _spaces_without_ownership(db: Session) -> Finding:
    """소속이 지정되지 않은 **지식 공간** (S14).

    예전에는 미러(`document_cache.owner_kind`)를 세고 문서마다 소속을 일괄 지정하는
    고치기 단추가 붙어 있었다. 그 축이 사라졌다 — 정본인 `documents` 에는 소속 컬럼이
    아예 없고, 문서의 가시성은 자기 공간이 정한다(D-245 · `app/knowledge/models.py`).
    문서에 소속을 적는 칸을 되살리면 공간과 두 벌이 되고, 어긋난 문서는
    「목록에는 없는데 링크로는 열린다」가 된다.

    그래서 **진짜 원인인 공간을 센다.** 이것이 추상적인 걱정이 아니라는 것은 실측으로
    확인됐다: 이관 공간 하나가 `owner_kind='unset'` 이라 어느 가시성 갈래에도 안 걸렸고,
    그 사이 활성 사용자 24명 중 전역 관리자 넷 말고는 문서 110건을 하나도 못 봤다.

    고치기 단추는 여기 두지 않는다. 공간의 소속을 바꾸는 자리는 이미
    `PATCH /api/knowledge/spaces/{id}` 하나이고, 그 경로는 낙관적 잠금과 감사 로그를
    지난다 — 같은 일을 하는 두 번째 쓰기 경로를 만들 이유가 없다.
    """
    from app.knowledge.models import Document, KnowledgeSpace

    rows = list(
        db.execute(
            select(KnowledgeSpace)
            .where(
                KnowledgeSpace.owner_kind == ownership.OWNER_UNSET,
                KnowledgeSpace.archived.is_(False),
            )
            .order_by(KnowledgeSpace.name)
        ).scalars()
    )
    doc_counts = dict(
        db.execute(
            select(Document.space_id, func.count())
            .where(Document.archived.is_(False))
            .group_by(Document.space_id)
        ).all()
    )
    return Finding(
        key="spaces_without_ownership",
        title="소속이 지정되지 않은 지식 공간",
        why=(
            "이 공간이 어느 부서/프로젝트 것인지 포털이 알지 못합니다. 그래서 전체 관리자 "
            "외에는 이 공간의 문서가 목록, 검색, 첨부 어디에서도 보이지 않습니다."
        ),
        remedy="지식 공간 설정에서 그 공간의 소속(부서 또는 프로젝트)을 지정하세요.",
        count=len(rows),
        items=_sample(
            {"id": s.id, "name": s.name,
             "reason": f"문서 {int(doc_counts.get(s.id, 0))}건이 닫혀 있습니다."}
            for s in rows
        ),
    )


def _projects_without_scope(db: Session) -> Finding:
    rows = list(
        db.execute(
            select(Project).where(
                Project.archived_at.is_(None),
                or_(Project.org_id.is_(None), Project.org_id == ""),
            ).order_by(Project.name)
        ).scalars()
    )
    return Finding(
        key="projects_without_scope",
        title="조직이 지정되지 않은 프로젝트",
        why=(
            "조직이 없으면 소속을 판정할 수 없어 전체 관리자만 볼 수 있고, 그 프로젝트에 "
            "달린 티켓도 함께 닫힙니다."
        ),
        remedy="프로젝트의 조직(그리고 필요하면 부서)을 지정하세요.",
        count=len(rows),
        items=_sample({"id": p.id, "name": p.name, "code": p.code} for p in rows),
    )


def _resources_on_inactive_departments(db: Session) -> Finding:
    """비활성 부서에 매달린 자원. 비활성은 '새로 고를 수 없다' 는 뜻이지 '없다' 가 아니라서
    범위 계산은 그대로 통과한다 — 그래서 조용히 남고, 조직 개편 때 잊힌다."""
    inactive = set(
        db.execute(select(Department.id).where(Department.active.is_(False))).scalars()
    )
    if not inactive:
        return Finding(
            key="resources_on_inactive_departments",
            title="비활성 부서에 연결된 자원",
            why="비활성 부서는 새로 고를 수 없지만 기존 연결은 그대로 남습니다.",
            remedy="그 자원을 활성 부서로 옮기거나, 부서를 다시 활성화하세요.",
            count=0, items=[],
        )
    from app.knowledge.models import KnowledgeSpace

    users = list(db.execute(select(User).where(User.department_id.in_(inactive))).scalars())
    projects = list(db.execute(select(Project).where(Project.dept_id.in_(inactive))).scalars())
    # 문서가 아니라 **공간**이 부서를 가리킨다 (D-245). 문서를 세면 같은 공간에 든
    # 수십 건이 같은 이유로 줄줄이 나와, 정작 고칠 대상 하나가 목록에 묻힌다.
    spaces = list(
        db.execute(
            select(KnowledgeSpace).where(KnowledgeSpace.owner_dept_id.in_(inactive))
        ).scalars()
    )
    items = (
        [{"kind": "user", "id": u.id, "name": u.display_name} for u in users]
        + [{"kind": "project", "id": p.id, "name": p.name} for p in projects]
        + [{"kind": "space", "id": s.id, "name": s.name} for s in spaces]
    )
    return Finding(
        key="resources_on_inactive_departments",
        title="비활성 부서에 연결된 자원",
        why=(
            "비활성 부서는 새로 고를 수 없을 뿐 기존 연결은 그대로 동작합니다. 조직 개편 "
            "때 이 자원들이 잊히기 쉽습니다."
        ),
        remedy="그 자원을 활성 부서로 옮기거나, 부서를 다시 활성화하세요.",
        count=len(items),
        items=_sample(items),
    )


def _admin_scope_overview(db: Session) -> dict:
    """조직/부서 관리자 현황 — **설정은 있는데 아무도 안 쓰는** 상태를 드러낸다.

    `admin_scope` 조합(조직관리자/부서관리자)은 코드에 오래 있었지만 실제 계정은 전원
    `global` 이었다. 그러면 범위 로직이 정상 동작해도 화면 결과는 예전과 같다 — 그 사실을
    숫자로 보여 주지 않으면 아무도 모른다.
    """
    tree = DeptTree.load(db)
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
    return {
        "total": len(rows),
        "by_scope": by_scope,
        "items": _sample(
            {
                "id": u.id,
                "display_name": u.display_name,
                "role": u.role,
                "admin_scope": u.admin_scope,
                "scope_path": [
                    {"id": n.id, "name": n.name}
                    for n in tree.path(u.scope_dept_id or u.department_id)
                ] if u.admin_scope == ADMIN_SCOPE_DEPT else [],
            }
            for u in rows
        ),
    }


_CHECKS = (
    _users_without_membership,
    _tickets_without_one_project,
    _tickets_with_unmapped_assignees,
    _spaces_without_ownership,
    _projects_without_scope,
    _resources_on_inactive_departments,
)


def report(db: Session) -> dict:
    """읽기 전용 진단 한 벌. 아무 데이터도 바꾸지 않는다."""
    findings = [f for f in (check(db) for check in _CHECKS)]
    return {
        "sample_limit": SAMPLE_LIMIT,
        "total_issues": sum(f.count for f in findings),
        "findings": [
            {
                "key": f.key, "title": f.title, "why": f.why, "remedy": f.remedy,
                "count": f.count, "items": f.items, "fixable_here": f.fixable_here,
            }
            for f in findings
        ],
        "admins": _admin_scope_overview(db),
    }


# ── 일괄 지정 ────────────────────────────────────────────────────────────────

def assign_membership(
    db: Session, *, user_ids: list[str], department_id: str | None, organization_direct: bool,
) -> int:
    """소속 미지정 사용자에게 소속을 지정한다. 바뀐 건수를 돌려준다.

    부서와 조직 직속 중 **하나만** 받는다. 둘 다 주면 무엇을 의도했는지 알 수 없고, 둘 다
    안 주면 아무 것도 안 바뀐다 — 어느 쪽도 조용히 넘기지 않는다.
    """
    if bool(department_id) == bool(organization_direct):
        raise ValidationAppError("부서 지정과 조직 직속 중 하나만 고르세요.")
    if not user_ids:
        return 0
    dept = db.get(Department, department_id) if department_id else None
    if department_id and dept is None:
        raise NotFoundError("부서를 찾을 수 없습니다.")

    rows = list(db.execute(select(User).where(User.id.in_(user_ids))).scalars())
    changed = 0
    for user in rows:
        if dept is not None:
            user.department_ref = dept
            user.membership_kind = "department"
        else:
            user.department_ref = None
            user.membership_kind = MEMBERSHIP_ORGANIZATION
        changed += 1
    return changed


__all__ = [
    "Finding", "SAMPLE_LIMIT", "report",
    "assign_membership",
    "MEMBERSHIP_UNASSIGNED",
]
