"""Workflow Registry schemas (spec §16.2)."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator


class WorkflowConfig(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str | None = Field(default=None, max_length=2000)
    webhook_url: str = Field(min_length=1, max_length=500)
    http_method: str = "POST"
    payload_schema: dict | None = None
    response_schema: dict | None = None
    operation_mode: str = "read"
    approval_required: bool = False
    enabled: bool = True
    owner: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list)

    @field_validator("http_method")
    @classmethod
    def _method_known(cls, v: str) -> str:
        v = v.upper()
        if v not in {"POST", "GET"}:
            raise ValueError("http_method는 POST 또는 GET만 허용됩니다.")
        return v

    @field_validator("operation_mode")
    @classmethod
    def _mode_known(cls, v: str) -> str:
        if v not in {"read", "write"}:
            raise ValueError("operation_mode는 read 또는 write여야 합니다.")
        return v

    @field_validator("payload_schema", "response_schema")
    @classmethod
    def _schema_serializable(cls, v: dict | None) -> dict | None:
        if v is not None:
            json.dumps(v)
        return v


class WorkflowUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    purpose: str | None = None
    webhook_url: str | None = Field(default=None, min_length=1, max_length=500)
    http_method: str | None = None
    payload_schema: dict | None = None
    response_schema: dict | None = None
    operation_mode: str | None = None
    approval_required: bool | None = None
    owner: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = None
