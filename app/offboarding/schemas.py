"""오프보딩 요청 스키마.

`extra="forbid"` 를 쓰는 이유: 이 API 는 **계정을 잠그고 티켓을 옮기는** 요청이다. 오타 하나
(`deactivate` 를 `deactive` 로)가 조용히 무시되면 관리자는 '비활성화까지 했다'고 믿는데 계정은
그대로 열려 있게 된다. 모르는 필드는 400 으로 되돌려 준다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OffboardingRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 옮길 티켓을 **서버가 고르지 않는다**. 미리보기에서 사용자가 확인한 목록 그대로 온다 —
    # 그래야 "미리 보여 준 것과 실제로 실행한 것이 같다"가 성립한다.
    ticket_page_ids: list[str] = Field(default_factory=list, max_length=100)
    successor_user_id: str | None = Field(default=None, max_length=36)
    deactivate: bool = True
    archive: bool = False
    note: str | None = Field(default=None, max_length=1000)
