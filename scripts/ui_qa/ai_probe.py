"""AI 도우미 실사용 조사 — 화면이 아니라 **대화 내용**을 본다.

앞선 시도는 말풍선 선택자를 추측했다가 실패했다. 이번에는 `/chat` 이 실제로 쓰는 API 를
같은 세션으로 직접 부르고, 화면은 그 결과를 확인하는 데만 쓴다.
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
OUT = Path("dist/ai-e2e")


def jget(ctx, path: str):
    r = ctx.request.get(BASE + path, timeout=60_000)
    try:
        return r.status, r.json()
    except Exception:  # noqa: BLE001
        return r.status, (r.text() or "")[:300]


def jpost(ctx, path: str, payload: dict, csrf: str, timeout=240_000):
    r = ctx.request.post(BASE + path, data=payload, timeout=timeout,
                         headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"})
    try:
        return r.status, r.json()
    except Exception:  # noqa: BLE001
        return r.status, (r.text() or "")[:400]


def main() -> int:
    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    out: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        s = ensure_session(browser, BASE, OUT, insecure=True, log=print)
        ctx = new_context(browser, storage_state=s.storage_state, user_id=s.user_id,
                          theme="light", viewport=Viewport("1600x1000", 1600, 1000),
                          insecure=True)
        page = ctx.new_page()
        page.goto(f"{BASE}/#/chat", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)

        csrf = page.evaluate(
            "() => (document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)||[])[1] || ''")
        out["csrf_found"] = bool(csrf)

        st, convs = jget(ctx, "/api/conversations")
        items = convs.get("items", []) if isinstance(convs, dict) else []
        out["conversations_total"] = len(items)
        out["titles"] = [c["title"] for c in items]
        newest = items[0]["id"] if items else None

        # 1) 방금 무슨 일이 있었나 — 가장 최근 대화의 실제 메시지
        if newest:
            st, detail = jget(ctx, f"/api/conversations/{newest}/messages")
            msgs = (detail.get("items") or detail.get("messages") or []
                    ) if isinstance(detail, dict) else (detail if isinstance(detail, list) else [])
            out["newest_conv"] = {
                "status": st, "id": newest, "n": len(msgs),
                "tail": [{"role": m.get("role"), "at": m.get("created_at"),
                          "len": len(m.get("content") or ""),
                          "text": (m.get("content") or "")[:220]} for m in msgs[-6:]],
            }

        # 2) 새 대화를 만들고 3턴을 실제로 돌린다
        st, created = jpost(ctx, "/api/conversations", {}, csrf)
        out["create"] = {"status": st, "body": str(created)[:200]}
        cid = created.get("id") if isinstance(created, dict) else None

        turns = []
        if cid:
            for q in ("내 티켓 중에서 아직 안 끝난 게 몇 건이야?",
                      "방금 말한 것 중에 제일 오래된 건 뭐야?",
                      "표와 코드블록을 써서 파이썬 예시를 하나 보여줘."):
                t0 = time.time()
                st, body = jpost(ctx, f"/api/conversations/{cid}/messages",
                                 {"content": q}, csrf)
                txt = ""
                if isinstance(body, dict):
                    txt = (body.get("content") or body.get("answer")
                           or json.dumps(body, ensure_ascii=False))[:900]
                turns.append({"q": q, "status": st, "sec": round(time.time() - t0, 1),
                              "len": len(txt), "a": txt})
        out["turns"] = turns

        # 3) 그 대화를 화면에서 열어 실제 렌더를 본다
        if cid:
            page.goto(f"{BASE}/#/chat", wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3500)
            page.screenshot(path=str(OUT / "10-qa-conversation.png"), full_page=True)
            out["render"] = page.evaluate(
                """() => { const r=document.querySelector('#main-content')||document.body;
                   return { pre:r.querySelectorAll('pre').length,
                            code:r.querySelectorAll('code').length,
                            table:r.querySelectorAll('table').length,
                            li:r.querySelectorAll('li').length,
                            copy:[...r.querySelectorAll('button')].filter(b=>(b.innerText||'').includes('복사')).length }; }"""
            )

        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ai_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2)[:6000])
        ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
