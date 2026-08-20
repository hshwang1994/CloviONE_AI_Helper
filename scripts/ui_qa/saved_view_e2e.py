"""한 번도 쓰인 적 없는 기능 하나를 **끝까지** 돌려 본다 — 저장된 뷰(`saved_views` 0행).

`USE-01`이 말하는 12개 기능 중 부작용이 전혀 없는 것을 골랐다. 목적은 두 가지다.
① 이 기능이 실제로 동작하는가(`F` 축) ② 저장한 것이 서버에 남는가(`D` 축).
"""

from __future__ import annotations

import json
import ssl
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402

# 치는 곳은 `capture.DEFAULT_BASE_URL` 이 정한다 — 각자 문자열을 들면 이름이 바뀌는 날
# 이런 파일 14개가 옛 호스트에 남는다(W5 · F-W5D-129).
BASE = DEFAULT_BASE_URL
OUT = Path("dist/saved-view")


def main() -> int:
    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    log: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, BASE, OUT, insecure=True, log=print)
        ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id, theme="light",
                          viewport=Viewport("1920x1080", 1920, 1080), insecure=True)
        page = ctx.new_page()
        page.goto(f"{BASE}/#/workflows", wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(2500)

        # 1) 실제로 필터를 건다 — 보이는 입력만 고른다(숨은 입력이 먼저 잡히는 함정).
        typed = page.evaluate(
            """() => {
              const r = document.querySelector('#main-content');
              const inp = [...r.querySelectorAll('input')].find(i => {
                const b = i.getBoundingClientRect();
                return b.width > 100 && b.height > 10 && i.type !== 'hidden';
              });
              return inp ? {placeholder: inp.placeholder, cls: inp.className.slice(0,40)} : null;
            }"""
        )
        log["filter_input"] = typed
        if typed:
            page.locator("#main-content input").filter(visible=True).first.fill("notion")
            page.wait_for_timeout(1500)
        log["rows_after_filter"] = page.evaluate(
            "() => document.querySelectorAll('#main-content tbody tr').length")
        log["hash_after_filter"] = page.evaluate("() => location.hash")

        # 2) 저장된 뷰 메뉴
        page.click("button:has-text('저장된 뷰')")
        page.wait_for_timeout(1000)
        log["menu"] = page.evaluate(
            """() => { const m=document.querySelector('[role=menu]');
               return m ? {text:(m.innerText||'').trim().slice(0,200),
                           items:[...m.querySelectorAll('[role=menuitem],li,button')]
                                 .map(e=>(e.innerText||'').trim()).filter(Boolean)} : null; }"""
        )
        # 메뉴 항목을 role 로 정확히 집는다
        item = page.locator("[role=menu] [role=menuitem], [role=menu] li, [role=menu] button").filter(
            has_text="저장").first
        log["save_item_visible"] = item.is_visible()
        if item.is_visible():
            item.click()
            page.wait_for_timeout(1500)
        log["after_click"] = page.evaluate(
            """() => { const ds=[...document.querySelectorAll('[role=dialog]')]
                        .filter(d=>{const r=d.getBoundingClientRect(); return r.width>0&&r.left<innerWidth;});
               return ds.map(d=>({text:(d.innerText||'').trim().slice(0,220),
                     inputs:[...d.querySelectorAll('input')].map(i=>i.placeholder||i.name||i.type),
                     buttons:[...d.querySelectorAll('button')].map(x=>(x.innerText||'').trim()).filter(Boolean)})); }"""
        )
        page.screenshot(path=str(OUT / "01-save-dialog.png"))

        # 3) 이름을 넣고 저장
        name_input = page.locator("[role=dialog] input:visible").first
        if name_input.count() and name_input.is_visible():
            name_input.fill("QA 조사용 뷰")
            page.wait_for_timeout(300)
            for lbl in ("저장", "확인", "만들기", "추가"):
                btn = page.locator(f"[role=dialog] button:has-text('{lbl}')").first
                if btn.count() and btn.is_visible() and btn.is_enabled():
                    btn.click()
                    log["clicked"] = lbl
                    break
            page.wait_for_timeout(2500)

        # 4) 서버에 남았는가 — 화면이 아니라 API 로 확인한다
        # 2026-08-19: 세 경로 다 404 였다 — 기능이 없어서가 아니라 **이 목록이 틀렸기**
        # 때문이다. 실제 경로는 `ui/SavedViews.jsx` 가 부르는 `/api/me/views` 다.
        # 없는 경로를 물어 404 를 받아 오면 "서버에 안 남는다"로 잘못 읽힌다 — 검사가
        # 있는데 틀린 답을 주는 자리라 검사가 없는 것보다 나쁘다.
        for path in ("/api/me/views?screen_key=workflows", "/api/saved-views", "/api/views"):
            r = ctx.request.get(BASE + path, timeout=30_000)
            log[f"GET {path}"] = {"status": r.status, "body": (r.text() or "")[:250]}

        page.reload(wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(2500)
        page.click("button:has-text('저장된 뷰')")
        page.wait_for_timeout(1200)
        log["menu_after_reload"] = page.evaluate(
            """() => { const m=document.querySelector('[role=menu]');
               return m ? (m.innerText||'').trim().slice(0,220) : null; }"""
        )
        page.screenshot(path=str(OUT / "02-after-reload.png"))

        (OUT / "saved_view.json").write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        print(json.dumps(log, ensure_ascii=False, indent=2)[:3000])
        ctx.close()
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
