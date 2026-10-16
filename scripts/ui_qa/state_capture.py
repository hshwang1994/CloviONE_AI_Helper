"""상태별 캡처 (계획 8.2 「상태별 캡처 표」) — 시각 수용(8.5)이 볼 상태를 실제 스크린샷으로 만든다.

경로 캡처(`local_capture`)는 씨앗 그대로의 한 상태만 찍는다. 이 하네스는 같은 화면을 **여러 상태**로 세워 네 폭에서 찍는다. 상태는
가능한 한 실제 API 로 만든다(메일 설정 저장과 연결 확인, 시험 메일, 알림 주소 확인 코드, AI 설정, 대본 제공자로 돈 실제 도우미 차례).
만들기 어려운 것만(재로그인 필요 · 모델 목록 실패 · 정상 연결 표시 · 로컬 릴레이 구성 요소 · 0건 목록 · 긴 데이터) 그 API 응답을
`page.route` 로 바꿔 넣는다 — 바꾼 응답은 실제 응답을 받아 그 안의 값만 고친다(모양이 서버와 어긋나지 않는다).

    조직 관리   조직 선택 · 큰 부서(구성원 120명 이상) · 빈 부서 · 긴 이름과 이메일 · 삭제 불가 창
    초기 설정   필수 남음 · 모두 정상 · 메일 문제 · AI 문제 · 선택 기능 사용하지 않음
    메일        외부 SMTP 정상 · 연결 오류 · 로컬 릴레이 · 발송 기록 · 메일 미리 보기(데스크톱 · 모바일)
    내 프로필   계정 이메일 · 다른 주소 확인 중 · 다른 주소 확인됨
    AI 연결     미연결 · API 키(확인 전) · ChatGPT 연결 과정 · 정상 · 재로그인 필요 · 모델 목록 실패
    AI 도우미   첫 화면 · 문서 출처가 있는 답 · 내부 데이터(티켓) 조회 답
    목록 셋     프롬프트 · 정책 · 사용 통계 × 데이터 있음 · 0건 · 조건 0건 · 긴 데이터

결과: `dist/ui-qa/<label>/light/*.png`, `results.json`(대조표용, 경로 · 상태 · 폭), 같은 폭마다 치수 · 조합 · 시각 규율 프로브를
돌린 `dist/ui-qa/<label>-measure/measure.json`. 대조표는

    python -m scripts.ui_qa.visual_review --label <label> --measure <label>-measure

    python -m scripts.ui_qa.state_capture --label ux-after-states
"""

from __future__ import annotations

import argparse
import copy
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
VIEWPORTS = ((1366, 768), (1600, 900), (1920, 1080), (2560, 1440))
OUT_BASE = ROOT / "dist" / "ui-qa"


# ── 초기 설정 장면(서버 `_band` 로 두 문장을 만든다) ───────────────────────────

