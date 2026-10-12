"""클로비 패널 실브라우저 검증 (D-557, 기능 개선 회차 P2).

패널은 모달이 아니다 — 열어도 본문이 밀리지도 잠기지도 않아야 하고, 입력창 한 줄은 컨트롤 높이(34)와 보내기 단추가 같은
세로 중심이어야 하며, 넓게 보기는 저장되고, Esc 로 닫히면 초점이 클로비 단추로 돌아온다. 네 폭(1920 · 1366 · 1024 · 390) ×
두 테마에서 잰다. 대화가 있는 모양(말풍선 좌우 · 얼굴)은 심어 둔 대화(`UI_QA_AI_READY=1`)를 패널에 복원해 찍는다.

    UI_QA_AI_READY=1 python -m scripts.ui_qa.local_server --seed      # 다른 창
    python -m scripts.ui_qa.assistant_panel_e2e --base-url http://127.0.0.1:<port> --out dist/ui-qa/p2-panel
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "p2-panel"
CLOVI = '[aria-label="클로비 AI 도우미 열기"]'
PANEL = 'aside[data-assistant-panel="open"]'
VIEWPORTS = [Viewport("1920x1080", 1920, 1080), Viewport("1366x768", 1366, 768),
             Viewport("1024x768", 1024, 768), Viewport("390x844", 390, 844)]

PROBE_JS = """() => {
  const m = document.querySelector('main');
  const r = m ? m.getBoundingClientRect() : null;
  const aside = document.querySelector('aside[data-assistant-panel="open"]');
  const a = aside ? aside.getBoundingClientRect() : null;
  const ta = aside ? aside.querySelector('textarea') : null;
  const send = aside ? aside.querySelector('[aria-label="질문 전송"]') : null;
  const tr = ta ? ta.getBoundingClientRect() : null;
  const sr = send ? send.getBoundingClientRect() : null;
  // textarea 는 브라우저 기본 overflow 가 auto 라 스크롤 칸이 아니다 — 목록 칸만 센다.
  const scrollers = aside ? [...aside.querySelectorAll('*')].filter((el) => {
    if (el.tagName === 'TEXTAREA') return false;
    const cs = getComputedStyle(el); return cs.overflowY === 'auto' || cs.overflowY === 'scroll'; }).length : 0;
  const backdrops = [...document.querySelectorAll('.MuiBackdrop-root')].filter((el) => getComputedStyle(el).visibility !== 'hidden' && el.offsetWidth > 0).length;
  const header = document.querySelector('header');
  const hb = header ? header.getBoundingClientRect().bottom : null;
  return {
    main: r ? [Math.round(r.left), Math.round(r.width)] : null,
    body_style: document.body.getAttribute('style') || '',
    body_overflow: getComputedStyle(document.body).overflow,
    doc_scroll_w: document.documentElement.scrollWidth, vw: window.innerWidth, vh: window.innerHeight,
    panel: a ? { left: Math.round(a.left), right: Math.round(a.right), top: Math.round(a.top), bottom: Math.round(a.bottom), width: Math.round(a.width) } : null,
    header_bottom: hb == null ? null : Math.round(hb),
    textarea: tr ? { h: +tr.height.toFixed(1), cy: +((tr.top + tr.bottom) / 2).toFixed(1) } : null,
    send: sr ? { h: +sr.height.toFixed(1), cy: +((sr.top + sr.bottom) / 2).toFixed(1) } : null,
    scrollers, backdrops,
    active: document.activeElement ? (document.activeElement.getAttribute('aria-label') || document.activeElement.tagName) : null,
  };
}"""


class Run:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.failed = 0

    def check(self, name: str, ok: bool, detail=None) -> bool:
        self.rows.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            self.failed += 1
        print(("PASS " if ok else "FAIL ") + name + (f" — {json.dumps(detail, ensure_ascii=False)[:300]}" if detail is not None else ""), flush=True)
        return ok


def _goto(page, base: str, hash_path: str) -> None:
    page.goto(base + "/#" + hash_path, wait_until="domcontentloaded")
    page.wait_for_selector("#main-content", timeout=30_000)
    page.wait_for_timeout(900)


def _restore_seeded_conversation(page, base: str) -> str | None:
    """심어 둔 대화 id 를 세션에 적어 패널이 그 대화를 복원하게 한다(useChat 의 CHAT_LAST_CONV_KEY)."""
    # 씨앗 대화는 제목으로 고른다 - 다른 하네스가 남긴 빈 대화가 첫 줄에 서면 「말풍선이 보인다」가 거짓 실패였다.
    cid = page.evaluate("""async () => {
      const r = await fetch('/api/conversations?limit=50', { credentials: 'same-origin' });
      if (!r.ok) return null;
      const j = await r.json();
      const items = j.items || [];
      const seeded = items.find((c) => c.title === '이번 주 마감 정리') || items[0];
      if (!seeded) return null;
      sessionStorage.setItem('chat.lastConversationId', seeded.id);
      return seeded.id;
    }""")
    return cid


def main() -> int:
    # Windows 콘솔(cp949)은 「—」 같은 글자를 못 적어 출력 자체가 죽는다 — 결과는 utf-8 로 낸다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="클로비 패널 실브라우저 검증 (D-557)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.insecure:
        tls.apply_default_https_context()

    from playwright.sync_api import sync_playwright

    run = Run()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        cache = REPO_ROOT / "dist" / "ui-qa"
        sess = ensure_session(browser, base, cache, insecure=args.insecure, log=print)

        for theme in ("light", "dark"):
            for vp in VIEWPORTS:
                tag = f"{theme}-{vp.name}"
                ctx = new_context(browser, storage_state=sess.storage_state, user_id=sess.user_id,
                                  theme=theme, viewport=vp, insecure=args.insecure)
                page = ctx.new_page()
                _goto(page, base, "/me")
                cid = _restore_seeded_conversation(page, base)
                _goto(page, base, "/me")
                before = page.evaluate(PROBE_JS)
                page.locator(CLOVI).first.click()
                page.wait_for_selector(PANEL, timeout=10_000)
                page.wait_for_timeout(1500)
                after = page.evaluate(PROBE_JS)
                run.check(f"[{tag}] 본문 자리 · body 스타일 · 가로 넘침이 그대로다",
                          before["main"] == after["main"] and before["body_style"] == after["body_style"]
                          and after["doc_scroll_w"] <= after["vw"] and after["body_overflow"] == before["body_overflow"],
                          {"before": before["main"], "after": after["main"], "body": after["body_style"], "scroll_w": after["doc_scroll_w"], "vw": after["vw"]})
                run.check(f"[{tag}] 백드롭이 없다", after["backdrops"] == 0, after["backdrops"])
                p = after["panel"]
                narrow = vp.width < 600
                run.check(f"[{tag}] 패널이 오른쪽 가장자리에 붙고 머리 아래에서 바닥까지다",
                          p and p["right"] == after["vw"] and abs(p["top"] - (after["header_bottom"] or 0)) <= 1 and p["bottom"] == after["vh"]
                          and (p["width"] == after["vw"] if narrow else 440 <= p["width"] <= 480), p)
                ta, sd = after["textarea"], after["send"]
                run.check(f"[{tag}] 입력 한 줄 34 · 보내기 단추와 세로 중심 일치",
                          ta and sd and abs(ta["h"] - 34) <= 1 and abs(ta["cy"] - sd["cy"]) <= 2, {"textarea": ta, "send": sd})
                run.check(f"[{tag}] 패널 안 스크롤 칸은 하나(메시지 목록)다", after["scrollers"] == 1, after["scrollers"])
                run.check(f"[{tag}] 열리면 초점이 입력 칸에 있다", after["active"] in ("클로비에게 질문", "TEXTAREA"), after["active"])
                page.screenshot(path=str(out / f"panel-{tag}.png"), full_page=False)
                if cid:
                    run.check(f"[{tag}] 심어 둔 대화의 말풍선이 보인다",
                              page.locator(f"{PANEL} .sr-only", has_text="도우미:").count() >= 1
                              or page.locator(f"{PANEL}").inner_text().find("도우미") >= 0, cid)
                    # 내 말풍선은 오른쪽, 도우미 말풍선은 왼쪽.
                    sides = page.evaluate("""() => {
                      const aside = document.querySelector('aside[data-assistant-panel="open"]');
                      const ar = aside.getBoundingClientRect();
                      const rows = [...aside.querySelectorAll('.sr-only')].filter((s) => /^(나|도우미): /.test(s.textContent));
                      return rows.map((s) => { const b = s.closest('div'); const r = b.getBoundingClientRect();
                        return { who: s.textContent.slice(0, 2), left: Math.round(r.left - ar.left), right: Math.round(ar.right - r.right) }; });
                    }""")
                    mine = [r for r in sides if r["who"] == "나:"]
                    theirs = [r for r in sides if r["who"] == "도우"]
                    # 긴 답은 말풍선이 기둥을 거의 다 쓰므로 「왼쪽에 붙어 시작하는가」로 본다(얼굴 34 + 사이 8 + 여백 16 ≈ 60).
                    # 내 말은 오른쪽 여백에 붙고 왼쪽에서 멀리 시작한다.
                    run.check(f"[{tag}] 내 말풍선은 오른쪽 · 도우미 말풍선은 왼쪽",
                              all(r["right"] <= 80 and r["left"] > r["right"] for r in mine)
                              and all(r["left"] <= 80 for r in theirs), sides[:4])
                if not narrow:
                    page.locator(f'{PANEL} [aria-label="넓게 보기"]').click()
                    page.wait_for_timeout(500)
                    wide = page.evaluate(PROBE_JS)
                    run.check(f"[{tag}] 넓게 보기는 폭이 커지고 본문은 그대로다",
                              wide["panel"] and wide["panel"]["width"] > p["width"] + 150 and wide["main"] == before["main"], wide["panel"])
                    page.screenshot(path=str(out / f"panel-{tag}-wide.png"), full_page=False)
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_selector("#main-content", timeout=30_000)
                    page.wait_for_timeout(900)
                    page.locator(CLOVI).first.click()
                    page.wait_for_selector(PANEL, timeout=10_000)
                    page.wait_for_timeout(800)
                    again = page.evaluate(PROBE_JS)
                    run.check(f"[{tag}] 넓게 보기가 새로고침 뒤에도 남는다", again["panel"] and again["panel"]["width"] > p["width"] + 150, again["panel"])
                    page.locator(f'{PANEL} [aria-label="좁게 보기"]').click()
                    page.wait_for_timeout(300)
                page.keyboard.press("Escape")
                page.wait_for_timeout(600)
                closed = page.evaluate(PROBE_JS)
                run.check(f"[{tag}] Esc 로 닫히고 초점이 클로비 단추로 돌아온다",
                          closed["panel"] is None and closed["active"] == "클로비 AI 도우미 열기", closed["active"])
                ctx.close()
        browser.close()

    (out / "result.json").write_text(json.dumps({"rows": run.rows, "failed": run.failed}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ASSISTANT_PANEL_E2E {'OK' if not run.failed else 'FAILED'} failed={run.failed} → {out / 'result.json'}", flush=True)
    return 0 if not run.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
