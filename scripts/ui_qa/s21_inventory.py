"""S21 이 감사할 화면들의 **접근 가능한 이름 목록**을 덤프한다 (W14).

Flow 표를 쓸 때 선택자를 소스에서 짐작하면 두 가지가 일어난다. 화면이 그 이름을 안 쓰면
Flow 는 「누를 것이 없다」로 죽고, 그 죽음이 **제품 결함처럼 보인다**. S18 이 같은 이유로
`--inventory` 를 먼저 돌렸다 — 여기서는 그 범위를 S21 의 72 화면으로 넓힌다.

같이 드러나는 것이 하나 더 있다: **화면이 자기 컨트롤에 이름을 안 준 자리**.

    python -m scripts.ui_qa.s21_inventory --base-url http://127.0.0.1:8099
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, new_context  # noqa: E402
from scripts.ui_qa.pilot_e2e import Backend, Recorder, Runner, VIEWPORT  # noqa: E402
from scripts.ui_qa import s21_surfaces  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "s21-inventory"

INVENTORY_JS = """
() => {
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim().slice(0, 70);
  const named = (el) => clean(el.getAttribute('aria-label') || el.innerText || el.value || '');
  const pick = (sel) => Array.from(document.querySelectorAll(sel)).map(named).filter(Boolean);
  const table = document.querySelector('#main-content table');
  return {
    heading: clean(document.querySelector('#main-content h1, #main-content h2')?.innerText),
    text: clean(document.querySelector('#main-content')?.innerText).slice(0, 300),
    buttons: Array.from(new Set(pick('#main-content button'))),
    links: Array.from(new Set(pick('#main-content a'))).slice(0, 30),
    inputs: Array.from(document.querySelectorAll(
        '#main-content input, #main-content textarea')).map(
        el => clean(el.getAttribute('aria-label') || el.getAttribute('placeholder')
                    || el.name || el.type)).filter(Boolean),
    comboboxes: Array.from(document.querySelectorAll('#main-content [role="combobox"]')).map(
        el => clean(el.getAttribute('aria-label') || el.innerText)),
    tabs: pick('#main-content [role="tab"]'),
    switches: Array.from(document.querySelectorAll(
        '#main-content [role="switch"], #main-content input[type=checkbox]')).map(named),
    columns: table ? Array.from(table.querySelectorAll('thead th')).map(
        th => clean(th.innerText)) : [],
    rows: table ? table.querySelectorAll('tbody tr').length : 0,
    sortable: table ? Array.from(table.querySelectorAll('thead th button')).map(
        b => clean(b.innerText)) : [],
    empty: clean(document.querySelector('#main-content [data-empty], #main-content .c-empty')
                 ?.innerText),
    errors: Array.from(document.querySelectorAll('#main-content [role="alert"]')).map(named),
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="S21 화면 이름 목록 덤프 (W14)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--surfaces", nargs="*", default=None)
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    wanted = args.surfaces or list(s21_surfaces.SURFACES)
    result: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            session = ensure_session(browser, args.base_url, REPO_ROOT / "dist" / "ui-qa",
                                     insecure=args.insecure)
            context = new_context(browser, storage_state=session.storage_state,
                                  user_id=session.user_id, theme="light",
                                  viewport=VIEWPORT, insecure=args.insecure)
            page = context.new_page()
            rec = Recorder(page)
            spec = context.request.get(args.base_url.rstrip("/") + "/openapi.json",
                                       timeout=30_000).json()
            runner = Runner(page, rec, Backend(spec), args.base_url.rstrip("/"), out,
                            browser=browser, insecure=args.insecure)
            ids = s21_surfaces.resolve_ids(runner.api_get)
            result["_ids"] = ids
            for sid in wanted:
                target = s21_surfaces.hash_for(sid, ids)
                if target is None:
                    result[sid] = {"error": "주소를 못 만들었다 (id 미해결)"}
                    print("[SKIP] %-36s 주소 미해결" % sid, flush=True)
                    continue
                hash_path, shell = target
                try:
                    if shell == "":
                        page.goto(args.base_url.rstrip("/") + hash_path,
                                  wait_until="domcontentloaded")
                        runner.settle(1200)
                    else:
                        runner.goto(hash_path, shell=shell)
                    entry = page.evaluate(INVENTORY_JS)
                    entry["hash"] = runner.hash_of()
                    entry["calls"] = sorted({
                        "%s %s" % (c["method"], c["path"]) for c in rec.calls})[:12]
                    rec.reset()
                    result[sid] = entry
                    print("[OK  ] %-36s %s · 버튼 %d · 열 %d · %d행"
                          % (sid, (entry.get("heading") or "")[:26],
                             len(entry.get("buttons") or []), len(entry.get("columns") or []),
                             entry.get("rows") or 0), flush=True)
                except Exception as exc:  # noqa: BLE001
                    result[sid] = {"error": "%s: %s" % (type(exc).__name__, str(exc)[:180])}
                    print("[ERR ] %-36s %s" % (sid, str(exc)[:80]), flush=True)
            context.close()
        finally:
            browser.close()

    (out / "inventory.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print("\ninventory.json: %s" % (out / "inventory.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
