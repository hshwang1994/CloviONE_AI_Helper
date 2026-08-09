"""화면이 **실패할 때** 무엇을 보여 주는가 (Empty 다음으로 사용자가 지목한 축).

지금까지의 조사는 전부 "정상 데이터가 있을 때"였다. 사용자 지시의
`Empty · Loading · Error · Permission Denied · 긴 데이터 · 많은 데이터 · 잘못된 입력`
중 **Error 와 Loading 은 한 번도 보지 않았다.**

Playwright 라우트 가로채기로 API 를 실제로 실패시킨다 — 서버를 건드리지 않고, 브라우저에서만.

  mode=500      : 모든 `/api/**` 가 500 + 에러 봉투
  mode=abort    : 네트워크 자체가 끊긴 상태(오프라인)
  mode=slow     : 응답을 6초 늦춘다 → **로딩 상태**를 잡는다
  mode=garbage  : 200 인데 본문이 JSON 이 아니다(프록시가 HTML 을 끼워 넣는 실제 상황)

각 화면에서 보는 것: ① 오류 문구가 있는가 ② 다시 시도 수단이 있는가
③ 화면이 통째로 빈 채 말이 없는가 ④ 콘솔에 처리되지 않은 예외가 났는가
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
OUT = Path("dist/failure-states")

# 화면이 "실패를 말했다"고 인정할 표현. 하나도 없으면 사용자는 왜 비었는지 알 수 없다.
ERROR_WORDS = ["오류", "실패", "문제", "불러오지", "가져오지", "다시 시도", "재시도",
               "잠시 후", "연결", "확인해"]

READ = """() => {
  const root = document.querySelector('#main-content') || document.body;
  const text = (root.innerText || '').replace(/\\s+/g, ' ').trim();
  const btns = [...root.querySelectorAll('button, a[role=button]')]
      .map(b => (b.innerText || '').trim()).filter(Boolean);
  return {
    chars: text.length,
    text: text.slice(0, 320),
    buttons: btns.slice(0, 12),
    spinners: root.querySelectorAll('[role=progressbar], .MuiCircularProgress-root, .MuiSkeleton-root').length,
    tables: root.querySelectorAll('table').length,
    rows: root.querySelectorAll('tbody tr').length,
  };
}"""


def install(page, mode: str) -> None:
    def handler(route):
        if mode == "abort":
            return route.abort("failed")
        if mode == "500":
            return route.fulfill(status=500, content_type="application/json",
                                 body=json.dumps({"error": {"code": "internal_error",
                                                            "message": "서버 오류"}}))
        if mode == "garbage":
            return route.fulfill(status=200, content_type="text/html",
                                 body="<html><body>proxy interstitial</body></html>")
        if mode == "slow":
            page.wait_for_timeout(6000)
            return route.continue_()
        return route.continue_()

    page.route("**/api/**", handler)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", nargs="*", default=[
        "user_me", "user_my-tickets", "admin_users", "admin_jobs",
        "user_team-docs", "user_projects", "admin_diagnostics", "user_chat"])
    ap.add_argument("--modes", nargs="*", default=["500", "abort", "garbage", "slow"])
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
                page.on("console", lambda m: errs.append(f"console.error: {m.text[:110]}")
                        if m.type == "error" else None)
                # 셸을 먼저 띄운 뒤 가로채기를 건다 — 번들 자체는 정상적으로 받아야 한다.
                page.goto(f"{BASE}{route.shell}", wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(800)
                install(page, mode)
                page.goto(f"{BASE}{route.shell}#{route.hash_path}",
                          wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2500 if mode != "slow" else 3000)
                got = page.evaluate(READ)
                spoke = [w for w in ERROR_WORDS if w in got["text"]]
                retry = [x for x in got["buttons"] if "시도" in x or "새로" in x or "재" in x]
                got.update({"error_words": spoke, "retry_buttons": retry,
                            "page_errors": errs[:4]})
                report[f"{mode}/{rid}"] = got
                verdict = ("말함" if spoke else "**침묵**") if mode != "slow" else \
                          ("로딩표시" if got["spinners"] else "**표시없음**")
                print(f"{mode:<8}{rid:<20}{verdict:<10}chars={got['chars']:<5}"
                      f"spin={got['spinners']} retry={len(retry)} js_err={len(errs)}", flush=True)
                page.screenshot(path=str(OUT / f"{mode}-{rid}.png"))
                ctx.close()
        b.close()

    (OUT / "failure_states.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
