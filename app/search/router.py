"""통합 검색 API (조회 전용).

GET /api/search?q=… — 로그인만 요구하고 역할 게이트는 걸지 않는다. **결과 자체가 범위와
역할로 걸러져 나가기 때문**이다(app/search/service.py). 라우터에서 역할로 막으면 일반
사용자가 자기 티켓조차 못 찾게 되고, 반대로 라우터만 열고 결과를 안 거르면 그게 유출이다.

핸들러는 동기 함수다(저장소 불변 §2). 하는 일은 로컬 SELECT 두 번과 파이썬 필터뿐이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_principal
from app.core.scope import Principal
from app.search import service
from app.search.query import MAX_QUERY_CHARS

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    q: str = Query("", max_length=MAX_QUERY_CHARS * 4, description="검색어"),
    limit: int = Query(service.DEFAULT_PER_KIND, ge=1, le=service.MAX_PER_KIND),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """유형별로 묶인 검색 결과. 3자 미만이면 LIKE 폴백으로 답한다(`mode` 로 알려 준다)."""
    return service.search(db, raw_query=q, principal=principal, per_kind=limit)
