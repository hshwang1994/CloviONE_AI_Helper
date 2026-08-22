"""Identity Provider — 로그인에서 **자격 증명 검증만** 떼어 낸 층 (S5).

## 왜 지금 떼는가

`app/auth/router.py::login` 은 한 함수에서 일곱 가지를 한다: 속도 제한 · 자격 증명 검증 ·
잠금 판정 · 실패 누적 · 보관/비활성/조직 정지 판정 · 세션 발급 · 감사. 그중 **설치처마다
달라질 수 있는 것은 하나뿐**이다 — 「이 비밀번호가 이 계정의 것인가」. 나머지는 이 제품의
계정 정책이라 Provider 가 바뀌어도 그대로여야 한다.

그래서 경계를 딱 그 한 조각에 긋는다. LDAP·OIDC 가 들어오는 날 바뀌는 것은 이 파일의
구현 하나이고, 잠금·감사·세션은 손대지 않는다. **반대로 그었다면**(Provider 가 로그인
전체를 맡는다) 새 Provider 마다 잠금 정책과 감사 로그를 다시 구현해야 하고, 그중 하나를
빠뜨려도 아무 시험이 빨개지지 않는다.

## 계약이 세 값인 이유

`verify()` 는 참/거짓이 아니라 세 값을 낸다. 「계정이 없다」와 「비밀번호가 틀렸다」를
호출부가 **구별할 수 있어야** 하기 때문이 아니라, 오히려 **구별해서 응답하지 않도록**
호출부가 두 경우를 같은 자리에서 다루게 하기 위해서다. 지금 라우터가 없는 계정에도
더미 해시를 검증해 응답 시간을 맞추는 것과 같은 이유다 — 계정 열거를 막는다.

## 지금 구현은 하나다

`local` — 이 저장소의 `users.password_hash`(Argon2id)를 본다. 값이 하나뿐이라도 이름을
붙여 두는 이유는, 이름이 없으면 다음 Provider 가 들어올 때 「기존 것」을 뭐라고 부를지부터
정해야 하고 그 순간 설정 이름이 두 벌이 되기 때문이다.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from app.core.providers import IdentityProvider
from app.core.security import generate_temp_password, hash_password, verify_password

__all__ = [
    "AuthResult",
    "VerifyOutcome",
    "LocalPasswordProvider",
    "PROVIDER_LOCAL",
    "resolve_identity_provider",
]

PROVIDER_LOCAL = "local"


class VerifyOutcome(str, Enum):
    """검증 결과 세 가지. **`OK` 가 아니면 응답은 전부 같아야 한다.**"""

    OK = "ok"
    NO_ACCOUNT = "no_account"
    BAD_CREDENTIALS = "bad_credentials"


@dataclass(frozen=True)
class AuthResult:
    outcome: VerifyOutcome
    user: object | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is VerifyOutcome.OK


class LocalPasswordProvider(IdentityProvider):
    """이 저장소의 계정 표를 그대로 보는 Provider.

    **없는 계정에도 해시를 한 번 검증한다.** 안 하면 응답 시간이 계정 존재 여부를 말한다 —
    Argon2 검증은 밀리초 단위로 눈에 띄게 느리고, 그 차이는 스크립트로 쉽게 잰다.
    """

    name = PROVIDER_LOCAL

    def verify(self, db: Session, email: str, password: str) -> AuthResult:
        from app.users.service import get_user_by_email

        user = get_user_by_email(db, email)
        if user is None:
            verify_password(_dummy_hash(), password)
            return AuthResult(VerifyOutcome.NO_ACCOUNT)
        if not verify_password(user.password_hash, password):
            return AuthResult(VerifyOutcome.BAD_CREDENTIALS, user=user)
        return AuthResult(VerifyOutcome.OK, user=user)

    # `app/core/providers.py::IdentityProvider` 의 추상 메서드. 그쪽 계약은 세션도 DB 도
    # 모르는 자리(§7.3 의 초안)라 이 제품에서는 쓰지 않는다 — 실제 입구는 위 `verify` 다.
    def authenticate(self, email: str, password: str):  # pragma: no cover - 계약 이행용
        raise NotImplementedError("DB 세션이 필요하다. verify(db, email, password) 를 쓴다")


_PROVIDERS: dict[str, IdentityProvider] = {PROVIDER_LOCAL: LocalPasswordProvider()}


@functools.lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """존재하지 않는 계정용 해시. **한 번만 만들어 두고 재사용한다.**

    매번 새로 만들면 「없는 계정」 경로가 해시 1회 + 검증 1회가 되고, 해시는 검증보다
    비싸다. 그러면 응답 시간이 계정 존재 여부를 **거꾸로** 알려 준다 — 타이밍을 맞추려던
    조치가 정확히 그 반대로 동작한다. 옛 `app/auth/router.py::_dummy_password_hash` 가
    같은 이유로 `lru_cache` 였다.

    값이 새어 나갈 자리는 없다 — 어디에도 보내지 않고 검증 인자로만 쓴다.
    """
    return hash_password(generate_temp_password())


def resolve_identity_provider(settings) -> IdentityProvider:
    """설정이 고른 Provider. **모르는 이름은 오류다** — 조용히 `local` 로 떨어뜨리지 않는다.

    폴백을 두면 오타 하나가 「LDAP 을 켰다고 믿는데 실제로는 로컬 비밀번호로 들어가는」
    상태를 만든다. 그건 로그인이 되기 때문에 아무도 신고하지 않는 종류의 사고다.
    """
    name = (getattr(settings, "auth_provider", "") or PROVIDER_LOCAL).strip().lower()
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise ValueError(
            f"알 수 없는 인증 Provider: {name!r}. "
            f"쓸 수 있는 값: {', '.join(sorted(_PROVIDERS))}"
        )
    return provider
