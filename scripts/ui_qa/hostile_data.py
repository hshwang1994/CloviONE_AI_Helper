"""**긴 데이터 · 많은 데이터 · 이상한 문자**를 주입해 레이아웃을 시험한다.

사용자 지시의 미검증 항목이다. 지금 서버 데이터는 얌전해서(제목이 짧고, 목록이 작고, 한글·영문뿐)
아무리 찍어도 이 축은 안 드러난다. 그래서 응답을 **가로채서 부풀린다** — 서버는 건드리지 않는다.

주입하는 것:
  long    : 긴 한글 문장(줄바꿈 기회 있음) · 긴 URL(줄바꿈 기회 **없음**, 표를 가장 잘 깨뜨린다)
  many    : 목록 항목을 200개로 복제 (페이지네이션·가상화·성능)
  weird   : RTL(히브리) · 이모지 · 결합 문자 · 제로폭 공백 · `<script>` 문자열(이스케이프 확인)

보는 것: 가로 넘침 · 잘림(overflow:hidden) · 세로 붕괴 · 렌더 시간 · JS 예외.

**넘침은 화면 밖으로 실제로 보이는 것만 센다.** 요소가 뷰포트 오른쪽을 넘어도 그 요소를 품은 조상이 가로로
굴리거나 자르고(`overflow-x` 가 auto · scroll · hidden · clip) 그 조상이 뷰포트 안에 서 있으면, 넘친 부분은 그 상자
안에서 굴러가거나 잘린다 — 1200 폭의 넓은 표가 제 상자 안에서 가로로 굴러가는 것이 그렇다(핸드오프 ACCEPTANCE E5).
그런 요소는 `contained` 로 따로 센다. 페이지 전체의 가로 넘침은 `문서폭`(scrollWidth 대 뷰포트)이 말한다.
`--selftest` 가 맞는 견본(굴리는 상자 안의 긴 줄)과 틀린 견본(보이는 상자 밖으로 나간 긴 줄)으로 이 판정을 먼저 본다.
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
from scripts.ui_qa.routes import BY_ID  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402

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
  const over = [], clipped = [], collapsed = [], truncated = [], contained = [];
  /* 넘친 요소를 품고 가로로 굴리거나 자르는 조상이 뷰포트 안에 서 있는가 — 그러면 넘친 부분은 보이지 않는다. */
  /* 자르는 조상이 여럿이면 끝까지 올라간다 — 표 칸(`overflow:hidden`)은 가로로 굴러가는 표 안에서 스스로 뷰포트 밖에
     서 있을 수 있고, 그 칸을 품은 표 상자가 뷰포트 안에서 굴린다(1366 · 1200 의 내 티켓 표). */
  const boxedIn = (el) => {
    for (let a = el.parentElement; a && a !== document.documentElement; a = a.parentElement) {
      const ox = getComputedStyle(a).overflowX;
      if ((ox === 'auto' || ox === 'scroll' || ox === 'hidden' || ox === 'clip') && a.getBoundingClientRect().right <= vw + 2) {
        return true;
      }
    }
    return false;
  };
  root.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    if (r.right > vw + 2) {
      const t = (el.innerText || '').trim().slice(0, 30);
      if (t) (boxedIn(el) ? contained : over).push({ tag: el.tagName.toLowerCase(), right: Math.round(r.right), text: t });
    }
    const st = getComputedStyle(el);
    if (st.overflow === 'hidden' || st.overflowX === 'hidden') {
      if (el.scrollWidth > el.clientWidth + 4) {
        const t = (el.innerText || '').trim().slice(0, 30);
        /* 🔴 **말줄임과 잘림은 다르다**(핸드오프 계획 §0-3). 한 줄 칸이 `text-overflow: ellipsis` 로 줄이고 전체 값을
           `title`(자기 자신이나 감싼 요소)로 들고 있으면 계약대로 줄인 것이다 — 「…」가 보이고 전체 값에 닿을 수 있다.
           그런 칸은 따로 세고(`truncated`), 말줄임 표시도 전체 값도 없이 글자가 사라지는 칸만 잘림이다. */
        const titled = el.getAttribute('title') || (el.closest('[title]') && el.closest('[title]').getAttribute('title'));
        if (t && st.textOverflow === 'ellipsis' && titled) {
          truncated.push({ tag: el.tagName.toLowerCase(), over: el.scrollWidth - el.clientWidth, text: t });
        } else if (t) {
          clipped.push({ tag: el.tagName.toLowerCase(), over: el.scrollWidth - el.clientWidth, text: t });
        }
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
  return { overflow: dedupe(over).slice(0, 8), contained: dedupe(contained).length, clipped: dedupe(clipped).slice(0, 8), truncated: dedupe(truncated).slice(0, 8),
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


SELFTEST_HTML = r"""() => {
  const long = '긴줄'.repeat(400);
  const host = document.createElement('div');
  host.id = 'hostile-selftest';
  host.style.cssText = 'position:absolute;left:0;top:0;width:600px;z-index:99999;background:#fff';
  host.innerHTML = `
    <div id="good"><div style="width:560px;overflow-x:auto"><span style="white-space:nowrap">${long}</span><div style="width:3000px;overflow:hidden;white-space:nowrap">${long}</div></div></div>
    <div id="bad"><div style="width:560px"><span style="white-space:nowrap">${long}</span></div></div>`;
  (document.querySelector('#main-content') || document.body).appendChild(host);
}"""


def selftest(base: str, insecure: bool, auth_dir: str) -> int:
    """맞는 견본(굴리는 상자 안)은 넘침으로 안 세고, 틀린 견본(보이는 상자 밖)은 센다."""
    from playwright.sync_api import sync_playwright

    route = BY_ID["user_kit"]
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, base, Path(auth_dir), insecure=insecure, log=print)
        ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id, theme="light",
                          viewport=Viewport("1920x1080", 1920, 1080), insecure=insecure)
        page = ctx.new_page()
        page.goto(f"{base}{route.shell}#{route.hash_path}", wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(1500)
        page.evaluate(SELFTEST_HTML)
        page.evaluate("() => { document.querySelector('#hostile-selftest #bad').style.display = 'none'; }")
        good = page.evaluate(PROBE)
        page.evaluate("() => { const h = document.querySelector('#hostile-selftest'); h.querySelector('#bad').style.display = ''; h.querySelector('#good').style.display = 'none'; }")
        bad = page.evaluate(PROBE)
        ctx.close()
        b.close()
    good_hit = [o for o in good["overflow"] if "긴줄" in o["text"]]
    bad_hit = [o for o in bad["overflow"] if "긴줄" in o["text"]]
    problems = []
    if good_hit:
        problems.append(f"굴리는 상자 안의 긴 줄을 넘침으로 셌다: {good_hit[:1]}")
    if not good.get("contained"):
        problems.append("굴리는 상자 안의 긴 줄을 contained 로도 세지 않았다")
    if not bad_hit:
        problems.append("보이는 상자 밖으로 나간 긴 줄을 못 잡았다")
    for line in problems:
        print("[SELFTEST] " + line)
    print("HOSTILE_PROBE_SELFTEST_" + ("FAILED" if problems else "OK"))
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", nargs="*",
                    default=["admin_users", "user_my-tickets", "user_projects", "admin_jobs"])
    ap.add_argument("--modes", nargs="*", default=["long", "many", "weird"])
    ap.add_argument("--auth-dir", default="dist/ui-qa-admin-2")
    ap.add_argument("--base-url", default=BASE,
                    help="기본은 설치처다. `local_capture --harness hostile_data` 가 "
                         "임시 서버 주소를 여기로 넘긴다 — 긴 데이터 검증에 배포가 "
                         "전제가 되면 E5 와 어긋난다")
    ap.add_argument("--viewports", nargs="*", default=["1600x1000"],
                    help="`WxH` 목록. R-90 은 긴 값을 FHD/QHD/4K 와 Zoom 3단계에서 보라고 "
                         "요구한다 — 4K 패널의 브라우저 확대 100/125/150%% 는 CSS 폭 "
                         "3840/3072/2560 과 같으므로 그 셋이 곧 Zoom 사다리다")
    ap.add_argument("--selftest", action="store_true",
                    help="넘침 판정을 맞는 견본 · 틀린 견본으로 먼저 본다(제품 판정 전에)")
    args = ap.parse_args()
    base = args.base_url
    if args.selftest:
        return selftest(base, tls.apply_default_https_context(), args.auth_dir)
    views = []
    for name in args.viewports:
        w, _, h = name.partition("x")
        views.append(Viewport(name, int(w), int(h or 1000)))

    insecure = tls.apply_default_https_context()
    print(tls.describe())
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, base, Path(args.auth_dir), insecure=insecure, log=print)
        for mode in args.modes:
          for view in views:
            for rid in args.routes:
                route = BY_ID.get(rid)
                if route is None:
                    continue
                ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id,
                                  theme="light", viewport=view,
                                  insecure=insecure)
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

                page.goto(f"{base}{route.shell}", wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(600)
                page.route("**/api/**", handler)
                t0 = time.time()
                page.goto(f"{base}{route.shell}#{route.hash_path}",
                          wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_timeout(3000)
                elapsed = round(time.time() - t0, 1)
                got = page.evaluate(PROBE)
                got.update({"seconds": elapsed, "page_errors": errs[:3], "viewport": view.name})
                report[f"{mode}/{view.name}/{rid}"] = got
                print(f"{mode:<7}{view.name:<10}{rid:<20}행={got['rows']:<4}"
                      f"넘침={len(got['overflow'])} 상자안={got.get('contained', 0)} "
                      f"잘림={len(got['clipped'])} 말줄임={len(got.get('truncated') or [])} 세로붕괴={len(got['collapsed'])} "
                      f"문서폭={got['bodyScrollW']}/{got['vw']} {elapsed}s err={len(errs)}",
                      flush=True)
                page.screenshot(path=str(OUT / f"{mode}-{view.name}-{rid}.png"))
                ctx.close()
        b.close()

    (OUT / "hostile_data.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
