"""Resource Ownership — **이 데이터가 어디에 속하는가**, 그리고 그로부터 나오는 접근 판정.

## 왜 이 파일이 필요한가

예전에는 자원마다 소속을 정하는 축이 달랐다. 티켓은 **담당자**의 부서, 문서는 **작성자**의
부서, 프로젝트만 자기 `dept_id` 를 썼다. 세 축은 서로 다른 답을 내고, 그래서 같은 조직
구조에서 "프로젝트는 보이는데 그 프로젝트의 티켓은 안 보인다" 같은 상태가 정상처럼 존재했다.
게다가 담당자·작성자 축은 **사람이 부서를 옮기면 과거 자원의 소속이 따라 움직인다** — 3년 전
ClovirONE팀이 쓴 문서가 작성자의 이직 한 번으로 다른 팀 문서가 된다.

그래서 축을 하나로 모은다: **자원은 자기 소속을 스스로 들고 있고, 사람의 현재 소속과 무관하다.**

## Ownership 과 Access Policy 는 다른 것이다

    Resource → Ownership Context → Visibility / Write / Management Policy

`Ownership` 은 "이 자원이 어디 것인가"만 말한다. 거기에 역할을 넣지 않는다 — 같은 소속의
같은 자원이라도 보는 사람에 따라 판정이 달라져야 하는데, 소속에 역할이 섞이면 그 둘을
분리할 수 없다.

## 공통 테이블을 만들지 않는다

모든 자원의 소속을 한 표에 모으면 조인이 늘고 자원마다 자연스러운 관계(프로젝트의
`dept_id`, 채팅방의 멤버 표)를 버리게 된다. 저장은 각 테이블이 자기 방식대로 하고,
**판정만 한 곳으로 모은다.** 그래서 이 파일에는 테이블이 없고 함수와 어휘만 있다.

## 조회 판정은 S5 에서 이 파일을 떠났다

「무엇이 보이는가」는 `app/authz/visibility.py::effective_visibility_clause` 한 곳이 답한다.
여기 남은 것은 **소속 어휘**(무엇이 어디 것인가)와 **관리 판정**(누가 그것을 옮길 수
있는가)이다. 둘을 갈라 둔 이유는 축이 다르기 때문이다 — 조회는 `visibility` 범위를,
관리는 `management` 범위를 본다. 그 둘을 한 함수가 답하면 「볼 수는 있는데 옮길 수는 없는」
상태를 표현할 수 없다.

## 판정할 수 없으면 닫는다

소속을 정할 수 없는 자원(`OWNER_UNSET`)은 전역 관리자만 본다. "작성자 부서일 것이다",
"프로젝트 이름이 비슷하니 이것일 것이다" 같은 추측을 하지 않는다 — 그런 추측은 언제나
넓히는 쪽으로 틀리고, 틀린 것을 아무도 신고하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.scope import Scope

# ── 소속 어휘 ────────────────────────────────────────────────────────────────
# 자원의 성격에 맞는 것 하나를 고른다. 모든 자원에 부서를 억지로 붙이지 않는다.
OWNER_PERSONAL = "personal"          # 그 사람 것 (프로필·개인 대화·알림)
OWNER_PROJECT = "project"            # 프로젝트 것 (티켓·프로젝트 문서)
OWNER_DEPARTMENT = "department"      # 부서 것 (부서 문서·부서 프로젝트)
OWNER_ORGANIZATION = "organization"  # 조직 공통 (게시판·제안·조직 공통 문서)
OWNER_MEMBERSHIP = "membership"      # 참여자 것 (채팅방·게임방) — 멤버 표가 판정한다
OWNER_GLOBAL = "global"              # 설치 전체 (설정·백업·연동) — 역할이 판정한다
OWNER_UNSET = "unset"                # 아직 정해지지 않음 — 전역 관리자만

ALL_OWNER_KINDS = frozenset({
    OWNER_PERSONAL, OWNER_PROJECT, OWNER_DEPARTMENT,
    OWNER_ORGANIZATION, OWNER_MEMBERSHIP, OWNER_GLOBAL, OWNER_UNSET,
})

# 자원 테이블이 직접 저장하는 값의 집합. `personal`/`membership`/`global` 은 저장하지 않고
# 그 자원의 구조 자체가 말한다(개인 자원은 user_id 를, 방은 멤버 표를 갖는다).
STORED_OWNER_KINDS = frozenset({
    OWNER_PROJECT, OWNER_DEPARTMENT, OWNER_ORGANIZATION, OWNER_UNSET,
})


@dataclass(frozen=True)
class Ownership:
    """자원 하나의 소속. **id 만 담는다** — 이름이나 경로 문자열은 권한 키가 아니다.

    부서 이름이 바뀌거나 상위 부서가 새로 생겨도 이 값은 그대로여야 하고, 실제로 그렇다:
    담고 있는 것이 `dept_id` 뿐이라 트리가 어떻게 바뀌어도 연결이 끊기지 않는다.
    """

    kind: str
    org_id: str | None = None
    dept_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None

    @property
    def is_unset(self) -> bool:
        return self.kind == OWNER_UNSET


UNSET = Ownership(kind=OWNER_UNSET)


# ── 소속 만들기 ──────────────────────────────────────────────────────────────

def for_project(project) -> Ownership:
    """프로젝트 자신의 소속. 부서가 있으면 부서 것, 없으면 조직 공통이다.

    `dept_id IS NULL` 을 '미지정'이 아니라 **조직 공통**으로 읽는 이유: 프로젝트는 조직
    전체가 함께 쓰는 것이 정상인 경우가 실제로 있고(전사 인프라 개선 등), 그때 부서를
    억지로 하나 고르게 하면 그 부서 것으로 잘못 좁혀진다. 조직조차 없으면 그건 진짜
    판정 불가라 UNSET 이다.
    """
    if project is None:
        return UNSET
    dept_id = getattr(project, "dept_id", None)
    org_id = getattr(project, "org_id", None)
    if dept_id:
        return Ownership(OWNER_DEPARTMENT, org_id=org_id, dept_id=dept_id,
                         project_id=getattr(project, "id", None))
    if org_id:
        return Ownership(OWNER_ORGANIZATION, org_id=org_id,
                         project_id=getattr(project, "id", None))
    return Ownership(OWNER_UNSET, project_id=getattr(project, "id", None))


def for_department(dept_id: str | None, org_id: str | None = None) -> Ownership:
    if not dept_id:
        return UNSET
    return Ownership(OWNER_DEPARTMENT, org_id=org_id, dept_id=dept_id)


def for_organization(org_id: str | None) -> Ownership:
    if not org_id:
        return UNSET
    return Ownership(OWNER_ORGANIZATION, org_id=org_id)


def for_personal(user_id: str | None) -> Ownership:
    if not user_id:
        return UNSET
    return Ownership(OWNER_PERSONAL, user_id=user_id)


# ── 판정 ─────────────────────────────────────────────────────────────────────

def _scope_allows(scope: Scope, ownership: Ownership) -> bool:
    """한 범위가 한 소속을 포함하는가. 조회·관리 판정이 **같은 표**를 쓰게 하는 공통부."""
    if scope.is_global:
        return True
    if scope.is_none:
        return False
    kind = ownership.kind
    if kind == OWNER_ORGANIZATION:
        # 조직 공통 자원은 그 조직 사람 전부에게 보인다 — 부서 범위 사용자도 포함이다.
        # (부서 집합에 없다고 막으면 'GMI 공통' 이라는 개념 자체가 성립하지 않는다.)
        return bool(ownership.org_id) and scope.org_id == ownership.org_id
    if kind == OWNER_DEPARTMENT:
        if scope.is_org:
            return bool(ownership.org_id) and scope.org_id == ownership.org_id
        return bool(ownership.dept_id) and ownership.dept_id in scope.dept_ids
    # UNSET / PROJECT(해석 전) / 그 밖 — 전역이 아니면 닫는다.
    return False


def can_manage(ownership: Ownership, principal) -> bool:
    """이 사람이 이 자원을 **관리**할 수 있는가(소속 변경·삭제 등 조직 결정).

    조회 범위가 아니라 관리 범위를 본다. A-1 부서 관리자는 상위 A 프로젝트를 *볼* 수는
    있어도 *옮길* 수는 없다 — 그게 위임과 승격의 차이다.
    """
    kind = ownership.kind
    if kind == OWNER_GLOBAL:
        return principal.manages_everything
    if kind == OWNER_PERSONAL:
        return bool(ownership.user_id) and ownership.user_id == principal.user_id
    if kind == OWNER_MEMBERSHIP:
        return False
    return _scope_allows(principal.management, ownership)
