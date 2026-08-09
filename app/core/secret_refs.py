"""File-based secret references (spec §0.2, §25.4).

The database stores only reference NAMES; values live as files under
settings.secrets_dir (production: /etc/clovirone-web-assistant/secrets,
root:clovirone-web 0640). SecretValue masks itself in repr/str/format so a
secret can never leak through logging or error messages by accident.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from app.core.errors import AppError

logger = logging.getLogger("app.secrets")

_REF_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

STATUS_CONFIGURED = "configured"
STATUS_MISSING = "missing"

# 새로 쓰는 secret 파일의 권한. 소유자만 읽는다.
# 설치 스크립트는 디렉터리를 root:clovirone-web 0750 으로 만들고 파일은 0640 으로 둔다.
# 웹이 직접 쓸 수 있는 설치(개발, 또는 secrets_dir 을 서비스 계정 소유로 둔 설치)에서는
# 그 파일의 소유자가 웹 계정이므로 0600 이 더 좁고 충분하다.
SECRET_FILE_MODE = 0o600


class SecretMissingError(AppError):
    status_code = 409
    code = "secret_missing"
    default_message = "필요한 Secret이 설정되어 있지 않습니다."


class InvalidSecretRefError(AppError):
    status_code = 422
    code = "invalid_secret_ref"
    default_message = "Secret reference 이름이 올바르지 않습니다."


class SecretDirNotWritableError(AppError):
    """웹 프로세스가 secret 디렉터리에 못 쓴다.

    운영 설치에서 **이것이 정상이다.** systemd 유닛이 `ProtectSystem=strict` 로 하드닝돼
    있고 `ReadWritePaths` 에 `/etc/clovirone-web-assistant` 가 없다. 디렉터리 자체도
    root:clovirone-web 0750 이라 웹 계정은 파일을 만들 수 없다.

    그래서 이 오류는 '고장' 이 아니라 **이 서버가 그렇게 만들어졌다는 사실**이다. 화면은
    이것을 실패로 그리지 말고, 대신 무엇을 해야 하는지(서버에서 파일을 놓는 절차)를
    말해야 한다. 되는 척하고 200 을 돌려주면 운영자는 토큰을 바꿨다고 믿는다.
    """

    status_code = 409
    code = "secret_dir_not_writable"
    default_message = "서버가 secret 디렉터리에 쓸 수 없습니다."


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
            # CORE-12: 예전엔 이 이름을 예외 메시지에 직접 실었다. AppError.message는
            # register_error_handlers(errors.py)가 그대로 응답 본문에 싣는다 — 이 예외를
            # 일으키는 요청은 관리자만 부르는 게 아니다(app/core/http_client.py의
            # OutboundClient가 일반 사용자 흐름에서도 부른다). 어떤 secret_ref 파일이
            # 서버에 없는지는 운영자가 로그에서 볼 정보지, 응답을 받는 사람 모두에게
            # 노출할 정보가 아니다. code="secret_missing" 만으로 화면이 판별할 수 있다.
            logger.warning("secret reference missing: %s", name)
            raise SecretMissingError()
        return value

    @property
    def directory(self) -> Path:
        """화면이 "어디에 놓으라" 고 말하려면 경로를 알아야 한다."""
        return self._secrets_dir

    def writable(self) -> bool:
        """이 프로세스가 secret 파일을 **실제로 만들 수 있는가**.

        `os.access` 만 보지 않는다. 그것은 uid/gid 만 보고 대답하는데, 운영에서 막는 것은
        systemd 의 `ProtectSystem=strict` 다 - 그 마운트 네임스페이스에서는 권한 비트가
        허용해도 쓰기가 EROFS 로 실패한다. 즉 `os.access` 는 **되는 척하는 대답**을 한다.
        그래서 임시 파일을 하나 만들어 보고 지운다. 부작용이 남지 않는 유일한 확인이다.
        """
        try:
            if not self._secrets_dir.is_dir():
                return False
            handle = tempfile.NamedTemporaryFile(
                dir=self._secrets_dir, prefix=".probe-", delete=False
            )
        except OSError:
            return False
        try:
            handle.close()
            os.unlink(handle.name)
        except OSError:  # pragma: no cover - 만들었는데 못 지우는 경우는 사실상 없다
            return False
        return True

    def write(self, name: str, value: str) -> None:
        """secret 값을 파일 하나로 놓는다. **되돌려 읽는 경로는 만들지 않는다.**

        같은 디렉터리에 임시 파일로 쓰고 `os.replace` 로 바꾼다. 곧바로 덮어쓰면 그 사이에
        읽는 쪽이 **잘린 토큰**을 읽는다 - 그 순간의 조회는 401 이 되고, 원인은 어디에도
        안 남는다. 권한은 파일을 만드는 순간부터 좁게 준다(먼저 만들고 나중에 chmod 하면
        그 틈에 다른 계정이 읽을 수 있다).
        """
        path = self._path_for(name)
        if not value or not value.strip():
            raise InvalidSecretRefError("빈 값은 secret 으로 저장하지 않습니다.")
        try:
            fd, tmp_name = tempfile.mkstemp(dir=self._secrets_dir, prefix=".tmp-")
        except OSError as exc:
            raise SecretDirNotWritableError(
                f"secret 디렉터리에 쓸 수 없습니다: {self._secrets_dir}"
            ) from exc
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(value.strip())
            os.chmod(tmp_path, SECRET_FILE_MODE)
            os.replace(tmp_path, path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise SecretDirNotWritableError(
                f"secret 파일을 쓰지 못했습니다: {self._secrets_dir}"
            ) from exc
