"""검색 인덱스 강제 재색인 API — 운영자 전용 쓰기 경로 (C7).

## `app/search/router.py` 와 **일부러** 분리한다

`tests/unit/test_search_no_hot_path.py::test_the_search_read_path_does_not_write` 가
`app/search/router.py`·`app/search/service.py` 소스에 `reindex_all` 문자열이 있으면 실패로
못박는다 — "검색 조회 한 번이 인덱스 쓰기가 되면 안 된다" 는 규칙을 소스에서 직접 확인하는
장치다. 이 라우터는 조회가 아니라 **운영자가 명시적으로 누르는 쓰기 행위**라서 그 규칙의
대상이 아니지만, 같은 파일에 넣으면 검사가 두 가지(진짜 핫패스 vs 명시적 관리자 액션)를
구별하지 못한다. 그래서 파일을 나눈다 — `app/search/router.py` 는 계속 순수 조회 전용으로
남고, 이 파일이 유일한 쓰기 진입점이다.

## 동기 호출이지 잡 큐가 아니다

게시판·사용자는 로컬 DB만 읽는다. 티켓·문서는 저장소 seam(`app/tickets/repository_notion.py`
`_cache_ready`) 뒤에 있어서, **캐시가 이미 채워져 있으면**(운영에서는 워커의 정기 동기화 틱이
항상 먼저 돌아 있으므로 이 경로가 기본이다) 로컬 미러만 읽고 Notion 을 왕복하지 않는다 — 그
경우 재구축은 자체 docstring이 말하는 대로 "코퍼스가 수천 건이라도 1초 안쪽"이다.

**드물게** 티켓 캐시가 한 번도 채워진 적이 없으면(예: 이 기능을 막 배포한 직후, 아직 워커가
첫 동기화를 못 돌린 순간) 티켓 저장소가 실시간 Notion 조회로 떨어진다 — 그래도 잡 큐로
옮기지 않는 이유는, `reindex_all` 자신이 유형별로 넓은 try/except 를 이미 두고 있어(모듈
docstring 참조) 그 조회가 실패해도(설정 안 됨·타임아웃) 요청은 몇 초 안에 `status:"error"`
로 끝나기 때문이다 — team_docs/tickets 의 수동 동기화와 정확히 같은 "동기로 부르고, 실패해도
요청 스레드를 영원히 붙잡지 않는다" 성격이라 같은 동기 요청-응답 패턴을 그대로 따른다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import MODERATOR_ROLES
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.errors import ConflictError, ForbiddenError
from app.observability.models import COMPONENT_SEARCH
from app.observability.service import upsert_sync_status
from app.search.indexer import reindex_all, reindex_lock
from app.settings.gate import block_if_maintenance
from app.users.models import User

router = APIRouter(
    prefix="/api/search",
    tags=["search-admin"],
    dependencies=[Depends(block_if_maintenance)],
)


def _reindex_view(result) -> dict:
    return {
        "status": result.status,
        "item_count": result.item_count,
        "error": result.error,
        "per_kind": dict(result.per_kind),
        "truncated": result.truncated,
    }


@router.post("/reindex", dependencies=[Depends(require_csrf)])
def trigger_reindex(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """검색 인덱스를 지금 당장 통째로 다시 만든다 — team_docs/tickets 의 수동 동기화 버튼과
    같은 뜻이다. 정기 워커 틱(search_index_interval_seconds)까지 기다리지 않아도 된다.

    운영자 권한은 team_docs·tickets 의 수동 동기화와 **같은 기준**(MODERATOR_ROLES)을 쓴다 —
    "운영자" 의 뜻이 화면마다 갈라지지 않게 한다.
    """
    if me.role not in MODERATOR_ROLES:
        raise ForbiddenError("검색 재색인은 운영자만 실행할 수 있습니다.")
    if not reindex_lock.acquire(blocking=False):
        # 기다리지 않는다 — app/tickets/claim_lock.py 와 같은 이유. 신경질적 더블클릭이
        # 같은 재구축을 두 번 돌리지 않는다.
        raise ConflictError("이미 검색 재색인이 진행 중입니다. 잠시 후 다시 시도해 주세요.")
    try:
        now = request.app.state.clock.now()
        result = reindex_all(
            db,
            tickets=request.app.state.repositories.tickets,
            documents=request.app.state.repositories.documents,
            now=now,
        )
        # 워커 틱과 같은 표(sync_status)에 남긴다 — 수동으로 돌렸어도 운영 대시보드가
        # "마지막 재색인이 언제였나" 를 정기 틱과 구별 없이 보여줘야 한다(app/worker_main.py
        # mirror_sync_status 와 같은 이유).
        upsert_sync_status(
            db, COMPONENT_SEARCH, status=result.status, now=now,
            item_count=result.item_count, truncated=result.truncated,
            error=result.error, detail={"per_kind": dict(result.per_kind)},
        )
    finally:
        reindex_lock.release()
    record_audit_from_request(
        request,
        db,
        action="search.reindex",
        object_type="search_index",
        object_id="search",
        after={"status": result.status, "item_count": result.item_count},
    )
    return {"reindex": _reindex_view(result)}
