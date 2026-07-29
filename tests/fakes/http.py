"""Programmable fake for outbound HTTP — injected as an httpx transport.

Test code may import httpx (the app-side ban applies to app/ only).
"""

from __future__ import annotations

import httpx


class _Route:
    def __init__(self, *, status=200, json_body=None, text=None, mode="normal"):
        self.status = status
        self.json_body = json_body
        self.text = text
        self.mode = mode  # normal | timeout | connect_error | invalid_json


class FakeHTTP:
    def __init__(self) -> None:
        self.routes: dict[str, _Route] = {}
        self.requests: list[httpx.Request] = []

    def on(self, url_prefix: str, *, status: int = 200, json_body=None, text=None) -> None:
        self.routes[url_prefix] = _Route(status=status, json_body=json_body, text=text)

    def on_timeout(self, url_prefix: str) -> None:
        self.routes[url_prefix] = _Route(mode="timeout")

    def on_connect_error(self, url_prefix: str) -> None:
        self.routes[url_prefix] = _Route(mode="connect_error")

    def on_invalid_json(self, url_prefix: str) -> None:
        self.routes[url_prefix] = _Route(mode="invalid_json")

    def _handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        for prefix, route in self.routes.items():
            if url.startswith(prefix):
                if route.mode == "timeout":
                    raise httpx.ConnectTimeout("fake timeout", request=request)
                if route.mode == "connect_error":
                    raise httpx.ConnectError("fake connection refused", request=request)
                if route.mode == "invalid_json":
                    return httpx.Response(
                        200, text="{this is not json", request=request
                    )
                if route.json_body is not None:
                    return httpx.Response(route.status, json=route.json_body, request=request)
                return httpx.Response(route.status, text=route.text or "", request=request)
        return httpx.Response(
            502, json={"error": "no fake route configured"}, request=request
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handler)
