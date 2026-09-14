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
from app.core.errors import ValidationAppError
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


def _unassigned_membership_filter():
    """「소속이 지정되지 않은 사용자」의 정의 — **세는 쪽과 고치는 쪽이 같은 문장을 쓴다.**

    정의가 두 벌이면 화면이 세어 준 목록과 버튼이 고치는 목록이 갈라진다. 실제로
    갈라져 있었다: 진단은 활성·미보관 계정만 셌는데 일괄 지정(`assign_membership`)은
    보관 계정도, 이미 소속이 있는 사람도 그대로 받아 멀쩡한 소속을 덮어썼다. 정합성을
    고치라고 만든 동작이 정합성을 깨는 자리였다.
    """
    return (
        User.active.is_(True),
        User.archived_at.is_(None),
        or_(User.department_id.is_(None), User.department_id == ""),
        User.membership_kind != MEMBERSHIP_ORGANIZATION,
    )


def _users_without_membership(db: Session) -> Finding:
    stmt = (
        select(User)
        .where(*_unassigned_membership_filter())
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

    🔴 **아는 담당자의 집합이 반쪽이었다.** 여기서는 verified 매핑의 옛 id 만 «아는 값»
    으로 세고 있었는데, 담당자를 가리키는 값은 그 짝이 없으면 **자기 user id** 다
    (`app/tickets/service.py::assignee_token`, D-285). 컷오버 이후에 만든 계정이 담당한
    티켓은 전부 그 축으로 서 있어서, 정상적으로 배정된 티켓이 이 목록에 «연결 실패» 로
    올라왔다 — 그리고 안내는 이제 없는 화면으로 가라고 말했다. 두 축을 모두 아는 값으로
    센다: 옮겨 온 행은 옛 토큰이 그대로 살아 있고, 새 행은 user id 로 선다.
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
    known.update(db.execute(select(User.id)).scalars())
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
            "이관해 온 담당자 값이 이 포털의 계정 어느 것과도 맞지 않습니다. 티켓 자체는 "
            "프로젝트 범위에서 정상적으로 보이지만, '내 티켓'과 담당자별 집계에는 잡히지 않습니다."
        ),
        remedy="티켓 상세에서 담당자를 지금 있는 계정으로 다시 지정하세요.",
        count=len(rows),
        items=_sample(
            {"id": api_page_id(t), "number": t.notion_ticket_number, "title": t.title}
            for t in rows
        ),
    )


def _closed_account_tokens(db: Session) -> dict[str, dict[str, str]]:
    """담당자 토큰 → 그 토큰이 가리키는 **닫힌 계정**(보관·비활성)의 이름과 상태.

    두 축을 모두 담는 이유는 `app/tickets/service.py::_assignee_id_to_user` 와 같다:
    담당자를 가리키는 값은 옛 짝이 있으면 그것이고 없으면 자기 user id 다(D-285).
    한 축만 담으면 이관 이전 계정이나 컷오버 이후 계정 중 한쪽을 통째로 놓친다.
    """
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


