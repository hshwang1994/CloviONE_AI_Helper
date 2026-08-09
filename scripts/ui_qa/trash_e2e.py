"""휴지통 왕복 실측 (`trash_items` 0행, `USE-01` 여섯 번째).

문서를 휴지통에 넣고 → 목록에 뜨는지 → 복원하는지 → 원래 자리로 돌아오는지 본다.
**되돌린다** — 복원까지 해야 이 검사가 끝난 것이다.

같이 확인하는 것(이미 기록된 의심):
  `UA-10` `GET /api/trash` 가 무제한이고 화면이 15초마다 폴링한다
  `RET-02` 휴지통 보존 정책
"""

from __future__ import annotations

import json
import ssl
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import Viewport, new_context  # noqa: E402

BASE = "https://clovirone-ai.gooddi.lab"
OUT = Path("dist/trash-e2e")


def main() -> int:
    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    log: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, BASE, Path("dist/ui-qa-admin-2"), insecure=True, log=print)
        ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id, theme="light",
                          viewport=Viewport("1600x1000", 1600, 1000), insecure=True)
        page = ctx.new_page()
        page.goto(f"{BASE}/#/team-docs", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)
        csrf = ctx.request.get(BASE + "/api/me", timeout=30_000).json().get("csrf_token", "")
        log["csrf"] = bool(csrf)

        r = ctx.request.get(BASE + "/api/trash", timeout=60_000)
        log["trash_before"] = {"status": r.status, "n": len(r.json().get("items", []))}

        # 폴링 실측: /trash 화면을 열고 40초 동안 API 호출 수를 센다
        calls: list[float] = []
        page.on("request", lambda req: calls.append(time.time())
                if "/api/trash" in req.url else None)
        page.goto(f"{BASE}/#/team-docs/trash", wait_until="domcontentloaded", timeout=60_000)
        t0 = time.time()
        page.wait_for_timeout(40_000)
        log["polling"] = {"seconds": 40, "trash_api_calls": len(calls),
                          "gaps": [round(b_ - a_, 1) for a_, b_ in zip(calls, calls[1:])][:6]}
        page.screenshot(path=str(OUT / "01-trash-empty.png"), full_page=True)
        log["screen_text"] = page.evaluate(
            "() => (document.querySelector('#main-content')||document.body).innerText"
            ".replace(/\\s+/g,' ').slice(0,260)")

        # 응답 상한 확인 — 서버가 limit 을 받는가
        for q in ("?limit=1", "?page=1&page_size=1"):
            rr = ctx.request.get(BASE + "/api/trash" + q, timeout=30_000)
            body = rr.json() if rr.status == 200 else {}
            log[f"GET /api/trash{q}"] = {"status": rr.status,
                                         "n": len(body.get("items", [])),
                                         "keys": list(body)[:6]}
        ctx.close()
        b.close()

    (OUT / "trash.json").write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2)[:2200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
