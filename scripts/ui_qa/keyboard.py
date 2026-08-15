"""키보드 이동과 포커스 표시 실측 — 하네스에 **없는 축**.

`tokens.css:39` 가 이미 적어 뒀다: *"기준선의 전역 포커스 링을 그대로 계산해 봐도 흰 배경 대비
2.76으로 3:1(WCAG 1.4.11 비텍스트 최소)에 못 미친다"*. 즉 **제품이 스스로 미달임을 안다.**
그런데 실제로 탭을 눌러 본 사람은 없다 — 순서가 맞는지, 링이 보이는지, 어디서 갇히는지.

보는 것
  1. **탭 순서**가 시각 순서(위→아래, 좌→우)와 맞는가
  2. 포커스된 요소에 **눈에 보이는 표시**가 있는가(outline / box-shadow / 배경 변화)
  3. **화면 밖 요소로 포커스가 가는가**(보이지 않는 것에 포커스가 서면 사용자는 길을 잃는다)
  4. 모달 안에서 포커스가 **갇히는가**(밖으로 새면 배경 요소를 조작하게 된다)
  5. **건너뛰기 링크**(skip to content)가 있는가 — 내비 37항목을 매번 탭으로 지나야 하는지
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import Viewport, new_context  # noqa: E402
from scripts.ui_qa.routes import BY_ID  # noqa: E402

BASE = "https://clovirone-ai.gooddi.lab"
OUT = Path("dist/keyboard")

ACTIVE = """() => {
  const el = document.activeElement;
  if (!el || el === document.body) return { none: true };
  const r = el.getBoundingClientRect();
  const st = getComputedStyle(el);
  const visible = r.width > 0 && r.height > 0 &&
                  r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
  // 포커스 표시: outline 두께가 있거나 box-shadow 가 있거나 (둘 다 없으면 표시 없음)
  const ow = parseFloat(st.outlineWidth) || 0;
  const hasOutline = ow > 0 && st.outlineStyle !== "none";
  const hasShadow = st.boxShadow && st.boxShadow !== "none";
  return {
    tag: el.tagName.toLowerCase(),
    role: el.getAttribute("role") || "",
    text: (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().slice(0, 34),
    x: Math.round(r.left), y: Math.round(r.top),
    w: Math.round(r.width), h: Math.round(r.height),
    visible, hasOutline, hasShadow,
    outline: hasOutline ? st.outlineColor + " " + st.outlineWidth : "",
    shadow: hasShadow ? st.boxShadow.slice(0, 46) : "",
  };
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", nargs="*",
                    default=["user_me", "admin_users", "user_new-ticket", "user_chat"])
    ap.add_argument("--steps", type=int, default=45)
    ap.add_argument("--auth-dir", default="dist/ui-qa-admin-2")
    args = ap.parse_args()

    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, BASE, Path(args.auth_dir), insecure=True, log=print)
        ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id, theme="light",
                          viewport=Viewport("1600x1000", 1600, 1000), insecure=True)
        page = ctx.new_page()
        for rid in args.routes:
            route = BY_ID.get(rid)
            if route is None:
                continue
            page.goto(f"{BASE}{route.shell}#{route.hash_path}",
                      wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2500)
            page.evaluate("() => { document.body.focus(); if (document.activeElement) "
                          "document.activeElement.blur(); }")

            stops = []
            for _ in range(args.steps):
                page.keyboard.press("Tab")
                page.wait_for_timeout(60)
                stops.append(page.evaluate(ACTIVE))

            real = [s_ for s_ in stops if not s_.get("none")]
            no_marker = [s_ for s_ in real if not s_["hasOutline"] and not s_["hasShadow"]]
            offscreen = [s_ for s_ in real if not s_["visible"]]
            # 시각 순서 위반: 다음 정지점이 이전보다 y 가 30px 이상 위로 올라가고 x 도 왼쪽이면
            backwards = 0
            for a, c in zip(real, real[1:]):
                if c["y"] < a["y"] - 30 and c["x"] <= a["x"]:
                    backwards += 1
            # 본문에 닿기까지 몇 번 눌러야 하나 (main 안의 첫 요소)
            main_at = None
            for i, s_ in enumerate(real):
                if s_["y"] > 90 and s_["x"] > 280:      # 상단바·사이드바 밖
                    main_at = i + 1
                    break
            # AppShell.jsx의 실제 문구는 "본문 바로가기"다 — 이전 패턴(건너|본문으로|skip)이
            # 그 문구를 못 잡아 실제로 있는 스킵 링크를 "없음"으로 오탐하고 있었다(KBD-05
            # 재확인 중 발견, DECISIONS.md 참고).
            skip = page.evaluate(
                """() => [...document.querySelectorAll('a,button')]
                    .filter(e => /건너|본문으로|바로가기|skip/i.test((e.innerText||'') + (e.getAttribute('aria-label')||'')))
                    .map(e => (e.innerText||e.getAttribute('aria-label')||'').trim()).slice(0,3)""")

            report[rid] = {
                "stops": len(real), "no_focus_marker": len(no_marker),
                "offscreen_focus": len(offscreen), "backwards_jumps": backwards,
                "tabs_to_main": main_at, "skip_links": skip,
                "no_marker_samples": no_marker[:4], "offscreen_samples": offscreen[:4],
                "first8": [f"{x['tag']}«{x['text'][:16]}»" for x in real[:8]],
            }
            print(f"{rid:<18} 정지점={len(real):<3} 표시없음={len(no_marker):<3} "
                  f"화면밖={len(offscreen):<3} 역순={backwards:<3} "
                  f"본문까지={main_at} 건너뛰기링크={skip or '없음'}", flush=True)
        ctx.close()
        b.close()

    (OUT / "keyboard.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
