"""로컬 메일 E2E (계획 M5 E2E-0) — 배포 없이 개발 PC 에서 제품의 실제 전송기로 메일 흐름을 끝까지 따라간다.

로컬 서버(`local_server.serve`) + 127.0.0.1 받는 쪽(`mail_sink.MailSink`) + 같은 프로세스 안의 워커(`app.worker_main._bootstrap`
과 `build_handlers` — 운영 워커와 같은 핸들러 · 같은 SMTP 전송기)를 띄운다. 외부 SMTP 설정을 「127.0.0.1:받는 쪽 · 보안 연결 없음 ·
계정 없음」으로 저장하고, 그 뒤의 사건마다 받는 쪽에 **정확히 한 통**이 와야 한다.

    1 설정 저장 → 저장이 연 연결 확인 잡 → 메일 건강 「정상」과 단계 줄
    2 받는 주소를 넣은 시험 메일 → 한 통, 제목 접두, 두 부분(평문 → HTML), Message-ID = 발송 기록
    3 사용자 추가 → 초대 메일 한 통, 링크가 기준 주소의 절대 주소이고 열린다
    4 비밀번호 재설정 요청 → 한 통, 재설정 링크가 열린다
    5 알림 받을 다른 주소 → 그 주소로 확인 코드 한 통 → 코드를 넣으면 「확인됨」
    6 알림 메일 켬 + 티켓 배정 → 확인한 주소로 한 통
    7 알림 메일 끔 + 티켓 배정 → 0통

받은 메일의 HTML 부분은 Playwright 로 600 · 375px 폭 × 네 모양(밝음 · 밝음 그림 막힘 · 어둠 · 어둠 그림 막힘)에 그려 스크린샷을 남기고
가로 넘침 · 주 단추 높이(44±1) · 단추 글자색(흰색)을 잰다(D-571). 그림은 메일에 붙은 CID 로고를 data 주소로 바꿔 그리고, 막힘은 `cid:` 그대로다.
받는 주소는 `example.com` 시험 주소만 쓴다 — 실제 수신 주소는 랩 E2E(P18)의 화면 입력으로만 쓴다.

    python -m scripts.ui_qa.mail_e2e                # 결과 dist/mail-e2e/<시각>/
    python -m scripts.ui_qa.mail_e2e --no-render    # 스크린샷 없이
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from email import message_from_bytes
from email.policy import default as default_policy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa import local_server as ls  # noqa: E402
from scripts.ui_qa.mail_sink import MailSink  # noqa: E402

ADMIN_EMAIL, ADMIN_PASSWORD = "ui-qa@goodmit.co.kr", "Ui-Qa-Local-1!"
TEST_TO = "e2e-recipient@example.com"
INVITEE = "e2e-invitee@example.com"
INVITEE_PASSWORD = "Mail-E2e-Local-1!"
ALT_ADDRESS = "e2e-alt@example.com"
LINK_RE = re.compile(r'href="([^"]+)"')
CODE_RE = re.compile(r"\b(\d{6})\b")


class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, step: str, ok: bool, detail: str = "") -> bool:
        self.rows.append({"step": step, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + step + (f" — {detail}" if detail else ""))
        return ok

    @property
    def ok(self) -> bool:
        return all(r["ok"] for r in self.rows)


def _login(client, email: str, password: str) -> dict:
    r = client.post("/login", json={"email": email, "password": password})
    r.raise_for_status()
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _parse(path: Path):
    msg = message_from_bytes(path.read_bytes(), policy=default_policy)
    envelope = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    plain = msg.get_body(("plain",))
    html = msg.get_body(("html",))
    return {
        "path": path,
        "msg": msg,
        "to": envelope.get("to"),
        "subject": str(msg["Subject"] or ""),
        "message_id": str(msg["Message-ID"] or "").strip(),
        "content_type": msg.get_content_type(),
        "parts": [p.get_content_type() for p in msg.iter_parts()] if msg.is_multipart() else [msg.get_content_type()],
        "text": plain.get_content() if plain is not None else "",
        "html": html.get_content() if html is not None else "",
    }


def _wait_new(sink: MailSink, before: int, *, expect: int = 1, timeout: float = 40.0, settle: float = 2.0) -> list[Path]:
    """새로 온 메일 — 기대 수에 닿은 뒤에도 `settle` 초 더 기다려 중복이 오지 않는지 본다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(sink.messages()) - before < expect:
        time.sleep(0.2)
    if expect > 0:
        time.sleep(settle)
    else:
        time.sleep(max(settle, 4.0))
    return sink.messages()[before:]


