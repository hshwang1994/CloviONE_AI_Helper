"""작업 공간 채움 모드 실브라우저 하네스 (F5 · D-531).

jsdom 에는 배치가 없어서 채움 모드의 약속은 실브라우저로만 잴 수 있다. 개발용 견본 화면(`#/kit/workspace` —
`frontend/src/screens/dev/WorkspaceDemo.jsx`)을 연다 — 서버를 부르지 않고 왼쪽 트리 200줄, 오른쪽 구성원 150명을 50명씩 받는다.

채움 뷰포트(폭 1200 이상 · 높이 600 이상)에서 재는 것:
  doc_no_scroll      문서가 굴러가지 않는다(`scrollHeight ≤ innerHeight + 1`)
  pane_bottom        두 판의 아래 끝 = 창 높이 − 본문 상자 아래 여백(±1.5), 내용이 적은 판도
  sticky_head        표 상자를 600px 굴린 뒤 열 이름 윗변 = 상자 윗변(±1)
  inner_paging       표 상자 끝까지 굴리면 다음 묶음이 판 안에서 받아진다(50 → 100), 문서는 그대로
  independent        한 판 끝에서 휠을 더 굴려도 다른 판 · 문서의 scrollTop 이 그대로다
  fixed_regions      판 머리 · 도구 줄 · 열 이름 · 판 발의 윗변이 굴린 뒤에도 그대로다
  banner_shrinks     본문 위에 배너(60px)를 끼우면 격자가 그만큼 줄고 판 아래 끝 · 문서 높이는 그대로다

흐름 뷰포트(1199×900 · 1366×599)에서는 채움이 꺼져 있는지(`data-workspace="flow"`, 앱 틀 main 에 채움 표식 없음)만 본다.

쓰는 법(로컬 서버를 띄워 붙는다):

    python -m scripts.ui_qa.local_capture --label workspace-e2e --harness workspace_e2e

결과는 `dist/ui-qa/workspace-e2e/report.json`, 실패가 하나라도 있으면 종료 코드 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "workspace-e2e"
HASH = "#/kit/workspace"
FILL_VIEWPORTS = (
    Viewport("1366x768", 1366, 768), Viewport("1600x900", 1600, 900),
    Viewport("1920x1080", 1920, 1080), Viewport("2560x1440", 2560, 1440),
)
FLOW_VIEWPORTS = (Viewport("1199x900", 1199, 900), Viewport("1366x599", 1366, 599))

GEOMETRY_JS = r"""
() => {
  const r = (el) => el ? el.getBoundingClientRect() : null;
  const ws = document.querySelector('[data-workspace]');
  const main = document.querySelector('#main-content');
  const content = document.querySelector('.c-content');
  const panes = [...document.querySelectorAll('[data-workspace-pane]')];
  const box = document.querySelector('[data-table-box="fill"]');
  const tree = document.querySelector('[data-pane-body="scroll"]');
  const grid = document.querySelector('[data-workspace-grid]');
  const fixed = {};
  const tablePane = box ? box.closest('[data-workspace-pane]') : null;
  if (tablePane) {
    const pick = (sel) => { const el = tablePane.querySelector(sel); return el ? Math.round(r(el).top * 10) / 10 : null; };
    fixed.head = pick('[data-pane-head]');
    fixed.toolbar = pick('[data-pane-toolbar]');
    fixed.thead = pick('thead th');
    fixed.foot = pick('[data-list-footer]');
  }
  return {
    mode: ws ? ws.getAttribute('data-workspace') : null,
    shellFill: !!(main && main.hasAttribute('data-shell-fill')),
    innerHeight: window.innerHeight,
    scrollHeight: document.scrollingElement.scrollHeight,
    docTop: document.scrollingElement.scrollTop,
    padBottom: content ? parseFloat(getComputedStyle(content).paddingBottom) || 0 : 0,
    paneBottoms: panes.map((p) => Math.round(r(p).bottom * 10) / 10),
    gridHeight: grid ? Math.round(r(grid).height * 10) / 10 : null,
    rows: box ? box.querySelectorAll('tbody tr').length : 0,
    boxTop: box ? Math.round(r(box).top * 10) / 10 : null,
    boxScroll: box ? box.scrollTop : null,
    treeScroll: tree ? tree.scrollTop : null,
    treeMax: tree ? tree.scrollHeight - tree.clientHeight : null,
    fixed,
  };
}
"""


def _near(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def check_fill(page, vp: Viewport) -> list[dict]:
    out: list[dict] = []

    def record(name, ok, detail):
        out.append({"viewport": vp.name, "check": name, "ok": bool(ok), "detail": detail})

    g = page.evaluate(GEOMETRY_JS)
    record("fill_mode", g["mode"] == "fill" and g["shellFill"], {"mode": g["mode"], "shellFill": g["shellFill"]})
    record("doc_no_scroll", g["scrollHeight"] <= g["innerHeight"] + 1, {"scrollHeight": g["scrollHeight"], "innerHeight": g["innerHeight"]})
    want_bottom = g["innerHeight"] - g["padBottom"]
    record("pane_bottom", len(g["paneBottoms"]) == 2 and all(_near(b, want_bottom, 1.5) for b in g["paneBottoms"]),
           {"paneBottoms": g["paneBottoms"], "want": want_bottom})
    before = g["fixed"]

    # 열 이름은 상자 위에 붙는다 — 상자를 600px 굴린다.
    page.evaluate("() => { const b = document.querySelector('[data-table-box=\"fill\"]'); b.scrollTop = 600; }")
    page.wait_for_timeout(250)
    g2 = page.evaluate(GEOMETRY_JS)
    record("sticky_head", g2["boxScroll"] and g2["boxScroll"] > 0 and _near(g2["fixed"].get("thead"), g2["boxTop"], 1.0),
           {"boxScroll": g2["boxScroll"], "thead": g2["fixed"].get("thead"), "boxTop": g2["boxTop"]})
    record("fixed_regions", all(_near(before.get(k), g2["fixed"].get(k), 0.6) for k in ("head", "toolbar", "foot")),
           {"before": before, "after": g2["fixed"]})

    # 판 안 무한 받기 — 상자 끝까지 굴리면 다음 묶음이 판 안에서 받아진다.
    rows_before = g2["rows"]
    page.evaluate("() => { const b = document.querySelector('[data-table-box=\"fill\"]'); b.scrollTop = b.scrollHeight; }")
    page.wait_for_timeout(900)
    g3 = page.evaluate(GEOMETRY_JS)
    record("inner_paging", g3["rows"] > rows_before and g3["docTop"] == 0,
           {"rowsBefore": rows_before, "rowsAfter": g3["rows"], "docTop": g3["docTop"]})

    # 독립 굴림 — 트리 판을 끝까지 굴리고 휠을 더 굴려도 표 상자 · 문서가 그대로다.
    page.evaluate("() => { const t = document.querySelector('[data-pane-body=\"scroll\"]'); t.scrollTop = t.scrollHeight; }")
    page.wait_for_timeout(150)
    g4 = page.evaluate(GEOMETRY_JS)
    tree_box = page.evaluate("() => { const t = document.querySelector('[data-pane-body=\"scroll\"]').getBoundingClientRect(); return [t.left + t.width / 2, t.top + t.height / 2]; }")
    page.mouse.move(tree_box[0], tree_box[1])
    page.mouse.wheel(0, 800)
    page.wait_for_timeout(400)
    g5 = page.evaluate(GEOMETRY_JS)
    record("independent", g5["treeScroll"] == g4["treeScroll"] and g5["boxScroll"] == g4["boxScroll"] and g5["docTop"] == 0,
           {"tree": [g4["treeScroll"], g5["treeScroll"]], "box": [g4["boxScroll"], g5["boxScroll"]], "docTop": g5["docTop"]})

    # 배너 — 본문 상자 위에 60px 를 끼우면 격자가 그만큼 줄고 판 아래 끝은 그대로다.
    page.evaluate("""() => {
      const main = document.querySelector('#main-content');
      const content = document.querySelector('.c-content');
      const b = document.createElement('div');
      b.id = 'e2e-banner'; b.style.cssText = 'height:60px;flex:0 0 auto;background:#fde68a';
      main.insertBefore(b, content);
    }""")
    page.wait_for_timeout(300)
    g6 = page.evaluate(GEOMETRY_JS)
    shrink = (g["gridHeight"] or 0) - (g6["gridHeight"] or 0)
    record("banner_shrinks", _near(shrink, 60, 1.5) and g6["scrollHeight"] <= g6["innerHeight"] + 1
           and all(_near(b, want_bottom, 1.5) for b in g6["paneBottoms"]),
           {"gridBefore": g["gridHeight"], "gridAfter": g6["gridHeight"], "paneBottoms": g6["paneBottoms"]})
    page.evaluate("() => { const b = document.getElementById('e2e-banner'); if (b) b.remove(); }")
    return out


def check_flow(page, vp: Viewport) -> list[dict]:
    g = page.evaluate(GEOMETRY_JS)
    return [{"viewport": vp.name, "check": "flow_mode", "ok": g["mode"] == "flow" and not g["shellFill"],
             "detail": {"mode": g["mode"], "shellFill": g["shellFill"]}}]


def main() -> int:
    ap = argparse.ArgumentParser(description="작업 공간 채움 모드 실브라우저 하네스 (D-531)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--selftest", action="store_true",
                    help="반례 — 흐름 모드 창(1199×900)에 채움 검사를 걸어 채움 · 문서 높이 · 판 아래 끝이 실패하는지 본다")
    args, _ = ap.parse_known_args()
    base = args.base_url.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.insecure:
        tls.apply_default_https_context()

    from playwright.sync_api import sync_playwright

    results: list[dict] = []
    if args.selftest:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            sess = ensure_session(browser, base, REPO_ROOT / "dist" / "ui-qa", insecure=args.insecure, log=print)
            vp = FLOW_VIEWPORTS[0]
            ctx = new_context(browser, storage_state=sess.storage_state, user_id=sess.user_id, theme="light",
                              viewport=vp, insecure=args.insecure)
            page = ctx.new_page()
            page.goto(base + "/" + HASH)
            page.wait_for_selector("[data-workspace]", timeout=20000)
            page.wait_for_timeout(600)
            bad = {r["check"]: r["ok"] for r in check_fill(page, vp)}
            ctx.close()
            browser.close()
        must_fail = ("fill_mode", "doc_no_scroll", "pane_bottom")
        missed = [k for k in must_fail if bad.get(k, True)]
        print("SELFTEST", json.dumps(bad, ensure_ascii=False))
        print("WORKSPACE_E2E_SELFTEST " + ("OK" if not missed else "FAILED (못 잡음: " + ", ".join(missed) + ")"))
        return 1 if missed else 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        sess = ensure_session(browser, base, REPO_ROOT / "dist" / "ui-qa", insecure=args.insecure, log=print)
        for vp, fill in [(v, True) for v in FILL_VIEWPORTS] + [(v, False) for v in FLOW_VIEWPORTS]:
            ctx = new_context(browser, storage_state=sess.storage_state, user_id=sess.user_id, theme="light",
                              viewport=vp, insecure=args.insecure)
            page = ctx.new_page()
            page.goto(base + "/" + HASH)
            page.wait_for_selector("[data-workspace]", timeout=20000)
            page.wait_for_timeout(600)
            results += check_fill(page, vp) if fill else check_flow(page, vp)
            page.screenshot(path=str(out / f"{vp.name}.png"))
            ctx.close()
        browser.close()

    failed = [r for r in results if not r["ok"]]
    (out / "report.json").write_text(json.dumps({"results": results, "failed": len(failed)}, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    for r in results:
        print(("PASS " if r["ok"] else "FAIL ") + f"{r['viewport']:>10} {r['check']:<16} " + json.dumps(r["detail"], ensure_ascii=False)[:220])
    print(f"WORKSPACE_E2E {'OK' if not failed else 'FAILED'} ({len(results) - len(failed)}/{len(results)})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
