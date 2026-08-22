"""저장소 설정 요청 스키마 (S8).

길이 상한을 전부 적는다 — 상한이 없는 문자열 필드는 그대로 DB 컬럼 길이 초과가 되고,
그 실패는 422 가 아니라 500 이다(`app/knowledge/schemas.py` 와 같은 이유).

**경로는 절대 경로만 받는다.** 상대 경로는 프로세스의 작업 디렉터리에 따라 다른 곳을
가리키고, 웹과 워커는 작업 디렉터리가 같다는 보장이 없다. 같은 검사가 DB CHECK 에도
있다 — 여기서 막는 것은 사용자에게 422 로 말해 주기 위해서다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.storage.adapters import KINDS, ROLES

# 절대 경로. 널바이트를 명시적으로 뺀다 — 경로 문자열의 널바이트는 C 계층에서 뒤를
# 잘라 버려서, 검사를 통과한 문자열과 실제로 열리는 경로가 달라진다.
# 드라이브 문자(`C:/…`)를 함께 받는 이유는 DB 제약과 같다(`app/storage/models.py`).
_ABS_PATH = r"^(/|[A-Za-z]:/)[^\x00]*$"
_KIND = "^(" + "|".join(KINDS) + ")$"
_ROLE = "^(" + "|".join(ROLES) + ")$"


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(pattern=_KIND)
    role: str = Field(pattern=_ROLE)
    base_path: str = Field(pattern=_ABS_PATH, max_length=1000)
    #: NFS/SMB 는 필수, LOCAL 은 비워 둔다. 짝이 안 맞으면 서비스가 422 로 거절한다.
    mount_point: str | None = Field(default=None, pattern=_ABS_PATH, max_length=1000)
    #: `nas.example:/export`(NFS) 또는 `//nas.example/share`(SMB).
    source: str = Field(default="", max_length=500)
    options: str = Field(default="", max_length=500)
    #: `secrets_dir` 안의 **파일 이름**이다. 비밀번호를 여기 적지 않는다.
    credentials_ref: str | None = Field(default=None, max_length=120)
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_path: str | None = Field(default=None, pattern=_ABS_PATH, max_length=1000)
    mount_point: str | None = Field(default=None, pattern=_ABS_PATH, max_length=1000)
    source: str | None = Field(default=None, max_length=500)
    options: str | None = Field(default=None, max_length=500)
    credentials_ref: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    #: 낙관적 잠금. S6 이 정한 규약 그대로다(D-240).
    base_version: int | None = Field(default=None, ge=1)


class AttachmentUpdate(BaseModel):
    caption: str | None = Field(default=None, max_length=500)
