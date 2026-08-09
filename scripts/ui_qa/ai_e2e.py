"""AI 도우미 End-to-End 실사용 조사 (조사 전용 — 제품 코드가 아니다).

**왜 별도 스크립트인가.** `scripts/ui_qa/run.py` 는 화면을 *찍는다*. 그것으로는
"열린다"까지만 알 수 있고 사용자가 지적한 것 — 대화 생성 · 연속 대화 · History ·
Context · Streaming · 새로고침 · 페이지 이동 후 상태 유지 · 오류 · 재시도 — 은
**실제로 대화를 해 봐야** 알 수 있다.

관찰만 한다. 어떤 것도 고치지 않고, 대화와 그 부산물만 남긴다.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import Viewport, new_context  # noqa: E402

SETTLE_MS = 1200
REPLY_TIMEOUT_S = 200


def log(msg: str) -> None:
    print(msg, flush=True)


def _api(context, base_url: str, path: str, *, method: str = "get", data=None):
    """앱의 실제 API 를 세션 쿠키로 호출한다(화면이 부르는 것과 같은 것)."""
    url = base_url.rstrip("/") + path
    try:
        if method == "get":
            res = context.request.get(url, timeout=60_000)
        else:
            res = context.request.post(url, data=data or {}, timeout=120_000)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {exc}"}
    body: object
    try:
        body = res.json()
    except Exception:  # noqa: BLE001
        body = (res.text() or "")[:400]
    return {"__status__": res.status, "body": body}


def _bubbles(page) -> list[dict]:
    """화면에 실제로 그려진 말풍선. DOM 을 믿되 구조에 기대지 않는다."""
    return page.evaluate(
        """() => {
        const out = [];
        const root = document.querySelector('#main-content') || document.body;
        root.querySelectorAll('[data-role], [class*="bubble"], li, article').forEach(el => {
          const t = (el.innerText || '').trim();
          if (!t || t.length < 2) return;
          if (out.some(o => o.text === t)) return;
          out.push({ tag: el.tagName.toLowerCase(),
                     role: el.getAttribute('data-role') || '',
                     len: t.length, text: t.slice(0, 300) });
        });
        return out.slice(-40);
      }"""
    )


def _composer(page):
    for sel in ("#main-content textarea", "textarea",
                "#main-content input[type=text]", "[contenteditable=true]"):
        el = page.query_selector(sel)
        if el and el.is_visible():
            return el, sel
    return None, ""


def _send(page, text: str) -> dict:
    """실제 컴포저에 입력하고 보낸다. 무엇으로 보냈는지 함께 돌려준다."""
    el, sel = _composer(page)
    if el is None:
        return {"ok": False, "why": "컴포저를 찾지 못함"}
    el.click()
    el.fill(text)
    page.wait_for_timeout(200)
    before = len(_bubbles(page))

    # Enter 로 보내지는가(제품이 주장하는 조작)를 먼저 본다.
    el.press("Enter")
    page.wait_for_timeout(700)
    if len(_bubbles(page)) > before:
        return {"ok": True, "via": "Enter", "selector": sel}

    for label in ("보내기", "전송", "send"):
        btn = page.query_selector(f"button:has-text('{label}')")
        if btn and btn.is_visible() and btn.is_enabled():
            btn.click()
            page.wait_for_timeout(700)
            return {"ok": True, "via": f"버튼:{label}", "selector": sel}
    return {"ok": False, "why": "Enter 로도 버튼으로도 보내지지 않음", "selector": sel}


def _await_reply(page, *, baseline: int, timeout_s: int = REPLY_TIMEOUT_S) -> dict:
    """답이 올 때까지 기다리며 **중간 상태를 표본으로 남긴다** — 스트리밍 여부를 보려면
    최종 결과만 봐서는 안 된다."""
    start = time.time()
    samples: list[dict] = []
    last_len = 0
    while time.time() - start < timeout_s:
        page.wait_for_timeout(1000)
        bubbles = _bubbles(page)
        tail = bubbles[-1]["text"] if bubbles else ""
        cur = len("".join(b["text"] for b in bubbles))
        samples.append({"t": round(time.time() - start, 1),
                        "n": len(bubbles), "chars": cur, "tail": tail[:90]})
        if len(bubbles) > baseline and cur == last_len and cur > 0:
            return {"arrived": True, "seconds": round(time.time() - start, 1),
                    "samples": samples}
        last_len = cur
    return {"arrived": False, "seconds": round(time.time() - start, 1), "samples": samples}


def run(base_url: str, out_dir: Path, *, insecure: bool, headed: bool) -> int:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"base_url": base_url, "steps": []}

    def step(name: str, **kw):
        entry = {"step": name, **kw}
        report["steps"].append(entry)
        log(f"[{name}] " + json.dumps(kw, ensure_ascii=False)[:600])

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        session = ensure_session(browser, base_url, out_dir, insecure=insecure, log=log)
        step("login", email=session.email, role=session.role, user_id=session.user_id)

        context = new_context(browser, storage_state=session.storage_state,
                              user_id=session.user_id, theme="light",
                              viewport=Viewport("1600x1000", 1600, 1000),
                              insecure=insecure)
        page = context.new_page()
        console: list[str] = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text[:200]}")
                if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: console.append(f"pageerror: {str(e)[:200]}"))

        # ── 1. 대화 목록 API 초기 상태 ──────────────────────────────────
        step("conversations.before", **_api(context, base_url, "/api/conversations"))

        # ── 2. /chat 진입 ──────────────────────────────────────────────
        page.goto(f"{base_url}/#/chat", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(SETTLE_MS * 2)
        page.screenshot(path=str(out_dir / "01-chat-empty.png"), full_page=True)
        el, sel = _composer(page)
        step("chat.open", composer=sel or "없음", bubbles=len(_bubbles(page)))

        # ── 3. 첫 메시지 ────────────────────────────────────────────────
        q1 = "내 티켓 중에서 아직 안 끝난 게 몇 건이야?"
        base = len(_bubbles(page))
        step("send.1", question=q1, **_send(page, q1))
        r1 = _await_reply(page, baseline=base)
        page.screenshot(path=str(out_dir / "02-reply-1.png"), full_page=True)
        step("reply.1", arrived=r1["arrived"], seconds=r1["seconds"],
             growth=[s["chars"] for s in r1["samples"]],
             tail=(r1["samples"][-1]["tail"] if r1["samples"] else ""))

        # ── 4. 문맥이 이어지는가 — 앞 답을 가리키는 후속 질문 ──────────
        q2 = "방금 말한 것 중에 제일 오래된 건 뭐야?"
        base = len(_bubbles(page))
        step("send.2", question=q2, **_send(page, q2))
        r2 = _await_reply(page, baseline=base)
        page.screenshot(path=str(out_dir / "03-reply-2.png"), full_page=True)
        step("reply.2", arrived=r2["arrived"], seconds=r2["seconds"],
             tail=(r2["samples"][-1]["tail"] if r2["samples"] else ""))

        # ── 5. 마크다운·코드블록을 요구한다 ────────────────────────────
        q3 = "표와 코드블록을 써서 예시를 하나 보여줘. 파이썬 코드로."
        base = len(_bubbles(page))
        step("send.3", question=q3, **_send(page, q3))
        r3 = _await_reply(page, baseline=base)
        page.screenshot(path=str(out_dir / "04-reply-markdown.png"), full_page=True)
        md = page.evaluate(
            """() => {
              const root = document.querySelector('#main-content') || document.body;
              return { pre: root.querySelectorAll('pre').length,
                       code: root.querySelectorAll('code').length,
                       table: root.querySelectorAll('table').length,
                       li: root.querySelectorAll('li').length };
            }"""
        )
        step("reply.3.markdown", arrived=r3["arrived"], seconds=r3["seconds"], dom=md,
             tail=(r3["samples"][-1]["tail"] if r3["samples"] else ""))

        # ── 6. 대화가 서버에 남았는가 ──────────────────────────────────
        after = _api(context, base_url, "/api/conversations")
        step("conversations.after", **after)

        # ── 7. 새로고침 후에도 대화가 보이는가 ─────────────────────────
        page.reload(wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(SETTLE_MS * 2)
        page.screenshot(path=str(out_dir / "05-after-reload.png"), full_page=True)
        step("reload", bubbles=len(_bubbles(page)),
             sample=[b["text"][:70] for b in _bubbles(page)[-4:]])

        # ── 8. 다른 화면에 갔다 돌아오면 ───────────────────────────────
        page.goto(f"{base_url}/#/my-tickets", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(SETTLE_MS)
        page.goto(f"{base_url}/#/chat", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(SETTLE_MS * 2)
        page.screenshot(path=str(out_dir / "06-after-nav.png"), full_page=True)
        step("navigate.away.back", bubbles=len(_bubbles(page)),
             sample=[b["text"][:70] for b in _bubbles(page)[-4:]])

        step("console", entries=console[:25], count=len(console))
        (out_dir / "ai_e2e.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"\n보고서: {out_dir / 'ai_e2e.json'}")
        context.close()
        browser.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://clovirone-ai.gooddi.lab")
    ap.add_argument("--out-dir", default="dist/ai-e2e")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args(argv)
    if args.insecure:
        ssl._create_default_https_context = ssl._create_unverified_context
    return run(args.base_url, Path(args.out_dir), insecure=args.insecure, headed=args.headed)


if __name__ == "__main__":
    raise SystemExit(main())