def setup_scenarios(real: dict) -> dict:
    from app.setup.checklist import STATUS_LABELS, _band

    state_of = {"done": "done", "skipped": "skipped", "check": "unknown"}

    def put(items, key, status, **extra):
        for i in items:
            if i["key"] == key:
                i.update(state=state_of.get(status, "todo"), status=status, status_label=STATUS_LABELS[status], **extra)
                if status in ("done", "skipped"):
                    i["action"] = extra.get("action")
                    i["question"] = extra.get("question")
        return items

    def finalize(items):
        by_key = {i["key"]: i for i in items}
        for i in items:
            if i["state"] in ("done", "skipped"):
                i["blocked_by"] = None
                i["blocked_by_label"] = None
                continue
            blocked = next((r for r in i.get("requires", []) if by_key[r]["state"] not in ("done", "skipped")), None)
            i["blocked_by"] = blocked
            i["blocked_by_label"] = by_key[blocked]["label"] if blocked else None
            if blocked:
                i.update(status="waiting", status_label=STATUS_LABELS["waiting"])
        open_items = [i for i in items if i["state"] not in ("done", "skipped")]
        remaining = [i["key"] for i in open_items if i["required"]]
        total = sum(1 for i in items if i["required"])
        nxt = next((i["key"] for i in open_items if i["blocked_by"] is None and i["required"]),
                   next((i["key"] for i in open_items if i["blocked_by"] is None), None))
        for i in items:
            i["current"] = i["key"] == nxt
        head, sub = _band(items, remaining, total, nxt)
        return {"items": items, "next_key": nxt, "current_key": nxt, "required_total": total,
                "required_done": total - len(remaining), "required_remaining": remaining,
                "complete": not remaining, "headline": head, "subline": sub}

    base = copy.deepcopy(real["items"])
    out = {}
    s = copy.deepcopy(base)
    put(s, "organization", "todo", detail="아직 조직이 없습니다.", action="조직 화면에서 조직과 부서를 추가하세요.", configured=True)
    put(s, "tls", "todo", detail="인증서 파일을 찾지 못했습니다.", choices=[{"key": "tls", "value": "proxy", "label": "외부 프록시가 맡음"}],
        action="인증서를 설치하세요. 앞단 프록시가 TLS를 맡는 구성이면 이 줄의 「외부 프록시가 맡음」을 고르세요.")
    put(s, "mail", "pending", detail="메일 발송이 비활성화되어 있습니다.", configured=False,
        choices=[{"key": "mail", "value": "unused", "label": "사용하지 않음"}],
        action="메일을 쓰려면 메일 화면에서 발송을 활성화하고 설정을 채우세요. 메일을 쓰지 않는다면 이 줄의 「사용하지 않음」을 고르세요.")
    out["required-left"] = finalize(s)
    s = copy.deepcopy(base)
    put(s, "organization", "done", detail="조직 1개, 부서 4개가 등록돼 있습니다.")
    put(s, "tls", "done", detail="외부 프록시가 TLS를 맡습니다.", choices=[{"key": "tls", "value": "app", "label": "이 서버의 인증서 사용"}],
        notes=["외부 프록시가 TLS를 맡는다고 표시했습니다. 프록시 인증서의 만료일은 이 서버가 확인하지 않습니다."])
    put(s, "mail", "done", detail="수신측 메일 서버까지 전달을 확인했습니다.", checked_at="2026-10-02T02:05:00", choices=[])
    put(s, "llm", "done", detail="AI 연결이 정상입니다.", checked_at="2026-10-02T02:00:00", choices=[], notes=[])
    put(s, "integrations", "done", detail="연동 1개가 모두 정상입니다.")
    out["all-done"] = finalize(s)
    s = copy.deepcopy(out["all-done"]["items"])
    put(s, "mail", "problem", detail="메일 서버가 로그인을 거부했습니다.", action="메일 화면에서 계정과 비밀번호를 확인하세요.",
        checked_at="2026-10-02T01:40:00", configured=True, choices=[])
    out["mail-problem"] = finalize(s)
    s = copy.deepcopy(out["all-done"]["items"])
    put(s, "llm", "problem", detail="AI 연결이 막혀 있습니다. 제공자가 키를 거부했습니다.",
        action="AI 연결 화면에서 다시 로그인하거나 키를 다시 넣으세요.", checked_at="2026-10-02T01:50:00", configured=True, choices=[])
    out["ai-problem"] = finalize(s)
    s = copy.deepcopy(out["all-done"]["items"])
    put(s, "mail", "skipped", detail="사용하지 않기로 했습니다.", choices=[{"key": "mail", "value": "use", "label": "다시 사용"}], checked_at=None)
    put(s, "llm", "skipped", detail="사용하지 않기로 했습니다.", choices=[{"key": "llm", "value": "use", "label": "다시 사용"}], checked_at=None)
    out["unused"] = finalize(s)
    return out


