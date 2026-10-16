"""설정 저장 왕복 하네스 (r23 §3A ④) — 여섯 영역 × 아홉 걸음, 실패 길 · 복원 확인.

화면에서 값을 바꾸고 「저장했습니다」가 떴다고 끝난 것이 아니다. 이 하네스는 설정 여섯 영역마다 같은 아홉 걸음을 걷고, 걸음마다
통과 · 실패 · 미검증과 **본 값**을 남긴다.

  1. 지금 값을 읽는다(화면 + API)
  2. 화면에서 바꾼다
  3. 저장한다
  4. 성공 표시(토스트 · 상태)가 선다
  5. 페이지를 새로 고친다
  6. 다시 읽는다 — 화면도 새 값, API 도 새 값
  7. 다른 화면에 갔다가 돌아와서, 그리고 새 브라우저 맥락(다시 로그인)에서 다시 읽는다
  8. 실제 효과 — 저장한 값이 서비스 동작에 닿는가(영역마다 다르다)
  9. 화면으로 원래 값을 되돌리고 되돌린 값을 확인한다(화면 + API)

영역마다 한 번씩 저장하지 않은 길과 실패 길도 본다.

  (a) 저장 전 — 저장 단추의 상태와 되돌리기 · 취소 동작
  (b) 강제 실패 — `page.route` 가 저장 요청에 500/409 JSON 오류를 돌려준다. 성공 토스트가 없고 오류가 보이며, 새로 고친 뒤에도
      옛 값이어야 한다(저장되지 않은 값을 저장된 것처럼 계속 보이면 안 된다)

영역: ① 메일 설정(보내는 주소 · 서버 이름) ② AI 연결(요청 제한 시간) ③ 내 프로필(방해금지 · 메일 알림) ④ 시스템 설정(정책 표 ·
OS와 서비스) ⑤ 사용자와 권한(역할) ⑥ 게임방 설정(맵 · 당첨 인원 · 배속).

**로컬 임시 DB 에서만 돈다.** 서버 · 워커 · 받는 쪽 SMTP 를 이 프로세스 안에 띄우고(`screen_ledger.run_local` 과 같은 배선),
씨앗의 시험 계정만 쓴다. 랩 주소를 받지 않는다. 브라우저는 빌드된 번들(`app/static/react`)을 본다 — 프런트를 고쳤으면 먼저
`npm run build` 를 한다.

틀린 경우를 잡는지 먼저 보인다(`--known-bad`).
  * `drop` — 저장 요청을 서버에 보내지 않고 가짜 200 을 돌려준다. 화면은 저장된 듯 보여도 6 이 FAIL 이어야 한다(④ · ②).
  * `wrong` — 기대값을 일부러 틀리게 둔다. 6 · 7 이 FAIL 이어야 한다(모든 영역).

    python -m scripts.ui_qa.settings_roundtrip
    python -m scripts.ui_qa.settings_roundtrip --areas mail profile
    python -m scripts.ui_qa.settings_roundtrip --areas system --known-bad drop
    python -m scripts.ui_qa.settings_roundtrip --areas system --known-bad wrong
    python -m scripts.ui_qa.settings_roundtrip --self-test

결과: `dist/ui-qa/r23-roundtrip/report.json`(영역 · 걸음마다) 과 주요 상태의 PNG. `--known-bad` 실행은
`report-known-bad-<종류>.json` 에 따로 남는다(정상 보고서를 덮지 않는다).
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa.auth import _submit_login  # noqa: E402
from scripts.ui_qa.capture import Viewport, build_fingerprint, new_context  # noqa: E402
from scripts.ui_qa.mail_sink import MailSink, _Handler  # noqa: E402
from scripts.ui_qa.screen_ledger import EMAIL, PASSWORD, ROLE_ACCOUNTS, login  # noqa: E402

OUT = ROOT / "dist" / "ui-qa" / "r23-roundtrip"
VP = Viewport("1366x768", 1366, 768)
AREAS = ("mail", "ai", "profile", "system", "users", "game")
TITLES = {
    "mail": "① 메일 설정 — 보내는 주소 · 서버 이름(HELO)",
    "ai": "② AI 연결 — 요청 제한 시간(초)",
    "profile": "③ 내 프로필 — 방해금지 · 메일 알림",
    "system": "④ 시스템 설정 — 정책 표(대화 보존 기간) · OS와 서비스",
    "users": "⑤ 사용자와 권한 — 역할",
    "game": "⑥ 게임방 설정 — 맵 · 당첨 인원 · 배속",
}
# 가짜 200 으로 저장을 버리는 길(`--known-bad drop`)을 둔 영역 — 응답 모양을 아는 곳만이다.
DROP_AREAS = ("system", "ai")
# 강제 실패 응답의 표지 — 화면에 이 낱말이 보이면 「서버가 준 오류를 그대로 보였다」는 뜻이다.
FORCED = "QA-강제실패"


# ── 받는 쪽 SMTP — 인사 이름(EHLO/HELO)까지 적는다 ─────────────────────────────
# `MailSink` 는 봉투(보낸 사람 · 받는 사람)만 남긴다. 서버 이름(HELO)의 실제 효과를 재려면 SMTP 인사에 실린 이름이 필요하다.
# 받는 쪽의 대화는 그대로 두고, 읽는 줄 가운데 EHLO/HELO 의 인자만 연결(스레드)마다 적어 봉투 JSON 에 더한다.
_TAP = threading.local()


class _TapReader:
    """받는 쪽이 읽는 줄을 그대로 넘기면서 인사 줄의 이름만 적는다."""

    def __init__(self, inner):
        self._inner = inner

    def readline(self, *args):
        raw = self._inner.readline(*args)
        if raw[:5].upper() in (b"EHLO ", b"HELO "):
            _TAP.helo = raw[5:].decode("utf-8", "replace").strip()
        return raw

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _TapHandler(_Handler):
    def setup(self) -> None:
        super().setup()
        _TAP.helo = None
        self.rfile = _TapReader(self.rfile)


class HeloSink(MailSink):
    """`MailSink` + 봉투 JSON 의 `helo`(그 연결이 댄 인사 이름)."""

    def __init__(self, out_dir: Path, port: int = 0) -> None:
        super().__init__(out_dir, port)
        self._server.RequestHandlerClass = _TapHandler

    def store(self, mail_from: str, rcpts: list[str], body: bytes) -> str:
        with self._lock:
            self._seq += 1
            seq = self._seq
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        name = f"{seq:04d}-{stamp}"
        (self.out_dir / f"{name}.eml").write_bytes(body)
        envelope = {"from": mail_from, "to": rcpts, "received_at": stamp, "helo": getattr(_TAP, "helo", None)}
        (self.out_dir / f"{name}.json").write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        return f"SINK{seq:04d}"

    def received(self) -> list[dict]:
        """받은 메일마다 봉투 + 머리(From · To · Subject)."""
        from email import message_from_bytes
        from email.policy import default as default_policy
        from email.utils import parseaddr

        out = []
        for eml in self.messages():
            env = json.loads(eml.with_suffix(".json").read_text(encoding="utf-8"))
            msg = message_from_bytes(eml.read_bytes(), policy=default_policy)
            name, addr = parseaddr(str(msg["From"] or ""))
            out.append({**env, "header_from": str(msg["From"] or ""), "header_from_name": name, "header_from_address": addr,
                        "subject": str(msg["Subject"] or ""), "file": eml.name})
        return out


# ── 화면 보조 ─────────────────────────────────────────────────────────────────
# 토스트는 3.5초(오류 8초) 뒤 사라진다 — 지나간 토스트도 놓치지 않게, 뜨는 순간마다 적는다(`ui/kit.jsx::ToastProvider`).
TOAST_JS = r"""(() => {
  if (window.__qaToasts) return;
  window.__qaToasts = [];
  const seen = new WeakSet();
  const scan = () => {
    document.querySelectorAll('.MuiSnackbar-root .MuiAlert-root').forEach((el) => {
      if (seen.has(el)) return;
      seen.add(el);
      const cls = String(el.className || '');
      const sev = /Success/.test(cls) ? 'success' : /Error/.test(cls) ? 'error' : /Warning/.test(cls) ? 'warning' : 'info';
      const box = el.querySelector('.MuiAlert-message') || el;
      window.__qaToasts.push({ sev, msg: (box.textContent || '').trim(), t: Date.now() });
    });
  };
  new MutationObserver(scan).observe(document, { childList: true, subtree: true });
})();"""

# 종 배지 — 보이는 숫자 · 점 · 접근 이름(`app/NotificationBell.jsx`).
BELL_JS = r"""() => {
  const btn = document.querySelector('[aria-controls="noti-pop"]');
  if (!btn) return null;
  const root = btn.closest('.MuiBadge-root');
  const b = root ? root.querySelector('.MuiBadge-badge') : null;
  return { label: btn.getAttribute('aria-label'), text: b ? b.textContent.trim() : null,
           dot: b ? b.classList.contains('MuiBadge-dot') : null, invisible: b ? b.classList.contains('MuiBadge-invisible') : null };
}"""


def toast_mark(page) -> int:
    return int(page.evaluate("() => (window.__qaToasts || []).length"))


def toasts_since(page, mark: int) -> list[dict]:
    return page.evaluate("(m) => (window.__qaToasts || []).slice(m)", mark)


def wait_toast(page, mark: int, timeout_s: float = 6.0) -> list[dict]:
    """`mark` 뒤에 뜬 토스트 — 하나라도 뜨면 잠깐 더 기다려(둘째 토스트) 모은다."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        got = toasts_since(page, mark)
        if got:
            page.wait_for_timeout(500)
            return toasts_since(page, mark)
        page.wait_for_timeout(150)
    return []


def success_toast(toasts: list[dict], text: str = "") -> bool:
    return any(t["sev"] == "success" and text in t["msg"] for t in toasts)


def page_has_text(page, text: str) -> bool:
    return bool(page.evaluate("(t) => document.body.innerText.includes(t)", text))


def forced_alert(scope):
    """강제 실패 문장을 든 오류 표시(경고 상자 · alert 역할)."""
    return scope.locator(".k-callout[data-tone=danger], [role=alert]").filter(has_text=FORCED)


def text_button(scope, text: str):
    """글자가 그 낱말인 단추 — 확인 창의 「닫기」는 머리의 닫기 아이콘(이름만 「닫기」)과 이름이 겹친다."""
    return scope.locator("button").filter(has_text=re.compile(rf"^\s*{re.escape(text)}\s*$"))


# 오류가 DOM 에 있는 것과 사람이 저장을 누른 자리에서 보이는 것은 다르다 — 화면 안에 있고 다른 것(붙박이 발 등)에 덮이지 않았는가.
IN_VIEW_JS = r"""(el) => {
  const r = el.getBoundingClientRect();
  const vw = window.innerWidth, vh = window.innerHeight;
  const visible = r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw;
  const cx = Math.min(Math.max(r.left + r.width / 2, 0), vw - 1);
  const cy = Math.min(Math.max(r.top + Math.min(r.height / 2, 12), 0), vh - 1);
  const hit = visible ? document.elementFromPoint(cx, cy) : null;
  return { in_view: visible && !!hit && (el === hit || el.contains(hit)), top: Math.round(r.top), bottom: Math.round(r.bottom),
           viewport_height: vh, scroll_y: Math.round(window.scrollY) };
}"""


def in_view(locator) -> dict:
    if not locator.count():
        return {"in_view": False, "missing": True}
    return locator.first.evaluate(IN_VIEW_JS)


def offscreen_error(env, a, page, iv: dict, where: str, detail: str = "") -> None:
    """저장 실패 문장이 저장을 누른 자리의 화면 밖에 섰다 — 결함으로 적고 전체 페이지 캡처를 남긴다."""
    if iv.get("in_view") or iv.get("missing"):
        return
    name = env.shot(a, page, "failure-viewport")
    full = f"{a.key}-failure-fullpage.png"
    try:
        page.screenshot(path=str(env.out / full), full_page=True)
        a.shots.append(full)
    except Exception:  # noqa: BLE001
        full = None
    a.defects.append({
        "kind": "실패 표시가 화면 밖(저장을 누른 자리에서 안 보인다)",
        "where": where,
        "what": f"저장 요청이 실패하면 오류 문장이 저장 단추를 누른 화면의 아래 {iv.get('top', 0) - iv.get('viewport_height', 0)}px "
                f"바깥(top={iv.get('top')}px, 화면 높이 {iv.get('viewport_height')}px)에 선다. {detail}".strip(),
        "repro": f"{VP.name} 에서 값을 바꾸고 저장 → 저장 요청이 오류 응답을 받는다(이 하네스는 page.route 로 500 · 409 를 강제한다) → "
                 "저장 단추를 누른 그 화면에서 오류 문장이 보이는가",
        "evidence": {"position": iv, "viewport_png": name, "fullpage_png": full},
    })


def json_error(status: int, message: str) -> dict:
    return {"status": status, "content_type": "application/json",
            "body": json.dumps({"error": {"code": "qa_forced_failure", "message": message, "request_id": "qa-forced"}},
                               ensure_ascii=False)}


def force_failure(page, pattern: str, method: str, status: int = 500):
    """저장 요청 하나를 서버에 보내지 않고 오류로 돌려준다. 돌려받은 함수를 부르면 걷는다. 가로챈 주소는 `hits`."""
    hits: list[str] = []
    message = f"{FORCED} {status} — 저장되지 않았습니다."

    def handler(route):
        if route.request.method.upper() != method.upper():
            route.fallback()
            return
        hits.append(route.request.url)
        route.fulfill(**json_error(status, message))

    page.route(pattern, handler)

    def undo():
        page.unroute(pattern, handler)
    undo.hits = hits  # type: ignore[attr-defined]
    return undo


