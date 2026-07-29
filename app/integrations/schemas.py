"""Integration Registry schemas (spec §14.3)."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.http_client import AUTH_TYPES

PROVIDER_TYPES = frozenset({"n8n", "http_service", "notion_via_n8n"})


class IntegrationConfig(BaseModel):
    """Full validated config — also used to re-validate rollback snapshots."""

    name: str = Field(min_length=1, max_length=120)
    provider_type: str
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
