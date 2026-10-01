"""AI 작업공간 요청 스키마 (S10).

길이 상한을 전부 적는다 — 상한이 없는 문자열 필드는 그대로 DB 컬럼 길이 초과가 되고,
그 실패는 422 가 아니라 500 이다.

질의 상한은 `app/search/query.py::MAX_QUERY_CHARS` 를 **네 배**로 받는다. 검색 라우터와
같은 규약이다: 서버는 넉넉히 받고 `normalize()` 가 자른다 — 붙여 넣은 글이 한 글자
넘었다고 422 를 내면 사용자는 무엇이 잘못됐는지 모른다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.ai.retrieval.service import MAX_TOP_K
from app.search.query import MAX_QUERY_CHARS

_QUERY_MAX = MAX_QUERY_CHARS * 4


class DraftRequest(BaseModel):
    """문서 초안. 어디에 만들지는 **프로젝트로** 말하고, 그것도 선택이다.

    예전에는 `space_id` 가 필수였다 — 「서버가 고르면 내 문서가 어디 갔는지 모르게 된다」는
    이유였다. 그 걱정은 화면이 「공간」을 고르게 만들었고, 새 문서 대화상자가 프로젝트를
    선택으로 바꾼 뒤에도 이 경로만 필수로 남아 **AI 초안은 프로젝트 없이 못 만들었다.**

    지금은 화면과 같은 규약을 쓴다: `project_id` 를 주면 그 프로젝트, 안 주면 조직 공통
    문서다. 어디로 갔는지는 응답의 `route` 가 그대로 말해 준다 — 그 자리가 원래 걱정을
    실제로 해소하는 자리다. `space_id` 는 옛 호출자를 위해 남기되 선택이다.
    """

    space_id: str | None = Field(default=None, max_length=36)
    project_id: str | None = Field(default=None, max_length=36)
    folder_id: str | None = Field(default=None, max_length=36)
    title: str = Field(min_length=1, max_length=500)
    instruction: str = Field(min_length=1, max_length=_QUERY_MAX)
    top_k: int | None = Field(default=None, ge=1, le=MAX_TOP_K)
