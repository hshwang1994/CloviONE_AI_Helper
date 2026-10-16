"""QA 하네스의 둘러보기 해제가 이미 끝낸 계정에는 쓰지 않는다 (r23).

랩 화면 대장은 사용자 본인 계정으로 읽기만 하려고 돈다. 그런데 하네스는 로그인할 때마다 「둘러보기 완료」를 보냈고, 서버는 그때마다
완료 시각을 지금으로 다시 적는다(`app/profiles/service.py::mark_tour_seen`) — 읽기 전용 실행이 그 계정의 기록을 바꿨다(10-17).
판정은 서버의 `tour.show` 다: 이미 끝낸 계정(show=False)이면 보내지 않고, 아직이면 보낸다(QA 계정의 첫 방문 창이 화면을 덮지 않게).
"""

from __future__ import annotations

from scripts.ui_qa.auth import _dismiss_tour


class _Response:
    def __init__(self, status: int, body: dict):
        self.status = status
        self._body = body

    def json(self) -> dict:
        return self._body


class _Request:
    def __init__(self, show):
        self.show = show
        self.posts: list[str] = []

    def get(self, url: str, timeout=None) -> _Response:
        if url.endswith("/api/me/preferences"):
            return _Response(200, {"tour": {"show": self.show}})
        return _Response(200, {"csrf_token": "token"})

    def post(self, url: str, data=None, headers=None, timeout=None) -> _Response:
        self.posts.append(url)
        return _Response(200, {})


class _Context:
    def __init__(self, show):
        self.request = _Request(show)


def _run(show) -> list[str]:
    ctx = _Context(show)
    _dismiss_tour(ctx, "https://lab.example", lambda *_: None)
    return ctx.request.posts


def test_already_finished_account_is_not_written():
    assert _run(False) == []


def test_unfinished_account_gets_the_tour_dismissed():
    assert _run(True) == ["https://lab.example/api/me/tour"]
