"""127.0.0.1 의 최소 SMTP 받는 쪽 — 로컬 메일 E2E(계획 M5 E2E-0)의 「받은 편지함」이다.

외부 SMTP 계정 없이 제품의 실제 전송기(`app/mail/transport.py`)가 보내는 메일을 그대로 받아 `.eml` 로 남긴다. 표준 라이브러리만 쓴다
(`smtpd` 는 3.12 에서 빠졌고 `aiosmtpd` 는 제품 의존성이 아니다). 받는 쪽이 하는 일은 SMTP 대화의 최소한이다:

    EHLO/HELO · MAIL FROM · RCPT TO · DATA(점 한 줄로 끝, 점 풀기) · RSET · NOOP · QUIT

보안 연결(STARTTLS)과 로그인(AUTH)은 하지 않는다 — 제품 설정을 「보안 연결 없음 · 계정 없음」으로 두고 쓴다. 들을 곳은 127.0.0.1 하나다.

메일 한 통 = `<out>/<순번>-<시각>.eml` + 같은 이름의 `.json`(봉투: 보낸 사람 · 받는 사람 · 받은 시각). DATA 가 끝나지 않고 끊긴 메일은
남기지 않는다(깨진 메일을 「받았다」로 세지 않는다).

    python -m scripts.ui_qa.mail_sink --port 2526 --out dist/mail-e2e/inbox
    python -m scripts.ui_qa.mail_sink --selftest
"""

from __future__ import annotations

import argparse
import json
import socketserver
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "dist" / "mail-e2e" / "inbox"
MAX_BYTES = 10 * 1024 * 1024


class _Handler(socketserver.StreamRequestHandler):
    timeout = 30

    def _say(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode("ascii"))
        self.wfile.flush()

    def handle(self) -> None:  # noqa: C901 - SMTP 대화 하나
        sink: MailSink = self.server.sink  # type: ignore[attr-defined]
        self._say("220 clovirassist-mail-sink ESMTP")
        mail_from: str | None = None
        rcpts: list[str] = []
        while True:
            raw = self.rfile.readline(4096)
            if not raw:
                return
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            verb = line[:4].upper()
            arg = line[4:].strip()
            if verb in ("EHLO", "HELO"):
                if verb == "EHLO":
                    self.wfile.write(b"250-clovirassist-mail-sink\r\n250-8BITMIME\r\n250-SMTPUTF8\r\n250 SIZE 10485760\r\n")
                    self.wfile.flush()
                else:
                    self._say("250 clovirassist-mail-sink")
            elif verb == "MAIL":
                mail_from = _addr(arg)
                rcpts = []
                self._say("250 2.1.0 Ok")
            elif verb == "RCPT":
                if mail_from is None:
                    self._say("503 5.5.1 MAIL first")
                    continue
                rcpts.append(_addr(arg))
                self._say("250 2.1.5 Ok")
            elif verb == "DATA":
                if mail_from is None or not rcpts:
                    self._say("503 5.5.1 RCPT first")
                    continue
                self._say("354 End data with <CR><LF>.<CR><LF>")
                body = bytearray()
                finished = False
                while True:
                    chunk = self.rfile.readline(1024 * 1024)
                    if not chunk:
                        break
                    if chunk in (b".\r\n", b".\n"):
                        finished = True
                        break
                    if chunk.startswith(b".."):
                        chunk = chunk[1:]
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                if not finished:
                    return
                queue_id = sink.store(mail_from, rcpts, bytes(body))
                self._say(f"250 2.0.0 Ok: queued as {queue_id}")
                mail_from, rcpts = None, []
            elif verb == "RSET":
                mail_from, rcpts = None, []
                self._say("250 2.0.0 Ok")
            elif verb == "NOOP":
                self._say("250 2.0.0 Ok")
            elif verb == "QUIT":
                self._say("221 2.0.0 Bye")
                return
            else:
                self._say("502 5.5.2 Error: command not recognized")


