"""권한 그룹 단일 정의 (§10, §25.5) — 역할 이름의 튜플이 흩어지지 않게 한다.

**왜 모으는가.** 이 파일이 생기기 전에는 `READ_ROLES = ("operator", "admin", "system_admin",
"auditor")` 가 **11개 라우터에 같은 문장으로 복사돼** 있었고 `WRITE_ROLES` 는 8개, `OPS_ROLES`
는 3개였다. 역할이 하나 늘거나 auditor 를 어디서 빼야 할 때, 고쳐야 할 곳이 스무 군데인데
어느 한 곳을 빠뜨려도 아무 테스트가 빨개지지 않는다 — 그 라우터만 조용히 옛 규칙으로 남는다.
권한 규칙은 "한 곳만 고치면 전부 반영"이 성립해야 하는 대표적인 대상이다.

`role`(무엇을 할 수 있는가)과 `admin_scope`(누구에게 할 수 있는가)는 직교한다 — 범위는
`app/core/scope.py` 가 담당한다. 여기는 역할만 본다.

**튜플인 이유**: `require_roles(*ROLES)` 가 가변인자를 받는다. 집합 비교가 필요한 곳
(`user.role in X`)에는 frozenset 인 `MODERATOR_ROLES` 를 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.users.models import (
    ADMIN_SCOPE_DEPT,
    ADMIN_SCOPE_GLOBAL,
    ADMIN_SCOPE_ORG,
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_OPERATOR,
    ROLE_SYSTEM_ADMIN,
    ROLE_USER,
    roles_at_least,
)

__all__ = [
    "CONSOLE_READ_ROLES",
    "CONSOLE_WRITE_ROLES",
    "CONSOLE_OPS_ROLES",
    "SENSITIVE_READ_ROLES",
    "SYSTEM_ADMIN_ONLY",
    "MODERATOR_ROLES",
    "ROLE_ADMIN",
    "ROLE_AUDITOR",
    "ROLE_OPERATOR",
    "ROLE_SYSTEM_ADMIN",
    "ROLE_USER",
    "Capability",
    "CAPABILITIES",
    "ROLE_ORDER",
    "ROLE_LABELS",
    "SCOPE_LABELS",
    "rbac_matrix",
]

# 관리 콘솔 **읽기**: 운영자군 전부 + 감사자. 목록·상세·버전 조회가 여기에 걸린다.
# auditor 가 포함되는 이유는 감사가 "무엇이 설정돼 있었는가"를 볼 수 있어야 하기 때문이다.
CONSOLE_READ_ROLES: tuple[str, ...] = (
    ROLE_OPERATOR,
    ROLE_ADMIN,
    ROLE_SYSTEM_ADMIN,
    ROLE_AUDITOR,
)

# 관리 콘솔 **설정 변경**: admin 이상. operator 는 운영은 하되 설정은 못 바꾸고,
# auditor 는 읽기 전용 가지라 절대 포함되지 않는다.
CONSOLE_WRITE_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_SYSTEM_ADMIN)

# 관리 콘솔 **운영 동작**: 실행·재시도·헬스체크·드라이런처럼 설정을 바꾸지는 않지만
# 부수효과가 있는 것들. operator 는 포함, auditor 는 제외(읽기 전용).
CONSOLE_OPS_ROLES: tuple[str, ...] = (ROLE_OPERATOR, ROLE_ADMIN, ROLE_SYSTEM_ADMIN)

# **민감 집계 읽기**: 감사 로그, 개발자 월간 리포트. 담당자별 생산성처럼 사람에 대한
# 평가가 담기므로 operator 를 뺀다(감사 로그 조회 권한과 같은 선).
SENSITIVE_READ_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_SYSTEM_ADMIN, ROLE_AUDITOR)

# 백업 생성·검증·복구 안내. 스펙 §14.6 이 system_admin 으로 못박은 것들.
SYSTEM_ADMIN_ONLY: tuple[str, ...] = (ROLE_SYSTEM_ADMIN,)

# 사용자 콘텐츠 중재(게시판 글·댓글 삭제, 문서 동기화·삭제, 휴지통 관리, 티켓 편집 우회).
# `user.role in MODERATOR_ROLES` 형태로 쓰이므로 frozenset 이다.
# 집합으로 보면 CONSOLE_OPS_ROLES 와 같다 — 같은지 여부는 tests/security/test_rbac_basics.py
# 가 못박는다(둘이 갈라지면 '운영자'의 뜻이 화면마다 달라진다).
MODERATOR_ROLES: frozenset[str] = roles_at_least(ROLE_OPERATOR)


# ── 권한 매트릭스 (Phase 6 — "누가 무엇을 할 수 있는가"를 한 화면에) ───────────
#
# **화면은 역할 목록을 다시 적지 않는다.** 관리 콘솔의 RBAC 매트릭스는 `GET /api/admin/rbac-matrix`
# 가 돌려주는 값만 그린다. 그 응답은 아래 `rbac_matrix()` 하나에서 나오고, 그 함수는 위의 그룹
# 상수만 읽는다 — 즉 **이 파일이 표의 유일한 출처**다. 프런트에 역할 배열을 한 벌 더 두면 규칙을
# 여기서 고쳐도 화면은 옛 표를 계속 보여 준다(그것이 이 파일이 애초에 생긴 이유와 같은 결함이다).
#
# 라벨을 여기 두는 이유: 화면이 역할 '값'만 받고 이름을 스스로 붙이면, 그 순간 화면에 역할
# 목록이 다시 생긴다(새 역할을 추가해도 라벨이 없어 raw 값이 노출된다).

# 표시 순서 = 권한 수준 오름차순. auditor 는 계층 밖(읽기 전용 가지)이라 operator 다음에 둔다.
ROLE_ORDER: tuple[str, ...] = (
    ROLE_USER,
    ROLE_OPERATOR,
    ROLE_AUDITOR,
    ROLE_ADMIN,
    ROLE_SYSTEM_ADMIN,
)

ROLE_LABELS: dict[str, str] = {
    ROLE_USER: "일반 사용자",
    ROLE_OPERATOR: "운영자",
    ROLE_AUDITOR: "감사자",
    ROLE_ADMIN: "관리자",
    ROLE_SYSTEM_ADMIN: "시스템 관리자",
}

# 범위(admin_scope)는 역할과 직교한다 — `app/core/scope.py` 가 해석한다. 매트릭스가 역할만
# 보여 주면 '부서 관리자'가 왜 남의 부서를 못 보는지 화면 어디에도 설명이 없다.
SCOPE_LABELS: dict[str, tuple[str, str]] = {
    ADMIN_SCOPE_GLOBAL: ("전체", "조직, 부서 제한 없이 모든 대상을 관리한다."),
    ADMIN_SCOPE_ORG: ("조직", "자기 조직(org_id)에 속한 대상만 보이고 관리할 수 있다."),
    ADMIN_SCOPE_DEPT: (
        "부서",
        "자기 부서와 그 하위 부서에 속한 대상만 보인다. 범위 밖 단건은 403 이 아니라 404 다.",
    ),
}


@dataclass(frozen=True)
class Capability:
    """매트릭스 한 행. `roles` 는 **반드시 위의 그룹 상수 중 하나**여야 한다.

    여기에 역할 이름을 손으로 나열하면 그 순간 이 파일 안에서 규칙이 두 벌이 된다 —
    `tests/security/test_rbac_matrix.py` 가 모든 행이 알려진 그룹과 동일한 집합인지 확인한다.
    """

    key: str
    label: str
    area: str
    roles: tuple[str, ...]
    note: str = ""


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "console.read", "관리 콘솔 목록, 상세 조회", "콘솔", CONSOLE_READ_ROLES,
        "감사자가 포함된다. 감사는 '무엇이 설정돼 있었는가'를 볼 수 있어야 한다.",
    ),
    Capability(
        "console.write", "설정 변경(생성, 수정, 활성/비활성)", "콘솔", CONSOLE_WRITE_ROLES,
        "운영자는 운영은 하되 설정은 못 바꾼다. 감사자는 읽기 전용이라 절대 포함되지 않는다.",
    ),
    Capability(
        "console.ops", "운영 동작(실행, 재시도, 헬스체크, 드라이런)", "운영", CONSOLE_OPS_ROLES,
        "설정을 바꾸지는 않지만 부수효과가 있는 것들.",
    ),
    Capability(
        "sensitive.read", "감사 로그, 개발자 월간 리포트 조회", "감사", SENSITIVE_READ_ROLES,
        "담당자별 생산성처럼 사람에 대한 평가가 담기므로 운영자를 뺀다.",
    ),
    Capability(
        "content.moderate", "사용자 콘텐츠 중재(게시판, 문서, 휴지통, 티켓 편집 우회)", "콘텐츠",
        tuple(r for r in ROLE_ORDER if r in MODERATOR_ROLES),
        "본인 글이 아니어도 지울 수 있는 권한. 티켓은 담당자가 아니어도 편집할 수 있다.",
    ),
    Capability(
        "users.manage", "사용자 계정 관리(생성, 수정, 비활성화, 보관)", "사용자",
        CONSOLE_WRITE_ROLES,
        "system_admin 계정에 대한 조작은 system_admin 만 할 수 있다(권한 경계).",
    ),
    Capability(
        "users.bulk", "사용자 대량 작업, CSV 가져오기/내보내기", "사용자", CONSOLE_WRITE_ROLES,
        "대상은 언제나 자기 관리 범위 안으로 제한된다.",
    ),
    Capability(
        "offboarding.run", "오프보딩 실행(보유 티켓 재배정 + 계정 비활성화, 보관)", "사용자",
        CONSOLE_WRITE_ROLES,
        "실행 전 미리보기가 강제되고, 실행 결과는 되돌릴 수 있다.",
    ),
    Capability(
        "org.manage", "부서, 직책 명부와 조직도 트리 편집", "사용자", CONSOLE_WRITE_ROLES,
    ),
    Capability(
        "system.admin", "백업 생성, 검증, 복구 안내", "시스템", SYSTEM_ADMIN_ONLY,
        "스펙 §14.6 이 system_admin 으로 못박은 것들.",
    ),
)


def rbac_matrix() -> dict:
    """화면이 그대로 그리는 매트릭스. **역할 목록도 여기서 나간다.**

    `allowed` 는 역할 값의 목록이다 — 화면은 `roles` 배열을 열로 깔고 각 칸에서
    `allowed` 포함 여부만 본다. 새 역할이 생기면 열이 저절로 하나 늘어난다.
    """
    return {
        "roles": [
            {"value": role, "label": ROLE_LABELS.get(role, role)} for role in ROLE_ORDER
        ],
        "items": [
            {
                "id": cap.key,
                "capability": cap.label,
                "area": cap.area,
                "note": cap.note,
                "allowed": [role for role in ROLE_ORDER if role in cap.roles],
            }
            for cap in CAPABILITIES
        ],
        "scopes": [
            {"value": value, "label": label, "help": help_text}
            for value, (label, help_text) in SCOPE_LABELS.items()
        ],
        "source": "app/core/authz.py",
    }
