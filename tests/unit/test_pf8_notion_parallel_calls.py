"""PF8 - Notion 왕복 지연시간 감소 검증.

`app/team_docs/notion_docs.py`·`app/tickets/notion_write.py` 안에서 서로 독립인 Notion
호출이 순서대로(직렬로) 나가면, 호출 하나에 지연이 있을 때 전체 지연이 호출 수만큼
누적된다. 이 파일은 그 누적이 사라졌는지(병렬로 나가는지)를 **경과 시간**으로 잰다.

가짜 outbound 는 모든 호출에 고정 지연(`delay`)을 준다. 호출이 직렬이면 총 경과가
`N * delay` 에 가깝고, 병렬이면 `delay` 하나에 가깝다 - 그 차이로 판정한다.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.team_docs import notion_docs
from app.tickets import notion_write as tickets_notion_write

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _SlowOutbound:
    """모든 호출에 `delay` 초를 재운 뒤 응답한다. 동시 호출 수(peak)도 함께 잰다."""

    def __init__(self, *, delay: float, blocks: list[dict] | None = None):
        self.delay = delay
        self.blocks = list(blocks or [])
        self.calls: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._inflight = 0
        self.peak_inflight = 0

    def request(self, method, url, **kwargs):
        with self._lock:
            self.calls.append((method, url))
            self._inflight += 1
            self.peak_inflight = max(self.peak_inflight, self._inflight)
        try:
            time.sleep(self.delay)
        finally:
            with self._lock:
                self._inflight -= 1
        if method == "GET" and "/children" in url:
            return _Resp(200, {"results": self.blocks, "has_more": False})
        if method == "DELETE":
            return _Resp(200, {"archived": True})
        if method == "PATCH":
            return _Resp(200, {"results": []})
        if method == "POST" and "/query" in url:
            return _Resp(200, {"results": [], "has_more": False})
        if method == "GET" and "/v1/databases/" in url:
            return _Resp(200, {"properties": {}})
        raise AssertionError(f"unexpected {method} {url}")


DELAY = 0.15
# 순차였다면 최소 이만큼 걸린다(호출 수 * delay 의 대부분). 병렬이면 delay 하나에 가깝다.
# delay 의 1.8배를 문턱으로 둔다 - 스레드 기동 오버헤드를 감안해도 순차(3배 이상)와는
# 확실히 구분된다.
_THRESHOLD = DELAY * 1.8
# 블록 삭제 두 테스트는 삭제 전에 blocks 를 읽는 GET 이 하나 더 필요하다(이건 병렬화 대상이
# 아니다 - 지울 목록을 알아야 지운다). 그래서 문턱은 "GET 1회 + 병렬 삭제 1배치"인
# 2*DELAY 를 기준으로 여유를 둔다 - 순차(GET + N*DELETE = 7*DELAY)와는 여전히 확실히 구분된다.
_DELETE_THRESHOLD = DELAY * 3.5


def test_resolve_relation_maps_sends_three_relation_queries_concurrently(settings):
    """유형·카테고리·프로젝트 relation 조회 세 개가 동시에 나가는지 - PF8 핵심 사례.

    이 셋은 서로 다른 DB 를 가리키는 완전히 독립인 조회다. 직렬이면 3 * DELAY, 병렬이면
    DELAY 하나에 가깝다.
    """
    schema = {
        notion_docs.PROP_TYPE: {"type": "relation", "relation": {"database_id": "type-db"}},
        notion_docs.PROP_CATEGORY: {"type": "relation", "relation": {"database_id": "cat-db"}},
        notion_docs.PROP_PROJECT: {"type": "relation", "relation": {"database_id": "proj-db"}},
    }
    ob = _SlowOutbound(delay=DELAY)

    start = time.perf_counter()
    maps = notion_docs.resolve_relation_maps(ob, settings, schema)
    elapsed = time.perf_counter() - start

    assert set(maps) == {notion_docs.PROP_TYPE, notion_docs.PROP_CATEGORY, notion_docs.PROP_PROJECT}
    assert ob.peak_inflight >= 2, "동시에 나간 호출이 없다 - 직렬로 돈다"
    assert elapsed < _THRESHOLD, (
        f"관계 조회 3개가 병렬로 돌지 않는다: 경과 {elapsed:.3f}s (문턱 {_THRESHOLD:.3f}s)"
    )


def test_replace_page_body_deletes_blocks_concurrently_for_tickets(settings):
    """티켓 본문 교체: 기존 블록 N 개를 지우는 DELETE 가 동시에 나가는지."""
    n = 6
    blocks = [
        {"id": f"b{i}", "type": "paragraph", "paragraph": {"rich_text": []}}
        for i in range(n)
    ]
    ob = _SlowOutbound(delay=DELAY, blocks=blocks)

    start = time.perf_counter()
    tickets_notion_write.replace_page_body(ob, settings, page_id="page-1", blocks=[])
    elapsed = time.perf_counter() - start

    deletes = [c for c in ob.calls if c[0] == "DELETE"]
    assert len(deletes) == n
    assert ob.peak_inflight >= 3, "블록 삭제가 동시에 나가지 않는다 - 직렬로 돈다"
    assert elapsed < _DELETE_THRESHOLD, (
        f"블록 {n}개 삭제가 병렬로 돌지 않는다: 경과 {elapsed:.3f}s (문턱 {_DELETE_THRESHOLD:.3f}s)"
    )


def test_replace_page_body_deletes_blocks_concurrently_for_team_docs(settings):
    """문서 본문 교체(team_docs): 기존 블록 N 개를 지우는 DELETE 가 동시에 나가는지."""
    n = 6
    blocks = [
        {"id": f"b{i}", "type": "paragraph", "paragraph": {"rich_text": []}}
        for i in range(n)
    ]
    ob = _SlowOutbound(delay=DELAY, blocks=blocks)

    start = time.perf_counter()
    notion_docs.replace_page_body(ob, settings, page_id="doc-1", blocks=[])
    elapsed = time.perf_counter() - start

    deletes = [c for c in ob.calls if c[0] == "DELETE"]
    assert len(deletes) == n
    assert ob.peak_inflight >= 3, "블록 삭제가 동시에 나가지 않는다 - 직렬로 돈다"
    assert elapsed < _DELETE_THRESHOLD, (
        f"블록 {n}개 삭제가 병렬로 돌지 않는다: 경과 {elapsed:.3f}s (문턱 {_DELETE_THRESHOLD:.3f}s)"
    )
