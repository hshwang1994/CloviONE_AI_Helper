"""AI-30 검증: 같은 질문을 **새 대화**에서 하면 다르게 답하는가.

AI-30 은 "낡은 CREATE 모드가 무관한 질문을 납치했다"는 주장이다. 그것이 맞다면 문맥이 비어
있는 새 대화에서 같은 문장을 물었을 때 **티켓 생성 플로우가 시작되면 안 된다.** 시작된다면
내 진단이 틀렸고 원인은 메시지 자체의 오분류다. 둘을 가르기 위한 스크립트다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402

# 치는 곳은 `capture.DEFAULT_BASE_URL` 이 정한다 — 각자 문자열을 들면 이름이 바뀌는 날
# 이런 파일 14개가 옛 호스트에 남는다(W5 · F-W5D-129).
BASE = DEFAULT_BASE_URL
OUT = Path("dist/ai-e2e")

QUESTIONS = [
    "방금 말한 것 중에 제일 오래된 건 뭐야?",   # 문맥 없는 상태에서의 같은 문장
]


def newest_conv(ctx):
    r = ctx.request.get(BASE + "/api/conversations", timeout=60_000)
    items = r.json().get("items", [])
    return items[0] if items else None


def messages(ctx, cid):
    r = ctx.request.get(BASE + f"/api/conversations/{cid}/messages", timeout=60_000)
    body = r.json()
    return body.get("items") or body.get("messages") or []


def main() -> int:
    insecure = tls.apply_default_https_context()
    print(tls.describe())
    from playwright.sync_api import sync_playwright

    out: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        s = ensure_session(browser, BASE, OUT, insecure=insecure, log=print)
        ctx = new_context(browser, storage_state=s.storage_state, user_id=s.user_id,
                          theme="light", viewport=Viewport("1600x1000", 1600, 1000),
                          insecure=insecure)
        page = ctx.new_page()
        page.goto(f"{BASE}/#/chat", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3500)

        before = newest_conv(ctx)
        out["before_newest"] = before and {"id": before["id"], "title": before["title"]}

        # 화면의 '새 대화' 버튼을 실제로 누른다.
        btn = page.query_selector("button:has-text('새 대화')")
        out["new_button_found"] = bool(btn)
        if btn:
            btn.click()
            page.wait_for_timeout(2500)

        after = newest_conv(ctx)
        out["after_newest"] = after and {"id": after["id"], "title": after["title"]}
        cid = after["id"] if after else None
        out["created_new"] = bool(before and after and before["id"] != after["id"])

        results = []
        for q in QUESTIONS:
            ta = page.query_selector("#main-content textarea")
            if ta is None:
                results.append({"q": q, "error": "컴포저 없음"})
                break
            prev_id = cid
            ta.click()
            ta.fill(q)
            page.wait_for_timeout(300)
            ta.press("Enter")
            t0 = time.time()
            answer, target = None, None
            while time.time() - t0 < 180:
                page.wait_for_timeout(2500)
                # '새 대화'는 **지연 생성**이다 — 첫 메시지를 보내야 행이 생긴다.
                # 그래서 보낸 뒤에 목록을 다시 읽어 실제 대상 대화를 찾는다.
                cur = newest_conv(ctx)
                target = cur["id"] if cur else prev_id
                msgs = messages(ctx, target) if target else []
                if msgs and msgs[-1].get("role") == "assistant":
                    answer = msgs[-1]
                    break
            results.append({
                "q": q, "sec": round(time.time() - t0, 1),
                "conversation": target, "was_new": target != prev_id,
                "turns": len(messages(ctx, target)) if target else 0,
                "answer": (answer or {}).get("content", "")[:700] if answer else None,
            })
        out["results"] = results
        page.screenshot(path=str(OUT / "20-new-conversation.png"), full_page=True)

        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ai_verify.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