class Capture:
    """한 상태를 네 폭에서 찍고 프로브를 돌린다."""

    def __init__(self, browser, base: str, label: str, storage_state: dict) -> None:
        from scripts.ui_qa.composition_checks import COMPOSITION_CONTRACT, COMPOSITION_JS, expect_for
        from scripts.ui_qa.kit_measure import MEASURE_JS, _mascot_hfrac, contract_for
        from scripts.ui_qa.visual_probes import VISUAL_CONTRACT, VISUAL_JS

        self.browser, self.base, self.label = browser, base, label
        self.storage_state = storage_state
        self.shots = OUT_BASE / label / "light"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.pages: list[dict] = []
        self.measure: dict[str, dict] = {}
        self.problems: list[str] = []
        self._js = (MEASURE_JS, contract_for, _mascot_hfrac(), COMPOSITION_JS, COMPOSITION_CONTRACT, expect_for, VISUAL_JS, VISUAL_CONTRACT)

    def shoot(self, route_id: str, state: str, label: str, hash_path: str, *, wait: str, routes=(), act=None,
              console: str = "admin", viewports=VIEWPORTS) -> None:
        measure_js, contract_for, hfrac, comp_js, comp_contract, expect_for, visual_js, visual_contract = self._js
        for width, height in viewports:
            vp = f"{width}x{height}"
            ctx = self.browser.new_context(viewport={"width": width, "height": height}, storage_state=self.storage_state)
            page = ctx.new_page()
            try:
                for pattern, handler in routes:
                    page.route(pattern, handler)
                shell = "/admin" if console == "admin" else "/"
                page.goto(f"{self.base}{shell}#{hash_path}", wait_until="domcontentloaded", timeout=45000)
                page.wait_for_selector(wait, timeout=20000)
                page.wait_for_timeout(700)
                if act is not None:
                    act(page)
                    page.wait_for_timeout(500)
                page.mouse.move(0, 0)
                name = f"{route_id}__{state}__{vp}.png"
                page.screenshot(path=str(self.shots / name), full_page=True)
                # 계약값은 루트 글자 비율로 곱한다(2560 구간은 루트 18px — `kit_measure.contract_for`).
                contract = contract_for(page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize) || 16"))
                result = page.evaluate(measure_js, {**contract, "scope": None, "mascotHfrac": hfrac})
                composed = page.evaluate(comp_js, {**comp_contract, "scope": None, "expect": expect_for(route_id)})
                if isinstance(composed, dict) and not composed.get("error"):
                    result.update(composed)
                looked = page.evaluate(visual_js, {**visual_contract, "scope": None})
                if isinstance(looked, dict) and not looked.get("error"):
                    result.update(looked)
                key = f"{route_id}:{state}"
                self.measure[f"{key}__light__{vp}"] = result
                self.pages.append({"route": key, "state": state, "label": label, "viewport": vp, "theme": "light",
                                   "screenshot": f"light/{name}"})
                print(f"[state] {key:<48} {vp}", flush=True)
            except Exception as exc:  # noqa: BLE001 - 한 상태가 실패해도 나머지를 찍고 실패를 남긴다
                self.problems.append(f"{route_id}:{state} {vp}: {exc}".splitlines()[0][:240])
                print(f"[state] FAIL {route_id}:{state} {vp}: {str(exc).splitlines()[0][:200]}", flush=True)
                try:
                    page.screenshot(path=str(self.shots / f"FAILED-{route_id}__{state}__{vp}.png"), full_page=True)
                except Exception:  # noqa: BLE001
                    pass
            finally:
                ctx.close()

    def write(self) -> None:
        (OUT_BASE / self.label / "results.json").write_text(
            json.dumps({"pages": self.pages, "problems": self.problems}, ensure_ascii=False, indent=1), encoding="utf-8")
        mdir = OUT_BASE / f"{self.label}-measure"
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / "measure.json").write_text(json.dumps({"pages": self.measure}, ensure_ascii=False), encoding="utf-8")


def _rewrite(pattern_fn):
    """실제 응답을 받아 고쳐 돌려주는 처리기 — `pattern_fn(data) -> data`."""
    def handler(route):
        if route.request.method != "GET":
            route.continue_()
            return
        resp = route.fetch()
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            route.fulfill(response=resp)
            return
        route.fulfill(response=resp, body=json.dumps(pattern_fn(data), ensure_ascii=False), content_type="application/json")
    return handler


