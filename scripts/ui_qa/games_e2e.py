"""놀이 실브라우저 검증 (기능 개선 회차 P5, D-563 · D-564).

재는 것 셋:
  A. 구슬 레이스 — 방장(Chromium)과 참가자(Firefox, `--participant-browser`)가 같은 seed 로 같은 경주를 계산해 **같은 지문**을
     올리고 서버가 `confirmed` 로 확정하는가. 두 화면이 같은 당첨자를 발표하고 축포(캔버스)가 각 화면에서 도는가. 늦게 들어온
     사람은 결과만 보고 축포가 없는가(D-563). 다시 하기 뒤 새 결과에서 다시 발표하는가. 콘솔 오류 0.
  B. 성능 — 참가자 100명 경주에서 프레임 시간 p50 · p95, 힙 전후, 3회 반복 뒤 힙(Chromium 의 performance.memory).
  C. 캡처 — 여덟 게임의 결과 화면을 「발표 시작 · 당첨자 공개 · 축포 중 · 종료 뒤」 네 순간으로, 그리고 다른 폭 × 테마는 종료 뒤
     한 장씩 찍어 review.html 로 묶는다. 구슬 레이스는 대기 · 진행 · 종료도 찍는다.

    python -m scripts.ui_qa.local_server --port 8765 --hold                       # 다른 창(씨앗 계정 포함)
    python -m scripts.ui_qa.games_e2e --base-url http://127.0.0.1:8765 --label r1 --digest --perf --capture

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
    "1366": Viewport("1366x768", 1366, 768),
    "1920": Viewport("1920x1080", 1920, 1080),
    "390": Viewport("390x844", 390, 844),
}
CONFETTI_JS = 'Array.from(document.querySelectorAll("canvas")).filter((c) => c.style.position === "fixed").length'
PANEL_JS = '(() => { const p = document.querySelector("[data-result-panel]"); return p ? p.getAttribute("data-result-panel") : null; })()'
WINNERS_JS = 'Array.from(document.querySelectorAll("[data-result-winners] [title]")).map((e) => e.getAttribute("title"))'
FRAMES_JS = """() => new Promise((res) => {
  const d = []; let last = performance.now();
  const f = (t) => { d.push(t - last); last = t; if (d.length < 600) requestAnimationFrame(f); else res(d); };
  requestAnimationFrame(f);
})"""
HEAP_JS = "performance.memory ? performance.memory.usedJSHeapSize : null"


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


def watch_pages(pages: dict, seconds: float) -> dict:
    """여러 화면을 함께 지켜본다 — 결과 판 단계와 축포 캔버스(canvas-confetti 가 더하는 role 없는 캔버스)."""
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


# ── A. 두 브라우저 지문 일치 ─────────────────────────────────────────────────


def run_digest(pw, base: str, out: Path, participant_browser: str, n: int) -> dict:
    chromium = pw.chromium.launch()
    other = getattr(pw, participant_browser).launch()
    vp = VP["1366"]
    host = open_actor(chromium, base, HOST_EMAIL, viewport=vp, theme="light", name="host(chromium)")
    part = open_actor(other, base, PART_EMAIL, viewport=vp, theme="dark", name=f"participant({participant_browser})")
    names = [f"참가자 {i + 1}" for i in range(n)]
    rid = create_room(host, base, "marble_race", {"participants": [{"name": x} for x in names], "winners": 2, "speed": 4}, "구슬 레이스 두 브라우저")
    goto_room(host, base, rid)
    goto_room(part, base, rid)
    host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
    part.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
    wait_state(host, base, rid, lambda s: s["room"]["member_count"] >= 2, 20)
    rounds = []
    for round_no in (1, 2):
        if round_no == 2:
            host.page.click('button:has-text("다시 하기")')
            host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=15_000)
            part.page.wait_for_selector('[data-marble-stage="idle"]', timeout=15_000)
        t0 = time.time()
        host.page.click('button:has-text("경주 시작")')
        host.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
        part.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
        st = wait_state(host, base, rid, lambda s: s["state"].get("phase") in ("finished", "abandoned"), 240)
        elapsed = round(time.time() - t0, 1)
        watched = watch_pages({"host": host.page, "participant": part.page}, 12)
        integ = st["state"].get("integrity") or {}
        subs = st["state"].get("submissions") or []
        digests = {s["role"]: s["digest"] for s in subs}
        row = {
            "round": round_no, "elapsed_s": elapsed, "phase": st["state"].get("phase"), "integrity": integ,
            "digest_host": digests.get("host"), "digest_attest": digests.get("attest"),
            "digests_equal": bool(digests.get("host")) and digests.get("host") == digests.get("attest"),
            "server_winners": (st["state"].get("result") or {}).get("winners"),
            "host_winners": winners_on(host.page), "participant_winners": winners_on(part.page),
            "watch": watched,
        }
        row["pass"] = (
            integ.get("status") == "confirmed" and row["digests_equal"]
            and row["host_winners"] and row["host_winners"] == row["participant_winners"]
            and watched["host"]["confetti"] > 0 and watched["participant"]["confetti"] > 0
            and watched["host"]["revealed_at"] is not None and watched["participant"]["revealed_at"] is not None
        )
        host.page.screenshot(path=str(out / f"digest-round{round_no}-host.png"))
        part.page.screenshot(path=str(out / f"digest-round{round_no}-participant.png"))
        rounds.append(row)
        log(f"[A] round {round_no}: phase={row['phase']} integrity={integ.get('status')} equal={row['digests_equal']} "
            f"winners host={row['host_winners']} part={row['participant_winners']} confetti={watched['host']['confetti']}/{watched['participant']['confetti']} ({elapsed}s)")
    # 늦게 들어온 사람 — 결과는 바로, 축포는 없다.
    late = open_actor(chromium, base, LATE_EMAIL, viewport=vp, theme="light", name="late(chromium)")
    goto_room(late, base, rid)
    late.page.wait_for_selector('[data-result-panel="revealed"]', timeout=20_000)
    late_watch = watch_pages({"late": late.page}, 3)["late"]
    late_row = {
        "winners": winners_on(late.page), "confetti": late_watch["confetti"], "announcing": late_watch["announcing"],
        "pass": late_watch["confetti"] == 0 and not late_watch["announcing"] and winners_on(late.page) == rounds[-1]["host_winners"],
    }
    late.page.screenshot(path=str(out / "digest-late-joiner.png"))
    log(f"[A] late joiner: winners={late_row['winners']} confetti={late_row['confetti']} announcing={late_row['announcing']}")
    errors = {a.name: a.errors for a in (host, part, late)}
    result = {"rounds": rounds, "late": late_row, "console_errors": errors, "participants": n, "room": rid,
              "pass": all(r["pass"] for r in rounds) and late_row["pass"] and not any(errors.values())}
    for a in (host, part, late):
        a.ctx.close()
    chromium.close()
    other.close()
    return result


# ── B. 성능 ──────────────────────────────────────────────────────────────────


def run_perf(pw, base: str, out: Path, n: int, repeats: int) -> dict:
    chromium = pw.chromium.launch()
    host = open_actor(chromium, base, HOST_EMAIL, viewport=VP["1366"], theme="light", name="perf(chromium)")
    rid = create_room(host, base, "marble_race", {"participants": [{"name": f"구슬 {i + 1}"} for i in range(n)], "winners": 3, "speed": 2}, "구슬 레이스 성능")
    goto_room(host, base, rid)
    host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
    runs = []
    for i in range(repeats):
        if i:
            host.page.click('button:has-text("다시 하기")')
            host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=15_000)
        heap0 = host.page.evaluate(HEAP_JS)
        t0 = time.time()
        host.page.click('button:has-text("경주 시작")')
        host.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
        frames = host.page.evaluate(FRAMES_JS)
        st = wait_state(host, base, rid, lambda s: s["state"].get("phase") in ("finished", "abandoned"), 400, every=2.0)
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
            host.page.screenshot(path=str(out / "perf-100-finished.png"))
        log(f"[B] run {i + 1}: p50={runs[-1]['frame_p50_ms']}ms p95={runs[-1]['frame_p95_ms']}ms heap {runs[-1]['heap_before_mb']}→{runs[-1]['heap_after_mb']}MB ({elapsed}s, {runs[-1]['integrity']})")
    heaps = [r["heap_after_mb"] for r in runs]
    result = {
        "participants": n, "runs": runs, "console_errors": host.errors,
        "heap_growth_mb": round(heaps[-1] - heaps[0], 1) if len(heaps) > 1 else 0.0,
        "pass": all(r["frame_p95_ms"] < 25 for r in runs) and not host.errors,
    }
    host.ctx.close()
    chromium.close()
    return result


# ── C. 캡처 ──────────────────────────────────────────────────────────────────

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
    """방장 · 참가자의 API 호출로 게임을 끝까지 몬다(구슬 레이스는 방장 화면이 계산하므로 화면의 단추를 누른다)."""
    p = lambda a, path, body=None: api(a, base, "POST", f"/api/games/rooms/{rid}/{path}", body)  # noqa: E731
    if game == "marble_race":
        host.page.click('button:has-text("경주 시작")')
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


def run_capture(pw, base: str, out: Path) -> dict:
    chromium = pw.chromium.launch()
    live_vp = VP["1366"]
    host = open_actor(chromium, base, HOST_EMAIL, viewport=live_vp, theme="light", name="capture-host")
    part = open_actor(chromium, base, PART_EMAIL, viewport=live_vp, theme="light", name="capture-part")
    host_storage = out / "host-storage.json"
    host.ctx.storage_state(path=str(host_storage))
    shots: list[dict] = []
    rooms: dict[str, str] = {}
    for game, config, label in GAMES:
        rid = create_room(host, base, game, config, f"{label} 캡처")
        rooms[game] = rid
        api(part, base, "POST", f"/api/games/rooms/{rid}/join")
        goto_room(host, base, rid)
        host.page.wait_for_selector("[data-head-row], .k-badge", timeout=20_000)
        host.page.wait_for_timeout(1500)
        if game == "marble_race":
            host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
            host.page.wait_for_timeout(600)
            path = out / f"{game}-waiting-1366-light.png"
            host.page.screenshot(path=str(path), full_page=True)
            shots.append({"game": game, "moment": "waiting", "viewport": "1366", "theme": "light", "file": path.name})
        drive_to_finish(game, host, part, base, rid)
        if game == "marble_race":
            host.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
            host.page.wait_for_timeout(2500)
            path = out / f"{game}-running-1366-light.png"
            host.page.screenshot(path=str(path), full_page=True)
            shots.append({"game": game, "moment": "running", "viewport": "1366", "theme": "light", "file": path.name})
        # 네 순간 — 발표 시작 · 당첨자 공개 · 축포 중 · 종료 뒤. 발표 전환은 0.8초라 놓칠 수 있다(놓치면 기록만).
        moments = {"announce": False, "reveal": False, "confetti": False, "after": False}
        try:
            host.page.wait_for_selector('[data-result-panel="announcing"]', timeout=90_000 if game == "marble_race" else 8_000)
            host.page.screenshot(path=str(out / f"{game}-announce-1366-light.png"), full_page=True)
            moments["announce"] = True
        except Exception:
            pass
        host.page.wait_for_selector('[data-result-panel="revealed"]', timeout=120_000)
        host.page.screenshot(path=str(out / f"{game}-reveal-1366-light.png"), full_page=True)
        moments["reveal"] = True
        host.page.wait_for_timeout(500)
        moments["confetti"] = int(host.page.evaluate(CONFETTI_JS) or 0)
        host.page.screenshot(path=str(out / f"{game}-confetti-1366-light.png"), full_page=True)
        host.page.wait_for_timeout(5000)
        moments["after"] = int(host.page.evaluate(CONFETTI_JS) or 0) == 0
        host.page.screenshot(path=str(out / f"{game}-after-1366-light.png"), full_page=True)
        for m in ("announce", "reveal", "confetti", "after"):
            shots.append({"game": game, "moment": m, "viewport": "1366", "theme": "light", "file": f"{game}-{m}-1366-light.png", "value": moments[m]})
        # 다른 폭 × 테마 — 끝난 뒤 한 장씩(늦은 입장과 같은 장면이라 발표 전환 없이 결과다).
        for vkey, theme in (("1920", "light"), ("1920", "dark"), ("1366", "dark"), ("390", "light"), ("390", "dark")):
            a = open_actor(chromium, base, HOST_EMAIL, viewport=VP[vkey], theme=theme, name="shot", storage_state=str(host_storage))
            goto_room(a, base, rid)
            a.page.wait_for_selector('[data-result-panel="revealed"]', timeout=60_000)
            a.page.wait_for_timeout(900)
            path = out / f"{game}-final-{vkey}-{theme}.png"
            a.page.screenshot(path=str(path), full_page=True)
            shots.append({"game": game, "moment": "final", "viewport": vkey, "theme": theme, "file": path.name})
            a.ctx.close()
        log(f"[C] {label}: announce={moments['announce']} reveal={moments['reveal']} confetti_canvases={moments['confetti']} cleared={moments['after']}")
    # 구슬 레이스 100명 대기 장면(라벨 축소 · 격자)과 전체 화면 요청 버튼은 Flow B 와 수동 관찰에 맡긴다.
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
    ap.add_argument("--participant-browser", default="firefox", choices=["firefox", "chromium", "webkit"])
    ap.add_argument("--marble-n", type=int, default=12)
    ap.add_argument("--perf-n", type=int, default=100)
    ap.add_argument("--perf-repeats", type=int, default=3)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    out = Path(args.out) / args.label
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    report = {"base_url": base, "label": args.label, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with sync_playwright() as pw:
        if args.digest:
            report["digest"] = run_digest(pw, base, out, args.participant_browser, args.marble_n)
        if args.perf:
            report["perf"] = run_perf(pw, base, out, args.perf_n, args.perf_repeats)
        if args.capture:
            report["capture"] = run_capture(pw, base, out)
    verdicts = {k: v.get("pass") for k, v in report.items() if isinstance(v, dict) and "pass" in v}
    report["pass"] = all(verdicts.values()) if verdicts else False
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[games_e2e] {verdicts} → {'PASS' if report['pass'] else 'FAIL'} ({out})")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
