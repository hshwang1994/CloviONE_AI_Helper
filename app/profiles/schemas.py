"""프로필 셀프서비스 요청 본문 스키마.

전부 Pydantic 으로 받는다 — 자유 dict(`await request.json()`)로 받으면 유효-JSON 이지만
객체가 아닌 본문(`[1,2]`, `"x"`, `42`)이 `.get` 에서 AttributeError 로 터져 잡히지 않는
500 이 된다(app/auth/router.py 의 ChangePasswordRequest 가 같은 이유로 만들어졌다).

부분 갱신(PATCH)은 "안 준 키는 안 바꾼다"가 계약이므로 전부 `None` 기본값이다 —
`False` 와 '안 줌'을 구분해야 방해금지를 끄는 요청과 다른 값만 바꾸는 요청이 섞이지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PreferenceUpdate(BaseModel):
    """PATCH /api/me/preferences — 준 키만 바꾼다."""

    muted_types: list[str] | None = None
    dnd_enabled: bool | None = None
    # 지금부터 N분간 조용. 0 이하면 자동 해제 시각을 지운다(수동으로 끌 때까지 유지).
    dnd_minutes: int | None = Field(default=None, ge=0, le=7 * 24 * 60)
    quiet_hours_enabled: bool | None = None
    quiet_start: str | None = Field(default=None, max_length=5)
    quiet_end: str | None = Field(default=None, max_length=5)


class TourUpdate(BaseModel):
    """POST /api/me/tour — 끝냈거나(completed) 건너뛰었거나(skipped) 다시 보기(reset)."""

    action: str = Field(default="complete", max_length=16)


class SavedViewCreate(BaseModel):
    screen_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    query: str = Field(default="", max_length=1024)
    # 같은 이름이 이미 있을 때 덮어쓸지. 기본은 거절(409)이고, 화면이 물어본 뒤 다시 보낸다.
    overwrite: bool = False
