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


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=_QUERY_MAX)
    top_k: int | None = Field(default=None, ge=1, le=MAX_TOP_K)


class DraftRequest(BaseModel):
    """문서 초안. **어디에 만들지를 요청이 정한다** — 서버가 공간을 고르지 않는다.

    고르면 「내 문서가 어디 갔는지 모르겠다」가 되고, 그 문서는 검색으로만 찾을 수 있다.
    """

    space_id: str = Field(min_length=1, max_length=36)
    folder_id: str | None = Field(default=None, max_length=36)
    title: str = Field(min_length=1, max_length=500)
    instruction: str = Field(min_length=1, max_length=_QUERY_MAX)
    top_k: int | None = Field(default=None, ge=1, le=MAX_TOP_K)
