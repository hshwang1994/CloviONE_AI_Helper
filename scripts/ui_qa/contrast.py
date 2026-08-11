"""텍스트 대비(WCAG) 실측 — 하네스의 21개 검사에 **없는 축**이다.

`theme_applied` 는 "다크 클래스가 붙었는가"만 본다. 그래서 **읽히지 않는 색**은 전 페이지
통과로 나온다. 실제로 손으로 계산해서 라이트 테마의 프로젝트 톤 색 하나가 2.48:1 인 것을
찾은 적이 있는데(BACKLOG `DS-30`), 그 방식으로는 한 번에 하나씩밖에 못 본다.

판정 기준(WCAG 2.1 AA):
  * 보통 텍스트           4.5:1
  * 큰 텍스트(≥18.66px 또는 ≥14px bold)  3:1

**배경은 조상까지 거슬러 올라가 실제로 칠해진 색**을 찾는다 — `transparent` 를 그대로 쓰면
모든 요소가 통과한다(가장 흔한 가짜 통과).
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import Viewport, new_context  # noqa: E402
from scripts.ui_qa.routes import BY_ID  # noqa: E402

BASE = "https://clovirone-ai.gooddi.lab"
OUT = Path("dist/contrast")

PROBE = r"""() => {
  const lum = (r, g, b) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const parse = (s) => {
    const m = /rgba?\(([^)]+)\)/.exec(s || "");
    if (!m) return null;
    const p = m[1].split(",").map(x => parseFloat(x.trim()));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  // 조상까지 올라가 실제로 칠해진 배경을 찾는다 — transparent 를 그대로 쓰면 다 통과한다.
  //
  // 🔴 **그라디언트를 만나면 판정을 포기한다(null).** `background-image` 는
  // `backgroundColor` 에 안 잡히므로, 그냥 지나치면 상단바(보라 그라디언트) 위의 흰 글씨가
  // **흰 body 배경 위의 흰 글씨**로 계산돼 1.07:1 로 나온다 — 전부 위양성이다. 실제로 처음
  // 만든 프로브가 상단바 로고·검색 placeholder·「클로비」·사용자 이름을 위반으로 셌다.
  // **모르면 모른다고 하고 건너뛴다**(하지 않은 판정을 한 척하지 않는다).
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const st = getComputedStyle(n);
      if (st.backgroundImage && st.backgroundImage !== "none") return null;  // 판정 불가
      const c = parse(st.backgroundColor);
      if (c && c.a > 0.5) return c;
      n = n.parentElement;
    }
    const bs = getComputedStyle(document.body);
    if (bs.backgroundImage && bs.backgroundImage !== "none") return null;
    const c = parse(bs.backgroundColor);
    return c && c.a > 0.5 ? c : { r: 255, g: 255, b: 255, a: 1 };
  };
  const ratio = (a, b) => {
    const l1 = lum(a.r, a.g, a.b), l2 = lum(b.r, b.g, b.b);
    const hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    return (hi + 0.05) / (lo + 0.05);
  };

  const out = [];
  let skipped = 0;
  const seen = new Set();
  document.querySelectorAll("body *").forEach(el => {
    // 자기 자신이 직접 가진 텍스트만 (부모가 자식 텍스트를 중복 보고하지 않게)
    const own = [...el.childNodes]
      .filter(n => n.nodeType === 3 && n.textContent.trim())
      .map(n => n.textContent.trim()).join(" ").trim();
    if (!own || own.length < 2) return;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return;
    const st = getComputedStyle(el);
    if (st.visibility === "hidden" || st.display === "none" || parseFloat(st.opacity) < 0.5) return;
    const fg = parse(st.color);
    if (!fg || fg.a < 0.5) return;
    const size = parseFloat(st.fontSize) || 16;
    const weight = parseInt(st.fontWeight, 10) || 400;
    const large = size >= 18.66 || (size >= 14 && weight >= 700);
    const need = large ? 3.0 : 4.5;
    const bg = bgOf(el);
    if (!bg) { skipped++; return; }          // 배경을 확정 못 함 — 판정하지 않는다
    const cr = ratio(fg, bg);
    if (cr >= need) return;
    const key = st.color + "|" + Math.round(size) + "|" + own.slice(0, 24);
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      text: own.slice(0, 40), ratio: Math.round(cr * 100) / 100, need,
      color: st.color, size: Math.round(size), weight,
      tag: el.tagName.toLowerCase(),
      cls: (el.className && el.className.toString ? el.className.toString() : "").slice(0, 46),
    });
  });
  return { skipped, items: out.sort((a, b) => a.ratio - b.ratio).slice(0, 25) };
}"""


def evaluate_contrast(page) -> dict:
    """CTR-05: 이미 열려 있는 페이지에서 대비를 측정한다(추가 네비게이션 없음).

    `main()`의 독립 실행 루프에서 뽑아냈다 — `scripts/ui_qa/run.py`의 기존 캡처 루프
    (`capture.py::capture_route`)가 페이지당 한 번만 도는 자리에 얹기 위해서다. 반환값은
    `{"items": [...위반...], "skipped": N}` — `PROBE`가 이미 내는 모양 그대로.
    """
    return page.evaluate(PROBE)


def contrast_verdict(probe_result: dict, *, max_samples: int = 5) -> dict:
    """`evaluate_contrast()`가 낸 원시 측정을 `assertions._verdict()`와 같은 모양으로 바꾼다.

    Playwright 없이도(순수 dict만으로) 테스트할 수 있게 `evaluate_contrast`와 분리했다 —
    실제 페이지 없이 이 변환 로직만 확인하려는 것이 CTR-05가 요구한 "reusable function"의
    핵심이다. `note`에 판정불가(그라디언트 등) 건수를 항상 남긴다(CTR-05 요구사항 — 위반이
    0건이어도 "이 페이지는 몇 건을 판정 못 했다"는 사실 자체가 정보다).
    """
    violations = probe_result.get("items") or []
    skipped = probe_result.get("skipped", 0)
    return {
        "status": "fail" if violations else "pass",
        "count": len(violations),
        "samples": [
            f"{v['tag']}.{v['cls']} 「{v['text']}」 ratio={v['ratio']} (기준 {v['need']})"
            for v in violations[:max_samples]
        ],
        "note": f"판정불가(그라디언트 등) {skipped}건",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", nargs="*", default=[
        "user_me", "admin_dashboard", "admin_jobs", "user_my-tickets",
        "admin_diagnostics", "user_projects", "admin_users", "user_chat"])
    ap.add_argument("--themes", nargs="*", default=["light", "dark"])
    ap.add_argument("--auth-dir", default="dist/ui-qa-admin-2")
    args = ap.parse_args()

    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    tally: Counter = Counter()
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, BASE, Path(args.auth_dir), insecure=True, log=print)
        for theme in args.themes:
            ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id,
                              theme=theme, viewport=Viewport("1920x1080", 1920, 1080),
                              insecure=True)
            page = ctx.new_page()
            for rid in args.routes:
                route = BY_ID.get(rid)
                if route is None:
                    continue
                page.goto(f"{BASE}{route.shell}#{route.hash_path}",
                          wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(2200)
                res = evaluate_contrast(page)
                found, skipped = res["items"], res["skipped"]
                report[f"{theme}/{rid}"] = {"violations": found, "undecidable": skipped}
                for f in found:
                    tally[f"{f['color']} {f['size']}px ratio={f['ratio']}"] += 1
                print(f"{theme:<6}{rid:<22} 위반 {len(found):<4} 판정불가(그라디언트) {skipped}",
                      flush=True)
            ctx.close()
        b.close()

    (OUT / "contrast.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    print("\n=== 가장 흔한 위반 (색·크기별) ===")
    for k, n in tally.most_common(12):
        print(f"  x{n:<3} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
