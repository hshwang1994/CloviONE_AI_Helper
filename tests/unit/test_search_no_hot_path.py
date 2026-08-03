"""검색 인덱싱은 **워커 틱 한 곳에서만** 일어난다 (PLAN Phase 5).

"저장할 때 인덱스도 같이 갱신하면 더 신선하다"는 유혹은 언젠가 반드시 온다. 이 앱에서는
그게 정확히 가장 나쁜 자리를 때린다:
  * 채팅 전송(`_append_message`)은 INSERT + `event_seq` UPDATE 로 SAVEPOINT 재시도를 도는
    가장 뜨거운 쓰기 경로다(PLAN C9 — 계획서가 지목했던 'presence 병목'은 틀렸고 여기가
    진짜였다). 여기에 인덱스 쓰기를 얹으면 병목을 가장 나쁜 곳에서 키운다.
  * 폴링 경로(놀이 3초, 휴지통 15초, 알림 60초)에 걸면 **읽기가 쓰기가 된다** — ETag/304 로
    아끼려던 것을 그대로 되돌린다.

주석으로만 적어 두면 좋은 뜻으로 누가 건다. 소스에서 직접 확인한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 인덱서를 부르면 안 되는 모듈들. usage_events 의 금지 목록과 같은 자리다.
HOT_PATH_MODULES = (
    "app/team_chat/router.py",
    "app/team_chat/service.py",
    "app/team_chat/repository.py",
    "app/games/router.py",
    "app/games/service.py",
    "app/notifications/router.py",
    "app/trash/router.py",
    "app/chat/router.py",
    "app/chat/service.py",
    "app/board/router.py",
    "app/board/service.py",
    "app/tickets/router.py",
    "app/tickets/service.py",
    "app/team_docs/router.py",
    "app/team_docs/service.py",
)


@pytest.mark.parametrize("relative", HOT_PATH_MODULES)
def test_hot_paths_do_not_import_the_search_indexer(relative):
    source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
    assert "search.indexer" not in source, (
        f"{relative} 가 검색 인덱서를 import 한다. 인덱싱 훅은 워커 틱 한 곳뿐이다 — "
        "뜨거운 쓰기/폴링 경로에 인덱스 쓰기를 얹으면 읽기가 쓰기로 바뀐다 "
        "(app/search/indexer.py 의 규칙 참조)."
    )


def test_the_guard_above_is_not_vacuous():
    """검사 문자열이 판별력을 가진다는 증명 — 실제로 거는 워커에서는 보인다."""
    worker = (PROJECT_ROOT / "app/worker_main.py").read_text(encoding="utf-8")
    assert "search.indexer" in worker, "워커에 인덱싱 틱이 배선돼 있지 않다"


def test_the_search_read_path_does_not_write():
    """조회 엔드포인트가 인덱스를 쓰지 않는다 — 검색 한 번이 쓰기가 되면 안 된다."""
    for relative in ("app/search/router.py", "app/search/service.py"):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        for banned in ("db.add(", "db.commit(", "db.delete(", "reindex_all"):
            assert banned not in source, f"{relative} 의 조회 경로에 쓰기({banned})가 있다"
