"""ChatGPT 계정 연결 도우미 (`tools/connect/`) — 관리자 PC 에서 콜백만 받아 서버에 넘긴다 (계획 3.14, D-516).

못박는 성질:
1. 도우미는 서버에 짝짓기 토큰과 자기가 연 포트를 알리고, 받은 콜백의 code · state · client_id 를 그대로 넘긴다.
2. 콜백은 127.0.0.1 의 `/auth/callback` 에서만 받는다. 다른 경로는 404 다.
3. 서버 인증서 지문을 주면 그 지문의 인증서에만 붙는다. 다르면 아무것도 보내지 않는다.
4. 평문 http 는 개발 PC 의 루프백만 허락한다(짝짓기 토큰과 인가 코드가 평문으로 흐르면 안 된다).
5. PowerShell 도우미는 문법이 맞고, Windows PowerShell 5.1 이 한글을 읽도록 UTF-8 BOM 으로 저장돼 있다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import ssl
import subprocess
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = ROOT / "tools" / "connect"


def _helper_module():
    spec = importlib.util.spec_from_file_location("clovirassist_connect", HELPER_DIR / "clovirassist-connect.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _helper_module()


class FakeServer:
    """서버 자리. 받은 본문을 남기고 정해진 답을 준다."""

    def __init__(self, *_args, **_kwargs):
        self.posts: list[tuple[str, dict]] = []

    def post(self, path: str, body: dict) -> dict:
        self.posts.append((path, body))
        if path.endswith("/begin"):
            return {"transaction_id": "tx-1", "authorize_url": "https://auth.openai.com/api/accounts/authorize?x=1"}
        return {"ok": True, "account_label": "owner@example.com"}


def test_the_helper_relays_the_callback_and_nothing_more():
    server = FakeServer()
    printed: list[str] = []

    def browser(_url):
        port = server.posts[0][1]["port"]

        def visit():
            base = f"http://127.0.0.1:{port}"
            with pytest.raises(Exception):
                urllib.request.urlopen(base + "/favicon.ico", timeout=5)
            urllib.request.urlopen(base + "/auth/callback?code=CODE-1&state=STATE-1&client_id=oaiapp_1&scope=a+b",
                                   timeout=5).read()

        threading.Thread(target=visit, daemon=True).start()

    code = helper.run(["--server", "https://ca.example", "--token", "T" * 43, "--port", "18455"],
                      open_browser=browser, client_factory=lambda *_a: server, out=printed.append)
    assert code == 0
    (begin_path, begin), (complete_path, complete) = server.posts
    assert begin_path == "/api/connect/openai/begin" and begin["pairing_token"] == "T" * 43
    assert 18455 <= begin["port"] < 18475
    assert complete_path == "/api/connect/openai/complete"
    assert complete == {"pairing_token": "T" * 43, "transaction_id": "tx-1", "callback": {
        "code": "CODE-1", "state": "STATE-1", "client_id": "oaiapp_1", "scope": "a b", "error": None}}
    assert not any("CODE-1" in line for line in printed), "인가 코드를 화면에 찍지 않는다"


@pytest.mark.parametrize("server", ["http://clovirassist.example", "ftp://x.example", "not a url"])
def test_plain_http_is_allowed_only_for_loopback(server):
    with pytest.raises(helper.HelperError):
        helper.check_server(server)
    assert helper.check_server("http://127.0.0.1:8080")[0] == "http"


def test_fingerprint_formats():
    digest = "ab" * 32
    assert helper.normalize_fingerprint("sha256:" + digest.upper()) == digest
    assert helper.normalize_fingerprint(":".join(digest[i:i + 2] for i in range(0, 64, 2))) == digest
    with pytest.raises(helper.HelperError):
        helper.normalize_fingerprint("sha256:1234")


@pytest.fixture(scope="module")
def tls_server(tmp_path_factory):
    """자체 서명 인증서로 도는 작은 서버 - 설치가 만든 인증서와 같은 모양이다."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "clovirassist.test")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=1)).sign(key, hashes.SHA256()))
    folder = tmp_path_factory.mktemp("tls")
    (folder / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (folder / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                      serialization.PrivateFormat.PKCS8,
                                                      serialization.NoEncryption()))
    received: list = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            received.append(json.loads(self.rfile.read(length)))
            body = json.dumps({"transaction_id": "tx", "authorize_url": "https://auth.openai.com/x"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(folder / "cert.pem", folder / "key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fingerprint = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    yield f"https://127.0.0.1:{server.server_address[1]}", fingerprint, received
    server.shutdown()


def test_a_pinned_self_signed_certificate_is_trusted(tls_server):
    url, fingerprint, received = tls_server
    reply = helper.ServerClient(url, fingerprint).post("/api/connect/openai/begin", {"pairing_token": "t", "port": 1})
    assert reply["transaction_id"] == "tx" and received[-1] == {"pairing_token": "t", "port": 1}


def test_a_different_certificate_gets_nothing(tls_server):
    url, _fingerprint, received = tls_server
    before = len(received)
    with pytest.raises(helper.HelperError):
        helper.ServerClient(url, "00" * 32).post("/api/connect/openai/begin", {"pairing_token": "secret", "port": 1})
    assert len(received) == before, "지문이 다르면 토큰을 보내기 전에 멈춘다"


def test_without_a_pin_an_untrusted_certificate_is_refused(tls_server):
    url, _fingerprint, received = tls_server
    before = len(received)
    with pytest.raises(helper.HelperError):
        helper.ServerClient(url, None).post("/api/connect/openai/begin", {"pairing_token": "secret", "port": 1})
    assert len(received) == before


def test_the_powershell_helper_is_bom_encoded_and_parses():
    raw = (HELPER_DIR / "clovirassist-connect.ps1").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "Windows PowerShell 5.1 은 BOM 없는 UTF-8 의 한글을 깨뜨린다"
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell 이 없는 환경이다(문법 검사는 Windows 개발 PC 와 CI 에서 한다)")
    script = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{HELPER_DIR / 'clovirassist-connect.ps1'}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; $errors.Count"
    )
    done = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().splitlines()[-1] == "0", done.stdout