def _addr(arg: str) -> str:
    text = arg.split(":", 1)[1] if ":" in arg else arg
    text = text.strip()
    if text.startswith("<") and ">" in text:
        text = text[1:text.index(">")]
    return text.split()[0] if text else ""


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class MailSink:
    """받은 메일을 디렉터리에 남기는 받는 쪽. `start()` 뒤 `port` 로 붙는다."""

    def __init__(self, out_dir: Path, port: int = 0) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        self._server = _Server(("127.0.0.1", port), _Handler)
        self._server.sink = self  # type: ignore[attr-defined]
        self.port = self._server.server_address[1]
        self._thread: threading.Thread | None = None

    def start(self) -> "MailSink":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def store(self, mail_from: str, rcpts: list[str], body: bytes) -> str:
        with self._lock:
            self._seq += 1
            seq = self._seq
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        name = f"{seq:04d}-{stamp}"
        (self.out_dir / f"{name}.eml").write_bytes(body)
        (self.out_dir / f"{name}.json").write_text(
            json.dumps({"from": mail_from, "to": rcpts, "received_at": stamp}, ensure_ascii=False), encoding="utf-8")
        return f"SINK{seq:04d}"

    def messages(self) -> list[Path]:
        return sorted(self.out_dir.glob("*.eml"))

    def wait_for(self, count: int, timeout: float = 30.0) -> list[Path]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = self.messages()
            if len(found) >= count:
                return found
            time.sleep(0.2)
        return self.messages()


def selftest() -> int:
    """맞는 발송 한 통은 남고, DATA 가 끝나지 않고 끊긴 발송은 남지 않는다."""
    import shutil
    import smtplib
    import socket
    import tempfile
    from email.message import EmailMessage

    out = Path(tempfile.mkdtemp(prefix="mail-sink-selftest-"))
    sink = MailSink(out).start()
    try:
        msg = EmailMessage()
        msg["From"] = "noreply@example.test"
        msg["To"] = "someone@example.test"
        msg["Subject"] = "[ClovirAssist] 받는 쪽 자기 시험"
        msg.set_content("첫 줄\n.점으로 시작하는 줄\n")
        with smtplib.SMTP("127.0.0.1", sink.port, timeout=5) as s:
            s.ehlo("selftest")
            s.send_message(msg)
        with socket.create_connection(("127.0.0.1", sink.port), timeout=5) as raw:
            f = raw.makefile("rwb")
            f.readline()
            for cmd in (b"EHLO x\r\n", b"MAIL FROM:<a@b.test>\r\n", b"RCPT TO:<c@d.test>\r\n", b"DATA\r\n"):
                f.write(cmd)
                f.flush()
                while True:
                    reply = f.readline()
                    if not reply or reply[3:4] != b"-":
                        break
            f.write(b"Subject: broken\r\n\r\nno terminating dot")
            f.flush()
        time.sleep(0.5)
        files = sink.messages()
        problems = []
        if len(files) != 1:
            problems.append(f"남은 메일이 {len(files)}통이다(1통이어야 한다)")
        else:
            from email import message_from_bytes
            from email.policy import default as default_policy

            parsed = message_from_bytes(files[0].read_bytes(), policy=default_policy)
            text = parsed.get_body(("plain",)).get_content() if parsed.get_body(("plain",)) else ""
            envelope = json.loads(files[0].with_suffix(".json").read_text(encoding="utf-8"))
            if ".점으로 시작하는 줄" not in text:
                problems.append("본문이 빠졌거나 점 풀기가 틀렸다")
            if parsed["Subject"] != "[ClovirAssist] 받는 쪽 자기 시험":
                problems.append("제목이 다르다")
            if envelope.get("to") != ["someone@example.test"]:
                problems.append(f"봉투 받는 사람이 다르다: {envelope.get('to')}")
        if problems:
            for p in problems:
                print("  -", p)
            print("MAIL_SINK_SELFTEST_FAILED")
            return 1
        print("MAIL_SINK_SELFTEST_OK (맞는 발송 1통 저장 · 끊긴 DATA 0통)")
        return 0
    finally:
        sink.stop()
        shutil.rmtree(out, ignore_errors=True)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="127.0.0.1 의 최소 SMTP 받는 쪽(메일 E2E)")
    ap.add_argument("--port", type=int, default=2526)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    sink = MailSink(Path(args.out), args.port).start()
    print(f"MAIL_SINK_LISTENING 127.0.0.1:{sink.port} → {sink.out_dir}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sink.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
