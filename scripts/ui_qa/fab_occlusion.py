"""떠 있는 클로비(그리고 좌하단 도킹 카드) **아래에 무엇이 깔려 있는지** 센다.

기존 `fab_overlap` 검사는 "어느 스크롤 위치에서도 도달 불가한가"를 묻는다(assertions.py:399).
그 질문은 옳고, 통과하는 것도 옳다. 하지만 사용자가 겪는 문제는 다르다 —
**기본 화면에서 무엇이 가려져 있는가.** 스크롤하면 가려지는 대상이 바뀔 뿐 항상 무엇인가는 가려진다.

`elementsFromPoint` 로 떠 있는 요소를 걷어내고 그 아래 첫 요소를 본다.
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
from scripts.ui_qa.routes import ALL_ROUTES as ROUTES  # noqa: E402

# 치는 곳은 `capture.DEFAULT_BASE_URL` 이 정한다 — 각자 문자열을 들면 이름이 바뀌는 날
# 이런 파일 14개가 옛 호스트에 남는다(W5 · F-W5D-129).
BASE = DEFAULT_BASE_URL
OUT = Path("dist/fab-occlusion")

PROBE = """() => {
  const fixed = [...document.querySelectorAll('body *')].filter(e => {
    const s = getComputedStyle(e);
    if (s.position !== 'fixed') return false;
    const r = e.getBoundingClientRect();
    // 우하단/좌하단에 있는 작은 떠 있는 것만 (상단바·사이드바 제외)
    return r.width > 30 && r.width < 340 && r.height > 30 && r.height < 200
        && r.bottom > innerHeight - 200;
  });
  const out = [];
  for (const f of fixed) {
    const r = f.getBoundingClientRect();
    const cx = Math.round(r.left + r.width/2), cy = Math.round(r.top + r.height/2);
    const stack = document.elementsFromPoint(cx, cy);
    // 떠 있는 것 자신과 그 조상들을 건너뛴다
    const under = stack.find(el => !f.contains(el) && el !== f && el !== document.body
                                   && el !== document.documentElement);
    let hit = null;
    if (under) {
      const act = under.closest('button, a, [role=button], input, textarea, select, td, th, tr');
      hit = { tag: under.tagName.toLowerCase(),
              actionable: !!(act && /^(button|a|input|textarea|select)$/i.test(act.tagName)),
              actTag: act ? act.tagName.toLowerCase() : null,
              actText: act ? (act.innerText||'').trim().slice(0,40) : null,
              text: (under.innerText||'').trim().slice(0,50) };
    }
    out.push({ floater: (f.innerText||'').trim().slice(0,28) || f.tagName.toLowerCase(),
               box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
               under: hit });
  }
  return out;
}"""


def main() -> int:
    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    rows, covered_actions = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        s = ensure_session(browser, BASE, OUT, insecure=True, log=print)
        ctx = new_context(browser, storage_state=s.storage_state, user_id=s.user_id,
                          theme="light", viewport=Viewport("1920x1080", 1920, 1080),
                          insecure=True)
        page = ctx.new_page()
        for route in ROUTES:
            if route.is_detail or route.is_public:
                continue
            try:
                page.goto(f"{BASE}/#{route.hash_path}", wait_until="domcontentloaded",
                          timeout=45_000)
                page.wait_for_timeout(1600)
                found = page.evaluate(PROBE)
            except Exception as exc:  # noqa: BLE001
                rows.append({"route": route.id, "error": f"{type(exc).__name__}"})
                continue
            rows.append({"route": route.id, "floaters": found})
            for f in found:
                u = f.get("under") or {}
                if u.get("actionable"):
                    covered_actions.append(
                        f"{route.id}: «{f['floater'][:16]}» 가 {u['actTag']} «{u['actText']}» 위에")
            print(f"{route.id}: floaters={len(found)} "
                  f"actionable_under={sum(1 for f in found if (f.get('under') or {}).get('actionable'))}",
                  flush=True)
        ctx.close()
        browser.close()

    summary = {"routes": len(rows),
               "routes_with_actionable_covered": len({c.split(':')[0] for c in covered_actions}),
               "covered": covered_actions}
    (OUT / "fab_occlusion.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n=== 요약 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
