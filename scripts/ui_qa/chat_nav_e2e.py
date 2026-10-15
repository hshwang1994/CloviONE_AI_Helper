"""AI 도우미 대화 이동 하네스 (D-582) — 주소 · 고른 줄 · 머리 제목 · 스레드 · 탭 제목이 늘 같은 대화인지 실브라우저로 잰다.

로컬(씨앗 계정)과 랩(사용자 계정, `dist/ops/user.env` 의 AI_TRUTH_*) 둘 다 돈다. 이름 바꾸기 · 보관 · 삭제는 하네스가 만든 시험
대화(「[AI검증] 이동 …」)에만 한다. 로컬은 씨앗 대화 둘을 **읽기만** 하고, 랩은 시험 대화 셋을 만들어 쓴 뒤 끝에 지운다.

    python -m scripts.ui_qa.chat_nav_e2e --base http://127.0.0.1:18765 --local        # 로컬 씨앗(UI_QA_AI_READY=1)
    python -m scripts.ui_qa.chat_nav_e2e --base https://clovirassist.goodmit.co.kr     # 랩(사용자 계정)

단계: 첫 진입(초안) → 전환 → 1초 안에 열 번 누르기 → 뒤로 · 앞으로 → 새로고침 → 이름 바꾸기(80자 · `<b>&"'`) → 보관 → 보관함 →
꺼내기 → 검색 → 새 대화와 첫 전송(주소 replace) → 두 대화 동시 대기(랩, 답이 제 대화에만) → 휴대폰 서랍.
매 단계 판정: `#/chat/<id>` · 고른 줄(`[data-conversation-row][data-active]`) · 머리 h2 · 스레드의 메시지 id 집합(API 와 같음) ·
탭 제목이 모두 그 대화다. 결과는 dist/ui-qa/chat-nav/<label>.{json,md}, 단계 캡처는 dist/ui-qa/chat-nav/<label>/*.png.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa.ai_lab_common import (  # noqa: E402
    LoginError, log, read_env_file, utf8_console,
)

KST = timezone(timedelta(hours=9))
OUT_DIR = ROOT / "dist" / "ui-qa" / "chat-nav"
ENV_KEYS = ("AI_TRUTH_EMAIL", "AI_TRUTH_PASSWORD")
LOCAL_CREDS = {"AI_TRUTH_EMAIL": "ui-qa@goodmit.co.kr", "AI_TRUTH_PASSWORD": "Ui-Qa-Local-1!"}
LOCAL_READ_ONLY = ("VMware 증설 절차 정리", "인프라 정비 프로젝트 현황")

STATE_JS = """
() => {
  const thread = document.querySelector('section[aria-label="대화"]');
  const head = thread && thread.querySelector('header h2');
  const ids = thread ? [...thread.querySelectorAll('[data-message-id]')].map((e) => e.getAttribute('data-message-id')) : [];
  return {
    hash: location.hash,
    active: [...document.querySelectorAll('[data-conversation-row][data-active]')].map((e) => e.getAttribute('data-conversation-row')),
    head: head ? head.textContent.trim() : null,
    messages: ids.filter((id) => id && !id.startsWith('tmp-')),
    title: document.title,
    banner: !!(thread && thread.textContent.includes('보관한 대화입니다.')),
  };
}
"""


class Run:
    def __init__(self, base: str, label: str):
        self.base = base.rstrip("/")
        self.label = label
        self.rows: list[dict] = []
        self.shots: list[str] = []
        self.out = OUT_DIR / label
        self.out.mkdir(parents=True, exist_ok=True)
        self.page = None
        self.ctx = None
        self.headers: dict = {}

    # ── 기록 ──────────────────────────────────────────────────────────────────────────────────────────
    def record(self, step: str, ok: bool, detail: str = "") -> bool:
        self.rows.append({"step": step, "ok": bool(ok), "detail": detail})
        log(("PASS " if ok else "FAIL ") + step + (f" — {detail}" if detail else ""))
        return ok

    def shot(self, name: str) -> None:
        path = self.out / f"{name}.png"
        self.page.screenshot(path=str(path))
        self.shots.append(path.name)

    # ── API(같은 브라우저 세션) ─────────────────────────────────────────────────────────────────────────
    def get(self, path: str):
        r = self.ctx.request.get(self.base + path)
        return r.status, (r.json() if r.ok else None)

    def send(self, method: str, path: str, body: dict | None = None):
        r = self.ctx.request.fetch(self.base + path, method=method, data=body or {}, headers=self.headers)
        try:
            payload = r.json()
        except Exception:  # noqa: BLE001 - 본문 없는 응답
            payload = None
        return r.status, payload

    def thread_truth(self, cid: str) -> dict:
        status, body = self.get(f"/api/conversations/{cid}/messages")
        if status != 200 or not body:
            return {"status": status}
        return {"status": 200, "title": (body.get("conversation") or {}).get("title"),
                "archived": bool((body.get("conversation") or {}).get("archived")),
                "messages": sorted(str(m["id"]) for m in body.get("items") or [])}

    # ── 판정 ──────────────────────────────────────────────────────────────────────────────────────────
    def state(self) -> dict:
        return self.page.evaluate(STATE_JS)

    def consistent(self, step: str, cid: str, *, row_expected: bool = True, timeout: float = 10.0) -> bool:
        """주소 · 고른 줄 · 머리 · 스레드 · 탭 제목이 모두 `cid` 인가. 화면이 자리를 잡을 때까지 `timeout` 동안 다시 본다."""
        deadline = time.monotonic() + timeout
        problems: list[str] = []
        while True:
            truth = self.thread_truth(cid)
            st = self.state()
            problems = []
            if st["hash"] != f"#/chat/{cid}":
                problems.append(f"주소 {st['hash']}")
            if row_expected and st["active"] != [cid]:
                problems.append(f"고른 줄 {st['active']}")
            if not row_expected and st["active"] and st["active"] != [cid]:
                problems.append(f"다른 줄이 골라짐 {st['active']}")
            if truth.get("status") != 200:
                problems.append(f"API {truth.get('status')}")
            else:
                if st["head"] != truth["title"]:
                    problems.append(f"머리 «{st['head']}» ≠ «{truth['title']}»")
                if sorted(st["messages"]) != truth["messages"]:
                    problems.append(f"스레드 {len(st['messages'])}개 ≠ API {len(truth['messages'])}개")
                if truth["title"] and truth["title"] not in st["title"]:
                    problems.append("탭 제목에 대화 제목이 없음")
            if not problems or time.monotonic() > deadline:
                break
            self.page.wait_for_timeout(400)
        return self.record(step, not problems, "; ".join(problems) or f"대화 {cid[:8]}")

    # ── 화면 조작 ──────────────────────────────────────────────────────────────────────────────────────
    def open_list(self) -> None:
        opener = self.page.locator('#main-content [aria-label="대화 목록 열기"]:visible')
        if opener.count():
            opener.first.click()
            self.page.wait_for_timeout(400)

    def row(self, cid: str):
        return self.page.locator(f'[data-conversation-row="{cid}"] a').first

    def click_row(self, cid: str) -> None:
        self.open_list()
        self.row(cid).click()

    def menu(self, opener_selector: str, item: str) -> None:
        self.page.locator(opener_selector).first.click()
        self.page.wait_for_timeout(300)
        self.page.get_by_role("menuitem", name=item, exact=True).first.click()
        self.page.wait_for_timeout(400)


def login_context(browser, base: str, creds: dict, *, width: int, height: int):
    ctx = browser.new_context(viewport={"width": width, "height": height}, ignore_https_errors=True,
                              locale="ko-KR", timezone_id="Asia/Seoul")
    r = ctx.request.post(f"{base}/login", data={"email": creds["AI_TRUTH_EMAIL"], "password": creds["AI_TRUTH_PASSWORD"]})
    if r.status != 200:
        ctx.close()
        raise LoginError(r.status)
    token = (r.json() or {}).get("csrf_token") or ""
    return ctx, {"X-CSRF-Token": token}


def wait_reply(run: Run, cid: str, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = run.get(f"/api/conversations/{cid}/messages")
        items = (body or {}).get("items") or []
        if items and items[-1].get("role") == "assistant" and items[-1].get("processing_status") == "done":
            return True
        time.sleep(1.5)
    return False


def steps(run: Run, *, local: bool, stamp: str, made: list[str], reply_timeout: float) -> None:
    page = run.page
    # ── 준비 — 로컬은 씨앗 대화 둘(읽기만)과 시험 대화 하나, 랩은 시험 대화 셋(둘은 짧은 질문 하나씩) ────────────────────
    status, listing = run.get("/api/conversations?limit=100")
    items = (listing or {}).get("items") or []
    ids: list[str] = []
    if local:
        for title in LOCAL_READ_ONLY:
            hit = next((c for c in items if c["title"] == title), None)
            if hit is None:
                run.record(f"준비: 씨앗 대화 «{title}»", False, "UI_QA_AI_READY=1 로 띄운 로컬 서버가 아니다")
                return
            ids.append(hit["id"])
    for name in ("A", "B", "C")[len(ids):]:
        status, body = run.send("POST", "/api/conversations", {"title": f"[AI검증] 이동 {name} {stamp}"})
        cid = ((body or {}).get("conversation") or {}).get("id")
        if status != 201 or not cid:
            run.record(f"준비: 시험 대화 {name}", False, f"HTTP {status}")
            return
        made.append(cid)
        ids.append(cid)
    a, b, c = ids
    if not local:
        for cid, question in ((a, "[AI검증] 안녕"), (b, "[AI검증] 반가워")):
            run.send("POST", f"/api/conversations/{cid}/messages",
                     {"content": question, "client_message_id": "chatnav-" + cid[:8] + stamp.replace("-", "")})
        for cid in (a, b):
            run.record("준비: 시험 질문의 답", wait_reply(run, cid, timeout=reply_timeout), cid[:8])

    # ── 첫 진입 — `/chat` 은 초안이다 ───────────────────────────────────────────────────────────────────────
    page.goto(run.base + "/#/chat")
    page.wait_for_timeout(1500)
    st = run.state()
    run.record("첫 진입: /chat 은 초안이다(다른 대화를 저절로 열지 않는다)",
               st["hash"] in ("#/chat", "#/chat/") and not st["active"] and st["head"] == "새 대화",
               f"주소 {st['hash']} · 고른 줄 {st['active']} · 머리 «{st['head']}»")
    run.shot("01-draft")

    # ── 전환 ──────────────────────────────────────────────────────────────────────────────────────────────
    run.click_row(a)
    run.consistent("전환: A", a)
    run.click_row(b)
    run.consistent("전환: B", b)
    run.shot("02-switched")

    # ── 1초 안에 열 번 누르기 ───────────────────────────────────────────────────────────────────────────
    run.open_list()
    started = time.monotonic()
    for cid in (a, b, c, a, b, c, a, b, c, c):
        run.row(cid).click(no_wait_after=True)
    run.record("연타: 열 번을 1초 안에 눌렀다", time.monotonic() - started < 1.5, f"{time.monotonic() - started:.2f}초")
    run.consistent("연타 뒤: 마지막에 누른 C", c)

    # ── 뒤로 · 앞으로 · 새로고침 ─────────────────────────────────────────────────────────────────────────
    page.go_back()
    run.consistent("뒤로: 앞에 누른 B", b)
    page.go_forward()
    run.consistent("앞으로: 다시 C", c)
    page.reload()
    run.consistent("새로고침: 그대로 C", c)

    # ── 이름 바꾸기(시험 대화 C) — 80자 · 특수 문자 ───────────────────────────────────────────────────────
    new_title = f"[AI검증] 이름 <b>&\"' {stamp} " + "가나다라마바사아자차" * 8
    new_title = new_title[:80]
    run.open_list()
    run.menu(f'[data-conversation-row="{c}"] [aria-label^="대화 동작: "]', "이름 바꾸기")
    box = page.locator('#main-content [aria-label^="이름 바꾸기: "]').first
    box.fill(new_title)
    box.press("Enter")
    page.wait_for_timeout(1200)
    truth = run.thread_truth(c)
    run.record("이름 바꾸기: 서버에 그대로 저장됐다", truth.get("title") == new_title, f"«{truth.get('title')}»")
    run.consistent("이름 바꾸기: 머리 · 줄 · 탭 제목이 새 이름", c)
    row_title = page.locator(f'[data-conversation-row="{c}"] [title]').first.get_attribute("title")
    run.record("이름 바꾸기: 줄의 전체 제목(title)이 새 이름", row_title == new_title, f"«{row_title}»")

    # ── 보관 → 보관함 → 꺼내기 ─────────────────────────────────────────────────────────────────────────
    run.menu('section[aria-label="대화"] header [aria-label="대화 동작"]', "보관하기")
    page.wait_for_timeout(1200)
    st = run.state()
    run.record("보관: 지금 대화에 그대로 머물고 안내가 선다", st["hash"] == f"#/chat/{c}" and st["banner"],
               f"주소 {st['hash']} · 안내 {st['banner']}")
    run.consistent("보관: 대화 목록에서 빠져도 머리 · 스레드는 C", c, row_expected=False)
    run.shot("03-archived")
    run.open_list()
    page.locator("#main-content").get_by_role("tab", name="보관함", exact=True).first.click()
    page.wait_for_timeout(1500)
    run.consistent("보관함: C 가 보관함에 서고 골라져 있다", c)
    run.shot("04-archive-view")
    page.locator('section[aria-label="대화"]').get_by_role("button", name="보관함에서 꺼내기").first.click()
    page.wait_for_timeout(1500)
    run.open_list()
    page.locator("#main-content").get_by_role("tab", name="대화", exact=True).first.click()
    page.wait_for_timeout(1500)
    st = run.state()
    run.record("꺼내기: 안내가 걷히고 대화 목록에 다시 선다", not st["banner"] and st["active"] == [c],
               f"안내 {st['banner']} · 고른 줄 {st['active']}")

    # ── 검색 ─────────────────────────────────────────────────────────────────────────────────────────────
    token = stamp if not local else "VMware"
    box = page.locator('#main-content input[type="search"]').first
    box.fill(token)
    page.wait_for_timeout(1800)
    titles = page.locator("[data-conversation-row] [title]").evaluate_all("(els) => els.map((e) => e.getAttribute('title'))")
    run.record(f"검색: «{token}» 로 거른 줄만 남는다", bool(titles) and all(token.lower() in (t or "").lower() for t in titles)
               or (local and bool(titles)), f"{len(titles)}줄")
    run.shot("05-search")
    box.fill("")
    page.wait_for_timeout(1200)

    # ── 새 대화와 첫 전송 — 보내기가 끝나면 주소가 그 대화로 바뀐다(replace) ────────────────────────────────
    page.locator("#main-content").get_by_role("button", name="새 대화").first.click()
    page.wait_for_timeout(800)
    st = run.state()
    run.record("새 대화: 초안 주소와 머리", st["hash"] in ("#/chat", "#/chat/") and st["head"] == "새 대화", st["hash"])
    composer = page.get_by_role("textbox", name="메시지 입력")
    composer.fill(f"[AI검증] 첫 전송 확인 {stamp}")
    composer.press("Enter")
    new_id = None
    for _ in range(40):
        page.wait_for_timeout(250)
        h = run.state()["hash"]
        if h.startswith("#/chat/") and h[len("#/chat/"):] not in ids:
            new_id = h[len("#/chat/"):]
            break
    run.record("첫 전송: 주소가 새 대화로 바뀐다", bool(new_id), str(new_id))
    if new_id:
        made.append(new_id)
        run.consistent("첫 전송: 새 대화가 골라지고 보낸 말이 남는다", new_id)
        page.go_back()
        run.consistent("첫 전송 뒤 뒤로: 빈 초안이 끼지 않고 앞 대화(C)로 간다", c)
        if not local:
            wait_reply(run, new_id, timeout=reply_timeout)

    # ── 두 대화 동시 대기(랩) — 답이 제 대화에만 선다 ────────────────────────────────────────────────────────
    if not local:
        run.click_row(a)
        run.consistent("동시: A 를 연다", a)
        page.get_by_role("textbox", name="메시지 입력").fill("[AI검증] 하나 둘")
        page.get_by_role("textbox", name="메시지 입력").press("Enter")
        page.wait_for_timeout(600)
        run.click_row(b)
        page.get_by_role("textbox", name="메시지 입력").fill("[AI검증] 셋 넷")
        page.get_by_role("textbox", name="메시지 입력").press("Enter")
        both = wait_reply(run, a, timeout=reply_timeout) and wait_reply(run, b, timeout=reply_timeout)
        run.record("동시: 두 대화 모두 답을 받았다", both)
        for cid, mine, other in ((a, "하나 둘", "셋 넷"), (b, "셋 넷", "하나 둘")):
            _, body = run.get(f"/api/conversations/{cid}/messages")
            texts = [m.get("content") or "" for m in (body or {}).get("items") or []]
            run.record(f"동시: {cid[:8]} 에는 제 질문만 있다",
                       any(mine in t for t in texts) and not any(other in t for t in texts), f"{len(texts)}개")
        run.consistent("동시: B 를 보는 화면은 B 의 답이다", b)
        run.click_row(a)
        run.consistent("동시: A 로 돌아오면 A 의 답이다", a)


def mobile_drawer(run: Run, browser, creds: dict, first: str, second: str) -> None:
    ctx, headers = login_context(browser, run.base, creds, width=390, height=844)
    try:
        run.ctx, run.headers, run.page = ctx, headers, ctx.new_page()
        run.page.goto(f"{run.base}/#/chat/{first}")
        run.page.wait_for_timeout(1800)
        run.consistent("휴대폰: 주소로 연 대화", first, row_expected=False)
        run.page.locator('#main-content [aria-label="대화 목록 열기"]').first.click()
        run.page.wait_for_timeout(500)
        drawer = run.page.locator("#chat-conv-drawer")
        run.record("휴대폰: 서랍이 열리고 초점이 안으로 간다",
                   drawer.get_attribute("inert") is None
                   and run.page.evaluate("() => document.getElementById('chat-conv-drawer').contains(document.activeElement)"))
        run.shot("06-mobile-drawer")
        run.row(second).click()
        run.page.wait_for_timeout(800)
        run.record("휴대폰: 줄을 고르면 서랍이 닫힌다", drawer.get_attribute("inert") is not None)
        run.consistent("휴대폰: 고른 대화", second, row_expected=False)
    finally:
        ctx.close()


def render_md(report: dict) -> str:
    lines = [f"# AI 도우미 대화 이동 — {report['label']}", "",
             f"- 대상: {report['base']} · 시각 {report['started']} · {report['summary']}", ""]
    for row in report["rows"]:
        lines.append(f"- {'PASS' if row['ok'] else 'FAIL'} {row['step']}" + (f" — {row['detail']}" if row["detail"] else ""))
    if report.get("shots"):
        lines += ["", "캡처: " + ", ".join(report["shots"])]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--local", action="store_true", help="로컬 씨앗 계정 · 씨앗 대화로 잰다")
    ap.add_argument("--env-file", default=str(ROOT / "dist" / "ops" / "user.env"))
    ap.add_argument("--label", default="chat-nav")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--reply-timeout", type=float, default=240.0)
    args = ap.parse_args(argv)

    from playwright.sync_api import sync_playwright

    creds = LOCAL_CREDS if args.local else read_env_file(args.env_file, ENV_KEYS)
    if not all(creds.get(k) for k in ENV_KEYS):
        log("자격이 없습니다 — env 파일에 AI_TRUTH_EMAIL · AI_TRUTH_PASSWORD 가 있어야 합니다.")
        return 2
    stamp = datetime.now(KST).strftime("%m%d-%H%M%S")
    run = Run(args.base, args.label)
    made: list[str] = []
    report = {"label": args.label, "base": args.base, "started": datetime.now(KST).isoformat(timespec="seconds")}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            ctx, headers = login_context(browser, run.base, creds, width=1920, height=1080)
            run.ctx, run.headers, run.page = ctx, headers, ctx.new_page()
            try:
                steps(run, local=args.local, stamp=stamp, made=made, reply_timeout=args.reply_timeout)
                pair = list(made[:2]) if not args.local else None
                if args.local:
                    _, listing = run.get("/api/conversations?limit=100")
                    hits = [c["id"] for c in (listing or {}).get("items") or [] if c["title"] in LOCAL_READ_ONLY]
                    pair = hits[:2]
                main_ctx = (run.ctx, run.headers, run.page)
                try:
                    if pair and len(pair) == 2:
                        mobile_drawer(run, browser, creds, pair[0], pair[1])
                finally:
                    run.ctx, run.headers, run.page = main_ctx
            except LoginError:
                raise
            except Exception as exc:  # noqa: BLE001 - 끊긴 자리를 기록하고 정리는 한다
                run.record("하네스가 끝까지 돌았다", False, str(exc).splitlines()[0][:300])
            finally:
                if not args.keep:
                    report["deleted"] = [run.send("DELETE", f"/api/conversations/{cid}", {})[0] for cid in made]
                ctx.close()
        except LoginError as exc:
            log(f"로그인 실패: HTTP {exc}")
            return 2
        finally:
            browser.close()
    passed = sum(1 for r in run.rows if r["ok"])
    failed = len(run.rows) - passed
    report.update({"rows": run.rows, "shots": run.shots, "summary": f"pass={passed} fail={failed}"})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{args.label}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (OUT_DIR / f"{args.label}.md").write_text(render_md(report), encoding="utf-8", newline="\n")
    log(f"CHAT_NAV_E2E {'OK' if not failed else 'FAILED'} {report['summary']} → {OUT_DIR / (args.label + '.md')}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
