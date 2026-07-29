"""File-based secret references (spec §0.2, §25.4).

The database stores only reference NAMES; values live as files under
settings.secrets_dir (production: /etc/clovirone-web-assistant/secrets,
root:clovirone-web 0640). SecretValue masks itself in repr/str/format so a
secret can never leak through logging or error messages by accident.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.errors import AppError

_REF_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

STATUS_CONFIGURED = "configured"
STATUS_MISSING = "missing"


class SecretMissingError(AppError):
    status_code = 409
    code = "secret_missing"
    default_message = "필요한 Secret이 설정되어 있지 않습니다."


class InvalidSecretRefError(AppError):
    status_code = 422
    code = "invalid_secret_ref"
    default_message = "Secret reference 이름이 올바르지 않습니다."


class SecretValue:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "***"

    def __str__(self) -> str:
        return "***"

    def __format__(self, _spec: str) -> str:
        return "***"


class FileSecretReferenceProvider:
    def __init__(self, secrets_dir: Path) -> None:
        self._secrets_dir = Path(secrets_dir)

    def _path_for(self, name: str) -> Path:
        if not _REF_NAME.match(name or ""):
            raise InvalidSecretRefError()
        return self._secrets_dir / name

    def status(self, name: str) -> str:
        try:
            path = self._path_for(name)
        except InvalidSecretRefError:
            return STATUS_MISSING
        return STATUS_CONFIGURED if path.is_file() else STATUS_MISSING

    def get(self, name: str) -> SecretValue | None:
        path = self._path_for(name)
        if not path.is_file():
            return None
        return SecretValue(path.read_text(encoding="utf-8").strip())

    def require(self, name: str) -> SecretValue:
        value = self.get(name)
        if value is None:
            raise SecretMissingError(f"Secret reference가 비어 있습니다: {name}")
        return value
