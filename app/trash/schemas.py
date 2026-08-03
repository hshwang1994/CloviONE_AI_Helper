"""휴지통 입력 스키마 (일괄 복원/영구삭제)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class TrashBulkIds(BaseModel):
    """일괄 복원/영구삭제 요청 — 휴지통 항목 id 목록(노션 page id 아님)."""

    model_config = ConfigDict(extra="forbid")
    ids: list[str]

    @field_validator("ids")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for x in v or []:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        if not out:
            raise ValueError("항목을 선택하세요.")
        return out[:100]
