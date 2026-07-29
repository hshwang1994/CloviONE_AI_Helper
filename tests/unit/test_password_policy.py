import pytest

from app.core.security import (
    generate_temp_password,
    hash_password,
    validate_password_policy,
    verify_password,
)

pytestmark = pytest.mark.unit


def test_short_password_rejected():
    assert validate_password_policy("Ab1!short")


def test_two_classes_rejected():
    assert validate_password_policy("alllowercase12345")  # lower+digit only


def test_three_classes_accepted():
    assert validate_password_policy("Abcdefgh12345") == []  # upper+lower+digit


def test_four_classes_accepted():
    assert validate_password_policy("Abcdefgh1234!") == []


def test_generated_temp_password_satisfies_policy():
    for _ in range(20):
        assert validate_password_policy(generate_temp_password()) == []


def test_argon2_hash_roundtrip():
    digest = hash_password("Str0ng-Passw0rd!")
    assert digest.startswith("$argon2id$")
    assert verify_password(digest, "Str0ng-Passw0rd!")
    assert not verify_password(digest, "wrong-password")
    assert not verify_password("not-a-hash", "anything")


def test_role_hierarchy():
    from app.users.models import roles_at_least

    assert roles_at_least("admin") == frozenset({"admin", "system_admin"})
    assert "auditor" not in roles_at_least("user")
