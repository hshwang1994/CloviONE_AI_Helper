"""AI 실측 하네스들이 함께 쓰는 조각 — 로그인 · TLS 기준점 · 질문 보내기 · 답 기다리기 · 이메일 가리기 · env 파일 읽기.

`ai_lab_e2e.py`(연결 · 채팅 실측)와 `ai_truth_e2e.py`(실데이터 진실 하네스, A10)가 같은 함수를 쓴다. 두 벌로 두면 한쪽만
고쳐지고, 그러면 「같은 랩에서 두 하네스가 다른 답을 받았다」가 하네스 탓인지 제품 탓인지 가릴 수 없다.

지키는 것 셋:

- 비밀은 명령행에 받지 않는다. 비밀번호는 환경 변수나 `read_env_file` 로만 들어오고, 이 모듈은 그 값을 어디에도 적지 않는다.
- TLS 는 기본으로 검증한다. 기준점은 명시한 `--cacert` → `UI_QA_TLS_CA` → `dist/ops/<호스트>.crt` → 시스템 기준점 순서다.
  검증을 끄는 것(`--insecure`)은 부르는 쪽이 명시할 때만이다.
- 결과 파일에 적는 글은 `mask_emails` 를 지난다.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]

#: 이메일 주소. 앞에 `*` 가 붙은 자리는 이미 가린 주소라 다시 잡지 않는다(가리기를 두 번 해도 같은 글이 나온다).
EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+*-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

#: 도우미 답을 기다리며 메시지 목록을 다시 읽는 간격(초).
POLL_SECONDS = 1.5


class LoginError(RuntimeError):
    """로그인이 200 이 아니다. 비밀번호 · 이메일은 메시지에 싣지 않는다(상태 코드만)."""

    def __init__(self, status: int) -> None:
        super().__init__(f"로그인에 실패했습니다(상태 {status}).")
        self.status = status


def utf8_console() -> None:
    """Windows 콘솔(cp949)에서 한국어 · 「—」 를 찍다 죽지 않게 표준 출력을 UTF-8 로 돌린다(`app/cli/ai_cli.py` 와 같은 이유)."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def log(msg: str) -> None:
    print(msg, flush=True)


def mask_emails(text: str) -> str:
    """글 안의 이메일 주소를 `a****b@도메인` 으로 가린다."""
    def one(m):
        local, _, domain = m.group(0).partition("@")
        return f"{local[:1]}****{local[-1:]}@{domain}"
    return EMAIL_RE.sub(one, text or "")


def ca_path(base: str) -> str | bool:
    """TLS 기준점 — `UI_QA_TLS_CA` → `dist/ops/<호스트>.crt` → 시스템 기준점(True)."""
    env = os.environ.get("UI_QA_TLS_CA")
    if env:
        return env
    host = urlsplit(base).hostname or ""
    candidate = ROOT / "dist" / "ops" / f"{host}.crt"
    return str(candidate) if candidate.exists() else True


def resolve_verify(base: str, *, cacert: str | None = None, insecure: bool = False) -> str | bool:
    """httpx 의 `verify` 값. 명시한 `cacert` 가 먼저이고, `insecure` 는 검증을 끈다(부르는 쪽이 경고를 찍는다)."""
    if insecure:
        return False
    if cacert:
        return cacert
    return ca_path(base)


def json_of(res: httpx.Response):
    """응답 본문을 JSON 으로. JSON 이 아니면 앞 300자를 `__text__` 로 싣는다."""
    try:
        return res.json()
    except ValueError:
        return {"__text__": (res.text or "")[:300]}


def read_env_file(path: str | os.PathLike, keys) -> dict[str, str]:
    """`KEY=VALUE` 줄로 된 파일에서 **요청한 키만** 읽는다. 값은 어디에도 찍지 않는다.

    - 빈 줄과 `#` 로 시작하는 줄은 건너뛴다. `export KEY=…` 도 받는다.
    - 값 양끝의 같은 따옴표(`"…"` · `'…'`)는 벗긴다. 따옴표 없는 값 뒤의 ` # 주석` 은 떼어 낸다.
    - 요청하지 않은 키는 돌려주지 않는다(다른 비밀이 같은 파일에 있어도 프로세스 안으로 들이지 않는다).
    """
    wanted = {str(k) for k in keys}
    out: dict[str, str] = {}
    text = Path(path).read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or key not in wanted:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            hash_at = value.find(" #")
            if hash_at >= 0:
                value = value[:hash_at].rstrip()
        out[key] = value
    return out


