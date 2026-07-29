"""Runner Registry schemas (spec §15.2)."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.http_client import AUTH_TYPES

RUNNER_PROVIDER_TYPES = frozenset({"local_http"})


class RunnerConfig(BaseModel):
    """Full validated config — also re-validates rollback snapshots."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    provider_type: str = "local_http"
    base_url: str = Field(min_length=1, max_length=500)
    health_url: str | None = Field(default=None, max_length=500)
    version: str | None = Field(default=None, max_length=64)
    capabilities: dict = Field(default_factory=dict)
    auth_type: str = "none"
    secret_ref: str | None = Field(default=None, max_length=128)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    concurrency_limit: int = Field(default=1, ge=1, le=32)
    retry_policy: dict = Field(default_factory=dict)
    enabled: bool = False  # spec §15.5: new runners start disabled
    maintenance_state: str = "normal"
    owner: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list)
    integration_id: str | None = None

    @field_validator("provider_type")
    @classmethod
    def _provider_known(cls, v: str) -> str:
        if v not in RUNNER_PROVIDER_TYPES:
            raise ValueError(f"provider_type은 {sorted(RUNNER_PROVIDER_TYPES)} 중 하나여야 합니다.")
        return v

    @field_validator("auth_type")
    @classmethod
    def _auth_known(cls, v: str) -> str:
        if v not in AUTH_TYPES:
            raise ValueError(f"auth_type은 {sorted(AUTH_TYPES)} 중 하나여야 합니다.")
        return v

    @field_validator("maintenance_state")
    @classmethod
    def _state_known(cls, v: str) -> str:
        if v not in {"normal", "degraded", "maintenance"}:
            raise ValueError("maintenance_state가 올바르지 않습니다.")
        return v

    @field_validator("capabilities", "retry_policy")
    @classmethod
    def _json_serializable(cls, v: dict) -> dict:
        json.dumps(v)
        return v

    @model_validator(mode="after")
    def _secret_required_for_auth(self):
        # 'none'이 아닌 인증인데 secret_ref가 비어 있으면 저장은 되고 health/test/dispatch
        # 시점에야 조용히 깨진다. 저장 시 즉시 막아 명확한 메시지로 실패하게 한다
        # (integrations 화면의 secret_ref 안내와 같은 계약).
        if self.auth_type != "none" and not (self.secret_ref and self.secret_ref.strip()):
            raise ValueError(
                "auth_type이 'none'이 아니면 secret_ref(서버 secrets 디렉터리의 파일 이름)를 "
                "반드시 지정해야 합니다."
            )
        return self


class RunnerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    health_url: str | None = Field(default=None, max_length=500)
    version: str | None = Field(default=None, max_length=64)
    capabilities: dict | None = None
    auth_type: str | None = None
    secret_ref: str | None = Field(default=None, max_length=128)
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    concurrency_limit: int | None = Field(default=None, ge=1, le=32)
    retry_policy: dict | None = None
    maintenance_state: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = None


class RunnerCloneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
