"""부서·직책 요청 스키마.

이름 검증은 서비스의 normalize_name이 한다(공백 정리 + 빈 이름 거부). 여기서 min_length로
한 번 더 막으면 '   '처럼 공백만 있는 이름이 통과해 두 곳의 규칙이 갈라진다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrgItemCreateRequest(BaseModel):
    name: str = Field(max_length=120)


class OrgItemUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    active: bool | None = None
