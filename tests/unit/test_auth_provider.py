"""자격 증명 검증만 Provider 가 한다 — 그 경계가 실제로 지켜지는가 (S5).

경계를 여기 그은 이유는 `app/auth/providers.py` 머리말에 있다: 설치처마다 달라질 수 있는
것은 「이 비밀번호가 이 계정의 것인가」 하나뿐이고, 잠금·실패 누적·보관/비활성/조직 정지·
세션 발급·감사는 이 제품의 계정 정책이라 Provider 가 바뀌어도 그대로여야 한다.

**반대로 그었다면**(Provider 가 로그인 전체를 맡는다) 새 Provider 마다 그 정책을 다시
구현해야 하고, 그중 하나를 빠뜨려도 아무 시험이 빨개지지 않는다.
"""

from __future__ import annotations

import pytest

from app.auth.providers import (
    PROVIDER_LOCAL,
    LocalPasswordProvider,
    VerifyOutcome,
    resolve_identity_provider,
)

pytestmark = pytest.mark.unit


class _Settings:
    def __init__(self, name):
        self.auth_provider = name


def test_the_default_is_the_local_password_provider():
    provider = resolve_identity_provider(_Settings(PROVIDER_LOCAL))
    assert isinstance(provider, LocalPasswordProvider)


def test_an_empty_value_falls_back_to_local():
    """설정을 비운 것은 「끄겠다」가 아니라 「기본대로」다."""
    assert isinstance(resolve_identity_provider(_Settings("")), LocalPasswordProvider)


def test_an_unknown_provider_is_an_error_not_a_silent_fallback():
    """오타 하나가 「LDAP 을 켰다고 믿는데 로컬 비밀번호로 들어가는」 상태를 만들면 안 된다.

    그건 로그인이 되기 때문에 아무도 신고하지 않는 종류의 사고다.
    """
    with pytest.raises(ValueError) as excinfo:
        resolve_identity_provider(_Settings("ldap"))
    assert "ldap" in str(excinfo.value)


def test_a_wrong_password_and_a_missing_account_are_different_outcomes(db, make_user):
    """호출부가 두 경우를 **같은 자리에서** 다루게 하려고 값을 나눠 준다.

    구별해서 응답하라는 뜻이 아니다 — 라우터는 둘 다 같은 401 로 답한다. 다만 계정이 있는
    경우에만 실패 누적과 감사 기록이 남아야 하고, 그 판단에는 구별이 필요하다.
    """
    provider = LocalPasswordProvider()
    make_user("prov@goodmit.co.kr", password="Correct-Horse-1!")

    missing = provider.verify(db, "nobody@goodmit.co.kr", "whatever")
    assert missing.outcome is VerifyOutcome.NO_ACCOUNT
    assert missing.user is None
    assert not missing.ok

    wrong = provider.verify(db, "prov@goodmit.co.kr", "wrong-password")
    assert wrong.outcome is VerifyOutcome.BAD_CREDENTIALS
    assert wrong.user is not None, "실패 누적을 남기려면 어느 계정인지 알아야 한다"
    assert not wrong.ok

    ok = provider.verify(db, "prov@goodmit.co.kr", "Correct-Horse-1!")
    assert ok.ok and ok.user is not None


def test_login_still_locks_the_account_after_repeated_failures(client, make_user, settings):
    """**정책은 Provider 밖에 있다** — 검증만 떼어 냈지 잠금을 함께 가져가지 않았다."""
    make_user("lockme@goodmit.co.kr", password="Correct-Horse-1!")
    for _ in range(settings.login_max_failures):
        client.post("/login", json={"email": "lockme@goodmit.co.kr", "password": "nope"})
    r = client.post(
        "/login", json={"email": "lockme@goodmit.co.kr", "password": "Correct-Horse-1!"}
    )
    assert r.status_code == 403, f"실패를 누적해도 잠기지 않는다: {r.status_code} {r.text}"
    assert r.json()["error"]["code"] == "account_locked"


def test_the_dummy_hash_is_made_once(db, make_user):
    """없는 계정 경로가 **해시 1회 + 검증 1회**가 되면 타이밍 조치가 거꾸로 동작한다.

    Argon2 는 해시가 검증보다 비싸다. 더미 해시를 매번 새로 만들면 「없는 계정」이 「있는
    계정」보다 **느려지고**, 응답 시간이 계정 존재를 거꾸로 알려 준다. 옛
    `app/auth/router.py::_dummy_password_hash` 가 `lru_cache` 였던 이유이고, Provider 로
    옮기면서 그 성질을 잃지 않았는지 여기서 지킨다.
    """
    from app.auth import providers

    provider = providers.LocalPasswordProvider()
    provider.verify(db, "ghost-1@goodmit.co.kr", "whatever")
    info = providers._dummy_hash.cache_info()
    first = providers._dummy_hash()

    provider.verify(db, "ghost-2@goodmit.co.kr", "whatever")
    assert providers._dummy_hash() == first, "더미 해시가 호출마다 새로 만들어진다"
    assert info.currsize == 1, f"더미 해시가 기억되지 않는다: {info}"
