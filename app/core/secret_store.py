"""비밀 값을 **쓰는** 단 하나의 길 (계획 2.3).

읽기는 `FileSecretReferenceProvider` 가 그대로 한다. 쓰기는 두 갈래다.

- 이 프로세스가 `SECRETS_DIR` 에 직접 쓸 수 있으면(개발 머신, 테스트) 파일을 곧바로 쓴다.
- 운영 설치처럼 못 쓰면 특권 헬퍼의 `secret.write` 액션을 부른다(`app/sysops/actions_secrets.py`).

어느 쪽이든 되돌려 읽는 API 는 만들지 않는다. 화면이 아는 것은 "저장돼 있는가" 와
"언제 바꿨는가" 뿐이다.

헬퍼가 없는 설치에서 "되는 척" 하지 않는다. 저장하지 못했으면 409 와 이유를 돌려준다 -
200 을 주면 운영자는 키를 바꿨다고 믿고 떠난다(`SecretDirNotWritableError` 머리말과 같은 원칙).
"""

from __future__ import annotations

from datetime import datetime

from app.core.errors import AppError
from app.core.secret_refs import (
    STATUS_CONFIGURED,
    FileSecretReferenceProvider,
    SecretDirNotWritableError,
)
from app.core.secret_slots import get_slot, normalize_value


class SecretHelperRefusedError(AppError):
    status_code = 422
    code = "secret_write_refused"
    default_message = "비밀 값을 저장하지 못했습니다."


class SecretStore:
    def __init__(self, provider: FileSecretReferenceProvider, client=None) -> None:
        self._provider = provider
        self._client = client

    def _helper(self):
        if self._client is None:
            from app.sysops.client import SysopsClient

            self._client = SysopsClient()
        return self._client

    def status(self, name: str) -> dict:
        get_slot(name)
        stored = self._provider.status(name) == STATUS_CONFIGURED
        updated: datetime | None = self._provider.modified_at(name) if stored else None
        return {"stored": stored, "updated_at": updated.isoformat() if updated else None}

    def write(self, name: str, value: object) -> bool:
        """값을 저장하고, 실제로 바뀌었는지를 돌려준다."""
        slot = get_slot(name)
        text = normalize_value(slot, value)
        if self._provider.writable():
            current = self._provider.get(name)
            if current is not None and current.reveal() == text:
                return False
            self._provider.write(name, text)
            return True
        reply = self._helper().call("secret.write", {"name": name, "value": text})
        return self._check(reply)

    def delete(self, name: str) -> bool:
        get_slot(name)
        if self._provider.writable():
            return self._provider.delete(name)
        reply = self._helper().call("secret.delete", {"name": name})
        return self._check(reply)

    @staticmethod
    def _check(reply) -> bool:
        if not reply.available:
            raise SecretDirNotWritableError(
                "비밀 값을 저장할 도우미(clovirassist-privhelper)에 연결하지 못했습니다. "
                + reply.detail
            )
        if not reply.ok:
            raise SecretHelperRefusedError(reply.detail or None)
        return bool(reply.changed)
