"""놀이 실브라우저 검증 (기능 개선 회차 P5 · 게임 공통 G8 — D-563 · D-564 · D-575 ~ D-578).

재는 것:
  A. 구슬 레이스 지문(`--digest --map <판>`) — 방장(Chromium)과 참가자(Firefox, `--participant-browser`)가 같은 seed 로 같은 경주를
     계산해 **같은 지문**을 올리고 서버가 `confirmed` 로 확정하는가. 두 화면이 같은 당첨자를 발표하고 축포가 각 화면에서 도는가.
     늦게 들어온 사람은 결과 대화 상자만 열리고(발표 전환 · 축포 없음) 같은 당첨자를 보는가. 다시 하기 뒤 새 결과에서 다시 발표하는가.
  B. 성능(`--perf --perf-n 20 50 100`) — 얼굴이 있는 참가자(씨앗 계정) + 자유 이름으로 경주를 돌려 프레임 시간 p50 · p95, 힙.
  C. 캡처(`--capture`) — 여덟 게임을 「툴바(대기) · 발표 · 공개 · 닫은 뒤의 판 · 다시 열기」, 구슬 레이스는 진행 장면, 그리고 다른 폭 ×
     테마에서 한 장씩. review.html 로 묶는다.
  D. 껍데기 기하(`--layout`) — 여덟 게임 × 1920 · 1366 · 1200 · 1024 · 390 × 밝음 · 어둠: 1200 이상은 문서가 굴러가지 않고 레일 바닥 ==
     판 바닥(±1.5) · 채팅 입력이 화면 안, 모든 폭에서 가로 넘침 0 · 상태 칩이 하나 · 상태 낱말이 페이지에 한 번, 구슬은 캔버스 == 판 틀,
     툴바 한 줄의 컨트롤 높이 · 윗선 같음(`control_row`). 그리고 대기 → 진행 → 종료 동안 판의 사각이 그대로인가(추첨 · 투표 · 구슬).
  E. 전체 화면(`--fullscreen`) — 방 루트가 전체 화면 요소인가(헤드리스가 거절하면 흉내 모드를 잰다), 툴바 「전체 화면 종료」, 결과 대화
     상자 · 축포 캔버스가 루트 안, Esc 로 풀림, 풀린 뒤 캔버스 == 판 틀, 토글 동안 구슬 판 요소가 그대로(엔진을 다시 만들지 않음).

    python -m scripts.ui_qa.local_server --port 8765 --hold                       # 다른 창(씨앗 계정 포함)
    python -m scripts.ui_qa.games_e2e --base-url http://127.0.0.1:8765 --label g1 --layout --capture --fullscreen
    python -m scripts.ui_qa.games_e2e --base-url http://127.0.0.1:8765 --label g1 --digest --participant-browser firefox --map wheel
    python -m scripts.ui_qa.games_e2e --base-url http://127.0.0.1:8765 --label g1 --perf --perf-n 20 50 100

계정은 로컬 서버가 심는 것(`local_server.py::seed`)이다. 원격 설치에는 그 계정이 없으므로 이 하네스는 로컬 전용이다.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import _submit_login  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context, theme_init_script  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "games-e2e"
# 로컬 서버의 씨앗 계정(`scripts/ui_qa/local_server.py` 의 기본값과 같다). 비밀이 아니라 임시 DB 의 시험 계정이다.
LOCAL_PASSWORD = os.environ.get("UI_QA_LOCAL_PASSWORD", "Ui-Qa-Local-1!")
HOST_EMAIL = os.environ.get("UI_QA_EMAIL", "ui-qa@goodmit.co.kr")
PART_EMAIL = "lee.seoyeon@goodmit.co.kr"
LATE_EMAIL = "park.minjun@goodmit.co.kr"
VP = {
    "1920": Viewport("1920x1080", 1920, 1080),
    "1366": Viewport("1366x768", 1366, 768),
    "1200": Viewport("1200x900", 1200, 900),
    "1024": Viewport("1024x768", 1024, 768),
    "390": Viewport("390x844", 390, 844),
}
FILL_VPS = ("1920", "1366", "1200")
CONFETTI_JS = 'Array.from(document.querySelectorAll("canvas")).filter((c) => c.style.position === "fixed").length'
PANEL_JS = '(() => { const p = document.querySelector("[data-result-panel]"); return p ? p.getAttribute("data-result-panel") : null; })()'
WINNERS_JS = 'Array.from(document.querySelectorAll("[data-result-winners] [title]")).map((e) => e.getAttribute("title"))'
FRAMES_JS = """() => new Promise((res) => {
  const d = []; let last = performance.now();
  const f = (t) => { d.push(t - last); last = t; if (d.length < 600) requestAnimationFrame(f); else res(d); };
  requestAnimationFrame(f);
})"""
HEAP_JS = "performance.memory ? performance.memory.usedJSHeapSize : null"
LAYOUT_JS = r"""() => {
  const R = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { l: b.left, t: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height }; };
  const visible = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden' && !el.closest('[hidden]');
  const root = document.querySelector('[data-game-room-layout]');
  const status = Array.from(document.querySelectorAll('[data-room-status]'));
  const label = status[0] ? status[0].textContent.trim() : null;
  const main = document.querySelector('#main-content') || document.body;
  let labelCount = 0;
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode.nodeValue.trim();
    const el = walker.currentNode.parentElement;
    if (label && t === label && el && visible(el) && !el.closest('[aria-hidden="true"]')) labelCount += 1;
  }
  const toolbar = document.querySelector('[data-room-toolbar]');
  const ctrls = toolbar ? Array.from(toolbar.querySelectorAll('.MuiButton-root, .MuiIconButton-root, .k-segmented')).filter(visible).map((e) => ({ text: (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 12), ...R(e) })) : [];
  const input = document.querySelector('input[aria-label="메시지 입력"]');
  return {
    mode: root && root.getAttribute('data-game-room-layout'), fullscreen: root && root.getAttribute('data-fullscreen'),
    vw: innerWidth, vh: innerHeight, docW: document.documentElement.scrollWidth, docH: document.documentElement.scrollHeight,
    board: R(document.querySelector('[data-board-frame]')), rail: R(document.querySelector('[data-game-room-rail]')),
    input: visible(input) ? R(input) : null, statusCount: status.length, label, labelCount,
    canvas: R(document.querySelector('[data-marble-canvas]')), toolbarCtrls: ctrls,
  };
}"""


@dataclass
class Actor:
    name: str
    ctx: object
    page: object
    csrf: str
    user_id: str
    errors: list = field(default_factory=list)
    storage: str | None = None


def log(msg: str) -> None:
    print(msg, flush=True)


def open_actor(browser, base: str, email: str, *, viewport: Viewport, theme: str, name: str, storage_state=None) -> Actor:
    ctx = new_context(browser, storage_state=storage_state, user_id="", theme=theme, viewport=viewport)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    if storage_state is None:
        _submit_login(page, base, email, LOCAL_PASSWORD)
    me = ctx.request.get(base + "/api/me").json()
    uid = me["user"]["id"]
    if storage_state is not None:
        # 저장된 세션은 처음 쓴 사람의 계정별 테마(밝음)를 싣고 온다 — 앱이 그 값을 이긴다(사용자 메뉴의 복원). 문서를 한 번 열어
        # 이 맥락의 테마로 덮고 다시 읽어야 어두운 캡처가 정말 어둡다(예전 캡처의 「어둠」이 밝게 찍힌 까닭).
        page.goto(base + "/", wait_until="domcontentloaded")
        page.evaluate(theme_init_script(theme, uid))
        page.reload(wait_until="domcontentloaded")
    else:
        page.evaluate(theme_init_script(theme, uid))
    # 로그인 인계 판의 축포 캔버스가 사라질 때까지 기다린다 — 그 뒤에 보이는 고정 캔버스만 게임의 축포다.
    try:
        page.wait_for_function('!Array.from(document.querySelectorAll("canvas")).some((c) => c.style.position === "fixed")', timeout=20_000)
    except Exception:
        errors.append("login confetti canvas did not clear within 20s")
    return Actor(name=name, ctx=ctx, page=page, csrf=me["csrf_token"], user_id=uid, errors=errors)


def api(actor: Actor, base: str, method: str, path: str, body=None):
    headers = {"X-CSRF-Token": actor.csrf} if method != "GET" else {}
    r = actor.ctx.request.fetch(base + path, method=method, data=body, headers=headers)
    try:
        payload = r.json()
    except Exception:
        payload = None
    return r.status, payload


def create_room(actor: Actor, base: str, game_type: str, config: dict, title: str, max_players: int = 8) -> str:
    st, j = api(actor, base, "POST", "/api/games/rooms", {
        "title": title, "game_type": game_type, "max_players": max_players, "allow_spectators": True, "config": config,
    })
    if st != 200:
        raise RuntimeError(f"방을 열지 못했다: {st} {j}")
    return j["room"]["id"]


def room_state(actor: Actor, base: str, rid: str) -> dict:
    st, j = api(actor, base, "GET", f"/api/games/rooms/{rid}/state?since=0")
    if st != 200:
        raise RuntimeError(f"상태를 읽지 못했다: {st}")
    return j


def wait_state(actor: Actor, base: str, rid: str, pred, timeout_s: float, every: float = 1.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = room_state(actor, base, rid)
        if pred(last):
            return last
        time.sleep(every)
    raise TimeoutError(f"상태를 기다리다 시간이 지났다: {json.dumps((last or {}).get('state', {}), ensure_ascii=False)[:300]}")


def goto_room(actor: Actor, base: str, rid: str) -> None:
    actor.page.goto(f"{base}/#/games/{rid}", wait_until="domcontentloaded")
    actor.page.wait_for_selector("#main-content", timeout=30_000)
    actor.page.wait_for_selector("[data-board-frame]", timeout=30_000)


def watch_pages(pages: dict, seconds: float) -> dict:
    """여러 화면을 함께 지켜본다 — 결과 대화 상자의 단계와 축포 캔버스(canvas-confetti 가 더하는 고정 캔버스)."""
    seen = {k: {"confetti": 0, "revealed_at": None, "announcing": False} for k in pages}
    t0 = time.time()
    while time.time() - t0 < seconds:
        for key, page in pages.items():
            try:
                n = page.evaluate(CONFETTI_JS)
                phase = page.evaluate(PANEL_JS)
            except Exception:
                continue
            s = seen[key]
            s["confetti"] = max(s["confetti"], int(n or 0))
            if phase == "announcing":
                s["announcing"] = True
            if phase == "revealed" and s["revealed_at"] is None:
                s["revealed_at"] = round(time.time() - t0, 2)
        time.sleep(0.12)
    return seen


def winners_on(page) -> list[str]:
    try:
        return page.evaluate(WINNERS_JS)
    except Exception:
        return []


def close_dialog(page) -> None:
    """결과 대화 상자를 닫는다(열려 있으면). 판의 마지막 장면을 보려면 닫아야 한다."""
    try:
        btn = page.locator('[role="dialog"] button:has-text("닫기")').last
        if btn.count() and btn.is_visible():
            btn.click()
            page.wait_for_selector('[data-result-dialog]', state="detached", timeout=5_000)
    except Exception:
        pass


def dialog_button(page, text: str):
    return page.locator(f'[role="dialog"] button:has-text("{text}")').last


# ── A. 두 브라우저 지문 일치 ─────────────────────────────────────────────────


def run_digest(pw, base: str, out: Path, participant_browser: str, n: int, map_key: str) -> dict:
    chromium = pw.chromium.launch()
    other = getattr(pw, participant_browser).launch()
    vp = VP["1366"]
    host = open_actor(chromium, base, HOST_EMAIL, viewport=vp, theme="light", name="host(chromium)")
    part = open_actor(other, base, PART_EMAIL, viewport=vp, theme="dark", name=f"participant({participant_browser})")
    names = [f"참가자 {i + 1}" for i in range(n)]
    rid = create_room(host, base, "marble_race", {"participants": [{"name": x} for x in names], "winners": 2, "speed": 4, "map": map_key}, f"구슬 레이스 두 브라우저 {map_key}")
    goto_room(host, base, rid)
    goto_room(part, base, rid)
    host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
    part.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
    wait_state(host, base, rid, lambda s: s["room"]["member_count"] >= 2, 20)
    rounds = []
    for round_no in (1, 2):
        if round_no == 2:
            dialog_button(host.page, "다시 하기").click()
            host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=15_000)
            part.page.wait_for_selector('[data-marble-stage="idle"]', timeout=15_000)
        t0 = time.time()
        host.page.click('[data-room-toolbar] button:has-text("경주 시작")')
        host.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
        part.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
        st = wait_state(host, base, rid, lambda s: s["state"].get("phase") in ("finished", "abandoned"), 400)
        elapsed = round(time.time() - t0, 1)
        watched = watch_pages({"host": host.page, "participant": part.page}, 12)
        integ = st["state"].get("integrity") or {}
        subs = st["state"].get("submissions") or []
        digests = {s["role"]: s["digest"] for s in subs}
        row = {
            "round": round_no, "map": map_key, "elapsed_s": elapsed, "phase": st["state"].get("phase"), "integrity": integ,
            "digest_host": digests.get("host"), "digest_attest": digests.get("attest"),
            "digests_equal": bool(digests.get("host")) and digests.get("host") == digests.get("attest"),
            "server_winners": (st["state"].get("result") or {}).get("winners"),
            "host_winners": winners_on(host.page), "participant_winners": winners_on(part.page),
            "watch": watched,
        }
        row["pass"] = bool(
            integ.get("status") == "confirmed" and row["digests_equal"]
            and row["host_winners"] and row["host_winners"] == row["participant_winners"]
            and watched["host"]["confetti"] > 0 and watched["participant"]["confetti"] > 0
            and watched["host"]["revealed_at"] is not None and watched["participant"]["revealed_at"] is not None
        )
        host.page.screenshot(path=str(out / f"digest-{map_key}-round{round_no}-host.png"))
        part.page.screenshot(path=str(out / f"digest-{map_key}-round{round_no}-participant.png"))
        rounds.append(row)
        log(f"[A] {map_key} round {round_no}: phase={row['phase']} integrity={integ.get('status')} equal={row['digests_equal']} "
            f"digest={str(row['digest_host'])[:16]} winners host={row['host_winners']} part={row['participant_winners']} "
            f"confetti={watched['host']['confetti']}/{watched['participant']['confetti']} ({elapsed}s)")
    # 늦게 들어온 사람 — 결과 대화 상자가 바로 열리고(발표 전환 없음) 축포는 없다.
    late = open_actor(chromium, base, LATE_EMAIL, viewport=vp, theme="light", name="late(chromium)")
    goto_room(late, base, rid)
    late.page.wait_for_selector('[data-result-panel="revealed"]', timeout=20_000)
    late_watch = watch_pages({"late": late.page}, 3)["late"]
    late_row = {
        "winners": winners_on(late.page), "confetti": late_watch["confetti"], "announcing": late_watch["announcing"],
        "pass": late_watch["confetti"] == 0 and not late_watch["announcing"] and winners_on(late.page) == rounds[-1]["host_winners"],
    }
    late.page.screenshot(path=str(out / f"digest-{map_key}-late-joiner.png"))
    log(f"[A] late joiner: winners={late_row['winners']} confetti={late_row['confetti']} announcing={late_row['announcing']}")
    errors = {a.name: a.errors for a in (host, part, late)}
    result = {"map": map_key, "rounds": rounds, "late": late_row, "console_errors": errors, "participants": n, "room": rid,
              "pass": all(r["pass"] for r in rounds) and late_row["pass"] and not any(errors.values())}
    for a in (host, part, late):
        a.ctx.close()
    chromium.close()
    other.close()
    return result


# ── B. 성능 ──────────────────────────────────────────────────────────────────


def perf_participants(actor: Actor, base: str, n: int) -> list[dict]:
    """얼굴이 있는 참가자(씨앗 계정 — 사진 또는 기본 그림) + 자유 이름(색 원 + 머리글자)으로 n명."""
    st, j = api(actor, base, "GET", "/api/admin/people?limit=200")
    people = (j or {}).get("items") or [] if st == 200 else []
    out: list[dict] = []
    seen: set[str] = set()
    for p in people:
        if len(out) >= min(n // 2, 40):
            break
        name = (p.get("display_name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "user_id": p["id"]})
    i = 0
    while len(out) < n:
        i += 1
        name = f"구슬 {i}"
        if name not in seen:
            seen.add(name)
            out.append({"name": name})
    return out


def run_perf(pw, base: str, out: Path, sizes: list[int], repeats: int, map_key: str = "wheel") -> dict:
    chromium = pw.chromium.launch()
    host = open_actor(chromium, base, HOST_EMAIL, viewport=VP["1366"], theme="light", name="perf(chromium)")
    by_size = []
    for n in sizes:
        parts = perf_participants(host, base, n)
        faces = sum(1 for p in parts if p.get("user_id"))
        rid = create_room(host, base, "marble_race", {"participants": parts, "winners": 3, "speed": 2, "map": map_key}, f"구슬 레이스 성능 {map_key} {n}")
        goto_room(host, base, rid)
        host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
        runs = []
        for i in range(repeats):
            if i:
                dialog_button(host.page, "다시 하기").click()
                host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=15_000)
            heap0 = host.page.evaluate(HEAP_JS)
            t0 = time.time()
            host.page.click('[data-room-toolbar] button:has-text("경주 시작")')
            host.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
            frames = host.page.evaluate(FRAMES_JS)
            st = wait_state(host, base, rid, lambda s: s["state"].get("phase") in ("finished", "abandoned"), 600, every=2.0)
            elapsed = round(time.time() - t0, 1)
            watch_pages({"host": host.page}, 6)
            heap1 = host.page.evaluate(HEAP_JS)
            srt = sorted(frames)
            p50 = srt[len(srt) // 2]
            p95 = srt[int(len(srt) * 0.95) - 1]
            runs.append({
                "run": i + 1, "frames": len(frames), "frame_p50_ms": round(p50, 1), "frame_p95_ms": round(p95, 1), "frame_max_ms": round(srt[-1], 1),
                "frame_mean_ms": round(statistics.mean(frames), 1), "heap_before_mb": round((heap0 or 0) / 1048576, 1), "heap_after_mb": round((heap1 or 0) / 1048576, 1),
                "elapsed_s": elapsed, "integrity": (st["state"].get("integrity") or {}).get("status"),
            })
            if i == 0:
                host.page.screenshot(path=str(out / f"perf-{map_key}-{n}-finished.png"))
            log(f"[B] {map_key} n={n} (얼굴 {faces}) run {i + 1}: p50={runs[-1]['frame_p50_ms']}ms p95={runs[-1]['frame_p95_ms']}ms "
                f"heap {runs[-1]['heap_before_mb']}→{runs[-1]['heap_after_mb']}MB ({elapsed}s, {runs[-1]['integrity']})")
        heaps = [r["heap_after_mb"] for r in runs]
        by_size.append({
            "map": map_key, "participants": n, "faces": faces, "runs": runs,
            "heap_growth_mb": round(heaps[-1] - heaps[0], 1) if len(heaps) > 1 else 0.0,
            "pass": all(r["frame_p95_ms"] < 25 for r in runs),
        })
    result = {"sizes": by_size, "console_errors": host.errors, "pass": all(s["pass"] for s in by_size) and not host.errors}
    host.ctx.close()
    chromium.close()
    return result


# ── C. 캡처 · D. 기하 ────────────────────────────────────────────────────────

GAMES = [
    ("random_draw", {"winners": 1}, "랜덤 추첨"),
    ("team_split", {"teams": 2}, "랜덤 팀 나누기"),
    ("ladder", {"options": ["당첨", "꽝"]}, "사다리타기"),
    ("quick_vote", {"question": "점심은 무엇으로 할까요?", "options": ["국밥", "파스타", "김밥"]}, "빠른 투표"),
    ("number", {"min": 1, "max": 10}, "숫자 눈치"),
    ("rps", {"mode": "single", "timer_seconds": 0}, "가위바위보"),
    ("quiz", {"questions": [{"q": "1 + 1 은?", "options": ["1", "2", "3"], "answer": 1}], "timer_seconds": 0}, "실시간 퀴즈"),
    ("marble_race", {"participants": [{"name": x} for x in ("김하나", "이두리", "박세찬", "최네온", "정다섯", "한여섯")], "winners": 1, "speed": 4}, "구슬 레이스"),
]


def drive_to_finish(game: str, host: Actor, part: Actor, base: str, rid: str) -> None:
    """방장 · 참가자의 API 호출로 게임을 끝까지 몬다(구슬 레이스는 방장 화면이 계산하므로 툴바의 단추를 누른다)."""
    p = lambda a, path, body=None: api(a, base, "POST", f"/api/games/rooms/{rid}/{path}", body)  # noqa: E731
    if game == "marble_race":
        host.page.click('[data-room-toolbar] button:has-text("경주 시작")')
        return
    p(host, "start")
    if game == "quick_vote":
        p(host, "vote", {"option": 1}); p(part, "vote", {"option": 1}); p(host, "finish")
    elif game == "number":
        p(host, "pick", {"value": 3}); p(part, "pick", {"value": 7}); p(host, "finish")
    elif game == "rps":
        p(host, "rps", {"option": 1}); p(part, "rps", {"option": 0}); p(host, "finish")
    elif game == "quiz":
        p(host, "quiz-answer", {"option": 1}); p(part, "quiz-answer", {"option": 0}); p(host, "reveal"); p(host, "next")


def layout_checks(geo: dict, vkey: str, game: str) -> dict:
    """한 장면의 기하 판정. 실패한 항목만 `fails` 에 이름으로 남는다."""
    fails: list[str] = []
    fill = vkey in FILL_VPS
    if geo["docW"] > geo["vw"] + 1:
        fails.append(f"h_overflow({geo['docW']}>{geo['vw']})")
    if fill:
        if geo["mode"] != "fill":
            fails.append(f"mode={geo['mode']}")
        if geo["docH"] > geo["vh"] + 1:
            fails.append(f"doc_scroll({geo['docH']}>{geo['vh']})")
        if geo["board"] and geo["rail"] and abs(geo["board"]["b"] - geo["rail"]["b"]) > 1.5:
            fails.append(f"rail_bottom({round(geo['rail']['b'], 1)}≠{round(geo['board']['b'], 1)})")
        if not geo["input"] or geo["input"]["b"] > geo["vh"] or geo["input"]["t"] < 0:
            fails.append("chat_input_outside")
    if geo["statusCount"] != 1:
        fails.append(f"status_chips={geo['statusCount']}")
    if geo["labelCount"] != 1:
        fails.append(f"status_text×{geo['labelCount']}")
    if game == "marble_race" and geo["canvas"] and geo["board"]:
        c, b = geo["canvas"], geo["board"]
        if abs(c["w"] - b["w"]) > 2.5 or abs(c["h"] - b["h"]) > 2.5:
            fails.append(f"canvas≠frame({round(c['w'])}x{round(c['h'])} vs {round(b['w'])}x{round(b['h'])})")
    # 툴바 한 줄 — 같은 줄(윗선 ±8)에 선 컨트롤의 높이 · 윗선이 1px 안에서 같다.
    rows: list[list[dict]] = []
    for ctrl in sorted(geo["toolbarCtrls"], key=lambda x: x["t"]):
        for row in rows:
            if abs(row[0]["t"] - ctrl["t"]) <= 8:
                row.append(ctrl)
                break
        else:
            rows.append([ctrl])
    for row in rows:
        hs = [x["h"] for x in row]
        ts = [x["t"] for x in row]
        if max(hs) - min(hs) > 1 or max(ts) - min(ts) > 1:
            fails.append("control_row(" + ",".join(f"{x['text']}:{round(x['h'])}@{round(x['t'])}" for x in row) + ")")
    return {"fails": fails, "pass": not fails}


def run_layout(pw, base: str, out: Path) -> dict:
    chromium = pw.chromium.launch()
    host = open_actor(chromium, base, HOST_EMAIL, viewport=VP["1366"], theme="light", name="layout-host")
    part = open_actor(chromium, base, PART_EMAIL, viewport=VP["1366"], theme="light", name="layout-part")
    storage = out / "host-storage.json"
    host.ctx.storage_state(path=str(storage))
    rooms: dict[str, str] = {}
    for game, config, label in GAMES:
        rid = create_room(host, base, game, config, f"{label} 기하")
        api(part, base, "POST", f"/api/games/rooms/{rid}/join")
        rooms[game] = rid
    rows = []
    errors: list[str] = []
    for vkey in ("1920", "1366", "1200", "1024", "390"):
        for theme in ("light", "dark"):
            a = open_actor(chromium, base, HOST_EMAIL, viewport=VP[vkey], theme=theme, name=f"layout-{vkey}-{theme}", storage_state=str(storage))
            for game, _, label in GAMES:
                goto_room(a, base, rooms[game])
                a.page.wait_for_timeout(900)
                geo = a.page.evaluate(LAYOUT_JS)
                if vkey == "390":
                    # 모바일은 「참여자 | 채팅」 탭 — 채팅 탭을 고르면 입력 칸이 선다.
                    try:
                        a.page.click('[data-room-rail="mobile"] [role="tab"]:has-text("채팅")')
                        a.page.wait_for_timeout(250)
                        geo["mobile_chat_input"] = a.page.evaluate(LAYOUT_JS)["input"]
                    except Exception:
                        geo["mobile_chat_input"] = None
                verdict = layout_checks(geo, vkey, game)
                if vkey == "390" and not geo.get("mobile_chat_input"):
                    verdict["fails"].append("mobile_chat_tab_no_input")
                    verdict["pass"] = False
                shot = out / f"layout-{game}-{vkey}-{theme}.png"
                a.page.screenshot(path=str(shot))
                rows.append({"game": game, "viewport": vkey, "theme": theme, "mode": geo["mode"], "board": geo["board"], "rail": geo["rail"],
                             "doc": [geo["docW"], geo["docH"]], "file": shot.name, **verdict})
                log(f"[D] {game:<12} {vkey:>4} {theme:<5} mode={geo['mode']:<6} {'PASS' if verdict['pass'] else 'FAIL ' + ','.join(verdict['fails'])}")
            errors += a.errors
            a.ctx.close()
    stability = run_stability(chromium, base, host, part, out)
    errors += host.errors + part.errors
    host.ctx.close()
    part.ctx.close()
    chromium.close()
    return {"rows": rows, "stability": stability, "console_errors": errors,
            "pass": all(r["pass"] for r in rows) and all(s["pass"] for s in stability) and not errors}


def run_stability(chromium, base: str, host: Actor, part: Actor, out: Path) -> list[dict]:
    """대기 → 진행 → 종료 동안 판의 사각이 그대로인가 — 채움(1366)과 흐름(1024)에서 추첨 · 투표 · 구슬."""
    rect_js = "(() => { const b = document.querySelector('[data-board-frame]').getBoundingClientRect(); return [b.left, b.top, b.width, b.height].map((v) => Math.round(v * 10) / 10); })()"
    results = []
    for vkey in ("1366", "1024"):
        storage = out / "host-storage.json"
        a = open_actor(chromium, base, HOST_EMAIL, viewport=VP[vkey], theme="light", name=f"stab-{vkey}", storage_state=str(storage))
        for game, config, label in [g for g in GAMES if g[0] in ("random_draw", "quick_vote", "marble_race")]:
            rid = create_room(host, base, game, config, f"{label} 판 사각")
            api(part, base, "POST", f"/api/games/rooms/{rid}/join")
            goto_room(a, base, rid)
            a.page.wait_for_timeout(900)
            rects = {"waiting": a.page.evaluate(rect_js)}
            p = lambda path, body=None: api(host, base, "POST", f"/api/games/rooms/{rid}/{path}", body)  # noqa: E731
            if game == "quick_vote":
                p("start")
                a.page.wait_for_selector('[data-vote-board="playing"]', timeout=10_000)
                rects["playing"] = a.page.evaluate(rect_js)
                api(part, base, "POST", f"/api/games/rooms/{rid}/vote", {"option": 0})
                p("finish")
            elif game == "random_draw":
                p("start")
            else:
                a.page.click('[data-room-toolbar] button:has-text("경주 시작")')
                a.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
                a.page.wait_for_timeout(1500)
                rects["playing"] = a.page.evaluate(rect_js)
            a.page.wait_for_selector('[data-result-panel="revealed"]', timeout=120_000)
            rects["finished"] = a.page.evaluate(rect_js)
            close_dialog(a.page)
            rects["closed"] = a.page.evaluate(rect_js)
            vals = list(rects.values())
            ok = all(max(abs(v[i] - vals[0][i]) for v in vals) <= 1 for i in range(4))
            results.append({"game": game, "viewport": vkey, "rects": rects, "pass": ok})
            log(f"[D] 판 사각 {game:<12} {vkey}: {'PASS' if ok else 'FAIL'} {rects}")
        a.ctx.close()
    return results


def run_capture(pw, base: str, out: Path) -> dict:
    chromium = pw.chromium.launch()
    live_vp = VP["1366"]
    host = open_actor(chromium, base, HOST_EMAIL, viewport=live_vp, theme="light", name="capture-host")
    part = open_actor(chromium, base, PART_EMAIL, viewport=live_vp, theme="light", name="capture-part")
    host_storage = out / "host-storage.json"
    host.ctx.storage_state(path=str(host_storage))
    shots: list[dict] = []
    rooms: dict[str, str] = {}

    def shot(game, moment, vkey="1366", theme="light", page=None, value=None, full=False):
        path = out / f"{game}-{moment}-{vkey}-{theme}.png"
        (page or host.page).screenshot(path=str(path), full_page=full)
        shots.append({"game": game, "moment": moment, "viewport": vkey, "theme": theme, "file": path.name, "value": value})

    for game, config, label in GAMES:
        rid = create_room(host, base, game, config, f"{label} 캡처")
        rooms[game] = rid
        api(part, base, "POST", f"/api/games/rooms/{rid}/join")
        goto_room(host, base, rid)
        host.page.wait_for_timeout(1500)
        shot(game, "toolbar")
        if game == "marble_race":
            # 참가자는 좁은 화면(390)으로 같은 경주를 본다 — 슬로 모션 표지가 미니맵 옆에 서고 선두 칩과 겹치지 않는지 두 폭에서 본다.
            part.page.set_viewport_size({"width": VP["390"].width, "height": VP["390"].height})
            goto_room(part, base, rid)
            part.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
        drive_to_finish(game, host, part, base, rid)
        moments = {"announce": False, "reveal": False, "confetti": 0, "closed": False, "reopen": False}
        if game == "marble_race":
            host.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
            host.page.wait_for_timeout(2500)
            shot(game, "running")
            moments["slowmo"] = False
            try:
                host.page.wait_for_selector("[data-slowmo]", timeout=90_000)
                shot(game, "slowmo")
                moments["slowmo"] = True
                part.page.wait_for_selector("[data-slowmo]", timeout=5_000)
                shot(game, "slowmo", "390", page=part.page)
            except Exception:
                pass
        try:
            host.page.wait_for_selector('[data-result-panel="announcing"]', timeout=120_000 if game == "marble_race" else 8_000)
            shot(game, "dialog-announce")
            moments["announce"] = True
        except Exception:
            pass
        host.page.wait_for_selector('[data-result-panel="revealed"]', timeout=120_000)
        host.page.wait_for_timeout(450)
        moments["reveal"] = True
        moments["confetti"] = int(host.page.evaluate(CONFETTI_JS) or 0)
        shot(game, "dialog-reveal", value=moments["confetti"])
        host.page.wait_for_timeout(4500)
        close_dialog(host.page)
        host.page.wait_for_timeout(600)
        moments["closed"] = host.page.locator('[data-result-dialog]').count() == 0
        shot(game, "dialog-closed-board")
        try:
            host.page.click('[data-room-toolbar] button:has-text("결과 보기")')
            host.page.wait_for_selector('[data-result-panel="revealed"]', timeout=5_000)
            host.page.wait_for_timeout(500)
            moments["reopen"] = host.page.evaluate(PANEL_JS) == "revealed"
            shot(game, "dialog-reopen", value=int(host.page.evaluate(CONFETTI_JS) or 0))
            close_dialog(host.page)
        except Exception:
            moments["reopen"] = False
        # 다른 폭 × 테마 — 끝난 방을 처음 여는 사람의 장면(발표 전환 없이 대화 상자가 열린다), 그리고 닫은 뒤의 판.
        for vkey, theme in (("1920", "light"), ("1920", "dark"), ("1366", "dark"), ("1200", "light"), ("1024", "light"), ("390", "light"), ("390", "dark")):
            a = open_actor(chromium, base, HOST_EMAIL, viewport=VP[vkey], theme=theme, name="shot", storage_state=str(host_storage))
            goto_room(a, base, rid)
            a.page.wait_for_selector('[data-result-panel="revealed"]', timeout=60_000)
            a.page.wait_for_timeout(900)
            shot(game, "final-dialog", vkey, theme, page=a.page)
            close_dialog(a.page)
            a.page.wait_for_timeout(500)
            shot(game, "final-board", vkey, theme, page=a.page)
            a.ctx.close()
        log(f"[C] {label}: announce={moments['announce']} reveal={moments['reveal']} confetti_canvases={moments['confetti']} "
            f"closed={moments['closed']} reopen={moments['reopen']}" + (f" slowmo={moments['slowmo']}" if "slowmo" in moments else ""))
    errors = {"host": host.errors, "part": part.errors}
    html = ["<!doctype html><meta charset='utf-8'><title>games-e2e review</title><body style='font-family:sans-serif;background:#f4f4f8'>"]
    for game, _, label in GAMES:
        html.append(f"<h2>{label}</h2><div style='display:flex;flex-wrap:wrap;gap:12px'>")
        for s in shots:
            if s["game"] != game:
                continue
            html.append(f"<figure style='margin:0;max-width:420px'><img src='{s['file']}' style='max-width:420px;border:1px solid #ccc'><figcaption>{s['moment']} {s['viewport']} {s['theme']}</figcaption></figure>")
        html.append("</div>")
    (out / "review.html").write_text("\n".join(html), encoding="utf-8")
    host.ctx.close()
    part.ctx.close()
    chromium.close()
    return {"shots": shots, "rooms": rooms, "console_errors": errors, "pass": not any(errors.values())}


# ── E. 전체 화면 ─────────────────────────────────────────────────────────────

FS_JS = r"""() => {
  const root = document.querySelector('[data-game-room-layout]');
  const dialog = document.querySelector('[data-result-dialog]');
  const canvas = document.querySelector('[data-celebrate-canvas]');
  const toolbar = document.querySelector('[data-room-toolbar]');
  const stage = document.querySelector('[data-marble-stage]');
  const frame = document.querySelector('[data-board-frame]');
  const mc = document.querySelector('[data-marble-canvas]');
  const R = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height)]; };
  return {
    native: !!document.fullscreenElement && document.fullscreenElement === root,
    attr: root && root.getAttribute('data-fullscreen'), mode: root && root.getAttribute('data-fullscreen-mode'),
    toolbarText: toolbar ? toolbar.textContent : '', dialogInRoot: !!(dialog && root && root.contains(dialog)),
    canvasInRoot: !!(canvas && root && root.contains(canvas)), probe: !!(stage && stage.__probe === 7),
    frame: R(frame), canvas: R(mc), layout: root && root.getAttribute('data-game-room-layout'),
  };
}"""


def run_fullscreen(pw, base: str, out: Path) -> dict:
    chromium = pw.chromium.launch()
    host = open_actor(chromium, base, HOST_EMAIL, viewport=VP["1366"], theme="light", name="fs-host")
    rows = []
    for game, config, label in [g for g in GAMES if g[0] in ("marble_race", "random_draw")]:
        rid = create_room(host, base, game, config, f"{label} 전체 화면")
        goto_room(host, base, rid)
        host.page.wait_for_timeout(1000)
        page = host.page
        page.evaluate("() => { const s = document.querySelector('[data-marble-stage]'); if (s) s.__probe = 7; }")
        page.click('[data-room-toolbar] button:has-text("전체 화면")')
        page.wait_for_timeout(900)
        on = page.evaluate(FS_JS)
        page.screenshot(path=str(out / f"fullscreen-{game}-on.png"))
        # 판을 끝까지 — 결과 대화 상자 · 축포 캔버스가 루트 안에 서는가.
        if game == "marble_race":
            page.click('[data-room-toolbar] button:has-text("경주 시작")')
        else:
            api(host, base, "POST", f"/api/games/rooms/{rid}/start")
        page.wait_for_selector('[data-result-panel="revealed"]', timeout=120_000)
        page.wait_for_timeout(300)
        mid = page.evaluate(FS_JS)
        page.screenshot(path=str(out / f"fullscreen-{game}-dialog.png"))
        # Esc — 먼저 대화 상자가 닫히고, 다음 Esc 가 전체 화면을 푼다.
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        after_first = page.evaluate(FS_JS)
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)
        off = page.evaluate(FS_JS)
        escape_exit = off["attr"] == "off"
        if not escape_exit:
            page.click('[data-room-toolbar] button:has-text("전체 화면 종료")')
            page.wait_for_timeout(900)
            off = page.evaluate(FS_JS)
        page.screenshot(path=str(out / f"fullscreen-{game}-off.png"))
        native = on["native"]
        checks = {
            "entered": on["attr"] == "on" and (native or on["mode"] == "pseudo"),
            "toolbar_exit_label": "전체 화면 종료" in on["toolbarText"],
            "dialog_in_root": mid["dialogInRoot"] if native else True,
            "confetti_canvas_in_root": mid["canvasInRoot"],
            "first_escape_closes_dialog": after_first["attr"] == "on" and not page.locator('[data-result-dialog]').count(),
            "escape_exits": escape_exit,
            "exited": off["attr"] == "off",
            "canvas_equals_frame": (game != "marble_race") or (off["canvas"] and off["frame"] and abs(off["canvas"][0] - (off["frame"][0] - 2)) <= 3 and abs(off["canvas"][1] - (off["frame"][1] - 2)) <= 3),
            "stage_not_remounted": (game != "marble_race") or (on["probe"] and off["probe"]),
        }
        row = {"game": game, "native": native, "mode": on["mode"], "layout_on": on["layout"], "checks": checks, "pass": all(checks.values())}
        rows.append(row)
        log(f"[E] {game}: native={native} mode={on['mode']} {checks}")
    errors = host.errors
    host.ctx.close()
    chromium.close()
    return {"rows": rows, "console_errors": errors, "pass": all(r["pass"] for r in rows) and not errors}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--label", default="r1")
    ap.add_argument("--digest", action="store_true")
    ap.add_argument("--perf", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--layout", action="store_true")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--participant-browser", default="firefox", choices=["firefox", "chromium", "webkit"])
    ap.add_argument("--map", default="wheel", choices=["wheel", "pot", "bubble", "yoru"])
    ap.add_argument("--marble-n", type=int, default=12)
    ap.add_argument("--perf-n", type=int, nargs="+", default=[100])
    ap.add_argument("--perf-repeats", type=int, default=2)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    out = Path(args.out) / args.label
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    report = {"base_url": base, "label": args.label, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with sync_playwright() as pw:
        if args.layout:
            report["layout"] = run_layout(pw, base, out)
        if args.fullscreen:
            report["fullscreen"] = run_fullscreen(pw, base, out)
        if args.digest:
            report[f"digest_{args.map}"] = run_digest(pw, base, out, args.participant_browser, args.marble_n, args.map)
        if args.perf:
            report[f"perf_{args.map}"] = run_perf(pw, base, out, args.perf_n, args.perf_repeats, args.map)
        if args.capture:
            report["capture"] = run_capture(pw, base, out)
    verdicts = {k: v.get("pass") for k, v in report.items() if isinstance(v, dict) and "pass" in v}
    report["pass"] = all(verdicts.values()) if verdicts else False
    name = f"report-digest-{args.map}.json" if args.digest else f"report-perf-{args.map}.json" if args.perf else "report.json"
    (out / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[games_e2e] {verdicts} → {'PASS' if report['pass'] else 'FAIL'} ({out})")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
