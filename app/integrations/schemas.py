"""Integration Registry schemas (spec §14.3)."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.http_client import AUTH_TYPES

#: 새로 만들 수 있는 유형. **하나뿐**이라 화면에서 그 선택기를 내렸다(S20) — 고를 것이
#: 하나뿐인 선택기는 고를 것이 없는 선택기다.
NEW_PROVIDER_TYPES = frozenset({"http_service"})

#: 이미 저장돼 있을 수 있는 값. S11 이 n8n 과 러너 셋을, S14 가 Notion 런타임을 걷으면서
#: 그 이름들은 **새로 만들 수 없게** 됐지만 **행은 남았다.**
#:
#: 🔴 그 둘을 같은 목록으로 두면 남은 행이 **고칠 수 없게 된다.** 수정 경로는 저장된 값에
#: 화면이 보낸 것만 얹어 이 스키마로 다시 검증하는데(`router.py::update_integration` 의
#: `merged`), 저장된 값이 어휘 밖이면 이름 한 글자를 고치려 해도 422 다. 롤백도 같은
#: 스키마를 지나므로 그 행의 옛 판으로 되돌릴 수도 없다. 운영 실측(2026-08-25): 연동 넷 중
#: `n8n` 행 하나가 정확히 그 상태였다 — 화면에는 「수정」이 그려져 있고 누르면 언제나 실패했다.
#:
#: 그래서 **읽기 어휘는 넓고 쓰기 어휘는 좁다.** 여기 있는 이름을 화면이 새로 고를 수는
#: 없지만(그 선택기가 없다), 이미 그 값을 든 행은 계속 고칠 수 있다.
LEGACY_PROVIDER_TYPES = frozenset({"notion", "n8n"})

PROVIDER_TYPES = NEW_PROVIDER_TYPES | LEGACY_PROVIDER_TYPES

#: 화면이 안 보내면 이 값이다. 새로 고를 수 있는 유형이 하나뿐이라 화면이 물을 것도 없다.
DEFAULT_PROVIDER_TYPE = "http_service"


class IntegrationConfig(BaseModel):
    """Full validated config — also used to re-validate rollback snapshots."""

    name: str = Field(min_length=1, max_length=120)
    provider_type: str = DEFAULT_PROVIDER_TYPE
    description: str | None = Field(default=None, max_length=2000)
    base_url: str = Field(min_length=1, max_length=500)
    health_url: str | None = Field(default=None, max_length=500)
    auth_type: str = "none"
    secret_ref: str | None = Field(default=None, max_length=128)
    capabilities: dict = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("provider_type")
    @classmethod
    def _provider_known(cls, v: str) -> str:
        if v not in PROVIDER_TYPES:
            raise ValueError(f"provider_type은 {sorted(PROVIDER_TYPES)} 중 하나여야 합니다.")
        return v

    @field_validator("auth_type")
    @classmethod
    def _auth_known(cls, v: str) -> str:
        if v not in AUTH_TYPES:
            raise ValueError(f"auth_type은 {sorted(AUTH_TYPES)} 중 하나여야 합니다.")
        return v

    @field_validator("capabilities")
    @classmethod
    def _capabilities_serializable(cls, v: dict) -> dict:
        json.dumps(v)
        return v

    @model_validator(mode="after")
    def _secret_required_for_auth(self):
        # secret_ref의 help text가 "'없음'이 아닌 인증이면 반드시 지정하세요"라고
        # 말하지만 저장 시점엔 강제되지 않아, 이후 첫 헬스체크/호출 때에야
        # OutboundClient가 "인증 방식에 필요한 secret_ref가 없습니다"로 실패했다
        # (app/core/http_client.py). runners/schemas.py의 동일 규칙과 맞춘다.
        if self.auth_type != "none" and not (self.secret_ref and self.secret_ref.strip()):
            raise ValueError(
                "auth_type이 'none'이 아니면 secret_ref(서버 secrets 디렉터리의 파일 이름)를 "
                "반드시 지정해야 합니다."
            )
        return self


class IntegrationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider_type: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    health_url: str | None = Field(default=None, max_length=500)
    auth_type: str | None = None
    secret_ref: str | None = Field(default=None, max_length=128)
    capabilities: dict | None = None
    enabled: bool | None = None
