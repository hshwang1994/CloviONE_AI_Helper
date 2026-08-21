"""검색 3중 구조를 **같은 질의**로 나란히 재 본다.

사용자 지시: "검색을 다시 설계하되(콘텐츠 검색 / 빠른 이동 / 커맨드 팔레트) 실제 결과와
이동까지 검증해라." 설계 이전에 **지금 셋이 실제로 무엇을 돌려주는지**부터 재야 한다.

세 표면: ① 상단바 검색창 ② `/search` 화면 ③ Ctrl+K 커맨드 팔레트.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402

# 치는 곳은 `capture.DEFAULT_BASE_URL` 이 정한다 — 각자 문자열을 들면 이름이 바뀌는 날
# 이런 파일 14개가 옛 호스트에 남는다(W5 · F-W5D-129).
BASE = DEFAULT_BASE_URL
OUT = Path("dist/search-surfaces")

QUERIES = ["티켓", "notion", "회의", "zzzz없는말"]

READ = """() => {
  const pick = (root) => [...root.querySelectorAll('[role=option],[role=menuitem],li,tr,a')]
      .map(e => (e.innerText||'').trim().replace(/\\s+/g,' '))
      .filter(t => t && t.length > 1 && t.length < 120);
  const pop = document.querySelector('[role=listbox],[role=menu],.MuiPopover-paper,.MuiAutocomplete-popper');
  const main = document.querySelector('#main-content');
  return { popup: pop ? [...new Set(pick(pop))].slice(0,14) : null,
           mainText: main ? (main.innerText||'').trim().replace(/\\s+/g,' ').slice(0,260) : null,
           mainCount: main ? main.querySelectorAll('tbody tr').length : 0,
           hash: location.hash };
}"""


def top_bar(page, q: str) -> dict:
    page.goto(f"{BASE}/#/me", wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(1800)
    box = page.locator("header input, header [role=combobox]").first
    if not box.count():
        return {"error": "상단바 검색 입력 없음"}
    box.click()
    box.fill(q)
    page.wait_for_timeout(2200)
    out = page.evaluate(READ)
    return {"popup": out["popup"], "hash": out["hash"]}


def search_page(page, q: str) -> dict:
    page.goto(f"{BASE}/#/search?q={q}", wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(2500)
    out = page.evaluate(READ)
    return {"hash": out["hash"], "rows": out["mainCount"], "text": out["mainText"]}


def palette(page, q: str) -> dict:
    page.goto(f"{BASE}/#/me", wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(1800)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(900)
    page.keyboard.type(q, delay=25)
    page.wait_for_timeout(2200)
    out = page.evaluate(READ)
    page.keyboard.press("Escape")
    return {"popup": out["popup"], "hash": out["hash"]}


def main() -> int:
    insecure = tls.apply_default_https_context()
    print(tls.describe())
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, BASE, OUT, insecure=insecure, log=print)
        ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id, theme="light",
                          viewport=Viewport("1920x1080", 1920, 1080), insecure=insecure)
        page = ctx.new_page()
        for q in QUERIES:
            report[q] = {}
            for name, fn in (("상단바", top_bar), ("/search", search_page), ("Ctrl+K", palette)):
                try:
                    report[q][name] = fn(page, q)
                except Exception as exc:  # noqa: BLE001
                    report[q][name] = {"error": f"{type(exc).__name__}: {exc}"[:160]}
            print(f"— «{q}» 완료", flush=True)
        # API 도 직접 본다 — 화면이 무엇을 버리는지 보려면 원본이 필요하다
        for q in QUERIES:
            r = ctx.request.get(f"{BASE}/api/search?q={q}", timeout=30_000)
            body = (r.text() or "")[:400]
            report[q]["API"] = {"status": r.status, "body": body}
        ctx.close()
        b.close()

    (OUT / "search.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:5000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
