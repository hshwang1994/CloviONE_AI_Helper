"""Password hashing (Argon2id), password policy, and token helpers (spec §25.1)."""

from __future__ import annotations

import hashlib
import secrets
import string
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # argon2id with library defaults

PASSWORD_MIN_LENGTH = 12
_SPECIAL_CHARS = set("!@#$%^&*()-_=+[]{};:,.<>?/|~`'\"\\")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def validate_password_policy(
    password: str, *, min_length: int = PASSWORD_MIN_LENGTH, min_classes: int = 3
) -> list[str]:
    """Return a list of policy violations (empty = OK). Spec §25.1: 최소 12자, 3종 이상.
    ``min_length``/``min_classes`` come from the effective password_policy setting."""
    problems: list[str] = []
    if len(password) < min_length:
        problems.append(f"비밀번호는 최소 {min_length}자 이상이어야 합니다.")
    # change_password.js의 countClasses()는 \p{Ll}/\p{Lu}/\p{Nd} 유니코드 속성으로 판정한다고
    # 명시하고(코드 주석) 서버와 "항상 일치"한다고 가정한다. str.isdigit()은 Nd의 진부분집합이
    # 아니다 — Unicode 'No'(원문자 숫자 ②, 위첨자 숫자 ² 등)도 True를 낸다. 클라이언트가
    # '아직 3종 미충족'으로 보여준 힌트가 서버에선 통과해 버리는 어긋남을 없애려면 서버도
    # 정확히 같은 유니코드 카테고리(Ll/Lu/Nd)로 판정해야 한다.
    classes = sum(
        [
            any(unicodedata.category(c) == "Ll" for c in password),
            any(unicodedata.category(c) == "Lu" for c in password),
            any(unicodedata.category(c) == "Nd" for c in password),
            any(c in _SPECIAL_CHARS for c in password),
        ]
    )
    if classes < min_classes:
        problems.append(f"대문자, 소문자, 숫자, 특수문자 중 {min_classes}종 이상을 조합해야 합니다.")
    return problems


def generate_temp_password(length: int = 20) -> str:
    """Cryptographically secure temporary password that satisfies any policy
    (length 20 with all 4 classes clears configured minimums up to 20/4)."""
    alphabet = string.ascii_lowercase + string.ascii_uppercase + string.digits + "!@#$%^&*-_"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        # Ensure all four classes present so it satisfies min_classes up to 4.
        if validate_password_policy(candidate, min_length=1, min_classes=4) == []:
            return candidate


def new_session_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
