"""권한 그룹은 정의가 **한 곳뿐**이어야 한다 (PLAN Phase 4 — RBAC 배관).

**고쳤던 상태.** `READ_ROLES = ("operator", "admin", "system_admin", "auditor")` 가 11개
라우터에 같은 문장으로 복사돼 있었다. `WRITE_ROLES` 는 8개, `OPS_ROLES` 는 3개.
`{operator, admin, system_admin}` 집합은 게시판·문서·휴지통·티켓·티켓댓글에 각각 다른 이름
(`MODERATOR_ROLES`/`SYNC_ROLES`/`_MANAGE_ROLES`/`_EDIT_BYPASS_ROLES`/`_MODERATOR_ROLES`)으로
또 복사돼 있었다.

문제는 '중복'이 아니라 **한 곳을 고쳐도 나머지가 안 따라오는데 아무 테스트도 빨개지지
않는다**는 점이다. 그 라우터만 조용히 옛 규칙으로 남고, 권한 규칙에서 그것은 곧 구멍이다.
그래서 여기서는 소스를 직접 훑어 사본이 다시 생기지 않는지 본다.
"""

import re
from pathlib import Path

import pytest

from app.core.authz import (
    CONSOLE_OPS_ROLES,
    CONSOLE_READ_ROLES,
    CONSOLE_WRITE_ROLES,
    MODERATOR_ROLES,
    SENSITIVE_READ_ROLES,
    SYSTEM_ADMIN_ONLY,
)
from app.users.models import ALL_ROLES

pytestmark = pytest.mark.security

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHZ = PROJECT_ROOT / "app" / "core" / "authz.py"

# 역할 이름이 두 개 이상 나열된 튜플/집합 리터럴. authz.py 밖에서는 나오면 안 된다.
_ROLE_LITERAL = re.compile(
    r"""[\(\{]\s*["'](?:operator|admin|system_admin|auditor|user)["']\s*,"""
    r"""\s*["'](?:operator|admin|system_admin|auditor|user)["']"""
)


def _python_sources():
    for path in sorted((PROJECT_ROOT / "app").rglob("*.py")):
        if path == AUTHZ:
            continue
        yield path


def test_no_role_tuple_literal_outside_authz():
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8")
        for match in _ROLE_LITERAL.finditer(text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line}")
    assert not offenders, (
        "역할 이름 목록이 authz.py 밖에서 다시 만들어졌다:\n  "
        + "\n  ".join(offenders)
        + "\napp/core/authz.py 의 상수를 import 해서 쓰라 — 사본이 생기면 한 곳만 고쳐지고 "
        "그 라우터만 조용히 옛 규칙으로 남는다."
    )


def test_the_scan_above_is_not_vacuous():
    """정규식이 실제로 무엇인가를 잡는다는 증명 — 옛 문장을 넣어 보고 걸리는지 본다."""
    old_shape = 'READ_ROLES = ("operator", "admin", "system_admin", "auditor")'
    assert _ROLE_LITERAL.search(old_shape), "정규식이 옛 문장을 못 잡는다 — 검사가 헛돈다"


def test_require_roles_is_never_called_with_string_literals():
    """`require_roles("admin", "system_admin")` 형태가 남아 있으면 그 자리만 규칙이 갈라진다."""
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"require_roles\(\s*[\"']", text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line}")
    assert not offenders, "require_roles 에 문자열 리터럴이 직접 들어갔다:\n  " + "\n  ".join(offenders)


def test_moderator_roles_and_console_ops_roles_are_the_same_set():
    """둘이 갈라지면 '운영자'의 뜻이 화면마다 달라진다.

    이름이 둘인 이유는 쓰임이 다르기 때문이다: `require_roles(*OPS)` 는 가변인자를 받고,
    `user.role in MODERATOR_ROLES` 는 집합 비교다. 값이 같다는 것은 여기서 못박는다.
    """
    assert MODERATOR_ROLES == set(CONSOLE_OPS_ROLES)


def test_every_group_only_contains_known_roles():
    """오타 하나가 '아무도 통과 못 하는 엔드포인트'를 만든다 — 그런데 오타는 조용하다."""
    groups = {
        "CONSOLE_READ_ROLES": CONSOLE_READ_ROLES,
        "CONSOLE_WRITE_ROLES": CONSOLE_WRITE_ROLES,
        "CONSOLE_OPS_ROLES": CONSOLE_OPS_ROLES,
        "SENSITIVE_READ_ROLES": SENSITIVE_READ_ROLES,
        "SYSTEM_ADMIN_ONLY": SYSTEM_ADMIN_ONLY,
        "MODERATOR_ROLES": MODERATOR_ROLES,
    }
    for name, group in groups.items():
        unknown = set(group) - ALL_ROLES
        assert not unknown, f"{name} 에 알 수 없는 역할이 있다: {sorted(unknown)}"


def test_auditor_is_read_only_everywhere():
    """auditor 는 읽기 전용 가지다(§10). 쓰기·운영 그룹에 들어가면 그 전제가 깨진다."""
    for name, group in (
        ("CONSOLE_WRITE_ROLES", CONSOLE_WRITE_ROLES),
        ("CONSOLE_OPS_ROLES", CONSOLE_OPS_ROLES),
        ("SYSTEM_ADMIN_ONLY", SYSTEM_ADMIN_ONLY),
        ("MODERATOR_ROLES", MODERATOR_ROLES),
    ):
        assert "auditor" not in group, f"{name} 에 auditor 가 들어 있다"


def test_operator_cannot_read_sensitive_aggregates():
    """감사 로그·개발자 월간 리포트는 사람에 대한 평가가 담긴다 — operator 는 제외다."""
    assert "operator" not in SENSITIVE_READ_ROLES
    assert "operator" in CONSOLE_READ_ROLES  # 일반 콘솔 읽기는 여전히 된다
