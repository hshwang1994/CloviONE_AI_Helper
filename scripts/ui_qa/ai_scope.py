"""AI 도우미가 **무엇을 볼 수 있는가** 를 실측한다.

기존 기록의 추정: "모델이 보는 데이터가 Notion 티켓·프로젝트뿐 — 검색·문서·게시판 접근 불가".
코드를 읽고 추론한 것이라 **실제로 물어봐서 확인**한다. 사용자가 지목한 "원하는 수준까지
기능이 제공이 아니라 한계가 있음"의 정확한 경계를 그리는 것이 목적이다.

각 질문은 **서버에 실제로 존재하는 데이터**를 가리킨다(그래서 "없다"는 답은 능력의 한계다).
매번 **새 대화**에서 묻는다 — 낡은 문맥에 납치되지 않기 위해서(`AI-30`).
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
OUT = Path("dist/ai-scope")

# (질문, 그 데이터가 서버에 실제로 있다는 근거)
QUESTIONS = [
    ("자유게시판에 올라온 글 제목을 알려줘", "board_posts 1건(제목 '기능개선')"),
    ("팀 문서 중에 회의록이 있어? 제목 하나만 알려줘", "search_documents 1201건, '회의록' 다수"),
    ("내 채팅방 목록 알려줘", "chat_rooms 4건"),
    ("지금 실패한 백그라운드 작업이 몇 건이야?", "jobs failed 4건"),
    ("SK하이닉스 프로젝트 진행률이 몇 퍼센트야?", "projects 22건에 SK하이닉스 포함"),
]


def newest(ctx):
    r = ctx.request.get(BASE + "/api/conversations", timeout=60_000).json()
    items = r.get("items", [])
    return items[0]["id"] if items else None


def msgs(ctx, cid):
    r = ctx.request.get(BASE + f"/api/conversations/{cid}/messages", timeout=60_000).json()
    return r.get("items") or r.get("messages") or []


def main() -> int:
    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        s = ensure_session(b, BASE, Path("dist/ai-e2e"), insecure=True, log=print)
        ctx = new_context(b, storage_state=s.storage_state, user_id=s.user_id, theme="light",
                          viewport=Viewport("1600x1000", 1600, 1000), insecure=True)
        page = ctx.new_page()
        for q, why in QUESTIONS:
            page.goto(f"{BASE}/#/chat", wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3000)
            btn = page.query_selector("button:has-text('새 대화')")
            if btn:
                btn.click()
                page.wait_for_timeout(1500)
            prev = newest(ctx)
            ta = page.query_selector("#main-content textarea")
            if ta is None:
                out.append({"q": q, "error": "컴포저 없음"})
                continue
            ta.click()
            ta.fill(q)
            page.wait_for_timeout(250)
            ta.press("Enter")
            t0 = time.time()
            answer, target = None, None
            while time.time() - t0 < 200:
                page.wait_for_timeout(2500)
                cur = newest(ctx)
                target = cur or prev
                m = msgs(ctx, target) if target else []
                if m and m[-1].get("role") == "assistant":
                    answer = m[-1]
                    break
            text = (answer or {}).get("content", "") if answer else ""
            out.append({"q": q, "ground_truth": why, "sec": round(time.time() - t0, 1),
                        "answer": text[:600], "len": len(text)})
            print(f"\n▸ {q}\n  (서버 실데이터: {why})\n  {round(time.time()-t0,1)}s  "
                  f"→ {text[:220]}", flush=True)
        ctx.close()
        b.close()

    (OUT / "ai_scope.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