def _shape_checks(report: Report, step: str, mail: dict, base: str) -> None:
    report.check(f"{step}: 제목 접두", mail["subject"].startswith("[ClovirAssist]"), mail["subject"])
    # HTML 쪽은 CID 로고를 담은 `multipart/related` 다(D-561) - 평문이 먼저, 그 다음이 HTML(관련 그림 포함)이다.
    html_part = mail["parts"][1] if len(mail["parts"]) > 1 else ""
    report.check(f"{step}: 두 부분(평문 → HTML)", mail["content_type"] == "multipart/alternative"
                 and mail["parts"][0] == "text/plain" and html_part in ("text/html", "multipart/related"), ", ".join(mail["parts"]))
    links = [u for u in LINK_RE.findall(mail["html"]) if not u.startswith("mailto:")]
    bad = [u for u in links if not u.startswith(base)]
    report.check(f"{step}: 링크가 기준 주소의 절대 주소", not bad, ", ".join(bad[:3]) or f"{len(links)}개")
    report.check(f"{step}: 원격 그림 없음", not re.search(r'<img[^>]+src="https?://', mail["html"], re.I))
    cids = [str(part["Content-ID"] or "") for part in mail["msg"].walk() if part.get_content_type() == "image/png"]
    report.check(f"{step}: 로고는 CID 로 붙인 PNG 한 장", cids == ["<clovi-mark@clovirassist>"]
                 and 'src="cid:clovi-mark@clovirassist"' in mail["html"], str(cids))


