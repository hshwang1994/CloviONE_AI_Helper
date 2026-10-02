"""초기 설정 E2E (계획 S1 ⑬) — 선택 하나가 다른 프로세스에서도 곧바로 같은 상태로 보이는가, 안내 띠 링크는 시스템 관리자에게만인가.

같은 데이터베이스에 로컬 서버 **둘**을 띄운다(앱 둘 = 설정 캐시 둘 — 웹 워커 넷의 축소판). 시스템 관리자가 서버 A 의 초기 설정 화면에서
TLS 줄의 「외부 프록시가 맡음」을 누르면, 서버 B 가 그 뒤 열 번 연속으로 체크리스트를 읽어도 TLS 가 「완료」여야 한다(D-532 판 번호 ·
D-534 선택 저장). 화면도 B 에서 새로 열어 같은 상태를 본다.

그다음 조직을 모두 보관해 안내 띠가 서게 하고, 전역 관리자(시스템 관리자 아님)와 시스템 관리자의 `/api/system/status` 를 견준다 —
링크(`href`)는 시스템 관리자에게만 있고, 다른 사람에게는 「시스템 관리자가 초기 설정을 끝내야 합니다.」만 있다.

    python -m scripts.ui_qa.setup_e2e     # 결과 dist/ui-qa/setup-e2e/
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa import local_server as ls  # noqa: E402

ADMIN_EMAIL, ADMIN_PASSWORD = "ui-qa@goodmit.co.kr", "Ui-Qa-Local-1!"
OTHER_ADMIN, OTHER_PASSWORD = "setup-e2e-admin@example.com", "Setup-E2e-Local-1!"
OUT = ROOT / "dist" / "ui-qa" / "setup-e2e"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    import httpx
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    def check(step: str, ok: bool, detail: str = "") -> None:
        rows.append({"step": step, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + step + (f" — {detail}" if detail else ""))

    workdir = Path(tempfile.mkdtemp(prefix="clovir-setup-e2e-"))
    url = ls.create_database()
    servers = []
    try:
        settings = ls.build_settings(url, workdir)
        ls.seed(url, ADMIN_EMAIL, ADMIN_PASSWORD, settings)
        port_a, port_b = ls._free_port(), ls._free_port()
        server_a, _ = ls.serve(settings, port_a)
        servers.append(server_a)
        server_b, _ = ls.serve(settings, port_b)
        servers.append(server_b)
        base_a, base_b = f"http://127.0.0.1:{port_a}", f"http://127.0.0.1:{port_b}"

        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1366, "height": 768})
            r = ctx.request.post(base_a + "/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            check("시스템 관리자 로그인(A)", r.ok, f"HTTP {r.status}")
            page = ctx.new_page()
            page.goto(base_a + "/admin#/setup")
            page.wait_for_selector("[data-testid=setup-item-tls]")
            tls = page.locator("[data-testid=setup-item-tls]")
            before = tls.get_attribute("data-row-status")
            check("TLS 줄은 처음에 「해야 함」", before == "todo", str(before))
            tls.get_by_role("button", name="외부 프록시가 맡음").click()
            page.wait_for_function("document.querySelector('[data-testid=setup-item-tls]').getAttribute('data-row-status') === 'done'",
                                   timeout=10000)
            check("A 화면이 응답으로 바로 「완료」를 그린다", tls.get_attribute("data-row-status") == "done")
            page.screenshot(path=str(OUT / "a-after-choice-1366.png"), full_page=True)

            # B — 다른 앱(다른 설정 캐시)이 곧바로 같은 상태를 본다.
            client_b = httpx.Client(base_url=base_b, timeout=20)
            r = client_b.post("/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            check("시스템 관리자 로그인(B)", r.status_code == 200, f"HTTP {r.status_code}")
            states = []
            for _ in range(10):
                data = client_b.get("/api/admin/setup/checklist").json()
                item = next((i for i in data.get("items", []) if i["key"] == "tls"), {})
                states.append(item.get("status"))
            check("B 가 열 번 연속 「완료」를 읽는다", states == ["done"] * 10, str(states))

            ctx_b = browser.new_context(viewport={"width": 1920, "height": 1080})
            ctx_b.request.post(base_b + "/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            page_b = ctx_b.new_page()
            page_b.goto(base_b + "/admin#/setup")
            page_b.wait_for_selector("[data-testid=setup-item-tls]")
            check("B 화면도 「완료」", page_b.locator("[data-testid=setup-item-tls]").get_attribute("data-row-status") == "done")
            page_b.screenshot(path=str(OUT / "b-after-choice-1920.png"), full_page=True)

            # 되돌리기 — B 에서 「이 서버의 인증서 사용」, A 가 곧바로 「해야 함」.
            page_b.get_by_role("button", name="TLS 인증서 자세히 보기").click()
            page_b.get_by_role("button", name="이 서버의 인증서 사용").click()
            page_b.wait_for_function("document.querySelector('[data-testid=setup-item-tls]').getAttribute('data-row-status') === 'todo'",
                                     timeout=10000)
            page.reload()
            page.wait_for_selector("[data-testid=setup-item-tls]")
            check("B 에서 되돌리면 A 도 「해야 함」", page.locator("[data-testid=setup-item-tls]").get_attribute("data-row-status") == "todo")

            # 안내 띠 — 조직을 모두 보관하면 필수 항목이 남는다. 링크는 시스템 관리자에게만.
            client_a = httpx.Client(base_url=base_a, timeout=20)
            r = client_a.post("/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            csrf = {"X-CSRF-Token": r.json()["csrf_token"]}
            r = client_a.post("/api/admin/users", json={"email": OTHER_ADMIN, "display_name": "전역 관리자", "role": "admin",
                                                        "password": OTHER_PASSWORD, "must_change_password": False,
                                                        "membership_kind": "unassigned"}, headers=csrf)
            check("전역 관리자 추가", r.status_code == 201, f"HTTP {r.status_code} {r.text[:160] if r.status_code != 201 else ''}")
            from sqlalchemy import text

            from app.core.db import make_engine

            engine = make_engine(url)
            with engine.begin() as conn:
                conn.execute(text("UPDATE organizations SET status = 'archived'"))
            engine.dispose()
            other = httpx.Client(base_url=base_b, timeout=20)
            r = other.post("/login", json={"email": OTHER_ADMIN, "password": OTHER_PASSWORD})
            check("전역 관리자 로그인(B)", r.status_code == 200, f"HTTP {r.status_code}")
            notices = other.get("/api/system/status").json().get("notices") or []
            setup = next((n for n in notices if n.get("id") == "setup.incomplete" or "초기 설정" in (n.get("message") or "")), None)
            check("전역 관리자에게 안내 띠가 선다", setup is not None, json.dumps(notices, ensure_ascii=False)[:200])
            if setup:
                check("전역 관리자의 안내 띠에는 링크가 없다", setup.get("href") is None, str(setup.get("href")))
                check("전역 관리자 문장", "시스템 관리자가 초기 설정을 끝내야 합니다" in (setup.get("message") or ""), setup.get("message"))
            notices = client_b.get("/api/system/status").json().get("notices") or []
            mine = next((n for n in notices if n.get("id") == "setup.incomplete" or "초기 설정" in (n.get("message") or "")), None)
            check("시스템 관리자의 안내 띠에는 초기 설정 링크가 있다", bool(mine and mine.get("href") == "#/setup"),
                  str(mine and mine.get("href")))
            page_b.goto(base_b + "/admin#/setup")
            page_b.wait_for_selector("[data-testid=setup-summary]")
            time.sleep(0.5)
            page_b.screenshot(path=str(OUT / "b-required-left-1920.png"), full_page=True)
            browser.close()
    finally:
        for s in servers:
            s.should_exit = True
        ls.drop_database()
    (OUT / "result.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = all(r["ok"] for r in rows)
    print(("SETUP_E2E_OK" if ok else "SETUP_E2E_FAILED") + f" ({sum(r['ok'] for r in rows)}/{len(rows)}) → {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
