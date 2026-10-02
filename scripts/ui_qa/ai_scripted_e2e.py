"""AI 도우미 대본 E2E (계획 A1 ⑬ 로컬) — 실제 제공자 없이 실제 화면 · 실제 런타임 · 실제 도구로 도우미 한 차례를 끝까지 따라간다.

로컬 서버와 같은 프로세스 안의 대화형 워커(`chat_message` 핸들러)가 **같은 런타임**을 쓴다. 런타임의 제공자 자리에만 대본 제공자
(`tests/fakes/ai.py::ScriptedToolAdapter` — 단위 · 통합 시험이 쓰는 그것)를 끼운다. 도구는 진짜다: 대화 주인의 권한으로 READ ONLY
트랜잭션에서 씨앗 데이터를 읽고, 출처는 서버가 만든다. 화면은 빌드된 번들을 띄운 실브라우저다.

    1 도구 차례 — 「이번 주 마감인 내 티켓을 알려 줘」: 대본 1라운드가 `my_work` 를 부르고 2라운드가 답한다 → 답 말풍선 · 「참고한 자료」 ·
      「확인한 내용」에 「내 업무」
    2 대체 모드 — 대본이 도구를 거절(요금제의 unsupported_capability) → 서버 검색 뒤 도구 없는 한 번의 호출 → 「도구를 쓸 수 없어 검색 결과로만
      답했습니다.」
    3 찾지 못함 — `search_documents` 가 0건 → 답은 보통 말풍선이고 「찾아본 검색어는 …」(쓸 수 없음 상태가 아니다)
    4 쓸 수 없음 — AI 사용을 끄면 입력이 닫히고 쓸 수 없음 판이 선다

    python -m scripts.ui_qa.ai_scripted_e2e     # 결과 dist/ui-qa/ai-scripted-e2e/
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa import local_server as ls  # noqa: E402

EMAIL, PASSWORD = "ui-qa@goodmit.co.kr", "Ui-Qa-Local-1!"
OUT = ROOT / "dist" / "ui-qa" / "ai-scripted-e2e"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    from playwright.sync_api import sync_playwright

    from app.ai.runtime import AiRuntime
    from app.core.clock import SystemClock
    from app.jobs.handlers.chat_message import handle_chat_message
    from app.jobs.worker import Worker, WorkerContext
    from app.settings.service import apply_setting
    from tests.fakes.ai import ScriptedToolAdapter, configure_ai, tool_call, unsupported_tools

    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    def check(step: str, ok: bool, detail: str = "") -> None:
        rows.append({"step": step, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + step + (f" — {detail}" if detail else ""))

    workdir = Path(tempfile.mkdtemp(prefix="clovir-ai-e2e-"))
    url = ls.create_database()
    stop = threading.Event()
    server = None
    try:
        settings = ls.build_settings(url, workdir)
        ls.seed(url, EMAIL, PASSWORD, settings)
        port = ls._free_port()
        base = f"http://127.0.0.1:{port}"
        server, _ = ls.serve(settings, port)
        app = server.config.app

        holder = {"adapter": ScriptedToolAdapter(["답입니다."])}
        configure_ai(app)
        runtime = AiRuntime(
            settings=app.state.settings, outbound=app.state.outbound_client, secrets=app.state.secret_provider,
            session_factory=app.state.session_factory, settings_cache=app.state.settings_cache, clock=app.state.clock,
            adapter_factory=lambda provider, auth_method: holder["adapter"],
        )
        app.state.ai_runtime = runtime
        clock = SystemClock()
        ctx = WorkerContext(settings=app.state.settings, clock=clock, extras={
            "ai_gateway": getattr(app.state, "ai_gateway", None), "ai_runtime": runtime,
            "session_factory": app.state.session_factory, "settings_cache": app.state.settings_cache,
            "secret_provider": app.state.secret_provider,
        })
        worker = Worker(app.state.session_factory, clock, {"chat_message": handle_chat_message}, ctx)

        def loop() -> None:
            while not stop.is_set():
                try:
                    if not worker.run_once():
                        time.sleep(0.2)
                except Exception as exc:  # noqa: BLE001 - 하네스 워커가 죽으면 남기고 계속 돈다
                    print("worker error:", exc)
                    time.sleep(0.5)

        threading.Thread(target=loop, daemon=True).start()

        def reset_capabilities() -> None:
            """도구 거절을 겪은 런타임은 그 모델을 「도구 안 됨」으로 기록하고 다음 차례부터 대체 모드로 접는다(D-535). 장면마다 그 기록을
            비워 각 장면이 자기 대본대로 돈다 — 기록이 남는 것 자체는 제품의 동작이다(첫 실행에서 셋째 장면이 대체 모드로 갔다)."""
            from sqlalchemy import text

            with app.state.session_factory() as db:
                db.execute(text("UPDATE ai_credential_state SET capabilities_json = NULL"))
                db.commit()

        with sync_playwright() as p:
            browser = p.chromium.launch()
            for width, height in ((1366, 768), (1920, 1080)):
                tag = f"{width}"
                bctx = browser.new_context(viewport={"width": width, "height": height})
                r = bctx.request.post(base + "/login", data={"email": EMAIL, "password": PASSWORD})
                check(f"[{tag}] 로그인", r.ok, f"HTTP {r.status}")
                page = bctx.new_page()

                def ask(question: str, wait_text: str, name: str) -> bool:
                    # 차례마다 새 대화다 — 같은 주소로 다시 가면 화면이 그대로라 「새 대화」를 누른다.
                    page.goto(base + "/#/chat")
                    page.wait_for_timeout(500)
                    new_chat = page.get_by_role("button", name="새 대화")
                    if new_chat.count():
                        new_chat.first.click()
                        page.wait_for_timeout(300)
                    box = page.get_by_role("textbox", name="메시지 입력")
                    box.wait_for(timeout=15000)
                    box.fill(question)
                    box.press("Enter")
                    try:
                        page.get_by_text(wait_text, exact=False).first.wait_for(timeout=30000)
                        ok = True
                    except Exception:  # noqa: BLE001 - 못 찾은 순간을 찍어 남긴다
                        ok = False
                    page.wait_for_timeout(600)
                    page.screenshot(path=str(OUT / f"{name}-{tag}.png"), full_page=True)
                    check(f"[{tag}] {name}: 답이 화면에 선다", ok, wait_text)
                    return ok

                # 1 도구 차례
                reset_capabilities()
                holder["adapter"] = ScriptedToolAdapter([
                    tool_call("my_work", {"view": "assigned", "include_done": None}),
                    "내가 담당한 티켓을 정리했습니다. 마감 전에 일정을 확인해 주세요.",
                ])
                ask("내가 담당한 티켓을 알려 줘", "내가 담당한 티켓을 정리했습니다", "tools")
                calls = holder["adapter"].converse_calls
                check(f"[{tag}] 도구 차례: 제공자를 두 번 불렀다", len(calls) == 2, f"{len(calls)}번")
                results = holder["adapter"].tool_results(1) if len(calls) >= 2 else []
                check(f"[{tag}] 도구 결과가 데이터 칸으로 갔다", bool(results), str(results[0].content[:120]) if results else "")
                checked = page.get_by_role("button", name="확인한 내용 보기")
                check(f"[{tag}] 「확인한 내용」 단추", checked.count() >= 1)
                sources = page.locator("section[aria-label='참고한 자료'] a")
                hrefs = [sources.nth(i).get_attribute("href") or "" for i in range(sources.count())]
                check(f"[{tag}] 「참고한 자료」에 티켓이 하나 이상", len(hrefs) >= 1, f"{len(hrefs)}개")
                check(f"[{tag}] 「참고한 자료」 링크는 앱 안 경로만", all(h.startswith("#/") or h.startswith("/") for h in hrefs),
                      ", ".join(hrefs[:3]))

                reset_capabilities()
                # 2 찾지 못함
                holder["adapter"] = ScriptedToolAdapter([
                    tool_call("search_documents", {"query": "존재하지않는우주정거장규정"}),
                    "사내 문서에서 '존재하지않는우주정거장규정'과 맞는 문서를 찾지 못했습니다.",
                ])
                ask("존재하지않는우주정거장규정 문서를 찾아 줘", "찾지 못했습니다", "no-results")
                check(f"[{tag}] 「찾아본 검색어」 줄", page.get_by_text("찾아본 검색어는", exact=False).count() >= 1)
                check(f"[{tag}] 찾지 못함은 쓸 수 없음 상태가 아니다",
                      page.get_by_role("textbox", name="메시지 입력").is_enabled())
                # 3 대체 모드(마지막 — 도구 안 됨 기록을 남긴다)
                holder["adapter"] = ScriptedToolAdapter([unsupported_tools(), "검색한 문서를 바탕으로 답합니다."],
                                                        replies=["검색한 문서를 바탕으로 답합니다."])
                ask("휴가 신청 방법을 알려 줘", "검색 결과로만 답했습니다", "fallback")
                check(f"[{tag}] 대체 모드 문장", page.get_by_text("도구를 쓸 수 없어 검색 결과로만 답했습니다.").count() >= 1)

                bctx.close()

            # 4 쓸 수 없음 — AI 사용을 끈다.
            with app.state.session_factory() as db:
                apply_setting(db, app.state.settings_cache, key="ai_generation_enabled", value=False, updated_by=None,
                              now=app.state.clock.now())
                db.commit()
            bctx = browser.new_context(viewport={"width": 1366, "height": 768})
            bctx.request.post(base + "/login", data={"email": EMAIL, "password": PASSWORD})
            page = bctx.new_page()
            page.goto(base + "/#/chat")
            page.wait_for_timeout(1500)
            box = page.get_by_role("textbox", name="메시지 입력")
            check("AI 사용을 끄면 입력이 닫힌다", box.count() >= 1 and not box.first.is_enabled())
            page.screenshot(path=str(OUT / "unavailable-1366.png"), full_page=True)
            browser.close()
    finally:
        stop.set()
        if server is not None:
            server.should_exit = True
        ls.drop_database()
    (OUT / "result.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = all(r["ok"] for r in rows)
    print(("AI_SCRIPTED_E2E_OK" if ok else "AI_SCRIPTED_E2E_FAILED") + f" ({sum(r['ok'] for r in rows)}/{len(rows)}) → {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
