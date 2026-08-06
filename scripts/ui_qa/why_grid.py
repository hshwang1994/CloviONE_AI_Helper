"""왜 격자/버튼/카드가 `None` 으로 나오는가 — 프로브 진단용(일회성 조사 도구).

계획서의 규칙: **측정값이 이상하면 화면을 고치기 전에 프로브를 먼저 의심한다.**
지금까지 프로브 오류를 6번 찾았고, 그때마다 "멀쩡한 것을 고칠 뻔" 했다.
이 스크립트는 후보 요소를 전부 나열하고 **어느 조건에서 탈락했는지**를 찍는다.
"""
from __future__ import annotations

import argparse
import json

from playwright.sync_api import sync_playwright

from scripts.ui_qa.auth import ensure_session
from scripts.ui_qa.baseline import FINGERPRINT_JS, ROUTE_MAP

DIAG = r"""
() => {
  const main = document.querySelector('#main-content') || document.body;
  const vis = (el) => { const r = el.getBoundingClientRect();
    return r.width > 4 && r.height > 4 && getComputedStyle(el).visibility !== 'hidden'; };
  const grids = [];
  for (const el of main.querySelectorAll('div, section, ul')) {
    const cs = getComputedStyle(el);
    if (cs.display !== 'grid') continue;
    const n = cs.gridTemplateColumns.split(' ').filter(Boolean).length;
    const w = el.getBoundingClientRect().width;
    const kids = [...el.children].filter(vis);
    const cardish = kids.filter((k) =>
      k.matches('.card, .MuiCard-root, .MuiPaper-root') ||
      k.querySelector('.card, .MuiCard-root, .MuiPaper-root')).length;
    const reasons = [];
    if (el.closest('table, thead, tbody, tr, .MuiTable-root, .toolbar, .MuiTableContainer-root')) reasons.push('표/툴바 안');
    if (n < 2) reasons.push('열<2'); if (n > 8) reasons.push('열>8');
    if (w < innerWidth * 0.5) reasons.push(`폭 ${Math.round(w)} < ${Math.round(innerWidth*0.5)}`);
    if (kids.length < n) reasons.push(`자식 ${kids.length} < 열 ${n}`);
    if (cardish < Math.min(n, 2)) reasons.push(`카드류 ${cardish} < ${Math.min(n,2)}`);
    grids.push({ cls: (el.className || '').toString().slice(0, 70), cols: cs.gridTemplateColumns.slice(0, 80),
                 n, w: Math.round(w), kids: kids.length, cardish, rejected: reasons });
  }
  const btns = [...main.querySelectorAll('button, .MuiButton-root, a.MuiButton-root')].filter(vis)
    .map((b) => ({ t: (b.textContent || '').trim().slice(0, 18), h: Math.round(b.getBoundingClientRect().height),
                   r: getComputedStyle(b).borderRadius, cls: (b.className || '').toString().slice(0, 60) }));
  const cards = [...main.querySelectorAll('.MuiCard-root, .MuiPaper-root, .card')].filter(vis)
    .map((c) => ({ r: getComputedStyle(c).borderRadius, sh: getComputedStyle(c).boxShadow.slice(0, 20),
                   cls: (c.className || '').toString().slice(0, 60) }));
  const empties = [...main.querySelectorAll('.k-empty')].filter(vis)
    .map((e) => (e.textContent || '').trim().slice(0, 60));
  const rows = main.querySelectorAll('tbody tr').length;
  return { empty: empties, tableRows: rows, grids, btns: btns.slice(0, 25), cards: cards.slice(0, 15) };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("routes")
    ap.add_argument("--base-url", default="http://127.0.0.1:8099")
    args = ap.parse_args()

    from pathlib import Path

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        session = ensure_session(browser, args.base_url,
                                 Path(__file__).resolve().parents[2] / "dist" / "ui-qa",
                                 log=lambda *a: None)
        ctx = browser.new_context(storage_state=session.storage_state,
                                  viewport={"width": 1920, "height": 1080}, locale="ko-KR")
        page = ctx.new_page()
        for spec in args.routes.split(","):
            # `route` 또는 `route=#/경로` — 상세 화면은 id 가 필요해 직접 준다.
            route, _, override = spec.partition("=")
            our = override or ROUTE_MAP[route]
            # 기준 대조와 **똑같이** 연다. 셸이 다르면 다른 화면을 재게 된다(이미 한 번 겪었다).
            shell = "/admin" if route.startswith("admin/") else "/"
            from scripts.ui_qa import capture as capture_mod

            page.goto(f"{args.base_url}{shell}{our}", wait_until="domcontentloaded", timeout=40000)
            page.reload(wait_until="domcontentloaded", timeout=40000)
            capture_mod._settle(page, settle_ms=600, timeout_ms=20000)
            print(f"\n{'='*70}\n{route}  →  {shell}{our}")
            # 진짜 프로브가 무엇을 보는지 **먼저** 찍는다 — 두 측정이 갈리면 그게 답이다.
            fp = page.evaluate(FINGERPRINT_JS)
            print("PROBE:", json.dumps(
                {k: fp.get(k) for k in ("shell", "grid", "cards", "controls")},
                ensure_ascii=False))
            print("DIAG :", json.dumps(page.evaluate(DIAG), ensure_ascii=False, indent=1))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