def _tickets_assigned_to_closed_accounts(db: Session) -> Finding:
    """보관·비활성 계정이 담당으로 남아 있는 티켓.

    ## 왜 이 항목이 필요한가

    계정을 비활성화하거나 보관하면 그 사람이 들고 있던 티켓이 **모든 대기열에서
    사라진다.** 티켓 화면의 담당자 해석은 활성·미보관 계정만 풀어서(같은 파일의
    `_assignee_id_to_user`) 담당자 칸이 빈 것처럼 보이고, 미할당 대기열은 담당자가
    정말 없는 티켓만 담으므로 거기에도 안 들어간다. 일은 그대로 남아 있는데 그 일을
    보여 주는 화면이 하나도 없는 상태다 — 퇴사·휴직 처리는 매달 있는 일이라
    인수인계 누락으로 곧장 이어진다.

    바로 위 `_tickets_with_unmapped_assignees` 와 겹치지 않는다. 그쪽은 **어느 계정으로도
    풀리지 않는** 담당자고, 여기는 누구인지 아는데 **그 사람이 이미 나갔다**는 뜻이다.

    ## 끝난 일은 안 센다

    이 숫자가 뜻하는 것은 **아직 남은 일**이다. 퇴사자 한 명이 몇 년 치 완료 티켓을 달고
    나가는데(오프보딩은 진행 중인 것만 옮기고 `list_my_tickets` 는 마감 무관이라 완료
    이력은 그 사람에게 그대로 붙어 있다), 그것까지 세면 이 소견은 **어떤 조치로도 0 이
    되지 않는다.** 표본 50건도 완료 티켓으로 차서 정작 멈춰 있는 진행 중인 일이 묻힌다.
    끝난 티켓에는 `remedy`(담당자를 다시 지정하세요)도 맞지 않는다 — 넘길 일이 없다.

    「끝났다」의 정의는 미할당 대기열이 쓰는 것과 같다(`app/tickets/service.py::_TERMINAL`).
    두 벌로 적으면 한쪽만 자라고, 그때 두 화면이 다른 일을 「남은 일」이라고 부른다.

    ## 여기서 고치지 않는다

    누구에게 넘길지는 사람이 정한다. 그 자리는 이미 둘 있다 — 티켓 상세의 담당자 칸과
    오프보딩 화면이다. 세 번째 쓰기 경로를 만들면 감사·알림이 갈라진다.
    """
    from app.tickets.service import _TERMINAL

    closed = _closed_account_tokens(db)
    hits: list[tuple[TicketCache, list[str]]] = []
    if closed:
        for t in db.execute(
            select(TicketCache)
            .where(
                TicketCache.assignee_notion_ids.is_not(None),
                TicketCache.assignee_notion_ids != "",
                # 완료 시각이 찍혔거나 상태가 완료·취소면 남은 일이 아니다. 상태가 비어
                # 있는 행(옛 이관 데이터)은 **남은 일 쪽으로** 읽는다 — 모르는 것을 끝난
                # 것으로 치면 진짜 멈춰 있는 일이 조용히 사라진다.
                TicketCache.completed_at.is_(None),
                or_(
                    TicketCache.status.is_(None),
                    TicketCache.status.not_in(tuple(sorted(_TERMINAL))),
                ),
            )
            .order_by(TicketCache.notion_ticket_number.desc().nullslast())
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
                hits.append((t, labels))
    return Finding(
        key="tickets_assigned_to_closed_accounts",
        title="보관하거나 비활성으로 바꾼 계정이 담당인 티켓",
        why=(
            "담당자가 보관되었거나 비활성인 계정입니다. 티켓 화면은 닫힌 계정을 담당자로 "
            "풀지 않아 담당자 칸이 비어 보이고, 담당자가 정말 없는 티켓만 담는 미할당 "
            "대기열에도 들어가지 않습니다. 그래서 이 일은 어느 목록에서도 눈에 띄지 않습니다. "
            "완료되었거나 취소된 티켓은 넘길 일이 없으므로 여기서 세지 않습니다."
        ),
        remedy=(
            "티켓 상세에서 담당자를 지금 일하는 계정으로 다시 지정하세요. 퇴사자가 들고 "
            "있던 일을 한 번에 넘기려면 오프보딩 화면에서 후임을 지정할 수 있습니다."
        ),
        count=len(hits),
        items=_sample(
            {
                "id": api_page_id(t),
                "number": t.notion_ticket_number,
                "title": t.title,
                "reason": f"담당자 {', '.join(labels)} 님의 계정이 닫혀 있습니다.",
            }
            for t, labels in hits
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


def _sprints_without_team(db: Session) -> Finding:
    """팀이 정해지지 않은 회차 (D-482). 0029 마이그레이션이 **근거 없이 귀속하지 않은**
    레거시다 — 조직·전역 관리자에게만 보이고, 팀을 정하기 전까지 담기·열기가 막힌다."""
    from app.work.models import Sprint

    rows = list(
        db.execute(
            select(Sprint).where(Sprint.department_id.is_(None))
            .order_by(Sprint.starts_on.desc(), Sprint.name)
        ).scalars()
    )
    return Finding(
        key="sprints_without_team",
        title="팀이 정해지지 않은 회차",
        why=(
            "회차는 팀이 운영하는 주기입니다. 팀이 없으면 팀 사용자에게 보이지 않고, "
            "티켓을 담거나 회차를 열 수 없습니다."
        ),
        remedy=(
            "작업 보드에서 회차를 열어 팀을 지정하세요. 닫힌 회차는 기록이므로 그대로 두어도 됩니다."
        ),
        count=len(rows),
        items=_sample(
            {"id": s.id, "name": s.name, "state": s.state, "org_id": s.org_id} for s in rows
        ),
    )


def _open_sprint_tickets_off_team(db: Session) -> Finding:
    """열린 회차에 담긴 **다른 팀의 티켓** (D-482). 담기 규칙은 「티켓의 팀(프로젝트의
    부서) == 회차의 팀」이고 API 가 막지만, 마이그레이션 이전 데이터나 직접 수정으로 어긋난
    행은 여기서만 드러난다. 닫힌 회차는 과거 기록이라 세지 않는다."""
    from app.work.models import SPRINT_CLOSED, Sprint

    rows = list(
        db.execute(
            select(TicketCache, Sprint, Project)
            .join(Sprint, Sprint.id == TicketCache.sprint_id)
            .outerjoin(Project, Project.id == TicketCache.project_uid)
            .where(
                Sprint.state != SPRINT_CLOSED,
                Sprint.department_id.is_not(None),
                or_(Project.id.is_(None), Project.dept_id.is_(None),
                    Project.dept_id != Sprint.department_id),
            )
            .order_by(Sprint.name, TicketCache.seq)
        ).all()
    )
    return Finding(
        key="open_sprint_tickets_off_team",
        title="열린 회차에 담긴 다른 팀의 티켓",
        why=(
            "회차에는 같은 팀 프로젝트의 티켓만 담깁니다. 팀이 어긋난 티켓은 그 팀의 회의에서 "
            "우리 일이 아닌 항목으로 보입니다."
        ),
        remedy="작업 보드에서 그 티켓을 회차에서 빼거나, 프로젝트의 부서를 회차의 팀에 맞추세요.",
        count=len(rows),
        items=_sample(
            {
                "ticket_id": t.id, "page_id": api_page_id(t), "key": t.canonical_key,
                "title": t.title, "sprint_id": s.id, "sprint": s.name,
                "project_id": p.id if p is not None else None,
                "project_dept_id": p.dept_id if p is not None else None,
                "sprint_dept_id": s.department_id,
            }
            for t, s, p in rows
        ),
    )


_CHECKS = (
    _users_without_membership,
    _tickets_without_one_project,
    _tickets_with_unmapped_assignees,
    _tickets_assigned_to_closed_accounts,
    _spaces_without_ownership,
    _projects_without_scope,
    _resources_on_inactive_departments,
    _sprints_without_team,
    _open_sprint_tickets_off_team,
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

def _skip_reason(user: User | None) -> str:
    """왜 이 id 는 못 고쳤는가. **건너뛴 사실을 말하지 않으면 아무도 모른다.**

    예전에는 없는 id 도 보관 계정도 그냥 지나갔고 응답은 바뀐 건수만 말했다 — 스크립트가
    잘못된 목록을 보내도 「200, changed 0」이라 성공으로 읽혔다.
    """
    if user is None:
        return "이 계정을 찾을 수 없습니다."
    if user.archived_at is not None:
        return "보관된 계정입니다. 보관을 해제한 뒤에 소속을 지정할 수 있습니다."
    if not user.active:
        return "비활성 계정입니다. 계정을 다시 활성화한 뒤에 소속을 지정할 수 있습니다."
    return "이미 소속이 지정된 계정입니다. 소속을 바꾸려면 사용자 화면에서 편집하세요."


def assign_membership(
    db: Session, *, user_ids: list[str], department_id: str | None, organization_direct: bool,
) -> dict:
    """소속 미지정 사용자에게 소속을 지정한다. `{"changed": n, "skipped": [...]}` 를 돌려준다.

    부서와 조직 직속 중 **하나만** 받는다. 둘 다 주면 무엇을 의도했는지 알 수 없고, 둘 다
    안 주면 아무 것도 안 바뀐다 — 어느 쪽도 조용히 넘기지 않는다.

    ## 대상과 부서를 모두 확인한다

    이 동작은 **진단 화면이 세어 준 사람들**을 고치는 자리다(`_users_without_membership`).
    그런데 대상 확인이 「그 id 의 행이 있는가」뿐이라, id 목록만 손대면 이미 소속이 있는
    사람의 부서를 덮어쓰고 보관된 계정에도 소속이 붙었다. 부서 쪽도 존재만 봐서 **비활성
    부서**를 새로 지정할 수 있었는데, 같은 제품의 사용자 편집(`resolve_assignable`)은 그것을
    422 로 막는다 — 한 규칙이 경로마다 다르면 좁은 쪽이 우회로가 된다.

    그래서 대상은 세는 쪽과 같은 정의(`_unassigned_membership_filter`)로 좁히고, 못 고친
    id 는 사유와 함께 돌려준다.
    """
    # 순환 참조를 피해 함수 안에서 부른다(이 모듈은 org 를 읽고, org 는 사용자 편집이 쓴다).
    from app.org.service import resolve_assignable

    if bool(department_id) == bool(organization_direct):
        raise ValidationAppError("부서 지정과 조직 직속 중 하나만 고르세요.")
    if not user_ids:
        return {"changed": 0, "skipped": []}
    # 없는 부서는 422 「알 수 없는 부서입니다」, 비활성 부서는 422 「새로 지정할 수 없습니다」 —
    # 사용자 편집과 같은 함수, 같은 문구다.
    dept = resolve_assignable(db, Department, department_id) if department_id else None

    # 같은 id 를 두 번 보내도 한 번만 센다(입력 순서는 그대로 유지한다).
    wanted = list(dict.fromkeys(user_ids))
    known = {
        u.id: u for u in db.execute(select(User).where(User.id.in_(wanted))).scalars()
    }
    eligible = {
        u.id: u
        for u in db.execute(
            select(User).where(User.id.in_(wanted), *_unassigned_membership_filter())
        ).scalars()
    }
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


__all__ = [
    "Finding", "SAMPLE_LIMIT", "report",
    "assign_membership",
    "MEMBERSHIP_UNASSIGNED",
]
