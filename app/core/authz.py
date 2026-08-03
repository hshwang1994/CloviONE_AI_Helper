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

from app.users.models import (
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
