"""권한 시험이 공유하는 **조직 트리 하나** (0060 §38).

## 왜 공유 세계가 필요한가

보안 시험마다 부서를 두세 개씩 즉석에서 심으면, 파일마다 트리 모양이 조금씩 다르다.
그러면 "형제 부서는 서로 안 보인다" 같은 성질은 **형제를 심은 파일에서만** 검사되고,
심지 않은 파일에서는 통과처럼 보인다. 0060 의 조회 규칙은 줄기(조상 ∪ 자기 ∪ 후손)라
형제·조카·사촌이 전부 다른 답을 내야 하는데, 그 구분은 3단 트리 + 두 갈래가 있어야만
드러난다.

## 모양

    GMI (조직)
    ├── A
    │   ├── A-1
    │   └── A-2
    └── B
        ├── B-1
        └── B-2

이 모양이 최소 크기다. 왜 이만큼이 필요한가:

  * `A-1` ↔ `A-2` — **형제**. 같은 부모를 공유하지만 서로의 줄기가 아니다. 가장 자주
    틀리는 자리다(“같은 본부니까 보이겠지”).
  * `A-1` ↔ `B-1` — **사촌**. 조직만 같다. 여기가 열리면 조회 범위가 사실상 조직 전체다.
  * `A` ↔ `A-1` — **조상/후손**. 양방향으로 보인다(조회), 관리는 위에서 아래로만 간다.
  * `A` ↔ `B` — **최상위 형제**. 조직 직속인 사람만 둘 다 본다.

## 사람

| 키 | 역할 | 소속 | 관리 범위 |
|---|---|---|---|
| `org_direct` | user | 조직 직속(부서 없음) | 없음 |
| `a`,`a1`,`a2`,`b1` | user | 그 부서 | 없음 |
| `unassigned` | user | **미지정** | 없음 |
| `a_admin` | admin | A | A ∪ 후손 |
| `a1_admin` | admin | A-1 | A-1 |
| `org_admin` | admin | 조직 직속 | 조직 전체 |
| `global_admin` | system_admin | 조직 직속 | 전역 |

`a1_admin` 이 있는 이유: **관리 범위는 아래로만 간다**(self ∪ descendants). A-1 관리자가
A 를 관리하게 되면 그건 위임이 아니라 승격이다. 그 경계는 조상이 있는 노드에서만 시험할
수 있다.
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.users.models import (
    ADMIN_SCOPE_DEPT,
    ADMIN_SCOPE_GLOBAL,
    ADMIN_SCOPE_ORG,
    MEMBERSHIP_DEPARTMENT,
    MEMBERSHIP_ORGANIZATION,
    MEMBERSHIP_UNASSIGNED,
)

# 고정 id — 시험이 부서를 이름으로 찾지 않게 한다(이름은 바뀔 수 있고, 바뀌어도 권한은
# 안 바뀌는 것이 0060 의 요구사항이다).
D_A = "ot-dept-a00000"
D_A1 = "ot-dept-a10000"
D_A2 = "ot-dept-a20000"
D_B = "ot-dept-b00000"
D_B1 = "ot-dept-b10000"
D_B2 = "ot-dept-b20000"

TREE_SHAPE: tuple[tuple[str, str, str | None], ...] = (
    (D_A, "A본부", None),
    (D_A1, "A-1팀", D_A),
    (D_A2, "A-2팀", D_A),
    (D_B, "B본부", None),
    (D_B1, "B-1팀", D_B),
    (D_B2, "B-2팀", D_B),
)


@pytest.fixture()
def org_tree(db):
    """GMI / A(A-1, A-2) / B(B-1, B-2). `{키: Department}` 를 돌려준다."""
    made = {}
    for dept_id, name, parent in TREE_SHAPE:
        row = Department(id=dept_id, name=name, parent_id=parent, org_id=DEFAULT_ORG_ID)
        db.add(row)
        made[dept_id] = row
    db.commit()
    return made


# 사람 정의: 키 → (역할, 소속 부서, 관리 범위 종류, 관리 대상 부서)
_PEOPLE: tuple[tuple[str, str, str | None, str | None, str | None], ...] = (
    ("org_direct", "user", None, None, None),
    ("a", "user", D_A, None, None),
    ("a1", "user", D_A1, None, None),
    ("a2", "user", D_A2, None, None),
    ("b1", "user", D_B1, None, None),
    ("unassigned", "user", None, None, None),
    ("a_admin", "admin", D_A, ADMIN_SCOPE_DEPT, D_A),
    ("a1_admin", "admin", D_A1, ADMIN_SCOPE_DEPT, D_A1),
    ("org_admin", "admin", None, ADMIN_SCOPE_ORG, None),
    ("global_admin", "system_admin", None, ADMIN_SCOPE_GLOBAL, None),
)


@pytest.fixture()
def people(db, make_user, org_tree):
    """위 표의 사람들. `{키: User}` 를 돌려준다 — 이메일은 `<키>@goodmit.co.kr`."""
    made = {}
    for key, role, dept, admin_scope, scope_dept in _PEOPLE:
        user = make_user(
            email=f"{key}@goodmit.co.kr", role=role, display_name=key,
            membership=(
                MEMBERSHIP_UNASSIGNED if key == "unassigned" else MEMBERSHIP_ORGANIZATION
            ),
        )
        user.org_id = DEFAULT_ORG_ID
        if dept:
            user.department_id = dept
            user.membership_kind = MEMBERSHIP_DEPARTMENT
        if admin_scope:
            user.admin_scope = admin_scope
            user.scope_dept_id = scope_dept
            user.scope_org_id = None if admin_scope == ADMIN_SCOPE_GLOBAL else DEFAULT_ORG_ID
        made[key] = user
    db.commit()
    return made


@pytest.fixture()
def resources(db, org_tree, make_project, make_document):
    """부서마다 프로젝트 하나 + 문서 하나, 그리고 조직 공통 문서와 미지정 문서.

    티켓은 파일마다 필요한 모양이 달라 여기서 심지 않는다 — 프로젝트만 있으면 티켓은
    `project_uid` 한 줄로 붙는다(`app/tickets/models.py`).
    """
    projects = {
        key: make_project(name=f"{key} 프로젝트", dept=dept_id)
        for key, dept_id in (
            ("a", D_A), ("a1", D_A1), ("a2", D_A2), ("b", D_B), ("b1", D_B1),
        )
    }
    # 부서 없는 프로젝트 = 조직 공통(0060: dept_id 가 없으면 ORGANIZATION).
    projects["org"] = make_project(name="조직 공통 프로젝트")
    docs = {
        key: make_document(page_id=f"ot-doc-{key}", title=f"{key} 문서", dept=dept_id)
        for key, dept_id in (
            ("a", D_A), ("a1", D_A1), ("a2", D_A2), ("b", D_B), ("b1", D_B1),
        )
    }
    docs["org"] = make_document(page_id="ot-doc-org", title="조직 공통 문서", org_wide=True)
    # 소속을 정하지 않은 문서 — 전역 관리자 말고는 아무도 못 본다(fail-closed).
    docs["unset"] = make_document(page_id="ot-doc-unset", title="미지정 문서")
    db.commit()
    return {"projects": projects, "documents": docs}