def _fixed(body: dict, status: int = 200):
    text = json.dumps(body, ensure_ascii=False)

    def handler(route):
        if route.request.method != "GET":
            route.continue_()
            return
        route.fulfill(status=status, body=text, content_type="application/json")
    return handler


def _empty_lists(data):
    if isinstance(data, dict):
        out = dict(data)
        for key in ("items", "data", "results", "rows", "records"):
            if isinstance(out.get(key), list):
                out[key] = []
        if isinstance(out.get("total"), int):
            out["total"] = 0
        return out
    return [] if isinstance(data, list) else data


def run(label: str) -> int:
    import httpx
    from playwright.sync_api import sync_playwright

    from app.ai.runtime import AiRuntime
    from app.core.clock import SystemClock
    from app.jobs.handlers.chat_message import handle_chat_message
    from app.jobs.worker import Worker, WorkerContext
    from app.worker_main import _bootstrap, build_handlers
    from scripts.dev.seed_large_org import seed as seed_large_org
    from scripts.ui_qa.hostile_data import transform
    from scripts.ui_qa.mail_sink import MailSink
    from tests.fakes.ai import ScriptedToolAdapter, configure_ai, tool_call

    workdir = Path(tempfile.mkdtemp(prefix="clovir-states-"))
    sink = MailSink(workdir / "inbox").start()
    url = ls.create_database()
    stop = threading.Event()
    server = None
    try:
        port = ls._free_port()
        base = f"http://127.0.0.1:{port}"
        settings = ls.build_settings(url, workdir).model_copy(update={"app_base_url": base})
        ls.seed(url, EMAIL, PASSWORD, settings)
        big = seed_large_org(url, app_env="test")
        server, _ = ls.serve(settings, port)
        app = server.config.app
        clock = SystemClock()
        session_factory, wctx, _cache, _out = _bootstrap(settings, clock)
        # 채팅 잡은 아래 대본 워커만 집는다 — 이 워커의 런타임은 진짜 제공자를 부르므로 둘이 다투면 대본 장면이 깨진다.
        worker = Worker(session_factory, clock, build_handlers(), wctx, exclude_types=("chat_message",))

        def loop() -> None:
            while not stop.is_set():
                try:
                    if not worker.run_once():
                        time.sleep(0.2)
                except Exception as exc:  # noqa: BLE001
                    print("worker error:", exc)
                    time.sleep(0.5)

        threading.Thread(target=loop, daemon=True).start()

        api = httpx.Client(base_url=base, timeout=30)
        r = api.post("/login", json={"email": EMAIL, "password": PASSWORD})
        csrf = {"X-CSRF-Token": r.json()["csrf_token"]}

        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            ctx.request.post(base + "/login", data={"email": EMAIL, "password": PASSWORD})
            storage = ctx.storage_state()
            ctx.close()
            cap = Capture(browser, base, label, storage)

            # ── 조직 관리 ──────────────────────────────────────────────────
            orgs = api.get("/api/admin/organizations").json()
            org_items = orgs.get("items") if isinstance(orgs, dict) else orgs
            org_id = (org_items or [{}])[0].get("id", "")
            pane = "[data-workspace-pane] [data-pane-head]"
            cap.shoot("admin_organizations", "org-selected", "조직 관리 · 조직 선택", f"/organizations?org={org_id}", wait=pane)
            cap.shoot("admin_organizations", "dept-large", "조직 관리 · 큰 부서(구성원 120명 이상)", f"/departments/{big['big']}", wait=pane)
            cap.shoot("admin_organizations", "dept-empty", "조직 관리 · 빈 부서", f"/departments/{big['empty']}", wait=pane)
            cap.shoot("admin_organizations", "long-values", "조직 관리 · 긴 이름과 이메일", f"/departments/{big['big']}", wait=pane,
                      routes=[("**/api/admin/users?*", _rewrite(lambda d: transform(d, "long")))])

            def open_delete(page):
                page.get_by_role("button", name=f"{big['big_name']} 작업 더 보기").click()
                page.get_by_role("menuitem", name="삭제").click()
                # 보이는 창을 기다린다 — 화면에 숨은 `role=dialog` 가 먼저 있으면 첫 일치가 그것이라 10초를 기다리다 끝난다(P17 실측).
                page.locator("[role=dialog]:visible").first.wait_for(timeout=10000)
            cap.shoot("admin_organizations", "delete-blocked", "조직 관리 · 삭제 불가 창", f"/departments/{big['big']}", wait=pane,
                      act=open_delete)

            # ── 초기 설정 ──────────────────────────────────────────────────
            real = api.get("/api/admin/setup/checklist").json()
            for name, body in setup_scenarios(real).items():
                cap.shoot("admin_setup", name, f"초기 설정 · {name}", "/setup", wait="[data-testid=setup-checklist]",
                          routes=[("**/api/admin/setup/checklist", _fixed(body))])

            # ── 메일 ───────────────────────────────────────────────────────
            mail_body = {"enabled": True, "host": "127.0.0.1", "port": sink.port, "security": "none",
                         "from_address": "noreply@goodmit.co.kr", "from_name": "ClovirAssist", "username": "",
                         "timeout_seconds": 10, "tls_verify": True, "ca_pem": "", "mode": "external"}

            def save_and_verify(body):
                res = api.put("/api/admin/mail/settings", json=body, headers=csrf).json()
                job = (res.get("verify") or {}).get("job_id")
                for _ in range(150):
                    if not job or not api.get(f"/api/admin/mail/verify/{job}").json().get("pending"):
                        break
                    time.sleep(0.2)

            save_and_verify(mail_body)
            cap.shoot("admin_mail", "external-ok", "메일 · 외부 SMTP 정상", "/mail?tab=settings", wait="[data-testid=mail-settings-form]")
            for i in range(3):
                api.post("/api/admin/mail/test", json={"to": f"state-{i}@example.com"}, headers=csrf)
            time.sleep(4)
            cap.shoot("admin_mail", "deliveries", "메일 · 발송 기록", "/mail?tab=deliveries", wait="table, [data-list-state]")
            cap.shoot("admin_mail", "preview-desktop", "메일 · 미리 보기(데스크톱)", "/mail?tab=notifications", wait="iframe")

            def mobile(page):
                # 세그먼티드는 tablist · tab 이다(`kit.jsx::Segmented`).
                for role in ("tab", "radio", "button"):
                    target = page.get_by_role(role, name="모바일")
                    if target.count():
                        target.first.click()
                        return
                raise RuntimeError("「모바일」 전환을 찾지 못했다")
            cap.shoot("admin_mail", "preview-mobile", "메일 · 미리 보기(모바일)", "/mail?tab=notifications", wait="iframe", act=mobile)
            closed = ls._free_port()
            save_and_verify({**mail_body, "port": closed})
            cap.shoot("admin_mail", "external-error", "메일 · 연결 오류", "/mail?tab=settings", wait="[data-testid=mail-settings-form]")
            save_and_verify(mail_body)
            relay_view = json.loads((ROOT / "scripts" / "ui_qa" / "fixtures" / "relay_view.json").read_text(encoding="utf-8")) \
                if (ROOT / "scripts" / "ui_qa" / "fixtures" / "relay_view.json").is_file() else None
            if relay_view:
                api.put("/api/admin/mail/settings", json={**mail_body, "mode": "local_relay", "relay": relay_view["config"]},
                        headers=csrf)

                def relay_status(data):
                    # 릴레이 줄만 바꾸면 건강 문장은 이 PC 의 실제 상태(릴레이 안 켬)를 말해 한 상태 면이 「켜지지 않았습니다」와
                    # 「동작 중」을 함께 보였다(P17V). 고정 응답의 릴레이(동작 중 · 바깥 전달 성공)와 같은 건강으로 맞춘다.
                    data = dict(data)
                    data["relay"] = relay_view["status_relay"]
                    data["health"] = {**(data.get("health") or {}), "state": "ok", "label": "정상",
                                      "message": "메일 발송을 사용할 수 있습니다.", "stage": None, "failure_kind": None,
                                      "stages": []}
                    data["problems"] = []
                    return data
                cap.shoot("admin_mail", "local-relay", "메일 · ClovirAssist 로컬 릴레이", "/mail?tab=settings",
                          wait="[data-testid=relay-component]",
                          routes=[("**/api/admin/mail/relay", _fixed(relay_view["view"])),
                                  ("**/api/admin/mail/status", _rewrite(relay_status))])
                save_and_verify(mail_body)

            # ── 내 프로필 ──────────────────────────────────────────────────
            cap.shoot("user_profile", "account-email", "내 프로필 · 계정 이메일", "/profile", wait="[data-testid=mail-address-state]", console="user")
            before = len(sink.messages())
            api.post("/api/me/notify-email", json={"email": "state-alt@example.com"}, headers=csrf)
            sink.wait_for(before + 1, timeout=30)
            cap.shoot("user_profile", "pending", "내 프로필 · 다른 주소 확인 중", "/profile", wait="[data-testid=mail-address-state]", console="user")
            import re
            from email import message_from_bytes
            from email.policy import default as default_policy

            last = sink.messages()[-1]
            text = message_from_bytes(last.read_bytes(), policy=default_policy).get_body(("plain",)).get_content()
            code = (re.findall(r"\b(\d{6})\b", text) or [""])[0]
            api.post("/api/me/notify-email/verify", json={"code": code}, headers=csrf)
            cap.shoot("user_profile", "verified", "내 프로필 · 다른 주소 확인됨", "/profile", wait="[data-testid=mail-address-state]", console="user")

            # ── AI 연결 ────────────────────────────────────────────────────
            wait_ai = "[data-testid=ai-connection-form]"
            cap.shoot("admin_ai-connection", "unconfigured", "AI 연결 · 미연결", "/ai-connection", wait=wait_ai)
            configure_ai(app)
            # 모델 목록은 이 PC 에서 진짜 제공자를 부르지 못해 늘 실패한다 — 그 실패 상자가 「확인 전」 · 「정상」 화면에까지 섰다(P17V).
            # 모델 목록 실패는 그 상태(`models-failed`)에서만 보이고, 다른 상태는 서버 응답 모양 그대로의 목록을 받는다.
            models_ok = ("**/api/admin/ai/models*", _fixed({
                "models": [{"id": "test-model", "label": "test-model"}, {"id": "claude-sonnet-4-5", "label": "Claude Sonnet 4.5"}],
                "recommended_id": "test-model",
            }))
            cap.shoot("admin_ai-connection", "api-key", "AI 연결 · API 키(확인 전)", "/ai-connection", wait=wait_ai,
                      routes=[models_ok])

            def display(key, label_, kind, message):
                def fn(data):
                    data = copy.deepcopy(data)
                    st = data.setdefault("state", {})
                    st["state"] = key
                    st["verifying"] = False
                    st["display"] = {**(st.get("display") or {}), "key": key, "label": label_, "kind": kind, "message": message}
                    if key == "ok":
                        data["capabilities"] = {"tools": "ok", "checked_at": "2026-10-02T02:00:00"}
                        st["last_success_at"] = "2026-10-02T02:00:00"
                        st["checked_at"] = "2026-10-02T02:00:00"
                    if key == "reauth_required":
                        # 재로그인은 ChatGPT 계정 연결의 상태다 — 지금 연결과 계정 칸도 그 모양이어야 한 화면이 한 상태를 말한다.
                        data["config"] = {**(data.get("config") or {}), "provider": "openai", "auth_method": "chatgpt"}
                        data["chatgpt"] = {**(data.get("chatgpt") or {}), "connected": False, "disconnected": True}
                    return data
                return fn
            cap.shoot("admin_ai-connection", "ok", "AI 연결 · 정상", "/ai-connection", wait=wait_ai,
                      routes=[("**/api/admin/ai", _rewrite(display("ok", "정상", "ok", "AI 가 정상으로 답합니다."))), models_ok])
            cap.shoot("admin_ai-connection", "reauth", "AI 연결 · 재로그인 필요", "/ai-connection", wait=wait_ai,
                      routes=[("**/api/admin/ai", _rewrite(display("reauth_required", "재로그인 필요", "error",
                                                                   "ChatGPT 로그인이 만료됐습니다. 다시 로그인하세요."))),
                              models_ok])
            cap.shoot("admin_ai-connection", "models-failed", "AI 연결 · 모델 목록 실패", "/ai-connection", wait=wait_ai,
                      routes=[("**/api/admin/ai/models*", _fixed({"error": {"code": "upstream_error",
                                                                          "message": "제공자에게서 모델 목록을 받지 못했습니다."}}, 502))])
            api.put("/api/admin/ai/config", json={"provider": "openai", "auth_method": "chatgpt"}, headers=csrf)

            def chatgpt(page):
                btn = page.get_by_role("button", name="Continue with ChatGPT")
                if btn.count():
                    with page.context.expect_page(timeout=5000) as _popup:
                        btn.first.click()
                    page.wait_for_timeout(800)
            cap.shoot("admin_ai-connection", "chatgpt-login", "AI 연결 · ChatGPT 연결 과정", "/ai-connection", wait=wait_ai,
                      act=chatgpt, viewports=((1366, 768), (1920, 1080)))
            configure_ai(app)

            # ── AI 도우미(대본 제공자 + 실제 런타임 · 도구) ────────────────────
            holder = {"adapter": ScriptedToolAdapter(["답입니다."])}
            runtime = AiRuntime(
                settings=app.state.settings, outbound=app.state.outbound_client, secrets=app.state.secret_provider,
                session_factory=app.state.session_factory, settings_cache=app.state.settings_cache, clock=app.state.clock,
                adapter_factory=lambda provider, auth_method: holder["adapter"],
            )
            app.state.ai_runtime = runtime
            chat_worker = Worker(app.state.session_factory, clock, {"chat_message": handle_chat_message}, WorkerContext(
                settings=app.state.settings, clock=clock, extras={
                    "ai_gateway": getattr(app.state, "ai_gateway", None), "ai_runtime": runtime,
                    "session_factory": app.state.session_factory, "settings_cache": app.state.settings_cache,
                    "secret_provider": app.state.secret_provider}))

            def chat_loop() -> None:
                while not stop.is_set():
                    try:
                        if not chat_worker.run_once():
                            time.sleep(0.2)
                    except Exception as exc:  # noqa: BLE001
                        print("chat worker error:", exc)
                        time.sleep(0.5)

            threading.Thread(target=chat_loop, daemon=True).start()
            cap.shoot("user_chat", "welcome", "AI 도우미 · 첫 화면", "/chat", wait="main", console="user")

            # 「문서 출처」가 찾을 문서. 씨앗 문서는 본문 판이 없어 색인 조각이 없다 — 검색이 0건이라 출처 없는 「찾지 못함」 답이
            # 찍혔다(P17V). 본문 판을 남기고 색인을 한 번 돌린다(`tests/integration/test_chat_assistant_turn.py` 와 같은 길).
            from sqlalchemy import select as _select

            from app.ai.index import service as index_service
            from app.knowledge import service as knowledge_service, versions as knowledge_versions
            from app.knowledge.models import Document as KnowledgeDocument, KnowledgeSpace
            with app.state.session_factory() as s:
                space = s.execute(_select(KnowledgeSpace).where(
                    KnowledgeSpace.slug == knowledge_service.COMMON_SPACE_SLUG)).scalars().first()
                leave_doc = KnowledgeDocument(space_id=space.id, title="휴가 신청 규정", archived=False)
                s.add(leave_doc)
                s.flush()
                knowledge_versions.snapshot(s, leave_doc, {"type": "doc", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": text}]} for text in (
                        "휴가 신청은 사흘 전까지 휴가 신청서를 올리고 팀장의 승인을 받습니다.",
                        "연차는 입사 1년 뒤부터 15일이 생기고, 반차는 오전과 오후로 나눠 씁니다.",
                    )]}, author_id=None)
                s.flush()
                index_service.run_once(s, gateway=app.state.ai_gateway, limit=50)
                s.commit()

            def answered(expect: str):
                # `/chat?ask=` 는 질문을 **새 대화**로 보낸다 — 폭마다 같은 대화에 질문이 쌓이거나, 앞 폭의 답을 보고 다음 폭의
                # 답을 기다리지 않은 채 찍는 일이 없다(P17V: 1920 이 「●●● 0초」인 채로 찍혔다).
                def act(page):
                    page.get_by_text(expect, exact=False).first.wait_for(timeout=30000)
                    page.wait_for_timeout(500)
                return act
            from urllib.parse import quote as _quote
            two_widths = ((1366, 768), (1920, 1080))
            doc_turn = [tool_call("search_documents", {"query": "휴가 신청"}),
                        "휴가 신청은 사흘 전까지 신청서를 올리고 팀장의 승인을 받습니다. 아래 참고한 자료에서 자세히 확인하세요."]
            holder["adapter"] = ScriptedToolAdapter(doc_turn * len(two_widths))
            cap.shoot("user_chat", "document-sources", "AI 도우미 · 문서 출처가 있는 답",
                      "/chat?ask=" + _quote("휴가 신청 방법을 사내 문서에서 찾아 줘"), wait="main", console="user",
                      act=answered("휴가 신청은 사흘 전까지"), viewports=two_widths)
            work_turn = [tool_call("my_work", {"view": "assigned", "include_done": None}),
                         "내가 담당한 티켓을 정리했습니다. 마감이 가까운 것부터 확인하세요."]
            holder["adapter"] = ScriptedToolAdapter(work_turn * len(two_widths))
            cap.shoot("user_chat", "internal-data", "AI 도우미 · 내부 데이터(티켓) 조회",
                      "/chat?ask=" + _quote("내가 담당한 티켓을 알려 줘"), wait="main", console="user",
                      act=answered("내가 담당한 티켓을 정리했습니다"), viewports=two_widths)

            # ── 프롬프트 · 정책 · 사용 통계 ──────────────────────────────────
            lists = (
                ("admin_prompts", "/prompts", "**/api/admin/prompts/features*", "프롬프트"),
                ("admin_policies", "/policies", "**/api/admin/policies*", "정책"),
                ("admin_ai-usage-stats", "/ai-usage", "**/api/admin/ai/usage/stats*", "사용 통계"),
            )
            for rid, path, api_pattern, name in lists:
                cap.shoot(rid, "data", f"{name} · 데이터 있음", path, wait="main")
                cap.shoot(rid, "zero", f"{name} · 0건", path, wait="main", routes=[(api_pattern, _rewrite(_empty_lists))])
                cap.shoot(rid, "long", f"{name} · 긴 데이터", path, wait="main",
                          routes=[(api_pattern, _rewrite(lambda d: transform(d, "long")))])
            cap.shoot("admin_policies", "filtered-zero", "정책 · 조건 0건", "/policies?q=zzzz-nothing-matches", wait="main")
            cap.shoot("admin_ai-usage-records", "filtered-zero", "호출 기록 · 조건 0건", "/ai-usage?tab=records&q=zzzz-nothing",
                      wait="main")
            browser.close()
        cap.write()
        print(f"STATE_CAPTURE_DONE ({len(cap.pages)}장, 실패 {len(cap.problems)}) → {OUT_BASE / label}")
        for problem in cap.problems:
            print("  -", problem)
        return 0 if not cap.problems else 1
    finally:
        stop.set()
        if server is not None:
            server.should_exit = True
        sink.stop()
        ls.drop_database()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="상태별 캡처(계획 8.2)")
    ap.add_argument("--label", default="ux-after-states")
    args = ap.parse_args()
    return run(args.label)


if __name__ == "__main__":
    raise SystemExit(main())
