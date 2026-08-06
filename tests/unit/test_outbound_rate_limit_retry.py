"""Notion 429 대응 (S9).

## 왜 필요했나

Notion 은 초당 평균 3요청으로 제한한다. 문서 동기화 한 번이 **최대 251요청**이라 429 가
실제로 난다. 그런데 저장소 전체에 `429` 도 `Retry-After` 도 **한 건도 없었다** - 즉 429 를
받으면 동기화가 통째로 실패하고, 사용자에게는 낡은 목록이 남았다. 원인은 로그를 파야만 보였다.

## 재시도를 어디까지 하는가

**429 에만** 한다. 429 는 "받았지만 처리하지 않았다" 는 뜻이라 같은 요청을 다시 보내도
안전하다 - 블록 추가처럼 두 번 하면 안 되는 요청도 마찬가지다.
5xx 는 서버가 처리했는지 알 수 없어 **중복 쓰기**가 될 수 있으므로 재시도하지 않는다.
애매할 때는 안 하는 쪽이 옳다.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.allowlist import AllowlistRegistry
from app.core.http_client import (
    MAX_RETRY_WAIT_SECONDS,
    OutboundClient,
    retry_wait_seconds,
)
from app.core.secret_refs import FileSecretReferenceProvider

pytestmark = pytest.mark.unit

URL = "https://api.notion.com/v1/databases/x/query"


def _response(status: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, request=httpx.Request("GET", URL))


# ── Retry-After 해석 ──────────────────────────────────────────────────────────


def test_the_servers_own_number_wins_over_our_guess():
    assert retry_wait_seconds(_response(429, {"Retry-After": "2"}), 0) == 2.0


def test_an_absurdly_long_wait_means_give_up_not_hang():
    """🔴 몇 분씩 기다리면 워커 한 칸이 잡히고 그 사이 다른 잡이 전부 밀린다."""
    assert retry_wait_seconds(_response(429, {"Retry-After": "600"}), 0) is None


def test_a_garbage_header_falls_back_to_backoff_instead_of_crashing():
    got = retry_wait_seconds(_response(429, {"Retry-After": "soon"}), 0)
    assert got is not None and got > 0


def test_without_a_header_we_back_off_further_each_time():
    """🔴 처음엔 `waits == sorted(waits)` 로만 단정했는데, 그건 **전부 같은 값도 통과**한다.

    백오프를 상수로 바꾸는 사보타주가 초록으로 지나갔다. 물러나는지 보려면 **엄격히 커지는지**
    를 봐야 한다. "정렬돼 있다" 와 "커진다" 는 다른 말이다.
    """
    waits = [retry_wait_seconds(_response(429), attempt) for attempt in range(4)]
    assert all(b > a for a, b in zip(waits, waits[1:])), f"물러나지 않는다: {waits}"
    assert all(w <= MAX_RETRY_WAIT_SECONDS for w in waits), waits


def test_a_negative_wait_is_not_treated_as_immediate_retry():
    """음수를 0으로 읽으면 **쉬지 않고 다시 때린다** - 제한을 더 세게 만든다."""
    assert retry_wait_seconds(_response(429, {"Retry-After": "-5"}), 0) is None


# ── 실제 재시도 동작 ──────────────────────────────────────────────────────────


class _Transport(httpx.BaseTransport):
    """정해진 순서대로 응답을 돌려주고 **몇 번 불렸는지** 센다."""

    def __init__(self, statuses: list[int], headers: dict | None = None) -> None:
        self.statuses = list(statuses)
        self.headers = headers or {}
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        status = self.statuses.pop(0) if self.statuses else 200
        return httpx.Response(status, headers=self.headers, json={"ok": True})


@pytest.fixture()
def make_client(tmp_path):
    import json as _json

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "allowed-services.json").write_text(
        # 허용 목록은 host:port 로 적는다(기본 포트도 명시해야 한다).
        _json.dumps({"hosts": ["api.notion.com:443"]}), encoding="utf-8"
    )
    allowlists = AllowlistRegistry(config_dir)

    def _make(transport):
        slept: list[float] = []
        client = OutboundClient(
            allowlists,
            FileSecretReferenceProvider(tmp_path),
            transport=transport,
            sleep=slept.append,   # 실제로 자면 테스트가 느려지고, 느린 테스트는 곧 지워진다
        )
        return client, slept

    return _make


def test_a_429_is_retried_and_then_succeeds(make_client):
    transport = _Transport([429, 429, 200], headers={"Retry-After": "1"})
    client, slept = make_client(transport)

    resp = client.get(URL, allowlist="services", rate_limit_retries=3)

    assert resp.status_code == 200, "재시도했는데도 실패로 남았다"
    assert transport.calls == 3, f"재시도 횟수가 다르다: {transport.calls}"
    assert slept == [1.0, 1.0], f"서버가 말한 만큼 안 기다렸다: {slept}"


def test_without_opting_in_nothing_is_retried(make_client):
    """🔴 기본값은 **재시도 안 함**이다.

    여기서 무조건 켜면 n8n 웹훅처럼 두 번 보내면 안 되는 경로까지 함께 재시도한다.
    그 판단은 부르는 쪽만 할 수 있다.
    """
    transport = _Transport([429, 200])
    client, slept = make_client(transport)

    resp = client.get(URL, allowlist="services")

    assert resp.status_code == 429
    assert transport.calls == 1, f"켜지 않았는데 재시도했다: {transport.calls}"
    assert slept == []


def test_a_server_error_is_not_retried(make_client):
    """5xx 는 처리 여부를 알 수 없다 - 재시도하면 **중복 쓰기**가 될 수 있다."""
    transport = _Transport([503, 200])
    client, slept = make_client(transport)

    resp = client.get(URL, allowlist="services", rate_limit_retries=3)

    assert resp.status_code == 503, "5xx 를 재시도했다"
    assert transport.calls == 1, f"5xx 를 재시도했다: {transport.calls}"


def test_giving_up_returns_the_429_instead_of_pretending(make_client):
    """끝까지 429 면 그대로 돌려준다 - 호출자가 SYNC_ERROR 로 남기고 화면이 말한다."""
    transport = _Transport([429, 429, 429, 429], headers={"Retry-After": "1"})
    client, _slept = make_client(transport)

    resp = client.get(URL, allowlist="services", rate_limit_retries=2)

    assert resp.status_code == 429
    assert transport.calls == 3, f"시도 횟수가 상한과 다르다: {transport.calls}"


def test_an_impossible_wait_stops_immediately(make_client):
    """서버가 10분을 기다리라고 하면 **기다리지 않는다.** 한 번 더 때리지도 않는다."""
    transport = _Transport([429, 200], headers={"Retry-After": "600"})
    client, slept = make_client(transport)

    resp = client.get(URL, allowlist="services", rate_limit_retries=3)

    assert resp.status_code == 429
    assert transport.calls == 1, f"기다리지 않기로 해 놓고 다시 때렸다: {transport.calls}"
    assert slept == []
