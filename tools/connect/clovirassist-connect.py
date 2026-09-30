#!/usr/bin/env python3
"""ClovirAssist ChatGPT 계정 연결 도우미 (macOS, Linux).

ClovirAssist 의 AI 설정 화면에서 「Continue with ChatGPT」를 누르면 이 파일을 실행하는 명령이 나온다. 이 도우미는
브라우저가 있는 이 PC 에서 ChatGPT 의 로그인 콜백(http://127.0.0.1:<포트>/auth/callback)을 받아 ClovirAssist 서버에
넘기기만 한다. 토큰은 이 PC 를 거치지 않는다 - 인가 코드를 토큰으로 바꾸는 일은 서버가 한다.

    python3 clovirassist-connect.py --server https://clovirassist.example --token <화면의 토큰> [--fingerprint sha256:<지문>]

표준 라이브러리만 쓴다. 서버 인증서 지문(--fingerprint)을 주면 그 지문의 인증서만 믿는다 - 설치가 만든 자체 서명
인증서에서도 안전하게 붙는다. 주지 않으면 이 PC 가 믿는 인증 기관으로 확인한다.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import socket
import ssl
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

VERSION = "1"
CALLBACK_PATH = "/auth/callback"
FIRST_PORT = 1455
PORT_TRIES = 20
WAIT_SECONDS = 600
DONE_PAGE = (
    "<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\"><title>ClovirAssist</title>"
    "<body style=\"font-family:sans-serif;padding:2rem\"><p>ChatGPT 승인을 받았습니다. "
    "ClovirAssist 화면으로 돌아가세요. 이 창은 닫아도 됩니다.</p></body></html>"
)


class HelperError(Exception):
    pass


class LoopbackServer(HTTPServer):
    # 다른 프로그램이 이미 쓰는 포트를 겹쳐 잡지 않는다(Windows 의 SO_REUSEADDR 는 그것을 허락한다).
    allow_reuse_address = False


def normalize_fingerprint(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip().lower()
    if text.startswith("sha256:"):
        text = text[len("sha256:"):]
    text = text.replace(":", "")
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise HelperError("인증서 지문 형식이 올바르지 않습니다. 화면의 명령을 그대로 붙여 넣으세요.")
    return text


def check_server(server: str) -> tuple[str, str, int]:
    parts = urlsplit(server.strip())
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise HelperError("서버 주소는 https:// 로 시작해야 합니다.")
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost"):
        # 짝짓기 토큰과 인가 코드가 평문으로 흐르면 안 된다. 개발 PC 의 루프백만 예외다.
        raise HelperError("서버 주소는 https:// 로 시작해야 합니다.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.scheme, parts.hostname, port


class ServerClient:
    """서버에 JSON 을 보낸다. 지문을 주면 TLS 연결 직후 그 지문을 비교한 뒤에만 요청을 보낸다."""

    def __init__(self, server: str, fingerprint: str | None, *, timeout: float = 30.0) -> None:
        self.scheme, self.host, self.port = check_server(server)
        self.fingerprint = fingerprint
        self.timeout = timeout

    def _connection(self):
        if self.scheme == "http":
            return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        if self.fingerprint:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        else:
            context = ssl.create_default_context()
        return http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout, context=context)

    def post(self, path: str, body: dict) -> dict:
        conn = self._connection()
        try:
            conn.connect()
            if self.scheme == "https" and self.fingerprint:
                der = conn.sock.getpeercert(binary_form=True) or b""
                if hashlib.sha256(der).hexdigest() != self.fingerprint:
                    raise HelperError("서버 인증서 지문이 화면의 값과 다릅니다. 연결하지 않습니다.")
            payload = json.dumps(body).encode("utf-8")
            conn.request("POST", path, body=payload, headers={
                "Content-Type": "application/json", "Accept": "application/json",
                "User-Agent": f"clovirassist-connect/{VERSION}",
            })
            response = conn.getresponse()
            raw = response.read()
        except (OSError, http.client.HTTPException) as exc:
            if isinstance(exc, ssl.SSLCertVerificationError):
                raise HelperError("서버 인증서를 확인하지 못했습니다. 화면의 명령을 그대로 붙여 넣었는지 확인하세요.") from None
            raise HelperError(f"서버에 연결하지 못했습니다: {type(exc).__name__}") from None
        finally:
            conn.close()
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            data = {}
        if response.status >= 400:
            error = data.get("error") if isinstance(data, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            raise HelperError(message or f"서버가 요청을 거절했습니다(HTTP {response.status}).")
        return data if isinstance(data, dict) else {}


def open_listener(first_port: int = FIRST_PORT, tries: int = PORT_TRIES) -> tuple[HTTPServer, dict]:
    """127.0.0.1 의 빈 포트에서 콜백 하나를 받는 서버. (서버, 받은 값 칸)을 돌려준다."""
    received: dict = {}
    event = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server 규약
            parts = urlsplit(self.path)
            if parts.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            query = parse_qs(parts.query)
            received.update({key: values[0] for key, values in query.items() if values})
            body = DONE_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            event.set()

        def log_message(self, *args):  # 인가 코드가 든 주소를 화면에 찍지 않는다
            return

    last_error = None
    for port in range(first_port, first_port + tries):
        try:
            server = LoopbackServer(("127.0.0.1", port), Handler)
        except OSError as exc:
            last_error = exc
            continue
        server.timeout = 0.5
        received["_event"] = event
        return server, received
    raise HelperError(f"콜백을 받을 빈 포트를 찾지 못했습니다: {type(last_error).__name__}")


def wait_for_callback(server: HTTPServer, received: dict, *, wait_seconds: float = WAIT_SECONDS,
                      clock=time.monotonic) -> dict:
    event: threading.Event = received["_event"]
    deadline = clock() + wait_seconds
    try:
        while not event.is_set():
            if clock() > deadline:
                raise HelperError("브라우저 승인을 기다리는 시간이 지났습니다. 화면에서 연결을 다시 시작하세요.")
            server.handle_request()
    finally:
        server.server_close()
    return {key: value for key, value in received.items() if key != "_event"}


def run(argv=None, *, open_browser=webbrowser.open, client_factory=ServerClient, out=print) -> int:
    parser = argparse.ArgumentParser(description="ClovirAssist ChatGPT 계정 연결 도우미")
    parser.add_argument("--server", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--fingerprint")
    parser.add_argument("--port", type=int, default=FIRST_PORT)
    args = parser.parse_args(argv)
    try:
        client = client_factory(args.server, normalize_fingerprint(args.fingerprint))
        server, received = open_listener(args.port)
        port = server.server_address[1]
        begun = client.post("/api/connect/openai/begin", {"pairing_token": args.token, "port": port})
        url = begun.get("authorize_url")
        transaction_id = begun.get("transaction_id")
        if not isinstance(url, str) or not url.startswith("https://") or not transaction_id:
            server.server_close()
            raise HelperError("서버가 인가 주소를 주지 않았습니다.")
        out("브라우저에서 ChatGPT 승인 화면을 엽니다. 열리지 않으면 아래 주소를 브라우저에 붙여 넣으세요.")
        out(url)
        open_browser(url)
        callback = wait_for_callback(server, received)
        done = client.post("/api/connect/openai/complete", {
            "pairing_token": args.token, "transaction_id": transaction_id,
            "callback": {key: callback.get(key) for key in ("code", "state", "client_id", "scope", "error")},
        })
    except HelperError as exc:
        out(f"연결하지 못했습니다. {exc}")
        return 1
    except KeyboardInterrupt:
        out("연결을 멈췄습니다.")
        return 130
    label = done.get("account_label") or "ChatGPT 계정"
    out(f"{label} 계정을 연결했습니다. ClovirAssist 화면으로 돌아가세요.")
    return 0


if __name__ == "__main__":
    socket.setdefaulttimeout(60)
    sys.exit(run())