def hash_path(url: str) -> str:
    """`…/admin#/mail?tab=settings` → `/admin#/mail` — 화면이 주소의 조건을 다시 쓰더라도 같은 화면인지만 본다."""
    head, _, frag = url.partition("#")
    return head.rsplit("/", 1)[-1] + "#" + frag.split("?")[0]


class Api:
    """씨앗 계정 하나의 API 세션(httpx). 쓰기는 CSRF 머리를 단다."""

    def __init__(self, base: str, email: str, password: str = PASSWORD):
        import httpx

        self.base, self.email, self.password = base, email, password
        self.c = httpx.Client(base_url=base, timeout=30)
        self.csrf = ""
        self.login()

    def login(self) -> None:
        r = self.c.post("/login", json={"email": self.email, "password": self.password})
        if r.status_code != 200:
            raise RuntimeError(f"API 로그인 실패({self.email}): HTTP {r.status_code}")
        self.csrf = r.json().get("csrf_token", "")

    @staticmethod
    def _body(r):
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return r.text[:300]

    def get(self, path: str, params: dict | None = None):
        r = self.c.get(path, params=params)
        return r.status_code, self._body(r)

    def send(self, method: str, path: str, body=None):
        r = self.c.request(method, path, json=body, headers={"X-CSRF-Token": self.csrf})
        return r.status_code, self._body(r)


@dataclass
class Area:
    """영역 하나의 기록 — 걸음 아홉 + 저장 전 길 + 실패 길 + 되돌림 + 결함."""

    key: str
    title: str
    steps: list = field(default_factory=list)
    unsaved: dict = field(default_factory=dict)
    failure: dict = field(default_factory=dict)
    restore: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    defects: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    shots: list = field(default_factory=list)
    current: str = "1"

    def step(self, no: int, name: str, checks: dict, *, unverified: list | None = None, **observed) -> bool:
        ok = all(bool(v) for v in checks.values())
        status = "FAIL" if not ok else ("미검증" if not checks else "PASS")
        row = {"step": no, "name": name, "status": status, "checks": checks, "observed": observed}
        if unverified:
            row["unverified"] = unverified
        self.steps.append(row)
        bad = [k for k, v in checks.items() if not v]
        print(f"[{self.key}] {no}. {name}: {status}" + (f" ✗ {bad}" if bad else "")
              + (f" (미검증: {'; '.join(unverified)})" if unverified else ""), flush=True)
        return ok

    def path(self, kind: str, checks: dict, **observed) -> dict:
        """저장 전 길 · 실패 길 기록."""
        status = "PASS" if checks and all(bool(v) for v in checks.values()) else "FAIL"
        bad = [k for k, v in checks.items() if not v]
        print(f"[{self.key}] ({kind}): {status}" + (f" ✗ {bad}" if bad else ""), flush=True)
        return {"status": status, "checks": checks, **observed}

    def as_dict(self) -> dict:
        statuses = [s["status"] for s in self.steps]
        paths = [self.unsaved.get("status"), self.failure.get("status")]
        verdict = "FAIL" if ("FAIL" in statuses or "FAIL" in paths or len(self.steps) < 9) else "PASS"
        return {"key": self.key, "title": self.title, "verdict": verdict, "steps": self.steps, "unsaved": self.unsaved,
                "failure_path": self.failure, "restore": self.restore, "extra": self.extra, "defects": self.defects,
                "notes": self.notes, "screenshots": self.shots}


# ── 실행 배선 ─────────────────────────────────────────────────────────────────
@dataclass
class Env:
    """한 실행의 배선 — 로컬 서버 · 받는 쪽 · 브라우저 · 계정별 세션."""

    base: str
    sink: HeloSink
    db_url: str
    out: Path
    session_factory: object = None
    worker_cache: object = None
    known_bad: str = ""
    browser: object = None
    storage: dict = field(default_factory=dict)     # 역할 → (storage_state, user_id)
    apis: dict = field(default_factory=dict)        # 이메일 → Api
    contexts: list = field(default_factory=list)
    page_errors: dict = field(default_factory=dict)
    area: str = ""
    aborts: list = field(default_factory=list)      # 영역이 중간에 멈췄을 때 API 로 되돌릴 일
    _engine: object = None

    def api(self, email: str = EMAIL) -> Api:
        if email not in self.apis:
            self.apis[email] = Api(self.base, email)
        return self.apis[email]

    def open(self, role: str = "system_admin", *, fresh_email: str = ""):
        """브라우저 맥락 하나. `fresh_email` 이면 저장된 세션 없이 로그인 화면에서 다시 로그인한다."""
        if fresh_email:
            ctx = new_context(self.browser, storage_state=None, user_id="", theme="light", viewport=VP)
        else:
            storage, uid = self.storage[role]
            ctx = new_context(self.browser, storage_state=storage, user_id=uid, theme="light", viewport=VP)
        ctx.add_init_script(TOAST_JS)
        page = ctx.new_page()
        area = self.area
        page.on("pageerror", lambda e: self.page_errors.setdefault(area, []).append(str(e)[:300]))
        if fresh_email:
            _submit_login(page, self.base, fresh_email, PASSWORD)
        self.contexts.append(ctx)
        return ctx, page

    def goto(self, page, path: str, ready: str = "main") -> None:
        page.goto(self.base + path, wait_until="domcontentloaded")
        page.locator(ready).first.wait_for(timeout=30_000)
        page.wait_for_timeout(700)

    def reload(self, page, ready: str) -> None:
        page.reload(wait_until="domcontentloaded")
        page.locator(ready).first.wait_for(timeout=30_000)
        page.wait_for_timeout(700)

    def away_and_back(self, page, away_hash: str, ready: str) -> dict:
        """앱 안에서 다른 화면으로 갔다가(해시만 — 새로 고침 없이) 뒤로 돌아온다."""
        here = page.url
        same = "(t) => window.location.hash.split('?')[0] === t"
        page.evaluate("(h) => { window.location.hash = h; }", away_hash)
        page.wait_for_function(same, arg=away_hash.split("?")[0], timeout=10_000)
        page.locator("main").first.wait_for(timeout=20_000)
        page.wait_for_timeout(900)
        away = page.url
        page.evaluate("() => history.back()")
        page.wait_for_function(same, arg="#" + here.partition("#")[2].split("?")[0], timeout=10_000)
        page.locator(ready).first.wait_for(timeout=20_000)
        page.wait_for_timeout(800)
        return {"ok": hash_path(away) != hash_path(here) and hash_path(page.url) == hash_path(here), "away": away,
                "back": page.url}

    def shot(self, area: Area, page, tag: str) -> str:
        name = f"{area.key}-{tag}.png"
        if self.known_bad:
            name = f"known-bad-{self.known_bad}-{name}"
        try:
            page.screenshot(path=str(self.out / name))
            area.shots.append(name)
        except Exception:  # noqa: BLE001 — 찍지 못해도 판정은 계속한다
            pass
        return name

    def expect(self, value):
        """`--known-bad wrong` 이면 기대값을 일부러 틀리게 둔다 — 하네스가 그 차이를 FAIL 로 잡는지 본다."""
        if self.known_bad != "wrong":
            return value
        if isinstance(value, bool):
            return not value
        if isinstance(value, int):
            return value + 1
        return f"{value}-틀린기대값"

    def drop_route(self, page, pattern: str, method: str, fake):
        """`--known-bad drop` 이면 저장 요청을 서버에 보내지 않고 `fake(요청 본문)` 을 200 으로 돌려준다."""
        if self.known_bad != "drop" or fake is None:
            return None
        dropped: list[dict] = []

        def handler(route):
            if route.request.method.upper() != method.upper():
                route.fallback()
                return
            body = json.loads(route.request.post_data or "{}")
            dropped.append(body)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(fake(body), ensure_ascii=False))

        page.route(pattern, handler)

        def undo():
            page.unroute(pattern, handler)
        undo.dropped = dropped  # type: ignore[attr-defined]
        return undo

    def worker_value(self, key: str):
        """워커가 다음 잡 직전에 읽을 값 — 워커와 같은 캐시에 워커와 같은 따라잡기(`refresh_if_stale`)를 부른다."""
        time.sleep(1.1)  # 판 번호 확인은 초당 한 번이다 — 바로 앞 확인이 1초 안이면 건너뛴다
        with self.session_factory() as db:
            self.worker_cache.refresh_if_stale(db)
        return self.worker_cache.current_value(key)

    def rows(self, sql: str, **params) -> list[dict]:
        """임시 DB 읽기(SELECT 만)."""
        from sqlalchemy import create_engine, text

        from app.core.db import normalize_database_url

        if self._engine is None:
            self._engine = create_engine(normalize_database_url(self.db_url), future=True)
        with self._engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql), params)]

    def close_all(self) -> None:
        for ctx in self.contexts:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass
        self.contexts.clear()


# ── ① 메일 설정 ───────────────────────────────────────────────────────────────
MAIL_PATH = "/admin#/mail?tab=settings"
MAIL_FORM = "[data-testid=mail-settings-form]"
SETTING_ROW_JS = r"""(label) => {
  for (const row of document.querySelectorAll('.k-settingrow')) {
    const grid = row.firstElementChild;
    const head = grid && grid.firstElementChild;
    if (!head || !head.textContent.trim().startsWith(label)) continue;
    const val = head.nextElementSibling;
    return val ? val.textContent.trim() : '';
  }
  return null;
}"""


def setting_row_value(page, label: str):
    return page.evaluate(SETTING_ROW_JS, label)


def _mail_settings(api: Api) -> dict:
    st, j = api.get("/api/admin/mail/settings")
    if st != 200:
        raise RuntimeError(f"메일 설정을 읽지 못했다: HTTP {st}")
    return j["settings"]


def _mail_put_body(settings: dict, **changes) -> dict:
    """GET 모양을 PUT 모양으로 — `relay.dkim_public` 은 PUT 이 받지 않는다(읽기 전용 값)."""
    body = json.loads(json.dumps(settings))
    body["relay"].pop("dkim_public", None)
    relay_changes = changes.pop("relay", None) or {}
    body.update(changes)
    body["relay"].update(relay_changes)
    return body


def _default_helo() -> str:
    """서버 이름(HELO)이 비었을 때 smtplib 가 대는 이 기계의 이름 — 제품 전송기의 기본값과 같다(`MailConfig.ehlo_name`)."""
    import smtplib

    return smtplib.SMTP().local_hostname