def run(out: Path, render: bool) -> int:
    import httpx

    from app.core.clock import SystemClock
    from app.jobs.worker import Worker
    from app.worker_main import _bootstrap, build_handlers

    report = Report()
    out.mkdir(parents=True, exist_ok=True)
    sink = MailSink(out / "inbox").start()
    workdir = Path(tempfile.mkdtemp(prefix="clovir-mail-e2e-"))
    url = ls.create_database()
    stop = threading.Event()
    server = None
    try:
        port = ls._free_port()
        base = f"http://127.0.0.1:{port}"
        settings = ls.build_settings(url, workdir).model_copy(update={"app_base_url": base})
        ls.seed(url, ADMIN_EMAIL, ADMIN_PASSWORD, settings)
        server, _ = ls.serve(settings, port)

        clock = SystemClock()
        session_factory, ctx, _cache, _outbound = _bootstrap(settings, clock)
        worker = Worker(session_factory, clock, build_handlers(), ctx)

        def loop() -> None:
            while not stop.is_set():
                try:
                    if not worker.run_once():
                        time.sleep(0.2)
                except Exception as exc:  # noqa: BLE001 - 하네스 워커가 죽으면 그 사실을 남기고 계속 돈다
                    print("worker error:", exc)
                    time.sleep(0.5)

        threading.Thread(target=loop, daemon=True).start()

        admin = httpx.Client(base_url=base, timeout=30)
        csrf = _login(admin, ADMIN_EMAIL, ADMIN_PASSWORD)

        # 1 설정 저장 → 자동 연결 확인
        body = {"enabled": True, "host": "127.0.0.1", "port": sink.port, "security": "none",
                "from_address": "noreply@goodmit.co.kr", "from_name": "ClovirAssist", "username": "",
                "timeout_seconds": 10, "tls_verify": True, "ca_pem": "", "mode": "external"}
        r = admin.put("/api/admin/mail/settings", json=body, headers=csrf)
        report.check("설정 저장", r.status_code == 200, f"HTTP {r.status_code}")
        verify = (r.json().get("verify") or {}) if r.status_code == 200 else {}
        report.check("저장이 연결 확인을 열었다", bool(verify.get("job_id")))
        result = None
        for _ in range(150):
            if not verify.get("job_id"):
                break
            v = admin.get(f"/api/admin/mail/verify/{verify['job_id']}").json()
            if not v.get("pending"):
                result = v
                break
            time.sleep(0.2)
        health = (result or {}).get("health") or {}
        report.check("연결 확인 성공", bool(result and (result.get("result") or {}).get("ok")),
                     json.dumps((result or {}).get("result"), ensure_ascii=False))
        report.check("메일 건강 「정상」", health.get("state") == "ok", f"{health.get('state')} {health.get('label')}")
        stages = [(s.get("key"), s.get("state")) for s in (health.get("stages") or [])]
        report.check("단계 줄", bool(stages) and all(state in ("ok", "skipped") for _, state in stages), str(stages))
        report.check("연결 확인은 메일을 보내지 않는다", not sink.messages(), f"{len(sink.messages())}통")

        # 2 시험 메일
        before = len(sink.messages())
        r = admin.post("/api/admin/mail/test", json={"to": TEST_TO}, headers=csrf)
        report.check("시험 메일 요청", r.status_code == 200, f"HTTP {r.status_code}")
        delivery_id = (r.json().get("delivery") or {}).get("id") if r.status_code == 200 else None
        got = _wait_new(sink, before)
        report.check("시험 메일 한 통", len(got) == 1, f"{len(got)}통")
        if got:
            mail = _parse(got[0])
            report.check("시험 메일 받는 사람", mail["to"] == [TEST_TO], str(mail["to"]))
            _shape_checks(report, "시험 메일", mail, base)
            d = admin.get(f"/api/admin/mail/deliveries/{delivery_id}").json().get("delivery") or {}
            report.check("Message-ID = 발송 기록", bool(d.get("message_id")) and d.get("message_id") == mail["message_id"],
                         f"{d.get('message_id')} / {mail['message_id']}")
            report.check("발송 기록 낱말이 「접수」(도착이 아니다)", "도착" not in (d.get("status_label") or "")
                         and "접수" in (d.get("status_label") or ""), d.get("status_label") or "")
            # 7단계(D-560): 접수된 시험 메일 뒤 남은 일은 받은 편지함 확인이고, 사람이 「받았습니다」를 적어야 끝난다.
            prog = (admin.get("/api/admin/mail/status").json().get("progress") or {})
            report.check("7단계: 접수 뒤 남은 일은 받은 편지함 확인", (prog.get("next") or {}).get("key") == "inbox_confirmed"
                         and prog.get("done_count") == 6, json.dumps(prog.get("next"), ensure_ascii=False))
            r2 = admin.post("/api/admin/mail/inbox-confirm", json={"delivery_id": delivery_id, "received": True}, headers=csrf)
            done = ((r2.json().get("status") or {}).get("progress") or {}) if r2.status_code == 200 else {}
            report.check("7단계: 「받았습니다」 기록 뒤 완료", r2.status_code == 200 and done.get("complete") is True,
                         f"HTTP {r2.status_code} {done.get('done_count')}/{done.get('total')}")

        # 3 초대
        before = len(sink.messages())
        projects = admin.get("/api/projects").json()
        items = projects.get("items") if isinstance(projects, dict) else projects
        # 티켓 열람은 프로젝트의 부서 범위가 정한다(0060) — 시험 사용자를 배정할 프로젝트의 부서에 넣는다. 부서가 없으면 배정 알림은
        # 「열람 권한 없음」으로 보내지 않는 것이 맞다(D-547, 첫 실행이 그렇게 막혔다).
        project = next((p for p in (items or []) if p.get("dept_id")), (items or [{}])[0])
        project_id = project.get("id")
        r = admin.post("/api/admin/users", json={"email": INVITEE, "display_name": "메일 시험", "role": "user",
                                                 "password": INVITEE_PASSWORD, "must_change_password": False,
                                                 **({"department_id": project["dept_id"]} if project.get("dept_id")
                                                    else {"membership_kind": "unassigned"})}, headers=csrf)
        report.check("사용자 추가", r.status_code == 201, f"HTTP {r.status_code} {r.text[:200] if r.status_code != 201 else ''}")
        invitee_id = (r.json().get("user") or r.json()).get("id") if r.status_code == 201 else None
        got = _wait_new(sink, before)
        report.check("초대 메일 한 통", len(got) == 1, f"{len(got)}통")
        if got:
            mail = _parse(got[0])
            _shape_checks(report, "초대 메일", mail, base)
            links = [u for u in LINK_RE.findall(mail["html"]) if u.startswith(base)]
            if links:
                opened = httpx.get(links[0], timeout=15, follow_redirects=True)
                report.check("초대 링크가 열린다", opened.status_code == 200, f"HTTP {opened.status_code}")

        # 4 비밀번호 재설정
        before = len(sink.messages())
        r = httpx.post(base + "/forgot-password", json={"email": INVITEE}, timeout=15)
        report.check("재설정 요청", r.status_code in (200, 202), f"HTTP {r.status_code}")
        got = _wait_new(sink, before)
        report.check("재설정 메일 한 통", len(got) == 1, f"{len(got)}통")
        if got:
            mail = _parse(got[0])
            _shape_checks(report, "재설정 메일", mail, base)
            links = [u for u in LINK_RE.findall(mail["html"]) if u.startswith(base)]
            report.check("재설정 링크에 토큰이 있다", any("token" in u or "reset" in u for u in links), ", ".join(links[:2]))
            if links:
                opened = httpx.get(links[0], timeout=15, follow_redirects=True)
                report.check("재설정 링크가 열린다", opened.status_code == 200, f"HTTP {opened.status_code}")

        # 5 알림 받을 다른 주소 — 코드
        user = httpx.Client(base_url=base, timeout=30)
        ucsrf = _login(user, INVITEE, INVITEE_PASSWORD)
        before = len(sink.messages())
        r = user.post("/api/me/notify-email", json={"email": ALT_ADDRESS}, headers=ucsrf)
        report.check("알림 주소 확인 요청", r.status_code == 200, f"HTTP {r.status_code} {r.text[:200] if r.status_code != 200 else ''}")
        got = _wait_new(sink, before)
        report.check("확인 코드 메일 한 통", len(got) == 1, f"{len(got)}통")
        if got:
            mail = _parse(got[0])
            report.check("확인 코드 메일은 그 주소로", mail["to"] == [ALT_ADDRESS], str(mail["to"]))
            _shape_checks(report, "확인 코드 메일", mail, base)
            codes = CODE_RE.findall(mail["text"])
            report.check("본문에 6자리 코드", bool(codes))
            if codes:
                r = user.post("/api/me/notify-email/verify", json={"code": codes[0]}, headers=ucsrf)
                report.check("코드 확인", r.status_code == 200, f"HTTP {r.status_code}")
                prefs = user.get("/api/me/preferences").json()
                custom = (((prefs.get("mail") or {}).get("address") or {}).get("custom") or {})
                report.check("알림 주소 「확인됨」", custom.get("email") == ALT_ADDRESS and bool(custom.get("verified_at")),
                             json.dumps(custom, ensure_ascii=False))

        # 6 알림 메일 켬 + 티켓 배정 → 확인한 주소로 한 통
        r = user.patch("/api/me/preferences", json={"mail_enabled": True, "mail_types": ["ticket_assigned"]}, headers=ucsrf)
        report.check("알림 메일 켬", r.status_code == 200, f"HTTP {r.status_code}")
        before = len(sink.messages())
        due = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        r = admin.post("/api/tickets", json={"title": "메일 E2E 배정 확인", "project_id": project_id, "est_wd": 1,
                                             "due_date": due, "assignee_user_ids": [invitee_id]}, headers=csrf)
        report.check("티켓 추가(배정)", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:200] if r.status_code not in (200, 201) else ''}")
        got = _wait_new(sink, before)
        report.check("배정 알림 메일 한 통", len(got) == 1, f"{len(got)}통")
        if got:
            mail = _parse(got[0])
            report.check("배정 알림은 확인한 주소로", mail["to"] == [ALT_ADDRESS], str(mail["to"]))
            _shape_checks(report, "배정 알림 메일", mail, base)

        # 7 알림 메일 끔 → 0통
        r = user.patch("/api/me/preferences", json={"mail_enabled": False}, headers=ucsrf)
        report.check("알림 메일 끔", r.status_code == 200, f"HTTP {r.status_code}")
        before = len(sink.messages())
        r = admin.post("/api/tickets", json={"title": "메일 E2E 끈 뒤 배정", "project_id": project_id, "est_wd": 1,
                                             "due_date": due, "assignee_user_ids": [invitee_id]}, headers=csrf)
        report.check("티켓 추가(끈 뒤 배정)", r.status_code in (200, 201), f"HTTP {r.status_code}")
        got = _wait_new(sink, before, expect=0)
        report.check("끈 뒤 배정 알림 0통", len(got) == 0, f"{len(got)}통")

        # 증거 — 발송 기록 전부(받는 주소는 시험 주소뿐이다)와 시험 사용자의 알림.
        debug = {
            "deliveries": admin.get("/api/admin/mail/deliveries", params={"limit": 50}).json(),
            "notifications": user.get("/api/notifications").json(),
        }
        (out / "debug.json").write_text(json.dumps(debug, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        if render:
            _render(out, sink.messages(), report)
    finally:
        stop.set()
        if server is not None:
            server.should_exit = True
        sink.stop()
        ls.drop_database()

    (out / "result.json").write_text(json.dumps(report.rows, ensure_ascii=False, indent=1), encoding="utf-8")
    passed = sum(1 for r in report.rows if r["ok"])
    print(("MAIL_E2E_OK" if report.ok else "MAIL_E2E_FAILED") + f" ({passed}/{len(report.rows)}) → {out}")
    return 0 if report.ok else 1


# 네 모양(D-571) - (이름, 다크인가, 그림을 그리는가). 그림 막힘은 `cid:` 를 그대로 두어 브라우저가 그림을 못 찾게 한다.
RENDER_VARIANTS = (("light", False, True), ("light-noimg", False, False), ("dark", True, True), ("dark-noimg", True, False))


def _with_inline_images(mail: dict) -> str:
    """HTML 의 `cid:` 그림을 메일에 붙은 그 그림의 data 주소로 바꾼다(받은 편지함이 그림을 보여 주는 모양)."""
    import base64

    html = mail["html"]
    for part in mail["msg"].walk():
        cid = str(part["Content-ID"] or "").strip("<>")
        if cid and part.get_content_maintype() == "image":
            data = base64.b64encode(part.get_payload(decode=True)).decode("ascii")
            html = html.replace(f"cid:{cid}", f"data:{part.get_content_type()};base64,{data}")
    return html


def _render(out: Path, files: list[Path], report: Report) -> None:
    from playwright.sync_api import sync_playwright

    from scripts.ui_qa.mail_render_matrix import MEASURE

    shots = out / "render"
    shots.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for path in files:
            mail = _parse(path)
            if not mail["html"]:
                continue
            shown = _with_inline_images(mail)
            for variant, dark, images in RENDER_VARIANTS:
                html = shown if images else mail["html"]
                for width in (600, 375):
                    page = browser.new_page(viewport={"width": width, "height": 900}, color_scheme="dark" if dark else "light")
                    page.set_content(html)
                    page.wait_for_timeout(150)
                    m = page.evaluate(MEASURE)
                    page.screenshot(path=str(shots / f"{path.stem}-{variant}-{width}.png"), full_page=True)
                    page.close()
                    name = f"{path.stem} {variant} {width}px"
                    report.check(f"{name} 가로 넘침 없음", m["overflow"] <= 1, f"{m['overflow']}px")
                    button = m.get("button")
                    if button:
                        report.check(f"{name} 단추 높이 44", abs(button["height"] - 44) <= 1, f"{button['height']}px")
                        report.check(f"{name} 단추 글자 흰색", button["color"] == "rgb(255, 255, 255)", str(button["color"]))
        browser.close()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="로컬 메일 E2E (계획 M5 E2E-0)")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()
    out = Path(args.out) if args.out else ROOT / "dist" / "mail-e2e" / datetime.now().strftime("%Y%m%d-%H%M%S")
    return run(out, render=not args.no_render)


if __name__ == "__main__":
    raise SystemExit(main())
