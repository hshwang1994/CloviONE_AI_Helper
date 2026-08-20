"""**긴 데이터 · 많은 데이터 · 이상한 문자**를 주입해 레이아웃을 시험한다.

사용자 지시의 미검증 항목이다. 지금 서버 데이터는 얌전해서(제목이 짧고, 목록이 작고, 한글·영문뿐)
아무리 찍어도 이 축은 안 드러난다. 그래서 응답을 **가로채서 부풀린다** — 서버는 건드리지 않는다.

주입하는 것:
  long    : 긴 한글 문장(줄바꿈 기회 있음) · 긴 URL(줄바꿈 기회 **없음**, 표를 가장 잘 깨뜨린다)
  many    : 목록 항목을 200개로 복제 (페이지네이션·가상화·성능)
  weird   : RTL(히브리) · 이모지 · 결합 문자 · 제로폭 공백 · `<script>` 문자열(이스케이프 확인)

보는 것: 가로 넘침 · 잘림(overflow:hidden) · 세로 붕괴 · 렌더 시간 · JS 예외.
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
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa.routes import BY_ID  # noqa: E402

# 치는 곳은 `capture.DEFAULT_BASE_URL` 이 정한다 — 각자 문자열을 들면 이름이 바뀌는 날
# 이런 파일 14개가 옛 호스트에 남는다(W5 · F-W5D-129).
BASE = DEFAULT_BASE_URL
OUT = Path("dist/hostile-data")

LONG_KO = ("사내 업무 자동화 플랫폼의 티켓 상태 전이 규칙을 재정의하고 담당자 배정 로직을 "
           "부서 범위 관리자 권한과 함께 재검토하는 매우 긴 제목의 작업 항목 " * 2)
LONG_URL = "https://internal.example.co.kr/very/deep/path/" + "segment-without-any-break-opportunity/" * 6
WEIRD = ("עברית RTL 🇰🇷 ""👨‍👩‍👧 é́ ""zero​width <script>alert(1)</script> x")

PROBE = """() => {
  const root = document.querySelector('#main-content') || document.body;
  const vw = innerWidth;
  const over = [], clipped = [], collapsed = [];
  root.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    if (r.right > vw + 2) {
      const t = (el.innerText || '').trim().slice(0, 30);
      if (t) over.push({ tag: el.tagName.toLowerCase(), right: Math.round(r.right), text: t });
    }
    const st = getComputedStyle(el);
    if (st.overflow === 'hidden' || st.overflowX === 'hidden') {
      if (el.scrollWidth > el.clientWidth + 4) {
        const t = (el.innerText || '').trim().slice(0, 30);
        if (t) clipped.push({ tag: el.tagName.toLowerCase(),
                              over: el.scrollWidth - el.clientWidth, text: t });
      }
    }
    // 세로 붕괴: 폭이 아주 좁은데 높이가 크고 글자가 있다
    if (r.width < 60 && r.height > 90) {
      const own = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim());
      if (own.length) collapsed.push({ tag: el.tagName.toLowerCase(),
        w: Math.round(r.width), h: Math.round(r.height),
        text: own.map(n => n.textContent.trim()).join('').slice(0, 24) });
    }
  });
  const dedupe = (a) => { const s = new Set(), o = []; for (const x of a) {
      const k = x.tag + '|' + (x.text || ''); if (!s.has(k)) { s.add(k); o.push(x); } } return o; };
  return { overflow: dedupe(over).slice(0, 8), clipped: dedupe(clipped).slice(0, 8),
           collapsed: dedupe(collapsed).slice(0, 8),
           bodyScrollW: document.documentElement.scrollWidth, vw,
           rows: root.querySelectorAll('tbody tr').length };
}"""


def transform(payload, mode: str):
    """리스트 응답의 문자열 값을 갈아 끼운다. 구조는 그대로 둔다."""
    def swap(v):
        if not isinstance(v, str) or len(v) < 3:
            return v
        if v.startswith(("http://", "https://")):
            return LONG_URL if mode == "long" else v
        if mode == "long":
            return LONG_KO
        if mode == "weird":
            return WEIRD
        return v

    def walk(o):
        if isinstance(o, dict):
            return {k: (walk(v) if isinstance(v, (dict, list)) else swap(v))
                    for k, v in o.items()}
        if isinstance(o, list):
            return [walk(x) for x in o]
        return o

    out = walk(payload)
    if mode == "many" and isinstance(out, dict):
        for key in ("items", "data", "results", "rows"):
            if isinstance(out.get(key), list) and out[key]:
                base = out[key]
                grown = []
                while len(grown) < 200:
                    grown.extend(json.loads(json.dumps(base)))
                out[key] = grown[:200]
                if isinstance(out.get("total"), int):
                    out["total"] = len(out[key])
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", nargs="*",
                    default=["admin_users", "user_my-tickets", "user_projects", "admin_jobs"])
    ap.add_argument("--modes", nargs="*", default=["long", "many", "weird"])
    ap.add_argument("--auth-dir", default="dist/ui-qa-admin-2")
    args = ap.parse_args()

    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, BASE, Path(args.auth_dir), insecure=True, log=print)
        for mode in args.modes:
            for rid in args.routes:
                route = BY_ID.get(rid)
                if route is None:
                    continue
                ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id,
                                  theme="light", viewport=Viewport("1600x1000", 1600, 1000),
                                  insecure=True)
                page = ctx.new_page()
                errs: list[str] = []
                page.on("pageerror", lambda e: errs.append(str(e)[:120]))

                def handler(r):
                    try:
                        resp = r.fetch()
                        body = resp.json()
                    except Exception:  # noqa: BLE001
                        return r.continue_()
                    try:
                        return r.fulfill(response=resp, json=transform(body, mode))
                    except Exception:  # noqa: BLE001
                        return r.continue_()

                page.goto(f"{BASE}{route.shell}", wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(600)
                page.route("**/api/**", handler)
                t0 = time.time()
                page.goto(f"{BASE}{route.shell}#{route.hash_path}",
                          wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_timeout(3000)
                elapsed = round(time.time() - t0, 1)
                got = page.evaluate(PROBE)
                got.update({"seconds": elapsed, "page_errors": errs[:3]})
                report[f"{mode}/{rid}"] = got
                print(f"{mode:<7}{rid:<20}행={got['rows']:<4}넘침={len(got['overflow'])} "
                      f"잘림={len(got['clipped'])} 세로붕괴={len(got['collapsed'])} "
                      f"문서폭={got['bodyScrollW']}/{got['vw']} {elapsed}s err={len(errs)}",
                      flush=True)
                page.screenshot(path=str(OUT / f"{mode}-{rid}.png"))
                ctx.close()
        b.close()

    (OUT / "hostile_data.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