def _wait_mail(env: Env, before: int, to: str, subject: str = "", timeout_s: float = 45.0) -> dict | None:
    """`before` 통 뒤에 `to` 로 온 첫 메일(제목 조각이 있으면 그것까지). 워커가 잡을 집어 보내기까지 기다린다."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for m in env.sink.received()[before:]:
            if to in m["to"] and subject in m["subject"]:
                return m
        time.sleep(0.3)
    return None


def _mail_ui(page) -> dict:
    return {"from": page.locator("#mail-from").input_value(), "helo_row": setting_row_value(page, "메일 서버 이름(HELO)")}


def _mail_save(page) -> tuple[int, list]:
    mark = toast_mark(page)
    with page.expect_response(lambda r: r.url.endswith("/api/admin/mail/settings") and r.request.method == "PUT",
                              timeout=20_000) as resp:
        page.locator(MAIL_FORM).get_by_role("button", name="저장", exact=True).click()
    return resp.value.status, wait_toast(page, mark, 6.0)


def _mail_test_ui(env: Env, page) -> tuple[list, dict | None]:
    """화면의 「시험 메일 보내기」 — 받는 주소는 내 계정(기본값) 그대로 둔다. 받는 쪽에 온 메일을 돌려준다."""
    before = len(env.sink.messages())
    mark = toast_mark(page)
    page.locator('[data-check-row="test"]').get_by_role("button", name="시험 메일 보내기").click()
    dlg = page.get_by_role("dialog", name="시험 메일 보내기")
    dlg.wait_for(timeout=10_000)
    dlg.get_by_role("button", name="보내기", exact=True).click()
    mail = _wait_mail(env, before, EMAIL)
    deadline = time.time() + 20
    while time.time() < deadline and not any("접수" in t["msg"] for t in toasts_since(page, mark)):
        page.wait_for_timeout(300)
    return toasts_since(page, mark), mail


def area_mail(env: Env, a: Area) -> None:
    api = env.api(EMAIL)
    # 시험 메일은 한 사람이 10분에 5통까지다 — 화면 발송은 나(시스템 관리자), API 확인 발송은 다른 전체 관리자가 나눠 보낸다.
    probe = env.api(ROLE_ACCOUNTS["admin"])
    token = secrets.token_hex(3)
    _ctx, page = env.open()
    env.goto(page, MAIL_PATH, ready="#mail-from")
    form = page.locator(MAIL_FORM)
    save_btn = form.get_by_role("button", name="저장", exact=True)
    revert_btn = form.get_by_role("button", name="되돌리기", exact=True)

    # 1. 지금 값
    s0 = _mail_settings(api)
    ui0 = _mail_ui(page)
    orig_from, orig_helo, orig_name = s0["from_address"], s0["relay"]["helo_name"], s0["from_name"]
    env.aborts.append(lambda: api.send("PUT", "/api/admin/mail/settings", _mail_put_body(
        _mail_settings(api), from_address=orig_from, from_name=orig_name, relay={"helo_name": orig_helo})))
    default_helo = _default_helo()
    a.step(1, "지금 값 읽기(화면 + API)", {
        "ui_from_equals_api": ui0["from"] == orig_from,
        "helo_row_matches_api": ui0["helo_row"] == (orig_helo or "이 서버의 기본 이름"),
        "mode_external": s0["mode"] == "external",
    }, ui=ui0, api={"from_address": orig_from, "helo_name": orig_helo, "mode": s0["mode"]}, smtplib_default_helo=default_helo)
    # 기준 발송 — 바꾸기 전의 인사 이름 · 보낸 사람(독립성 비교의 기준). API 확인 발송은 받는 주소가 그 계정 자신이다.
    before = len(env.sink.messages())
    st_base, _ = probe.send("POST", "/api/admin/mail/test", {})
    base_mail = _wait_mail(env, before, ROLE_ACCOUNTS["admin"])
    a.extra["baseline_test_mail"] = {"http": st_base, "helo": (base_mail or {}).get("helo"),
                                     "from": (base_mail or {}).get("header_from_address")}

    # (a) 저장 전 — 단추 상태 · 되돌리기
    a.current = "unsaved"
    clean = {"clean_save_disabled": save_btn.is_disabled(), "clean_revert_disabled": revert_btn.is_disabled()}
    draft = f"qa-draft-{token}@goodmit.co.kr"
    page.locator("#mail-from").fill(draft)
    dirty = {"dirty_save_enabled": save_btn.is_enabled(), "dirty_revert_enabled": revert_btn.is_enabled(),
             "dirty_note": page_has_text(page, "저장하지 않은 수정 내용이 있습니다."),
             "test_send_locked_while_dirty": page.locator('[data-check-row="test"]').get_by_role(
                 "button", name="시험 메일 보내기").is_disabled()}
    revert_btn.click()
    page.wait_for_timeout(300)
    reverted = {"revert_restores_saved": page.locator("#mail-from").input_value() == orig_from,
                "save_disabled_again": save_btn.is_disabled(), "api_unchanged": _mail_settings(api)["from_address"] == orig_from}
    a.unsaved = a.path("unsaved", {**clean, **dirty, **reverted}, draft=draft)

    # (b) 강제 실패 — 500
    a.current = "failure"
    undo = force_failure(page, "**/api/admin/mail/settings", "PUT", 500)
    page.locator("#mail-from").fill(draft)
    mark = toast_mark(page)
    save_btn.click()
    page.wait_for_timeout(1500)
    toasts = toasts_since(page, mark)
    alert = forced_alert(form)
    iv = in_view(alert)
    checks = {"intercepted": len(undo.hits) == 1, "no_success_toast": not any(t["sev"] == "success" for t in toasts),
              "error_shown": alert.count() > 0, "error_in_view": iv["in_view"],
              "draft_marked_unsaved": page_has_text(page, "저장하지 않은 수정 내용이 있습니다."),
              "save_still_enabled": save_btn.is_enabled(), "api_unchanged": _mail_settings(api)["from_address"] == orig_from}
    error_text = alert.first.inner_text() if alert.count() else None
    env.shot(a, page, "failure-500")
    offscreen_error(env, a, page, iv, "/admin#/mail?tab=settings → 발신 정보의 「보내는 주소」를 바꾸고 저장(실패)",
                    "오류 상자는 폼 맨 끝(「요청 내용과 기술 상세」 아래)에 서고, 붙박이 발에는 「저장하지 않은 수정 내용이 있습니다.」만 "
                    "보인다 — 왜 저장되지 않았는지는 아래로 내려가야 보인다.")
    undo()
    env.reload(page, "#mail-from")
    checks["reload_shows_old"] = page.locator("#mail-from").input_value() == orig_from
    a.failure = a.path("failure", checks, http=500, toasts=toasts, error_text=error_text, error_position=iv)

    # 2 · 3 · 4 — 보내는 주소를 바꾸고 저장한다
    a.current = "2"
    new_from = f"qa-rt-{token}@goodmit.co.kr"
    expect_from = env.expect(new_from)
    page.locator("#mail-from").fill(new_from)
    a.step(2, "화면에서 보내는 주소를 바꾼다", {"input_has_new": page.locator("#mail-from").input_value() == new_from,
                                          "save_enabled": save_btn.is_enabled()},
           new_from=new_from, helo_control="외부 SMTP 화면에서는 서버 이름이 읽기 전용 줄이다 — 칸은 「인터넷으로 직접 전달」에서만 선다")
    a.current = "3"
    http, toasts = _mail_save(page)
    a.step(3, "저장", {"http_200": http == 200}, http=http)
    a.current = "4"
    a.step(4, "성공 토스트", {"success_toast": success_toast(toasts, "메일 설정을 저장했습니다"),
                          "no_error_callout": form.locator(".k-callout[data-tone=danger]").count() == 0}, toasts=toasts)
    env.shot(a, page, "04-saved")

    # 5 · 6 — 새로 고침 뒤 다시 읽는다
    a.current = "5"
    env.reload(page, "#mail-from")
    a.step(5, "새로 고침", {"form_back": page.locator("#mail-from").count() == 1})
    a.current = "6"
    ui6, s6 = _mail_ui(page), _mail_settings(api)
    a.step(6, "다시 읽기 — 화면 · API 가 새 값, 서버 이름은 그대로", {
        "ui_new": ui6["from"] == expect_from, "api_new": s6["from_address"] == expect_from,
        "helo_api_unchanged": s6["relay"]["helo_name"] == orig_helo, "helo_row_unchanged": ui6["helo_row"] == ui0["helo_row"],
    }, ui=ui6, api={"from_address": s6["from_address"], "helo_name": s6["relay"]["helo_name"]})
    env.shot(a, page, "06-reloaded")

    # 7 — 다른 화면에 갔다 돌아오기 + 새 맥락(다시 로그인)
    a.current = "7"
    nav = env.away_and_back(page, "#/jobs", "#mail-from")
    ui7 = _mail_ui(page)
    _fctx, fresh = env.open(fresh_email=EMAIL)
    env.goto(fresh, MAIL_PATH, ready="#mail-from")
    ui7f = _mail_ui(fresh)
    _fctx.close()
    a.step(7, "다른 화면에 갔다 와서 · 다시 로그인한 새 맥락에서 다시 읽기", {
        "nav_ok": nav["ok"], "after_nav_new": ui7["from"] == expect_from, "fresh_login_new": ui7f["from"] == expect_from,
    }, nav=nav, after_nav=ui7, fresh_login=ui7f)

    # 8 — 실제 효과: 화면의 시험 메일 → 받는 쪽의 From · 인사 이름
    a.current = "8"
    toasts, mail = _mail_test_ui(env, page)
    checks = {
        "mail_received": mail is not None,
        "header_from_is_saved": bool(mail) and mail["header_from_address"] == expect_from,
        "envelope_from_is_saved": bool(mail) and mail["from"] == expect_from,
        "helo_is_saved_default": bool(mail) and mail["helo"] == (orig_helo or default_helo),
        "helo_unchanged_by_sender_change": bool(mail) and bool(base_mail) and mail["helo"] == base_mail["helo"],
        "accepted_toast": success_toast(toasts, "접수"),
    }
    # 서버 이름(HELO)은 외부 SMTP 화면에서 읽기 전용이다 — 값은 API 로 바꾸고, 읽기 전용 줄 · 실제 인사 이름 · 보내는 주소를 본다.
    helo_new = f"qa-helo-{token}.goodmit.co.kr"
    st_put, _ = api.send("PUT", "/api/admin/mail/settings", _mail_put_body(_mail_settings(api), relay={"helo_name": helo_new}))
    env.reload(page, "#mail-from")
    ui8 = _mail_ui(page)
    env.shot(a, page, "08-helo-row")
    before = len(env.sink.messages())
    probe.send("POST", "/api/admin/mail/test", {})
    helo_mail = _wait_mail(env, before, ROLE_ACCOUNTS["admin"])
    checks.update({
        "helo_api_put_200": st_put == 200, "helo_row_shows_new": ui8["helo_row"] == helo_new,
        "sender_unchanged_by_helo_change": ui8["from"] == expect_from and _mail_settings(api)["from_address"] == expect_from,
        "helo_effect": bool(helo_mail) and helo_mail["helo"] == helo_new,
        "sender_effect_kept": bool(helo_mail) and helo_mail["header_from_address"] == expect_from,
    })
    st_back, _ = api.send("PUT", "/api/admin/mail/settings", _mail_put_body(_mail_settings(api), relay={"helo_name": orig_helo}))
    checks["helo_api_restored"] = st_back == 200 and _mail_settings(api)["relay"]["helo_name"] == orig_helo
    a.step(8, "실제 효과 — 시험 메일의 From · 인사 이름(HELO), 둘이 서로 따로 움직인다", checks,
           unverified=["서버 이름(HELO)을 화면에서 바꾸는 길 — 외부 SMTP 화면은 읽기 전용이라 API 로 바꿔 효과만 쟀다"],
           ui_test_mail={k: (mail or {}).get(k) for k in ("from", "header_from", "helo", "subject")}, toasts=toasts,
           helo_probe={"saved": helo_new, "row": ui8["helo_row"], "received_helo": (helo_mail or {}).get("helo"),
                       "received_from": (helo_mail or {}).get("header_from_address")},
           baseline_helo=(base_mail or {}).get("helo"))

    # 9 — 화면으로 되돌리기
    a.current = "9"
    env.reload(page, "#mail-from")
    page.locator("#mail-from").fill(orig_from)
    http, toasts = _mail_save(page)
    env.reload(page, "#mail-from")
    ui9, s9 = _mail_ui(page), _mail_settings(api)
    a.step(9, "원래 값으로 되돌리고 확인(화면 + API)", {
        "http_200": http == 200, "success_toast": success_toast(toasts),
        "ui_restored": ui9["from"] == orig_from, "api_restored": s9["from_address"] == orig_from,
        "helo_restored": s9["relay"]["helo_name"] == orig_helo and ui9["helo_row"] == ui0["helo_row"],
    }, ui=ui9, api={"from_address": s9["from_address"], "helo_name": s9["relay"]["helo_name"]})
    a.restore = {"from_address": {"original": orig_from, "now_api": s9["from_address"], "now_ui": ui9["from"]},
                 "helo_name": {"original": orig_helo, "now_api": s9["relay"]["helo_name"], "now_ui": ui9["helo_row"]}}

    # 덧붙인 관찰 — 「보내는 이름」 칸의 도움말(「비우면 주소만 보입니다.」)과 실제 발송(D-572: 비면 제품 이름)을 대조한다.
    help_says_address_only = page_has_text(page, "비우면 주소만 보입니다.")
    st_n, _ = api.send("PUT", "/api/admin/mail/settings", _mail_put_body(_mail_settings(api), from_name=""))
    before = len(env.sink.messages())
    probe.send("POST", "/api/admin/mail/test", {})
    nameless = _wait_mail(env, before, ROLE_ACCOUNTS["admin"])
    api.send("PUT", "/api/admin/mail/settings", _mail_put_body(_mail_settings(api), from_name=orig_name))
    shown_name = (nameless or {}).get("header_from_name")
    a.extra["from_name_blank"] = {"help_says_address_only": help_says_address_only, "put_http": st_n,
                                  "received_header_from": (nameless or {}).get("header_from"),
                                  "restored_from_name": _mail_settings(api)["from_name"] == orig_name}
    if nameless and shown_name and help_says_address_only:
        a.defects.append({
            "kind": "문구(도움말과 동작이 다르다)",
            "where": "/admin#/mail?tab=settings → 발신 정보 → 「보내는 이름」 칸의 도움말",
            "what": f"도움말은 「비우면 주소만 보입니다.」인데, 비우고 보낸 시험 메일의 From 은 「{(nameless or {}).get('header_from')}」 — "
                    "발송 처리기가 제품 이름을 채운다(`app/jobs/handlers/mail_send.py::_with_sender_name`, D-572).",
            "repro": "보내는 이름을 비우고 저장 → 시험 메일 보내기 → 받은 메일의 From 표시 이름을 본다",
            "evidence": {"header_from": (nameless or {}).get("header_from"), "file": (nameless or {}).get("file")},
        })


# ── ② AI 연결 ─────────────────────────────────────────────────────────────────
AI_PATH = "/admin#/ai-connection"


def _ai_config(api: Api) -> dict:
    st, j = api.get("/api/admin/ai")
    if st != 200:
        raise RuntimeError(f"AI 설정을 읽지 못했다: HTTP {st}")
    return j


def _ai_ui(page) -> int | None:
    raw = page.locator("#ai-timeout").input_value()
    return int(raw) if raw.strip().lstrip("-").isdigit() else None


def _setting_value(api: Api, key: str):
    st, j = api.get("/api/admin/settings")
    return ((j or {}).get("settings") or {}).get(key, {}).get("value") if st == 200 else None


def _ai_save(page, sec) -> tuple[int | None, list]:
    if sec.get_by_role("button", name="저장", exact=True).is_disabled():
        return None, []     # 바뀐 것이 없다(저장이 버려진 실행의 되돌리기) — 보낼 것이 없다
    mark = toast_mark(page)
    with page.expect_response(lambda r: r.url.endswith("/api/admin/ai/config") and r.request.method == "PUT",
                              timeout=20_000) as resp:
        sec.get_by_role("button", name="저장", exact=True).click()
    return resp.value.status, wait_toast(page, mark, 6.0)


def area_ai(env: Env, a: Area) -> None:
    api = env.api(EMAIL)
    _ctx, page = env.open()
    env.goto(page, AI_PATH, ready="#ai-timeout")
    sec = page.locator("section.k-form-section").filter(has=page.get_by_role("heading", name="실행 옵션", exact=True))
    save_btn = sec.get_by_role("button", name="저장", exact=True)
    revert_btn = sec.get_by_role("button", name="되돌리기", exact=True)

    # 1
    j0 = _ai_config(api)
    t0 = j0["config"]["timeout_seconds"]
    env.aborts.append(lambda: api.send("PUT", "/api/admin/ai/config", {"timeout_seconds": t0}))
    ui0, raw0 = _ai_ui(page), _setting_value(api, "ai_timeout_seconds")
    a.step(1, "지금 값 읽기(화면 + API)", {"ui_equals_api": ui0 == t0, "raw_setting_equals": raw0 == t0},
           ui=ui0, api_config=t0, api_setting=raw0, limits=(j0.get("limits") or {}).get("timeout_seconds"),
           provider=(j0.get("config") or {}).get("provider"))

    # (a) 저장 전
    a.current = "unsaved"
    clean = {"clean_save_disabled": save_btn.is_disabled(), "clean_revert_disabled": revert_btn.is_disabled()}
    page.locator("#ai-timeout").fill(str(t0 + 1))
    dirty = {"dirty_save_enabled": save_btn.is_enabled(), "dirty_revert_enabled": revert_btn.is_enabled()}
    revert_btn.click()
    page.wait_for_timeout(300)
    reverted = {"revert_restores_saved": _ai_ui(page) == t0, "save_disabled_again": save_btn.is_disabled(),
                "api_unchanged": _ai_config(api)["config"]["timeout_seconds"] == t0}
    a.unsaved = a.path("unsaved", {**clean, **dirty, **reverted})

    # (b) 강제 실패 — 409
    a.current = "failure"
    undo = force_failure(page, "**/api/admin/ai/config", "PUT", 409)
    page.locator("#ai-timeout").fill(str(t0 + 3))
    mark = toast_mark(page)
    save_btn.click()
    page.wait_for_timeout(1500)
    toasts = toasts_since(page, mark)
    alert = forced_alert(page)
    iv = in_view(alert)
    checks = {"intercepted": len(undo.hits) == 1, "no_success_toast": not any(t["sev"] == "success" for t in toasts),
              "error_shown": alert.count() > 0, "error_in_view": iv["in_view"],
              "draft_kept_as_unsaved": _ai_ui(page) == t0 + 3 and save_btn.is_enabled(),
              "api_unchanged": _ai_config(api)["config"]["timeout_seconds"] == t0}
    error_text = alert.first.inner_text() if alert.count() else None
    env.shot(a, page, "failure-409")
    offscreen_error(env, a, page, iv, "/admin#/ai-connection → 실행 옵션의 「요청 제한 시간(초)」을 바꾸고 저장(실패)",
                    "오류 상자는 저장 단추가 있는 「실행 옵션」(왼쪽 열)이 아니라 오른쪽 열 맨 아래 「확인과 오류」에 선다 — 단추 옆에는 "
                    "실패 표시가 없다.")
    undo()
    env.reload(page, "#ai-timeout")
    checks["reload_shows_old"] = _ai_ui(page) == t0
    a.failure = a.path("failure", checks, http=409, toasts=toasts, error_text=error_text, error_position=iv)

    # 2 · 3 · 4
    a.current = "2"
    new = t0 + 7 if t0 + 7 <= 300 else t0 - 7
    expect = env.expect(new)
    page.locator("#ai-timeout").fill(str(new))
    a.step(2, "화면에서 요청 제한 시간(초)을 바꾼다", {"input_has_new": _ai_ui(page) == new, "save_enabled": save_btn.is_enabled()},
           new=new)
    a.current = "3"

    def fake(body):
        j = _ai_config(api)
        j["config"] = {**j["config"], **body}
        return {**j, "verify_job_id": None}

    drop = env.drop_route(page, "**/api/admin/ai/config", "PUT", fake if "ai" in DROP_AREAS else None)
    http, toasts = _ai_save(page, sec)
    a.step(3, "저장", {"http_200": http == 200}, http=http, dropped=bool(drop))
    a.current = "4"
    a.step(4, "성공 토스트", {"success_toast": success_toast(toasts, "실행 옵션을 저장했습니다")}, toasts=toasts)
    env.shot(a, page, "04-saved")
    if drop:
        drop()

    # 5 · 6
    a.current = "5"
    env.reload(page, "#ai-timeout")
    a.step(5, "새로 고침", {"form_back": page.locator("#ai-timeout").count() == 1})
    a.current = "6"
    ui6, api6, raw6 = _ai_ui(page), _ai_config(api)["config"]["timeout_seconds"], _setting_value(api, "ai_timeout_seconds")
    a.step(6, "다시 읽기 — 화면 · API 가 새 값", {"ui_new": ui6 == expect, "api_new": api6 == expect, "raw_setting_new": raw6 == expect},
           ui=ui6, api_config=api6, api_setting=raw6)

    # 7
    a.current = "7"
    nav = env.away_and_back(page, "#/dashboard", "#ai-timeout")
    ui7 = _ai_ui(page)
    fctx, fresh = env.open(fresh_email=EMAIL)
    env.goto(fresh, AI_PATH, ready="#ai-timeout")
    ui7f = _ai_ui(fresh)
    fctx.close()
    a.step(7, "다른 화면에 갔다 와서 · 다시 로그인한 새 맥락에서 다시 읽기",
           {"nav_ok": nav["ok"], "after_nav_new": ui7 == expect, "fresh_login_new": ui7f == expect},
           nav=nav, after_nav=ui7, fresh_login=ui7f)

    # 8 — 실제 효과: AI 실행기가 읽는 값(콘솔 GET 은 실행기와 같은 클램프 값) + 워커가 다음 잡에서 읽을 값
    a.current = "8"
    eff_api = _ai_config(api)["config"]["timeout_seconds"]
    eff_worker = env.worker_value("ai_timeout_seconds")
    a.step(8, "실제 효과 — 콘솔 GET(실행기의 값) · 워커가 읽을 값", {"console_get_new": eff_api == expect,
                                                         "worker_reads_new": eff_worker == expect},
           unverified=["외부 모델 호출에 실제로 이 시간 제한이 걸리는지 — 제공자를 붙이지 않는다(외부)"],
           console_get=eff_api, worker_value=eff_worker)

    # 9
    a.current = "9"
    page.locator("#ai-timeout").fill(str(t0))
    http, toasts = _ai_save(page, sec)
    env.reload(page, "#ai-timeout")
    ui9, api9 = _ai_ui(page), _ai_config(api)["config"]["timeout_seconds"]
    a.step(9, "원래 값으로 되돌리고 확인(화면 + API)", {
        "saved_or_already": http == 200 or http is None, "success_toast": http is None or success_toast(toasts),
        "ui_restored": ui9 == t0, "api_restored": api9 == t0}, ui=ui9, api=api9, http=http)
    a.restore = {"timeout_seconds": {"original": t0, "now_api": api9, "now_ui": ui9}}


# ── ③ 내 프로필 — 방해금지 · 메일 알림 ─────────────────────────────────────────
PROFILE_PATH = "/#/profile"
SW_DND = "방해금지"
SW_MAIL = "메일 알림 받기"
SW_TYPE = "티켓 상태 변경 메일로 받기"
TYPE_KEY = "ticket_status_changed"


def _switch(page, name: str):
    return page.get_by_role("switch", name=name, exact=True)


def _prefs(api: Api) -> dict:
    st, j = api.get("/api/me/preferences")
    if st != 200:
        raise RuntimeError(f"내 설정을 읽지 못했다: HTTP {st}")
    return j


def _prefs_view(p: dict) -> dict:
    mail = p.get("mail") or {}
    types = mail.get("types")
    return {"dnd": bool((p.get("dnd") or {}).get("enabled")), "mail_enabled": bool(mail.get("enabled")),
            "type_on": None if types is None else (TYPE_KEY in types), "types": types,
            "quiet_now": (p.get("dnd") or {}).get("quiet_now")}


def _profile_ui(page) -> dict:
    return {"dnd": _switch(page, SW_DND).is_checked(), "mail_enabled": _switch(page, SW_MAIL).is_checked(),
            "type_on": _switch(page, SW_TYPE).is_checked()}


def _badges(api: Api) -> dict:
    out = {}
    for aud in ("user", "admin"):
        st, j = api.get("/api/notifications/unread-count", {"audience": aud})
        out[aud] = {"unread": (j or {}).get("unread"), "badge": (j or {}).get("badge"), "quiet": (j or {}).get("quiet")} \
            if st == 200 else {"http": st}
    return out


def _bell(page) -> dict:
    page.wait_for_timeout(600)
    return page.evaluate(BELL_JS) or {}


def _toggle(page, name: str) -> int:
    with page.expect_response(lambda r: "/api/me/preferences" in r.url and r.request.method == "PATCH", timeout=15_000) as resp:
        _switch(page, name).click()
    page.wait_for_timeout(250)
    return resp.value.status


def area_profile(env: Env, a: Area) -> None:
    api = env.api(EMAIL)
    actor = env.api(ROLE_ACCOUNTS["admin"])     # 알림을 만드는 사람 — 바꾼 사람 자신은 알림을 받지 않는다
    me_id = env.storage["system_admin"][1]
    _ctx, page = env.open()
    env.goto(page, PROFILE_PATH, ready=f'[role=switch][aria-label="{SW_DND}"]')

    # 1
    p0 = _prefs_view(_prefs(api))
    ui0 = _profile_ui(page)
    badges0, bell0 = _badges(api), _bell(page)
    env.aborts.append(lambda: api.send("PATCH", "/api/me/preferences", {
        "dnd_enabled": False, "dnd_minutes": 0, "mail_enabled": p0["mail_enabled"], "mail_types": p0["types"]}))
    a.step(1, "지금 값 읽기(화면 + API)", {
        "ui_dnd_equals_api": ui0["dnd"] == p0["dnd"], "ui_mail_equals_api": ui0["mail_enabled"] == p0["mail_enabled"],
        "ui_type_matches_api": ui0["type_on"] == (True if p0["type_on"] is None else p0["type_on"]),
        "mail_switch_enabled": _switch(page, SW_MAIL).is_enabled(),
    }, ui=ui0, api=p0, badges=badges0, bell=bell0)

    # (a) 저장 전 — 이 화면에는 저장 단추가 없다(스위치를 누르는 순간 저장된다)
    a.current = "unsaved"
    buttons = page.locator("main").get_by_role("button", name=re.compile(r"^(저장|되돌리기)$")).count()
    a.unsaved = a.path("unsaved", {"no_save_or_revert_button": buttons == 0},
                       note="즉시 저장 화면 — 저장 전 상태가 없다. 누르는 순간 PATCH 가 나가고 실패하면 스위치가 되돌아간다(아래 실패 길)")

    # (b) 강제 실패 — 500: 방해금지를 켜면 오류 토스트가 뜨고 스위치가 되돌아가야 한다
    a.current = "failure"
    undo = force_failure(page, "**/api/me/preferences", "PATCH", 500)
    mark = toast_mark(page)
    _switch(page, SW_DND).click()
    page.wait_for_timeout(1800)
    toasts = toasts_since(page, mark)
    checks = {"intercepted": len(undo.hits) >= 1, "no_success_toast": not any(t["sev"] == "success" for t in toasts),
              "error_toast_shown": any(t["sev"] == "error" and FORCED in t["msg"] for t in toasts),
              "switch_rolled_back": not _switch(page, SW_DND).is_checked(), "api_unchanged": not _prefs_view(_prefs(api))["dnd"]}
    env.shot(a, page, "failure-500")
    undo()
    env.reload(page, f'[role=switch][aria-label="{SW_DND}"]')
    checks["reload_shows_old"] = not _switch(page, SW_DND).is_checked()
    a.failure = a.path("failure", checks, http=500, toasts=toasts)

    # 2 · 3 · 4 — 메일 알림 받기 켬(유형 스위치가 서려면 먼저 켠다) → 「티켓 상태 변경」 메일 끔 → 방해금지 켬
    a.current = "2"
    mark = toast_mark(page)
    statuses = {}
    if not _switch(page, SW_MAIL).is_checked():
        statuses["mail_enabled"] = _toggle(page, SW_MAIL)
    statuses["type_off"] = _toggle(page, SW_TYPE)
    statuses["dnd_on"] = _toggle(page, SW_DND)
    ui2 = _profile_ui(page)
    exp = {"dnd": env.expect(True), "mail_enabled": True, "type_on": False}
    a.step(2, "화면에서 방해금지 · 메일 알림 받기 · 「티켓 상태 변경」 메일 스위치를 바꾼다",
           {"dnd_on": ui2["dnd"], "mail_on": ui2["mail_enabled"], "type_off": ui2["type_on"] is False}, ui=ui2)
    a.current = "3"
    a.step(3, "저장 — 스위치마다 PATCH", {f"{k}_200": v == 200 for k, v in statuses.items()}, http=statuses)
    a.current = "4"
    toasts = wait_toast(page, mark, 6.0)
    dnd_note = page_has_text(page, "지금 방해금지 중입니다")
    a.step(4, "성공 토스트 · 방해금지 표시", {"success_toast": success_toast(toasts, "설정을 저장했습니다"), "dnd_status_shown": dnd_note},
           toasts=toasts)
    env.shot(a, page, "04-saved")

    # 5 · 6
    a.current = "5"
    env.reload(page, f'[role=switch][aria-label="{SW_DND}"]')
    a.step(5, "새로 고침", {"switches_back": _switch(page, SW_DND).count() == 1})
    a.current = "6"
    ui6, p6 = _profile_ui(page), _prefs_view(_prefs(api))
    a.step(6, "다시 읽기 — 화면 · API 가 새 값", {
        "ui_dnd": ui6["dnd"] == exp["dnd"], "api_dnd": p6["dnd"] == exp["dnd"],
        "ui_mail": ui6["mail_enabled"] == exp["mail_enabled"], "api_mail": p6["mail_enabled"] == exp["mail_enabled"],
        "ui_type": ui6["type_on"] == exp["type_on"], "api_type": p6["type_on"] == exp["type_on"],
    }, ui=ui6, api=p6)
    env.shot(a, page, "06-reloaded")

    # 7
    a.current = "7"
    nav = env.away_and_back(page, "#/my-tickets", f'[role=switch][aria-label="{SW_DND}"]')
    ui7 = _profile_ui(page)
    fctx, fresh = env.open(fresh_email=EMAIL)
    env.goto(fresh, PROFILE_PATH, ready=f'[role=switch][aria-label="{SW_DND}"]')
    ui7f = _profile_ui(fresh)
    fctx.close()
    a.step(7, "다른 화면에 갔다 와서 · 다시 로그인한 새 맥락에서 다시 읽기", {
        "nav_ok": nav["ok"], "after_nav_new": ui7 == exp, "fresh_login_new": ui7f == exp,
    }, nav=nav, after_nav=ui7, fresh_login=ui7f)

    # 8 — 실제 효과: 배지 0 · 그래도 쌓이는 알림 · 그래도 나가는 배정 메일 · 끈 유형은 메일이 없다
    a.current = "8"
    badges8, bell8 = _badges(api), _bell(page)
    sys_before = int((re.search(r"시스템 알림 (\d+)건", (bell0 or {}).get("label") or "") or [0, 0])[1])
    st, projects = actor.get("/api/tickets/projects")
    project = next((p for p in (projects or {}).get("projects", []) if p.get("name") == "포털 개편"), None)
    t_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=2)   # DB 는 Z 없는 UTC 다
    before = len(env.sink.messages())
    title = f"설정 왕복 방해금지 확인 {secrets.token_hex(2)}"
    due = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    st_t, tj = actor.send("POST", "/api/tickets", {"title": title, "project_id": (project or {}).get("id"), "est_wd": 1,
                                                   "due_date": due, "assignee_user_ids": [me_id]})
    ticket = (tj or {}).get("ticket") or {} if isinstance(tj, dict) else {}
    assigned_mail = _wait_mail(env, before, EMAIL, "담당자로 지정")
    page_id = ticket.get("page_id") or ticket.get("id")
    cur = ticket.get("status")
    nxt = next(s for s in ("진행", "검증", "계획") if s != cur)
    st_s, _ = actor.send("PATCH", f"/api/tickets/{page_id}", {"status": nxt})
    time.sleep(6)   # 막힌 유형은 큐에 안 들어간다 — 들어갔다면 워커가 보낼 시간을 준다
    rows = env.rows("SELECT kind, status, params_json->>'type' AS type, to_email FROM mail_deliveries "
                    "WHERE recipient_user_id = :uid AND created_at >= :t ORDER BY created_at", uid=me_id, t=t_start)
    st_n, notis = api.get("/api/notifications", {"unread_only": 1})
    items = (notis or {}).get("items") if isinstance(notis, dict) else (notis or [])
    kinds = [n.get("type") for n in (items or []) if title in (n.get("body") or "") or title in (n.get("title") or "")]
    badges8b, bell8b = _badges(api), _bell(page)
    status_mails = [m for m in env.sink.received()[before:] if EMAIL in m["to"] and "상태 변경" in m["subject"]]
    a.step(8, "실제 효과 — 방해금지 중 배지 0, 알림은 쌓이고 배정 메일은 나가며, 끈 유형(상태 변경)은 메일이 없다", {
        "api_badge_zero": all((badges8b[aud].get("badge") == 0) for aud in ("user", "admin")),
        "unread_still_counted": (badges8b["user"].get("unread") or 0) >= (badges0["user"].get("unread") or 0) + 1,
        "bell_shows_only_system_notices": int(bell8b.get("text") or 0) == sys_before,
        "ticket_created": st_t in (200, 201) and bool(page_id),
        "assignment_notification_kept": "ticket_assigned" in kinds,
        "assignment_mail_sent_during_dnd": assigned_mail is not None,
        "assignment_delivery_row": any(r["type"] == "ticket_assigned" and r["kind"] == "notification" for r in rows),
        "status_change_notified": st_s == 200 and TYPE_KEY in kinds,
        "status_change_no_mail_row": not any(r["type"] == TYPE_KEY for r in rows),
        "status_change_no_mail_received": not status_mails,
    }, badges_before=badges0, badges_during=badges8b, bell_before=bell0, bell_during=bell8b,
        system_notices=sys_before, ticket={"http": st_t, "key": ticket.get("key"), "status": [cur, nxt], "status_http": st_s},
        notifications=kinds, deliveries=rows, mail={k: (assigned_mail or {}).get(k) for k in ("to", "subject", "helo")},
        note="시스템 공지(씨앗의 「정기 점검 안내」)는 방해금지도 숨기지 않는다 — 종에 남는 숫자는 그 공지 수다(NotificationBell 주석)",
        bell_after_save=bell8, badges_after_save=badges8)
    env.shot(a, page, "08-dnd-bell")

    # 9 — 되돌리기(방해금지 끔 → 유형 켬 → 메일 알림을 원래대로)
    a.current = "9"
    env.reload(page, f'[role=switch][aria-label="{SW_DND}"]')
    mark = toast_mark(page)
    statuses = {"dnd_off": _toggle(page, SW_DND), "type_on": _toggle(page, SW_TYPE)}
    if _switch(page, SW_MAIL).is_checked() != p0["mail_enabled"]:
        statuses["mail_restore"] = _toggle(page, SW_MAIL)
    toasts = wait_toast(page, mark, 6.0)
    env.reload(page, f'[role=switch][aria-label="{SW_DND}"]')
    ui9, p9, badges9 = _profile_ui(page), _prefs_view(_prefs(api)), _badges(api)
    a.step(9, "원래 값으로 되돌리고 확인(화면 + API)", {
        **{f"{k}_200": v == 200 for k, v in statuses.items()}, "success_toast": success_toast(toasts),
        "ui_restored": ui9 == ui0,
        "api_dnd_restored": p9["dnd"] == p0["dnd"], "api_mail_restored": p9["mail_enabled"] == p0["mail_enabled"],
        "api_types_restored": p9["types"] == p0["types"],
        "badge_back": (badges9["user"].get("badge") or 0) > 0,
    }, ui=ui9, api=p9, badges=badges9)
    a.restore = {"dnd": {"original": p0["dnd"], "now_api": p9["dnd"], "now_ui": ui9["dnd"]},
                 "mail_enabled": {"original": p0["mail_enabled"], "now_api": p9["mail_enabled"], "now_ui": ui9["mail_enabled"]},
                 "mail_types": {"original": p0["types"], "now_api": p9["types"]}}


# ── ④ 시스템 설정 — 정책 표 · OS와 서비스 ──────────────────────────────────────
SYS_PATH = "/admin#/settings"
SYS_KEY = "conversation_retention_days"
SYS_LABEL = "대화 보존 기간(일)"
SYS_ROW = f'tr[aria-label="상세 보기: {SYS_LABEL}"]'


def _sys_ui(page) -> int | None:
    m = re.search(r"(\d+)일", page.locator(SYS_ROW).first.inner_text())
    return int(m.group(1)) if m else None


def _sys_editor(page):
    page.locator(SYS_ROW).first.get_by_role("button", name="수정", exact=True).click()
    dlg = page.get_by_role("dialog", name=SYS_LABEL, exact=True)
    dlg.wait_for(timeout=10_000)
    return dlg


def _sys_close_editor(page, dlg) -> bool:
    """취소 — 바꾼 것이 있으면 「닫을까요?」를 묻는다. 물었으면 True."""
    dlg.get_by_role("button", name="취소", exact=True).click()
    confirm = page.get_by_role("dialog", name="확인")
    try:
        confirm.wait_for(timeout=3_000)
    except Exception:  # noqa: BLE001
        return False
    text_button(confirm, "닫기").click()
    page.wait_for_timeout(300)
    return True


def area_system(env: Env, a: Area) -> None:
    api = env.api(EMAIL)
    _ctx, page = env.open()
    env.goto(page, SYS_PATH, ready=SYS_ROW)

    # 1
    v0 = _setting_value(api, SYS_KEY)
    env.aborts.append(lambda: api.send("PUT", f"/api/admin/settings/{SYS_KEY}", {"value": v0}))
    ui0 = _sys_ui(page)
    a.step(1, "지금 값 읽기(화면 + API)", {"ui_equals_api": ui0 == v0}, ui=ui0, api=v0, key=SYS_KEY)

    # (a) 저장 전 — 같은 값이면 저장이 막히고, 바꾼 뒤 취소하면 닫을지 묻는다
    a.current = "unsaved"
    dlg = _sys_editor(page)
    spin = dlg.get_by_role("spinbutton", name="값")
    save_btn = dlg.get_by_role("button", name="저장", exact=True)
    clean = {"clean_save_disabled": save_btn.is_disabled(), "editor_shows_saved": spin.input_value() == str(v0)}
    spin.fill(str(v0 + 1))
    dirty = {"dirty_save_enabled": save_btn.is_enabled()}
    asked = _sys_close_editor(page, dlg)
    after = {"discard_confirm": asked, "api_unchanged": _setting_value(api, SYS_KEY) == v0, "table_unchanged": _sys_ui(page) == v0}
    a.unsaved = a.path("unsaved", {**clean, **dirty, **after})

    # (b) 강제 실패 — 409
    a.current = "failure"
    undo = force_failure(page, f"**/api/admin/settings/{SYS_KEY}", "PUT", 409)
    dlg = _sys_editor(page)
    dlg.get_by_role("spinbutton", name="값").fill(str(v0 + 1))
    mark = toast_mark(page)
    dlg.get_by_role("button", name="저장", exact=True).click()
    page.wait_for_timeout(1500)
    toasts = toasts_since(page, mark)
    alert = forced_alert(dlg)
    iv = in_view(alert)
    checks = {"intercepted": len(undo.hits) == 1, "no_success_toast": not any(t["sev"] == "success" for t in toasts),
              "error_shown": alert.count() > 0, "error_in_view": iv["in_view"], "dialog_stays_open": dlg.is_visible(),
              "api_unchanged": _setting_value(api, SYS_KEY) == v0}
    error_text = alert.first.inner_text() if alert.count() else None
    env.shot(a, page, "failure-409")
    offscreen_error(env, a, page, iv, f"/admin#/settings → 「{SYS_LABEL}」 수정 창에서 저장(실패)")
    _sys_close_editor(page, dlg)
    undo()
    env.reload(page, SYS_ROW)
    checks["reload_shows_old"] = _sys_ui(page) == v0
    a.failure = a.path("failure", checks, http=409, toasts=toasts, error_text=error_text, error_position=iv)

    # 2 · 3 · 4
    a.current = "2"
    new = v0 + 1
    expect = env.expect(new)
    dlg = _sys_editor(page)
    dlg.get_by_role("spinbutton", name="값").fill(str(new))
    a.step(2, f"화면에서 {SYS_LABEL}을 바꾼다", {"input_has_new": dlg.get_by_role("spinbutton", name="값").input_value() == str(new),
                                             "save_enabled": dlg.get_by_role("button", name="저장", exact=True).is_enabled()},
           new=new)
    a.current = "3"
    drop = env.drop_route(page, f"**/api/admin/settings/{SYS_KEY}", "PUT",
                          (lambda body: {"key": SYS_KEY, "before": v0, "after": body.get("value"), "restart_required": False})
                          if "system" in DROP_AREAS else None)
    mark = toast_mark(page)
    with page.expect_response(lambda r: r.url.endswith(f"/api/admin/settings/{SYS_KEY}") and r.request.method == "PUT",
                              timeout=20_000) as resp:
        dlg.get_by_role("button", name="저장", exact=True).click()
    http = resp.value.status
    a.step(3, "저장", {"http_200": http == 200}, http=http, dropped=bool(drop))
    a.current = "4"
    toasts = wait_toast(page, mark, 6.0)
    page.wait_for_timeout(600)
    a.step(4, "성공 토스트 · 창 닫힘", {"success_toast": success_toast(toasts, "설정을 저장했습니다"), "dialog_closed": not dlg.is_visible()},
           toasts=toasts)
    env.shot(a, page, "04-saved")
    if drop:
        drop()

    # 5 · 6
    a.current = "5"
    env.reload(page, SYS_ROW)
    a.step(5, "새로 고침", {"row_back": page.locator(SYS_ROW).count() >= 1})
    a.current = "6"
    ui6, api6 = _sys_ui(page), _setting_value(api, SYS_KEY)
    a.step(6, "다시 읽기 — 화면 · API 가 새 값", {"ui_new": ui6 == expect, "api_new": api6 == expect}, ui=ui6, api=api6)
    env.shot(a, page, "06-reloaded")

    # 7
    a.current = "7"
    nav = env.away_and_back(page, "#/dashboard", SYS_ROW)
    ui7 = _sys_ui(page)
    fctx, fresh = env.open(fresh_email=EMAIL)
    env.goto(fresh, SYS_PATH, ready=SYS_ROW)
    ui7f = _sys_ui(fresh)
    fctx.close()
    a.step(7, "다른 화면에 갔다 와서 · 다시 로그인한 새 맥락에서 다시 읽기",
           {"nav_ok": nav["ok"], "after_nav_new": ui7 == expect, "fresh_login_new": ui7f == expect},
           nav=nav, after_nav=ui7, fresh_login=ui7f)

    # 8 — 실제 효과: API · 워커(보존 정리 작업이 도는 쪽)가 읽을 값
    a.current = "8"
    st, j = api.get("/api/admin/settings")
    row = ((j or {}).get("settings") or {}).get(SYS_KEY) or {}
    worker = env.worker_value(SYS_KEY)
    a.step(8, "실제 효과 — 설정 API · 워커가 다음 잡에서 읽을 값", {"api_value": row.get("value") == expect,
                                                         "marked_not_default": row.get("is_default") is False,
                                                         "worker_reads_new": worker == expect},
           unverified=["보존 정리 작업이 실제로 지우는 대화 — 이 하네스는 정리 작업을 돌리지 않는다"],
           api=row, worker_value=worker)

    # 9
    a.current = "9"
    dlg = _sys_editor(page)
    dlg.get_by_role("spinbutton", name="값").fill(str(v0))
    http, toasts = None, []
    if dlg.get_by_role("button", name="저장", exact=True).is_enabled():
        mark = toast_mark(page)
        with page.expect_response(lambda r: r.url.endswith(f"/api/admin/settings/{SYS_KEY}") and r.request.method == "PUT",
                                  timeout=20_000) as resp:
            dlg.get_by_role("button", name="저장", exact=True).click()
        http = resp.value.status
        toasts = wait_toast(page, mark, 6.0)
    else:
        _sys_close_editor(page, dlg)    # 이미 원래 값이다(저장이 버려진 실행) — 보낼 것이 없다
    env.reload(page, SYS_ROW)
    ui9, api9 = _sys_ui(page), _setting_value(api, SYS_KEY)
    a.step(9, "원래 값으로 되돌리고 확인(화면 + API)", {
        "saved_or_already": http == 200 or http is None, "success_toast": http is None or success_toast(toasts),
        "ui_restored": ui9 == v0, "api_restored": api9 == v0}, ui=ui9, api=api9, http=http)
    a.restore = {SYS_KEY: {"original": v0, "now_api": api9, "now_ui": ui9}}

    # OS와 서비스 — 이 환경에서 바꿀 수 있는 항목이 있는가
    env.goto(page, SYS_PATH + "?tab=os", ready="#settings-tabpanel-os")
    panel = page.locator("#settings-tabpanel-os")
    st_sys, sysj = api.get("/api/admin/system")
    helper_note = "이 운영체제에서는 시스템 설정 기능을 쓸 수 없습니다."
    os_buttons = panel.get_by_role("button").count()
    env.shot(a, page, "os-tab")
    a.extra["os_item"] = {
        "status": "미검증(외부)",
        "reason": "이 탭의 모든 쓰기는 루트 도우미(clovirassist-privhelper)를 지나 OS 를 바꾼다 — 로컬(Windows)에는 도우미가 없어 화면에 "
                  "바꿀 단추가 서지 않는다. DB 에만 남는 안전한 항목은 이 탭에 없다.",
        "observed": {"helper_unavailable_notice": page_has_text(page, helper_note), "buttons_in_panel": os_buttons,
                     "api_system": {"http": st_sys, "available": (sysj or {}).get("available") if isinstance(sysj, dict) else None,
                                    "detail": (sysj or {}).get("detail") if isinstance(sysj, dict) else None},
                     "rows": [r for r in ("서비스 주소", "호스트 이름", "타임존", "시각 동기화", "DNS 서버",
                                                                     "아웃바운드 프록시", "TLS 인증서", "서비스")
                                                        if page_has_text(page, r)]},
    }
    print(f"[system] OS와 서비스: 미검증(외부) — 도우미 없음 안내={a.extra['os_item']['observed']['helper_unavailable_notice']}, "
          f"단추 {os_buttons}개", flush=True)


# ── ⑤ 사용자와 권한 ───────────────────────────────────────────────────────────
USERS_TARGET = ROLE_ACCOUNTS["user"]          # 씨앗의 일반 사용자 — 이 계정의 역할만 바꾸고 되돌린다
USERS_TARGET_NAME = "이서연"
ROLE_LABEL = {"user": "일반 사용자", "operator": "운영자", "admin": "관리자", "auditor": "감사자", "system_admin": "시스템 관리자"}
USERS_PATH = "/admin#/users?q=lee.seoyeon"
USERS_ROW = f'tr[aria-label="상세 보기: {USERS_TARGET_NAME}"]'


def _role_in(text: str) -> str | None:
    """보인 글에서 역할 낱말 — 「관리자」는 「시스템 관리자」 · 「전체 관리자」 안에도 있으니 긴 낱말부터 본다."""
    for key in ("system_admin", "operator", "auditor", "user"):
        if ROLE_LABEL[key] in text:
            return key
    return "admin" if "관리자" in text else None


def _users_api_role(api: Api) -> tuple[str | None, str | None]:
    st, j = api.get("/api/admin/users", {"q": "lee.seoyeon"})
    items = (j or {}).get("items") if isinstance(j, dict) else j
    for u in items or []:
        if u.get("email") == USERS_TARGET:
            return u.get("role"), u.get("id")
    return None, None


def _users_row_role(page) -> str | None:
    return _role_in(page.locator(USERS_ROW).first.inner_text())


def _users_edit(page):
    page.locator(USERS_ROW).first.click()
    detail = page.get_by_role("dialog", name=USERS_TARGET_NAME, exact=True)
    detail.wait_for(timeout=10_000)
    detail.get_by_role("button", name="수정", exact=True).click()
    form = page.get_by_role("dialog", name=f"{USERS_TARGET_NAME} 수정", exact=True)
    form.wait_for(timeout=10_000)
    return form


def _users_pick(page, form, role: str) -> None:
    form.locator("#ff-role").click()
    page.get_by_role("option", name=ROLE_LABEL[role], exact=True).click()
    page.wait_for_timeout(250)


def _users_close_dialogs(page) -> None:
    """열린 창을 모두 닫는다 — 바뀐 것을 버릴지 물으면 버린다(Esc 만 누르면 「버리기」 확인과 편집 창 사이를 맴돈다)."""
    for _ in range(6):
        if page.locator("[role=dialog]").filter(visible=True).count() == 0:
            return
        confirm = page.get_by_role("dialog", name="변경 사항 버리기")
        if confirm.count() and confirm.is_visible():
            text_button(confirm, "닫기").click()
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(350)


def _users_effect(env: Env, tag: str, a: Area) -> dict:
    """그 계정으로 로그인 화면에서 새로 로그인해 운영자 이상만 쓰는 것을 연다 — 작업 큐 API 와 관리 콘솔의 작업 큐 화면."""
    ctx, page = env.open(fresh_email=USERS_TARGET)
    jobs = ctx.request.get(env.base + "/api/admin/jobs").status
    page.goto(env.base + "/admin#/jobs", wait_until="domcontentloaded")
    page.locator("main").first.wait_for(timeout=30_000)
    page.wait_for_timeout(1500)
    me = ctx.request.get(env.base + "/api/me").json()
    out = {"jobs_http": jobs, "url": page.url, "on_admin_console": "/admin" in page.url,
           "switch_group": page.get_by_role("group", name="화면 전환").count() > 0,
           "jobs_heading": page.get_by_role("heading", name="작업 큐", level=1).count() > 0,
           "me_role": (me.get("user") or {}).get("role")}
    env.shot(a, page, f"{tag}-as-target")
    ctx.close()
    return out


def _users_save(page, form) -> tuple[int, list, object]:
    mark = toast_mark(page)
    with page.expect_response(lambda r: "/api/admin/users/" in r.url and r.request.method == "PATCH", timeout=20_000) as resp:
        form.get_by_role("button", name="저장", exact=True).click()
    sent = resp.value.request.post_data
    return resp.value.status, wait_toast(page, mark, 6.0), sent


def area_users(env: Env, a: Area) -> None:
    api = env.api(EMAIL)
    _ctx, page = env.open()
    env.goto(page, USERS_PATH, ready=USERS_ROW)

    # 1 — 지금 값 + 바꾸기 전의 효과(일반 사용자: 작업 큐 403, 관리 콘솔 없음)
    role0, uid = _users_api_role(api)
    env.aborts.append(lambda: api.send("PATCH", f"/api/admin/users/{uid}", {"role": role0}))
    ui0 = _users_row_role(page)
    effect0 = _users_effect(env, "01-before", a)
    a.step(1, "지금 값 읽기(화면 + API) — 대상은 씨앗의 일반 사용자", {
        "api_user": role0 == "user", "ui_equals_api": ui0 == role0,
        "before_jobs_403": effect0["jobs_http"] == 403, "before_no_admin_console": not effect0["on_admin_console"],
    }, target=USERS_TARGET, user_id=uid, ui=ui0, api=role0, effect_before=effect0)

    # (a) 저장 전 — 고른 뒤 취소하면 「변경 사항 버리기」를 묻고, 닫으면 그대로다
    a.current = "unsaved"
    form = _users_edit(page)
    _users_pick(page, form, "operator")
    save_enabled = form.get_by_role("button", name="저장", exact=True).is_enabled()
    form.get_by_role("button", name="취소", exact=True).click()
    confirm = page.get_by_role("dialog", name="변경 사항 버리기")
    asked = True
    try:
        confirm.wait_for(timeout=4_000)
    except Exception:  # noqa: BLE001 — 묻지 않았으면 그대로 기록한다
        asked = False
    if asked:
        text_button(confirm, "닫기").click()
    page.wait_for_timeout(400)
    form_closed = not form.is_visible()
    _users_close_dialogs(page)
    a.unsaved = a.path("unsaved", {"save_enabled_after_pick": save_enabled, "discard_confirm": asked, "form_closed": form_closed,
                                   "api_unchanged": _users_api_role(api)[0] == role0, "ui_unchanged": _users_row_role(page) == role0},
                       note="편집 창의 저장 단추는 늘 눌린다(바뀐 칸만 보낸다). 취소는 바꾼 것이 있으면 버릴지 묻는다.")

    # (b) 강제 실패 — 500
    a.current = "failure"
    undo = force_failure(page, "**/api/admin/users/*", "PATCH", 500)
    form = _users_edit(page)
    _users_pick(page, form, "operator")
    mark = toast_mark(page)
    form.get_by_role("button", name="저장", exact=True).click()
    page.wait_for_timeout(1500)
    toasts = toasts_since(page, mark)
    err = forced_alert(form)
    iv = in_view(err)
    checks = {"intercepted": len(undo.hits) == 1, "no_success_toast": not any(t["sev"] == "success" for t in toasts),
              "error_shown": err.count() > 0, "error_in_view": iv["in_view"], "form_stays_open": form.is_visible(),
              "api_unchanged": _users_api_role(api)[0] == role0}
    error_text = err.first.inner_text() if err.count() else None
    env.shot(a, page, "failure-500")
    offscreen_error(env, a, page, iv, f"/admin#/users → 「{USERS_TARGET_NAME} 수정」 창에서 역할을 바꾸고 저장(실패)")
    undo()
    env.reload(page, USERS_ROW)
    _users_close_dialogs(page)
    checks["reload_shows_old"] = _users_row_role(page) == role0
    a.failure = a.path("failure", checks, http=500, toasts=toasts, error_text=error_text, error_position=iv)

    # 2 · 3 · 4 — 운영자로 바꾸고 저장
    a.current = "2"
    expect_role = env.expect("operator")
    form = _users_edit(page)
    _users_pick(page, form, "operator")
    picked = form.locator("#ff-role").inner_text().strip()
    a.step(2, "화면에서 역할을 운영자로 고른다", {"picked_operator": picked == ROLE_LABEL["operator"]}, picked=picked)
    a.current = "3"
    http, toasts, sent = _users_save(page, form)
    a.step(3, "저장", {"http_2xx": 200 <= http < 300}, http=http, sent=sent)
    a.current = "4"
    a.step(4, "성공 토스트", {"success_toast": success_toast(toasts, "사용자 정보를 저장했습니다"),
                          "no_approval_detour": not any("승인 요청이 접수" in t["msg"] for t in toasts)},
           toasts=toasts, note="시스템 관리자가 바꾸면 승인 없이 바로 적용된다(승인은 시스템 관리자가 아닌 사람이 관리자로 올릴 때만)")
    env.shot(a, page, "04-saved")
    _users_close_dialogs(page)

    # 5 · 6
    a.current = "5"
    env.reload(page, USERS_ROW)
    _users_close_dialogs(page)
    a.step(5, "새로 고침", {"row_back": page.locator(USERS_ROW).count() >= 1})
    a.current = "6"
    ui6, (api6, _) = _users_row_role(page), _users_api_role(api)
    a.step(6, "다시 읽기 — 화면 · API 가 운영자", {"ui_new": ui6 == expect_role, "api_new": api6 == expect_role}, ui=ui6, api=api6)

    # 7
    a.current = "7"
    nav = env.away_and_back(page, "#/dashboard", USERS_ROW)
    ui7 = _users_row_role(page)
    fctx, fresh = env.open(fresh_email=EMAIL)
    env.goto(fresh, USERS_PATH, ready=USERS_ROW)
    ui7f = _users_row_role(fresh)
    fctx.close()
    a.step(7, "다른 화면에 갔다 와서 · 다시 로그인한 새 맥락에서 다시 읽기",
           {"nav_ok": nav["ok"], "after_nav_new": ui7 == expect_role, "fresh_login_new": ui7f == expect_role},
           nav=nav, after_nav=ui7, fresh_login=ui7f)

    # 8 — 실제 효과: 그 계정이 다시 로그인하면 운영자다(작업 큐 200, 관리 콘솔)
    a.current = "8"
    effect = _users_effect(env, "08-operator", a)
    a.step(8, "실제 효과 — 그 계정으로 새로 로그인하면 작업 큐 API 200 · 관리 콘솔의 작업 큐 화면", {
        "jobs_200": effect["jobs_http"] == 200, "admin_console": effect["on_admin_console"] and effect["jobs_heading"],
        "me_role_operator": effect["me_role"] == expect_role,
    }, effect=effect, before=effect0)

    # 9 — 화면으로 일반 사용자로 되돌리고 403 을 다시 본다
    a.current = "9"
    env.reload(page, USERS_ROW)
    _users_close_dialogs(page)
    form = _users_edit(page)
    _users_pick(page, form, "user")
    http, toasts, _sent = _users_save(page, form)
    _users_close_dialogs(page)
    env.reload(page, USERS_ROW)
    _users_close_dialogs(page)
    ui9, (api9, _) = _users_row_role(page), _users_api_role(api)
    effect9 = _users_effect(env, "09-restored", a)
    a.step(9, "원래 역할로 되돌리고 확인(화면 + API + 다시 403)", {
        "http_2xx": 200 <= http < 300, "success_toast": success_toast(toasts),
        "ui_restored": ui9 == role0, "api_restored": api9 == role0,
        "jobs_403_again": effect9["jobs_http"] == 403, "no_admin_console": not effect9["on_admin_console"],
    }, ui=ui9, api=api9, effect=effect9)
    a.restore = {"role": {"original": role0, "now_api": api9, "now_ui": ui9}, "jobs_http_after_restore": effect9["jobs_http"]}


# ── ⑥ 게임방 설정 ─────────────────────────────────────────────────────────────
MAP_LABELS = {"wheel": "운명의 바퀴", "pot": "탐욕의 항아리", "bubble": "비눗방울", "yoru": "밤을 달리다"}  # `stages/labels.js`
GAME_ORIGINAL = {"map": "pot", "winners": 1, "speed": 2}     # 게임방 추가 창에서 고르는 처음 값
GAME_NEW = {"map": "bubble", "winners": 2, "speed": 4}
# 사실 줄의 조각은 띄어 쓰지 않고 붙어 선다(「구슬 2」「당첨 1」「2배속」 → 「구슬 2당첨 12배속」) — 조각마다 따로 읽는다.
GAME_FACTS_JS = r"""(labels) => {
  const facts = document.querySelector('[data-room-facts]');
  const text = facts ? facts.textContent : '';
  const parts = facts ? Array.from(facts.querySelectorAll('span')).map((e) => e.textContent.trim()) : [];
  const pick = (re) => { for (const p of parts) { const m = p.match(re); if (m) return Number(m[1]); } return null; };
  const winners = pick(/^당첨 (\d+)(\(꼴찌\))?$/);
  const speed = pick(/^(\d)배속$/);
  const canvas = document.querySelector('[data-marble-canvas]');
  const status = document.querySelector('[data-room-status]');
  return {
    map: Object.keys(labels).filter((k) => text.includes(labels[k])),
    winners, speed, parts,
    drawn: canvas ? canvas.getAttribute('data-drawn-map') : null,
    status: status ? status.getAttribute('data-room-status') : null,
  };
}"""


def _game_state(api: Api, rid: str) -> dict:
    st, j = api.get(f"/api/games/rooms/{rid}/state", {"since": 0})
    if st != 200:
        return {"http": st}
    s = j.get("state") or {}
    cfg = s.get("config") or {}
    return {"http": st, "room_status": j["room"]["status"], "members": j["room"].get("member_count"), "phase": s.get("phase"),
            "config": {"map": cfg.get("map"), "winners": cfg.get("winners"), "speed": cfg.get("speed")},
            "race": {"map": s.get("map"), "winners_n": s.get("winners_n"), "speed": s.get("speed")},
            "integrity": (s.get("integrity") or {}).get("status")}


def _game_facts(page) -> dict:
    f = page.evaluate(GAME_FACTS_JS, MAP_LABELS)
    return {"map": f["map"][0] if len(f["map"]) == 1 else f["map"], "winners": f["winners"], "speed": f["speed"],
            "drawn": f["drawn"], "status": f["status"]}


def _game_cfg(facts: dict) -> dict:
    return {"map": facts["map"], "winners": facts["winners"], "speed": facts["speed"]}


def _game_modal(page):
    page.locator("[data-room-toolbar]").get_by_role("button", name="설정", exact=True).first.click()
    dlg = page.get_by_role("dialog", name="경주 설정")
    dlg.wait_for(timeout=10_000)
    return dlg


def _game_modal_values(dlg) -> dict:
    label = dlg.locator("#marble-map").inner_text().strip()
    key = next((k for k, v in MAP_LABELS.items() if v == label), label)
    speed_text = dlg.locator("#marble-speed").inner_text().strip()
    return {"map": key, "winners": int(dlg.locator("#marble-winners").input_value() or 0),
            "speed": int(re.sub(r"\D", "", speed_text) or 0)}


def _game_modal_set(page, dlg, values: dict) -> None:
    dlg.locator("#marble-map").click()
    page.get_by_role("option", name=MAP_LABELS[values["map"]], exact=True).click()
    dlg.locator("#marble-winners").fill(str(values["winners"]))
    dlg.locator("#marble-speed").click()
    page.get_by_role("option", name=f"{values['speed']}배속", exact=True).click()
    page.wait_for_timeout(200)


def _game_read_modal(page) -> dict:
    dlg = _game_modal(page)
    vals = _game_modal_values(dlg)
    dlg.get_by_role("button", name="취소", exact=True).click()
    dlg.wait_for(state="hidden", timeout=5_000)
    return vals


def _game_save(page, dlg) -> int:
    with page.expect_response(lambda r: "/marble/config" in r.url and r.request.method == "PUT", timeout=20_000) as resp:
        dlg.get_by_role("button", name="저장", exact=True).click()
    return resp.value.status


def _game_wait(api: Api, rid: str, pred, timeout_s: float) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        last = _game_state(api, rid)
        if pred(last):
            return last
        time.sleep(0.8)
    return last


def area_game(env: Env, a: Area) -> None:
    api = env.api(EMAIL)
    token = secrets.token_hex(2)
    _ctx, page = env.open()
    # 방 만들기 — 게임방 추가 창에서 구슬 레이스 · 탐욕의 항아리 · 당첨 1 · 2배속(이 영역의 「원래 값」)
    env.goto(page, "/#/games", ready="main")
    page.get_by_role("button", name="게임방 추가").first.click()
    add = page.get_by_role("dialog", name="게임방 추가")
    add.wait_for(timeout=10_000)
    add.locator("#gr-game").click()
    page.get_by_role("option", name="구슬 레이스", exact=True).click()
    add.locator("#gr-title").fill(f"설정 왕복 구슬 레이스 {token}")
    add.locator("#gr-marble-map").click()
    page.get_by_role("option", name=MAP_LABELS[GAME_ORIGINAL["map"]], exact=True).click()
    add.locator("#gr-marble-speed").click()
    page.get_by_role("option", name=f"{GAME_ORIGINAL['speed']}배속", exact=True).click()
    add.get_by_role("button", name="추가", exact=True).click()
    page.wait_for_url(lambda u: "#/games/" in u, timeout=15_000)
    page.locator('[data-marble-stage="idle"]').wait_for(timeout=20_000)
    rid = page.url.split("#/games/")[1].split("?")[0].strip("/")
    env.aborts.append(lambda: api.send("POST", f"/api/games/rooms/{rid}/disband"))
    a.extra["room"] = rid
    # 참가자 — 경주는 지금 방에 있는 구성원 2명부터다. 운영자 계정이 같은 방을 연다.
    _pctx, part = env.open("operator")
    part.goto(env.base + f"/#/games/{rid}", wait_until="domcontentloaded")
    part.locator('[data-marble-stage="idle"]').wait_for(timeout=30_000)
    _game_wait(api, rid, lambda s: (s.get("members") or 0) >= 2, 20)
    room_ready = "#main-content [data-room-toolbar]"

    # 1
    a.current = "1"
    s0, f0 = _game_state(api, rid), _game_facts(page)
    m0 = _game_read_modal(page)
    a.step(1, "지금 값 읽기(툴바 · 설정 창 + API)", {
        "api_original": s0.get("config") == GAME_ORIGINAL, "toolbar_equals_api": _game_cfg(f0) == s0.get("config"),
        "modal_equals_api": m0 == s0.get("config"),
    }, api=s0, toolbar=f0, modal=m0)

    # (a) 저장 전 — 고른 뒤 취소하면 그대로다, Esc 는 버릴지 묻는다
    a.current = "unsaved"
    dlg = _game_modal(page)
    _game_modal_set(page, dlg, GAME_NEW)
    save_enabled = dlg.get_by_role("button", name="저장", exact=True).is_enabled()
    page.keyboard.press("Escape")
    confirm = page.get_by_role("dialog", name="변경 사항 버리기")
    esc_asks = True
    try:
        confirm.wait_for(timeout=3_000)
    except Exception:  # noqa: BLE001 — 묻지 않았으면 그대로 기록한다
        esc_asks = False
    if esc_asks:
        text_button(confirm, "취소").click()     # 계속 고친다 — 창은 열린 채여야 한다
    page.wait_for_timeout(300)
    still_open = dlg.is_visible()
    if still_open:
        dlg.get_by_role("button", name="취소", exact=True).click()
        dlg.wait_for(state="hidden", timeout=5_000)
    s_a, f_a = _game_state(api, rid), _game_facts(page)
    a.unsaved = a.path("unsaved", {"save_enabled": save_enabled, "escape_asks_discard": esc_asks, "kept_open_after_keep": still_open,
                                   "cancel_leaves_api": s_a.get("config") == GAME_ORIGINAL,
                                   "cancel_leaves_toolbar": _game_cfg(f_a) == GAME_ORIGINAL},
                       note="창 아래 「취소」는 묻지 않고 닫는다(바뀐 것을 버린다). Esc · 바깥 누름은 「변경 사항 버리기」를 묻는다.")

    # (b) 강제 실패 — 409
    a.current = "failure"
    undo = force_failure(page, f"**/api/games/rooms/{rid}/marble/config", "PUT", 409)
    dlg = _game_modal(page)
    _game_modal_set(page, dlg, GAME_NEW)
    mark = toast_mark(page)
    dlg.get_by_role("button", name="저장", exact=True).click()
    page.wait_for_timeout(1500)
    toasts = toasts_since(page, mark)
    alert = forced_alert(dlg)
    iv = in_view(alert)
    checks = {"intercepted": len(undo.hits) == 1, "no_success_toast": not any(t["sev"] == "success" for t in toasts),
              "error_shown": alert.count() > 0, "error_in_view": iv["in_view"], "modal_stays_open": dlg.is_visible(),
              "toolbar_unchanged": _game_cfg(_game_facts(page)) == GAME_ORIGINAL,
              "api_unchanged": _game_state(api, rid).get("config") == GAME_ORIGINAL}
    error_text = alert.first.inner_text() if alert.count() else None
    env.shot(a, page, "failure-409")
    offscreen_error(env, a, page, iv, "게임방 → 「경주 설정」 창에서 저장(실패)")
    dlg.get_by_role("button", name="취소", exact=True).click()
    undo()
    env.reload(page, room_ready)
    checks["reload_shows_old"] = _game_cfg(_game_facts(page)) == GAME_ORIGINAL
    a.failure = a.path("failure", checks, http=409, toasts=toasts, error_text=error_text, error_position=iv)

    # 2 · 3 · 4
    a.current = "2"
    expect = {**GAME_NEW, "winners": env.expect(GAME_NEW["winners"])}
    dlg = _game_modal(page)
    _game_modal_set(page, dlg, GAME_NEW)
    m2 = _game_modal_values(dlg)
    a.step(2, "설정 창에서 맵 · 당첨 인원 · 배속을 바꾼다", {"modal_has_new": m2 == GAME_NEW}, modal=m2)
    a.current = "3"
    mark = toast_mark(page)
    http = _game_save(page, dlg)
    a.step(3, "저장", {"http_200": http == 200}, http=http)
    a.current = "4"
    page.wait_for_timeout(1200)
    f4 = _game_facts(page)
    toasts = toasts_since(page, mark)
    a.step(4, "저장 표시 — 창이 닫히고 툴바의 사실 줄이 바뀐다(이 화면은 성공 토스트를 띄우지 않는다)", {
        "modal_closed": not dlg.is_visible(), "toolbar_updated": _game_cfg(f4) == GAME_NEW, "no_error_toast": not any(
            t["sev"] == "error" for t in toasts)}, toolbar=f4, toasts=toasts)
    env.shot(a, page, "04-saved")

    # 5 · 6
    a.current = "5"
    env.reload(page, room_ready)
    page.locator('[data-marble-stage="idle"]').wait_for(timeout=20_000)
    a.step(5, "새로 고침", {"room_back": page.locator('[data-marble-stage="idle"]').count() == 1})
    a.current = "6"
    f6, s6 = _game_facts(page), _game_state(api, rid)
    m6 = _game_read_modal(page)
    a.step(6, "다시 읽기 — 툴바 · 설정 창 · API 가 새 값", {"toolbar_new": _game_cfg(f6) == expect, "modal_new": m6 == expect,
                                                      "api_new": s6.get("config") == expect},
           toolbar=f6, modal=m6, api=s6.get("config"))

    # 7
    a.current = "7"
    nav = env.away_and_back(page, "#/games", room_ready)
    f7 = _game_facts(page)
    fctx, fresh = env.open(fresh_email=EMAIL)
    fresh.goto(env.base + f"/#/games/{rid}", wait_until="domcontentloaded")
    fresh.locator('[data-marble-stage="idle"]').wait_for(timeout=30_000)
    fresh.wait_for_timeout(800)
    f7f = _game_facts(fresh)
    m7f = _game_read_modal(fresh)
    fctx.close()
    a.step(7, "다른 화면에 갔다 와서 · 다시 로그인한 새 맥락에서 다시 읽기", {
        "nav_ok": nav["ok"], "after_nav_new": _game_cfg(f7) == expect, "fresh_toolbar_new": _game_cfg(f7f) == expect,
        "fresh_modal_new": m7f == expect,
    }, nav=nav, after_nav=f7, fresh_login={"toolbar": f7f, "modal": m7f})

    # 8 — 실제 효과: 경주를 시작하면 경주에 박힌 맵 · 당첨 인원 · 배속이 저장한 값이다
    a.current = "8"
    page.locator("[data-room-toolbar]").get_by_role("button", name="경주 시작").click()
    page.locator('[data-marble-stage="running"]').wait_for(timeout=15_000)
    s8 = _game_wait(api, rid, lambda s: s.get("phase") == "running", 10)
    f8 = _game_facts(page)
    env.shot(a, page, "08-running")
    a.step(8, "실제 효과 — 시작한 경주의 맵 · 당첨 인원 · 배속(방 상태 + 그린 판)", {
        "race_map": s8["race"]["map"] == expect["map"], "race_winners": s8["race"]["winners_n"] == expect["winners"],
        "race_speed": s8["race"]["speed"] == expect["speed"], "drawn_map": f8["drawn"] == expect["map"],
    }, race=s8.get("race"), toolbar=f8, participants=s8.get("members"))
    # 끝나면 「다시 하기」로 대기로 돌린다(설정은 대기 중에만 바꾼다)
    done = _game_wait(api, rid, lambda s: s.get("phase") in ("finished", "abandoned"), 240)
    page.locator('[data-result-panel="revealed"]').wait_for(timeout=60_000)
    a.extra["race_end"] = {"phase": done.get("phase"), "integrity": done.get("integrity")}
    page.locator('[role="dialog"] button:has-text("다시 하기")').last.click()
    page.locator('[data-marble-stage="idle"]').wait_for(timeout=15_000)

    # 9 — 설정 창으로 처음 값으로 되돌린다
    a.current = "9"
    dlg = _game_modal(page)
    _game_modal_set(page, dlg, GAME_ORIGINAL)
    http = _game_save(page, dlg)
    env.reload(page, room_ready)
    page.locator('[data-marble-stage="idle"]').wait_for(timeout=20_000)
    f9, s9 = _game_facts(page), _game_state(api, rid)
    m9 = _game_read_modal(page)
    a.step(9, "처음 값으로 되돌리고 확인(툴바 · 설정 창 + API)", {
        "http_200": http == 200, "toolbar_restored": _game_cfg(f9) == GAME_ORIGINAL, "modal_restored": m9 == GAME_ORIGINAL,
        "api_restored": s9.get("config") == GAME_ORIGINAL,
    }, toolbar=f9, modal=m9, api=s9.get("config"))
    a.restore = {"config": {"original": GAME_ORIGINAL, "now_api": s9.get("config"), "now_ui": _game_cfg(f9)}}

    # 정리 — 게임방 종료(방장 넘침 메뉴 → 확인)
    page.get_by_role("button", name="방 동작 더 보기").click()
    page.get_by_role("menuitem", name="게임방 종료").click()
    confirm = page.get_by_role("dialog", name="게임방 종료")
    confirm.wait_for(timeout=5_000)
    confirm.get_by_role("button", name="게임방 종료", exact=True).click()
    page.wait_for_url(lambda u: u.rstrip("/").endswith("#/games"), timeout=15_000)
    closed = _game_state(api, rid)
    a.restore["room_closed"] = {"http": closed.get("http"), "room_status": closed.get("room_status")}
    env.aborts.clear()


AREA_FUNCS = {"mail": area_mail, "ai": area_ai, "profile": area_profile, "system": area_system, "users": area_users,
              "game": area_game}


def run_area(env: Env, key: str) -> Area:
    a = Area(key, TITLES[key])
    env.area = key
    env.aborts = []
    print(f"\n=== {TITLES[key]} ===", flush=True)
    try:
        AREA_FUNCS[key](env, a)
    except Exception as exc:  # noqa: BLE001 — 한 영역이 멈춰도 나머지를 돈다
        a.steps.append({"step": a.current, "name": "중단", "status": "FAIL", "checks": {"no_exception": False},
                        "observed": {"error": str(exc).splitlines()[0][:400] if str(exc) else repr(exc)}})
        a.notes.append({"traceback": traceback.format_exc()[-3000:]})
        print(f"[{key}] 중단: {exc}", flush=True)
        for ctx in list(env.contexts):
            for pg in ctx.pages:
                env.shot(a, pg, f"ABORT-{a.current}")
                break
        for fn in env.aborts:
            try:
                fn()
                a.notes.append({"abort_restore": "API 로 원래 값을 되돌렸다(화면 되돌리기는 하지 못했다)"})
            except Exception as rexc:  # noqa: BLE001
                a.notes.append({"abort_restore_failed": str(rexc)[:200]})
    finally:
        env.close_all()
    if env.page_errors.get(key):
        a.notes.append({"pageerrors": env.page_errors[key][:20]})
    return a


# ── 실행 ─────────────────────────────────────────────────────────────────────
def boot(workdir: Path):
    """`screen_ledger.run_local` 과 같은 배선 — 임시 DB · 씨앗 · 서버 · 프로세스 안 워커 · 받는 쪽 SMTP."""
    from app.core.clock import SystemClock
    from app.jobs.worker import Worker
    from app.worker_main import _bootstrap, build_handlers
    from scripts.ui_qa import local_server as ls

    sink = HeloSink(workdir / "inbox").start()
    url = ls.create_database()
    stop = threading.Event()
    port = ls._free_port()
    base = f"http://127.0.0.1:{port}"
    settings = ls.build_settings(url, workdir).model_copy(update={"app_base_url": base})
    ls.seed(url, EMAIL, PASSWORD, settings)
    server, _ = ls.serve(settings, port)
    session_factory, wctx, worker_cache, _out = _bootstrap(settings, SystemClock())
    worker = Worker(session_factory, SystemClock(), build_handlers(), wctx, exclude_types=("chat_message",))

    def loop() -> None:
        while not stop.is_set():
            try:
                if not worker.run_once():
                    time.sleep(0.2)
            except Exception as exc:  # noqa: BLE001
                print("worker error:", exc)
                time.sleep(0.5)

    threading.Thread(target=loop, daemon=True).start()

    def shutdown() -> None:
        stop.set()
        server.should_exit = True
        sink.stop()
        ls.drop_database()

    return base, sink, url, session_factory, worker_cache, shutdown


def configure_mail(env: Env) -> int:
    """메일 발송을 이 프로세스의 받는 쪽으로 맞춘다(`screen_ledger.run_local` 과 같은 값) — 메일 알림 스위치가 서고 시험 메일이 닿는다."""
    st, body = env.api().send("PUT", "/api/admin/mail/settings", {
        "enabled": True, "host": "127.0.0.1", "port": env.sink.port, "security": "none", "from_address": "noreply@goodmit.co.kr",
        "from_name": "ClovirAssist", "username": "", "timeout_seconds": 10, "tls_verify": True, "ca_pem": "", "mode": "external"})
    if st != 200:
        raise RuntimeError(f"메일 설정을 맞추지 못했다: HTTP {st} {str(body)[:200]}")
    return st


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--areas", nargs="+", choices=AREAS, default=list(AREAS))
    ap.add_argument("--known-bad", choices=("drop", "wrong"), default="")
    ap.add_argument("--out", default=str(OUT), help="보고서 · PNG 를 둘 곳(기본 dist/ui-qa/r23-roundtrip)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.known_bad == "drop" and not set(args.areas) <= set(DROP_AREAS):
        print(f"--known-bad drop 은 응답 모양을 아는 영역({', '.join(DROP_AREAS)})에서만 돈다.", file=sys.stderr)
        return 2

    import logging

    from playwright.sync_api import sync_playwright

    # 접근 기록(요청마다 한 줄)이 진행 줄을 덮는다 — 경고 이상만 남긴다.
    logging.getLogger("app.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="clovir-roundtrip-"))
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    base, sink, url, session_factory, worker_cache, shutdown = boot(workdir)
    env = Env(base=base, sink=sink, db_url=url, out=out, session_factory=session_factory, worker_cache=worker_cache,
              known_bad=args.known_bad)
    results: dict[str, Area] = {}
    try:
        configure_mail(env)
        time.sleep(2)
        with sync_playwright() as pw:
            env.browser = pw.chromium.launch()
            env.storage = {role: login(env.browser, base, email, PASSWORD, False) for role, email in ROLE_ACCOUNTS.items()}
            for key in args.areas:
                results[key] = run_area(env, key)
            env.browser.close()
    finally:
        if env._engine is not None:
            env._engine.dispose()
        shutdown()
    areas = {k: a.as_dict() for k, a in results.items()}
    summary = {k: {"verdict": v["verdict"], "steps": {str(s["step"]): s["status"] for s in v["steps"]},
                   "unsaved": v["unsaved"].get("status"), "failure_path": v["failure_path"].get("status"),
                   "defects": len(v["defects"])} for k, v in areas.items()}
    report = {"label": "r23-roundtrip", "known_bad": args.known_bad or None, "base": base, "started_at": started,
              "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "bundle": build_fingerprint(),
              "summary": summary, "areas": areas, "mails_received": len(sink.messages())}
    name = f"report-known-bad-{args.known_bad}.json" if args.known_bad else "report.json"
    path = out / name
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False), flush=True)
    if args.known_bad:
        # 틀린 경우의 실행은 하네스가 FAIL 을 내야 성공이다 — 6(다시 읽기)이 FAIL 이어야 잡은 것이다.
        caught = {k: any(s["status"] == "FAIL" and s["step"] == 6 for s in v["steps"]) for k, v in areas.items()}
        print(f"KNOWN_BAD_{args.known_bad.upper()} {'CAUGHT' if all(caught.values()) else 'MISSED'} {caught} → {path}")
        return 0 if all(caught.values()) else 1
    ok = all(v["verdict"] == "PASS" for v in areas.values())
    print(f"SETTINGS_ROUNDTRIP_{'PASS' if ok else 'FAIL'} → {path}")
    return 0 if ok else 1


# ── 자기 시험 — 재는 도구가 맞는 견본에서 조용하고 틀린 견본에서 잡는가 ─────────────────
_TOAST_PAGE = """<!doctype html><html><body><main>본문</main><script>
function toast(cls, text) {
  const root = document.createElement('div'); root.className = 'MuiSnackbar-root';
  const a = document.createElement('div'); a.className = 'MuiAlert-root ' + cls;
  const m = document.createElement('div'); m.className = 'MuiAlert-message'; m.textContent = text;
  a.appendChild(m); root.appendChild(a); document.body.appendChild(root);
  setTimeout(() => root.remove(), 300);
}
</script></body></html>"""


_IN_VIEW_PAGE = """<!doctype html><html><body style="margin:0;height:3000px">
<div id="top" style="position:absolute;top:100px;height:40px;width:300px">화면 안</div>
<div id="covered" style="position:absolute;top:700px;height:40px;width:300px">발 밑</div>
<div id="below" style="position:absolute;top:2000px;height:40px;width:300px">화면 아래</div>
<div style="position:fixed;bottom:0;left:0;right:0;height:120px;background:#fff">붙박이 발</div>
</body></html>"""


def self_test() -> int:
    import shutil
    import smtplib
    from email.message import EmailMessage

    from playwright.sync_api import sync_playwright

    problems: list[str] = []
    # 1) 받는 쪽이 인사 이름을 연결마다 적는가 — 두 이름을 차례로 대고, 둘째가 첫째에 묶이지 않는가.
    tmp = Path(tempfile.mkdtemp(prefix="roundtrip-selftest-"))
    sink = HeloSink(tmp).start()
    try:
        for helo, sender in (("qa-helo-a.test", "a@example.test"), ("qa-helo-b.test", "b@example.test")):
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = sender, "to@example.test", "자기 시험"
            msg.set_content("본문")
            with smtplib.SMTP("127.0.0.1", sink.port, local_hostname=helo, timeout=5) as s:
                s.send_message(msg)
        got = [(m["helo"], m["header_from_address"]) for m in sink.received()]
        if got != [("qa-helo-a.test", "a@example.test"), ("qa-helo-b.test", "b@example.test")]:
            problems.append(f"인사 이름 · 보낸 사람 기록이 다르다: {got}")
    finally:
        sink.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    # 2) 토스트 기록 — 0.3초 만에 사라지는 토스트도 남고(성공 · 오류 구분), 안 띄우면 비어 있다.
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(_TOAST_PAGE)
        page.evaluate(TOAST_JS)
        mark = toast_mark(page)
        if wait_toast(page, mark, 1.0):
            problems.append("띄우지 않은 토스트가 기록됐다")
        page.evaluate("() => toast('MuiAlert-filledSuccess', '저장했습니다.')")
        page.wait_for_timeout(600)
        page.evaluate("() => toast('MuiAlert-filledError', '저장하지 못했습니다.')")
        page.wait_for_timeout(600)
        got = toasts_since(page, mark)
        if [(t["sev"], t["msg"]) for t in got] != [("success", "저장했습니다."), ("error", "저장하지 못했습니다.")]:
            problems.append(f"토스트 기록이 다르다: {got}")
        # 오류가 보이는 자리 — 화면 안(보임) · 화면 아래(안 보임) · 붙박이 발 밑(덮여 안 보임)
        page.set_viewport_size({"width": VP.width, "height": VP.height})
        page.set_content(_IN_VIEW_PAGE)
        seen = {k: in_view(page.locator(f"#{k}"))["in_view"] for k in ("top", "below", "covered")}
        if seen != {"top": True, "below": False, "covered": False}:
            problems.append(f"화면 안 판정이 다르다: {seen}")
        browser.close()
    # 3) 걸음 판정 — 다 맞으면 PASS, 하나라도 틀리면 FAIL, 잰 것 없이 미검증만 있으면 미검증, 걸음이 모자라면 영역 FAIL.
    a = Area("selftest", "자기 시험")
    a.step(1, "맞음", {"x": True})
    a.step(2, "틀림", {"x": True, "y": False})
    a.step(3, "못 잼", {}, unverified=["외부"])
    if [s["status"] for s in a.steps] != ["PASS", "FAIL", "미검증"] or a.as_dict()["verdict"] != "FAIL":
        problems.append(f"걸음 판정이 다르다: {[s['status'] for s in a.steps]}")
    b = Area("selftest", "자기 시험")
    for no in range(1, 9):
        b.step(no, "맞음", {"x": True})
    if b.as_dict()["verdict"] != "FAIL":
        problems.append("걸음이 여덟뿐인데 영역이 PASS 다")
    b.step(9, "맞음", {"x": True})
    b.unsaved, b.failure = {"status": "PASS"}, {"status": "PASS"}
    if b.as_dict()["verdict"] != "PASS":
        problems.append("아홉 걸음 · 두 길이 다 맞는데 영역이 PASS 가 아니다")
    if problems:
        for p in problems:
            print("  -", p)
        print("SETTINGS_ROUNDTRIP_SELFTEST_FAILED")
        return 1
    print("SETTINGS_ROUNDTRIP_SELFTEST_OK (인사 이름 2/2 · 토스트 성공/오류/없음 · 화면 안 판정 3/3 · 걸음 판정 5/5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