def make_client(base: str, *, verify, timeout: float = 90.0) -> httpx.Client:
    return httpx.Client(base_url=base, timeout=timeout, verify=verify)


def login(client: httpx.Client, email: str, password: str) -> dict:
    """`POST /login`(JSON) → CSRF 머리 하나. 실패하면 `LoginError`(상태 코드만 싣는다)."""
    r = client.post("/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise LoginError(r.status_code)
    body = json_of(r)
    token = body.get("csrf_token") if isinstance(body, dict) else None
    if not token:
        raise LoginError(r.status_code)
    return {"X-CSRF-Token": token}


def create_conversation(client: httpx.Client, headers: dict, title: str) -> tuple[str | None, dict]:
    """새 대화 하나. (대화 id 또는 None, 응답 본문)."""
    c = client.post("/api/conversations", json={"title": title[:200]}, headers=headers)
    body = json_of(c)
    if c.status_code != 201 or not isinstance(body, dict):
        return None, {"status": c.status_code, "body": body}
    conversation_id = (body.get("conversation") or {}).get("id") or body.get("id")
    return conversation_id, body


def delete_conversation(client: httpx.Client, headers: dict, conversation_id: str) -> int:
    return client.delete(f"/api/conversations/{conversation_id}", headers=headers).status_code


def post_question(client: httpx.Client, headers: dict, conversation_id: str, question: str, *,
                  prefix: str = "ailab-", retry_429: bool = True) -> tuple[int, dict]:
    """질문 하나를 보낸다. (상태 코드, 본문). 429 면 서버가 준 대기 시간(최대 60초)만큼 쉬고 한 번 더 보낸다."""
    client_message_id = prefix + uuid.uuid4().hex[:16]
    payload = {"content": question, "client_message_id": client_message_id}
    p = client.post(f"/api/conversations/{conversation_id}/messages", json=payload, headers=headers, timeout=60)
    if p.status_code == 429 and retry_429:
        body = json_of(p)
        wait = 10.0
        try:
            wait = float(((body or {}).get("error") or {}).get("retry_after_seconds") or wait)
        except (TypeError, ValueError, AttributeError):
            wait = 10.0
        time.sleep(max(1.0, min(wait, 60.0)))
        p = client.post(f"/api/conversations/{conversation_id}/messages", json=payload, headers=headers, timeout=60)
    return p.status_code, json_of(p)


def await_reply(client: httpx.Client, headers: dict, conversation_id: str, user_message_id: str, *,
                timeout: float, interval: float = POLL_SECONDS) -> dict:
    """사용자 메시지가 끝나고(done · failed) 도우미 답(`a-<id>-…`)이 붙을 때까지 기다린다.

    돌려주는 것: `{"user", "reply", "seconds"}` 또는 `{"timeout": True, "last", "seconds"}`.
    """
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        time.sleep(interval)
        r = client.get(f"/api/conversations/{conversation_id}/messages", headers=headers)
        if r.status_code != 200:
            last = {"status": r.status_code}
            continue
        items = (json_of(r).get("items") or [])
        mine = next((m for m in items if m.get("message_id") == user_message_id), None)
        if mine is None:
            continue
        reply = next((m for m in items if m.get("role") == "assistant"
                      and str(m.get("message_id", "")).startswith(f"a-{user_message_id}")), None)
        if mine.get("processing_status") in ("done", "failed") and reply is not None:
            return {"user": mine, "reply": reply, "seconds": round(time.monotonic() - started, 1)}
        last = {"processing_status": mine.get("processing_status")}
    return {"timeout": True, "last": last, "seconds": round(time.monotonic() - started, 1)}
