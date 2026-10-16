"""놀이 실브라우저 검증 (기능 개선 회차 P5 · 게임 공통 G8 — D-563 · D-564 · D-575 ~ D-578 · D-593 · D-594).

재는 것:
  A′. 기준 커밋과 지문 대조(`--digest` 앞 절반, `--digest-base 45c69235`) — 같은 seed · 판 · 참가자로 이 트리의 엔진과 기준 커밋의
     엔진을 Node 에서 따로 돌려(`marble_digest_runner.mjs`) 순위 · 완주 스텝 · 당첨 · 지문이 같은가, 논리 시간 조각 크기와 무관한가,
     서버의 `digest_of` · `_judge`(기준 커밋 판을 따로 올려서)가 같은 판정을 내는가. 서버 없이 돈다(`--digest-engine-only`).
  A. 구슬 레이스 지문(`--digest --map-key <판>`) — 방장(Chromium)과 참가자(Firefox, `--participant-browser`)가 같은 seed 로 같은 경주를
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
  F. 레일 높이 배분(`--rail`, D-594) — 구성원 12명 · 채팅 30줄(24자 이름 포함) 방을 1920 · 1366 에서 열어 보이는 참여자 줄 · 보이는
     메시지 · 입력 줄이 화면 안인가 · 위 판의 높이 비율, 인원 2 · 6 · 12 · 30 × 채팅 0 · 10 · 50 훑기에서 위 판이 갑자기 접히지
     않는가, 흐름(1024) · 모바일(390) · 낮은 채움 레일(1280 × 640). 계정은 관리 API 로 만들고(평범한 이름 29 · 24자 이름 11) API 로 들어온다.
  G. 구슬 레이스 맵 흐름(`--map`, D-593) — 방장(Chromium)이 추가 창에서 처음 맵을 고르고 툴바 「맵 선택」으로 바꾸고, 참가자(Firefox)가
     3초 안에 같은 맵을 보는가, 경주 중 막힘과 까닭, 결과 · 다시 하기 · 새 판의 맵. 단계마다 고른 맵 == 툴바 == 방 상태 == 그린 판.

    python -m scripts.ui_qa.local_server --port 8765 --hold                       # 다른 창(씨앗 계정 포함)
    python -m scripts.ui_qa.games_e2e --base-url http://127.0.0.1:8765 --label g1 --layout --capture --fullscreen
    python -m scripts.ui_qa.games_e2e --base-url http://127.0.0.1:8765 --label g1 --digest --participant-browser firefox --map-key wheel
    python -m scripts.ui_qa.games_e2e --base-url http://127.0.0.1:8765 --label g1 --perf --perf-n 20 50 100
    python -m scripts.ui_qa.games_e2e --base-url http://127.0.0.1:8765 --out dist/ui-qa --label r23-games --rail --map --digest

계정은 로컬 서버가 심는 것(`local_server.py::seed`)이다. 원격 설치에는 그 계정이 없으므로 이 하네스는 로컬 전용이다.
"""

from __future__ import annotations

import argparse
import contextlib
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
    "1280s": Viewport("1280x640", 1280, 640),  # 작은 노트북 창 — 채움 모드의 낮은 레일(`--rail`)
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


# ── A′. 기준 커밋과 지문 대조(`--digest`의 앞 절반) ───────────────────────────
#
# 물리 · 판정이 바뀌지 않았다는 증거 — 같은 seed · 판 · 참가자 · race_id 로 이 트리의 엔진과 기준 커밋(`--digest-base`, 기본 45c69235 —
# r23 회차 시작 직전)의 엔진을 따로 돌려 순위 · 완주 스텝 · 당첨 · 지문을 대조한다(`marble_digest_runner.mjs`, 엔진마다 프로세스 하나).
# 같은 경주를 논리 시간 조각 1000ms · 37ms 로 두 번 돌려 조각 크기와도 무관한지 본다. 서버 쪽은 기준 커밋의 `app/games/marble.py` 를
# 따로 올려 `digest_of` · `_winners_of` · `_judge`(확정 · 방장만 · 방장 없음 · 불일치)를 같은 입력으로 대조하고, 엔진 지문이 서버 지문과
# 같은 글의 SHA-256 인지도 본다.

DIGEST_BASE_DEFAULT = "45c69235"
ENGINE_REL = "frontend/src/screens/game-room/marble/engine"
DIGEST_SEEDS = ("00112233aabbccdd", "deadbeefcafef00d")
DIGEST_SIZES = (2, 12, 30)
DIGEST_MAPS = ("wheel", "pot", "bubble", "yoru")


def _git(*args: str) -> bytes:
    import subprocess

    r = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {r.stderr.decode('utf-8', 'replace')[:300]}")
    return r.stdout


def extract_engine(rev: str, dest: Path) -> list[str]:
    """기준 커밋의 엔진 파일(시험 제외)을 `dest` 에 그대로 쓴다. 이름 목록을 돌려준다."""
    names = [n for n in _git("ls-tree", "-r", "--name-only", rev, ENGINE_REL + "/").decode().split("\n") if n and not n.endswith(".test.js")]
    for name in names:
        target = dest / Path(name).relative_to(ENGINE_REL)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git("show", f"{rev}:{name}"))
    return [str(Path(n).relative_to(ENGINE_REL)).replace("\\", "/") for n in names]


def run_engine(engine_dir: Path, spec_path: Path) -> dict:
    import subprocess

    runner = REPO_ROOT / "scripts" / "ui_qa" / "marble_digest_runner.mjs"
    r = subprocess.run(["node", str(runner), str(engine_dir), str(spec_path)], capture_output=True, timeout=900, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"엔진 실행 실패({engine_dir}): {r.stderr.decode('utf-8', 'replace')[:600]}")
    return json.loads(r.stdout.decode("utf-8"))


def load_module_at(rev: str, rel: str, name: str, tmp: Path):
    """기준 커밋의 파이썬 모듈 하나를 다른 이름으로 올린다(그 모듈의 `app.*` 가져오기는 이 트리에서 풀린다 — 순수 함수 대조용)."""
    import importlib.util

    path = tmp / f"{name}.py"
    path.write_bytes(_git("show", f"{rev}:{rel}"))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def judge_cases(race: dict) -> list[tuple[str, dict]]:
    """한 경주 결과로 만든 제출 묶음 — 확정 · 방장만 · 방장 없음 · 방장과 다름 · 참가자끼리 다름, 그리고 꼴찌 당첨."""
    good = {"ranking": race["ranking"], "finish_steps": race["finish_steps"], "digest": race["digest"]}
    bad = {**good, "digest": "f" * 64}
    sub = lambda role, body, uid: {"role": role, "user_id": uid, **body}  # noqa: E731
    base = {"winners_n": race["winners"], "pick_last": False}
    return [
        ("confirmed", {**base, "submissions": [sub("host", good, "h"), sub("attest", good, "p1"), sub("attest", good, "p2")]}),
        ("host_only", {**base, "submissions": [sub("host", good, "h")]}),
        ("host_absent", {**base, "submissions": [sub("attest", good, "p1"), sub("attest", good, "p2")]}),
        ("disputed_vs_host", {**base, "submissions": [sub("host", good, "h"), sub("attest", bad, "p1")]}),
        ("disputed_attest", {**base, "submissions": [sub("attest", good, "p1"), sub("attest", bad, "p2")]}),
        ("pick_last", {"winners_n": 2, "pick_last": True, "submissions": [sub("host", good, "h"), sub("attest", good, "p1")]}),
    ]


def run_digest_compare(base_rev: str, out: Path) -> dict:
    import shutil
    import tempfile

    races = []
    for m in DIGEST_MAPS:
        for seed in DIGEST_SEEDS:
            for n in DIGEST_SIZES:
                races.append({"map": m, "seed": seed, "n": n, "winners": 2 if n > 2 else 1, "pickLast": False,
                              "raceId": (seed * 2)[:32], "chunks": [1000, 37]})
        races.append({"map": m, "seed": DIGEST_SEEDS[0], "n": 12, "winners": 3, "pickLast": True, "raceId": "f" * 16 + DIGEST_SEEDS[0], "chunks": [1000, 37]})
    spec_path = out / "digest-spec.json"
    spec_path.write_text(json.dumps({"races": races}), encoding="utf-8")

    # 기준 엔진은 `frontend/` 아래(무시되는 dist)에 풀어야 `import "planck"` 가 같은 node_modules 에서 풀린다.
    scratch = REPO_ROOT / "frontend" / "dist" / ".games-e2e-digest"
    base_dir = scratch / base_rev
    if base_dir.exists():
        shutil.rmtree(base_dir)
    here_dir = REPO_ROOT / ENGINE_REL
    try:
        base_files = extract_engine(base_rev, base_dir)
        changed = []
        for rel in base_files:
            here = here_dir / rel
            a = (base_dir / rel).read_bytes().replace(b"\r\n", b"\n")
            b = here.read_bytes().replace(b"\r\n", b"\n") if here.exists() else None
            if a != b:
                changed.append(rel)
        t0 = time.time()
        here_res = run_engine(here_dir, spec_path)
        base_res = run_engine(base_dir, spec_path)
        elapsed = round(time.time() - t0, 1)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)  # 풀어 둔 기준 엔진은 실행이 실패해도 남기지 않는다
        with contextlib.suppress(OSError):
            scratch.parent.rmdir()  # 이 하네스가 만든 빈 `frontend/dist` 만 걷힌다(내용이 있으면 그대로 둔다)

    from app.games import marble as marble_here

    tmp = Path(tempfile.mkdtemp(prefix="games-e2e-digest-"))
    try:
        marble_base = load_module_at(base_rev, "app/games/marble.py", "marble_base_" + base_rev, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    rows = []
    for h, b in zip(here_res["races"], base_res["races"]):
        hr, br = h["runs"], b["runs"]
        first = hr[0]
        py_here = marble_here.digest_of(h["raceId"], first["ranking"] or [], first["finish_steps"] or [])
        py_base = marble_base.digest_of(h["raceId"], first["ranking"] or [], first["finish_steps"] or [])
        row = {
            "map": h["map"], "seed": h["seed"], "n": h["n"], "winners": h["winners"], "pick_last": h["pickLast"],
            "steps": first["steps"], "digest_here": first["digest"], "digest_base": br[0]["digest"],
            "finished": all(r["finished"] for r in hr + br),
            "same_as_base": all(x[k] == y[k] for x, y in zip(hr, br) for k in ("ranking", "finish_steps", "winners", "digest", "steps")),
            "chunk_independent": all(r[k] == first[k] for r in hr for k in ("ranking", "finish_steps", "digest", "steps")),
            "python_digest": py_here == first["digest"] and py_base == first["digest"],
        }
        row["pass"] = row["finished"] and row["same_as_base"] and row["chunk_independent"] and row["python_digest"]
        rows.append(row)
        log(f"[A′] {row['map']:<6} seed={row['seed'][:8]} n={row['n']:>2} w={row['winners']}{' 꼴찌' if row['pick_last'] else ''} "
            f"steps={row['steps']:>5} 지문 {str(row['digest_here'])[:12]} / 기준 {str(row['digest_base'])[:12]} → {'PASS' if row['pass'] else 'FAIL'}")

    judges = []
    for h in here_res["races"][:4]:
        race = {**h["runs"][0], "winners": h["winners"]}
        for name, state in judge_cases(race):
            mine = marble_here._judge(json.loads(json.dumps(state)))
            theirs = marble_base._judge(json.loads(json.dumps(state)))
            judges.append({"case": name, "map": h["map"], "n": h["n"], "integrity": (mine[1] or {}).get("status"),
                           "winners": (mine[0] or {}).get("winners"), "same_as_base": mine == theirs})
    winners_same = all(marble_here._winners_of(list("abcdefgh"), k, pl) == marble_base._winners_of(list("abcdefgh"), k, pl)
                       for k in (1, 2, 3, 8, 12) for pl in (False, True))
    log(f"[A′] 서버 판정 {len(judges)}건 기준과 같음: {all(j['same_as_base'] for j in judges)} · 당첨 고르기 같음: {winners_same} "
        f"· 엔진 파일 바뀐 것: {changed or '없음'} ({elapsed}s)")
    return {"base": base_rev, "engine_files_changed": changed, "races": rows, "judge": judges, "winners_of_same": winners_same,
            "elapsed_s": elapsed,
            "pass": all(r["pass"] for r in rows) and all(j["same_as_base"] for j in judges) and winners_same}


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


# ── F. 레일 높이 배분(`--rail`, D-594) ───────────────────────────────────────
#
# 레일 위 판(참여자 · 구슬 순위)은 자기 내용만큼 서되 레일 높이의 55% 를 넘지 않고, 채팅이 나머지를 받는다. 재는 것: 보이는 참여자 줄 ·
# 보이는 채팅 메시지 · 입력 줄이 화면 안인가 · 위 판의 높이 비율, 그리고 인원(2 · 6 · 12 · 30) · 채팅(0 · 10 · 50) · 24자 이름이 바뀌어도
# 위 판이 갑자기 접히지 않는가(같은 인원이면 채팅 수와 무관하게 같은 높이, 인원이 늘면 줄지 않는다).

RAIL_TOP_MAX = 0.55
RAIL_MIN_ROWS = {"1920": 6, "1366": 4}
RAIL_ROW_MAX_PX = 48  # 한 줄 줄의 상한 — 두 줄(이름 / 소속) 줄은 57 ~ 61px 였다.
RAIL_NAMES = (
    "강민서", "고은비", "곽도윤", "구하린", "권지호", "김서준", "김하은", "남궁민", "노유진", "문지환",
    "민서아", "박도현", "배수아", "백승우", "서지안", "성하윤", "손예준", "송채원", "신동하", "안소율",
    "양현우", "오다인", "유건우", "윤서진", "이준서", "임나연", "장시우", "전하늘", "조은호",
)
LONG_NAME = "크리스티아나 알레한드라 페르난데스 로드리게스"  # 24자 — 구슬 이름 상한(`marble.NAME_MAX`)과 같은 길이
LONG_TAILS = "스즈드트크프브르므느흐"
# 게임방 채팅의 흔한 길이 — 레일 말풍선 한 줄에 드는 짧은 말. 주 장면과 훑기가 쓴다(채팅 바닥 18rem 은 한 줄 메시지 셋의 몫이다).
CHAT_SHORT = ("안녕하세요!", "저도 왔습니다.", "언제 시작하나요?", "좋습니다.", "준비됐습니다.", "꼭 당첨될 거예요!", "커피 내기입니다.", "화이팅!")
# 두세 줄로 접히는 긴 말 — 위 판이 눌리지 않고 입력 줄이 화면 안인지를 본다. 1366 의 레일(509px)에서 참여자 네 줄과 두 줄 말풍선 셋은
# 함께 들어가지 않으므로(머리 · 입력 줄 · 여백을 더하면 545px 이상) 이 방의 보이는 메시지 기준은 1366 에서 둘, 1920 에서 셋이다.
CHAT_LONG = (
    "안녕하세요, 오늘 점심 추첨에 참여합니다.", "저도 들어왔습니다.", "당첨되면 커피를 사겠습니다.", "몇 분 뒤에 시작하나요?",
    "곧 시작합니다. 잠시만 기다려 주세요.", "오늘은 꼭 당첨되고 싶습니다!", "회의가 끝나면 바로 돌아오겠습니다.", "좋습니다.",
)
CHAT_LONG_MIN_MSGS = {"1920": 3, "1366": 2}
RAIL_JS = r"""() => {
  const R = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { l: b.left, t: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height }; };
  /* 요소를 자르는 조상(넘침이 visible 이 아닌 상자)들과 화면이 만드는 창 — 그 창 안에 위아래가 다 들어와야 「보인다」. */
  const clipOf = (el) => {
    let c = { t: 0, b: innerHeight, l: 0, r: innerWidth };
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.overflowY === 'visible' && cs.overflowX === 'visible') continue;
      const b = p.getBoundingClientRect();
      const top = b.top + p.clientTop; const left = b.left + p.clientLeft;
      c = { t: Math.max(c.t, top), b: Math.min(c.b, top + p.clientHeight), l: Math.max(c.l, left), r: Math.min(c.r, left + p.clientWidth) };
    }
    return c;
  };
  const shown = (el) => {
    if (!el || !el.getClientRects().length || el.closest('[hidden]')) return false;
    const b = el.getBoundingClientRect(); const c = clipOf(el);
    return b.height > 0 && b.top >= c.t - 0.5 && b.bottom <= c.b + 0.5;
  };
  const inView = (el) => {
    if (!shown(el)) return false;
    const b = el.getBoundingClientRect();
    return b.top >= -0.5 && b.bottom <= innerHeight + 0.5 && b.left >= -0.5 && b.right <= innerWidth + 0.5;
  };
  const root = document.querySelector('[data-game-room-layout]');
  const aside = document.querySelector('aside[data-room-rail]');
  const top = document.querySelector('[data-rail-top]');
  const pane = top || document.querySelector('[data-rail-pane="members"]');
  const rows = pane ? Array.from(pane.querySelectorAll('li')) : [];
  const log = document.querySelector('[data-testid="game-chat-log"]');
  const isEmpty = (c) => c.matches('.k-empty,[data-empty-layout]') || !!c.querySelector('.k-empty,[data-empty-layout]');
  const msgs = log ? Array.from(log.children).filter((c) => !isEmpty(c)) : [];
  const input = document.querySelector('input[aria-label="메시지 입력"]');
  const scope = input ? input.closest('[data-form-scope]') : null;
  const send = scope ? Array.from(scope.querySelectorAll('button')).find((b) => b.textContent.trim() === '보내기') : null;
  const rowInfo = rows.map((li) => {
    const t = li.querySelector('[title]');
    return { h: Math.round(li.getBoundingClientRect().height * 10) / 10, title: t ? t.getAttribute('title') : null,
             truncated: t ? t.scrollWidth > t.clientWidth + 1 : null, text: (li.textContent || '').trim().slice(0, 48) };
  });
  return {
    mode: root && root.getAttribute('data-game-room-layout'), vw: innerWidth, vh: innerHeight,
    docW: document.documentElement.scrollWidth, docH: document.documentElement.scrollHeight,
    rail: R(aside), top: R(top), chat: R(document.querySelector('[data-chat-panel]')), log: R(log),
    rows: rows.length, visibleRows: rows.filter(shown).length, rowInfo,
    msgs: msgs.length, visibleMsgs: msgs.filter(shown).length, emptyShown: !!(log && log.querySelector('.k-empty,[data-empty-layout]') && shown(log.querySelector('.k-empty,[data-empty-layout]'))),
    input: R(input), send: R(send), composerInView: inView(input) && inView(send),
  };
}"""
RAIL_READY_JS = r"""([n, m]) => {
  const pane = document.querySelector('[data-rail-top]') || document.querySelector('[data-rail-pane="members"]');
  const log = document.querySelector('[data-testid="game-chat-log"]');
  if (!pane || !log) return false;
  const isEmpty = (c) => c.matches('.k-empty,[data-empty-layout]') || !!c.querySelector('.k-empty,[data-empty-layout]');
  return pane.querySelectorAll('li').length === n && Array.from(log.children).filter((c) => !isEmpty(c)).length === m;
}"""


def api_login(pw, base: str, email: str, password: str = LOCAL_PASSWORD) -> dict:
    """화면 없이 API 로만 움직이는 구성원 — 로그인 세션 하나(쿠키) + CSRF."""
    req = pw.request.new_context(base_url=base)
    r = req.post("/login", data={"email": email, "password": password})
    if r.status != 200:
        raise RuntimeError(f"{email} 로그인 실패: {r.status}")
    me = req.get("/api/me").json()
    return {"email": email, "req": req, "csrf": me["csrf_token"], "user_id": me["user"]["id"], "name": me["user"].get("display_name")}


def sess_api(sess: dict, method: str, path: str, body=None):
    headers = {"X-CSRF-Token": sess["csrf"]} if method != "GET" else {}
    r = sess["req"].fetch(path, method=method, data=body, headers=headers)
    try:
        payload = r.json()
    except Exception:
        payload = None
    return r.status, payload


def rail_accounts(pw, host: Actor, base: str) -> dict:
    """레일 시험용 계정 — 이름이 평범한 29명(첫 사람은 24자 이름)과 24자 이름 11명. 이미 있으면 로그인만 한다."""
    st, depts = api(host, base, "GET", "/api/admin/departments")
    st2, titles = api(host, base, "GET", "/api/admin/job-titles")
    dept_ids = [d["id"] for d in (depts or {}).get("items", []) if d.get("active")][:3] or [None]
    title_ids = [t["id"] for t in (titles or {}).get("items", []) if t.get("active")][:3] or [None]
    plan = [("rail.m%02d" % (i + 1), LONG_NAME if i == 0 else RAIL_NAMES[i]) for i in range(len(RAIL_NAMES))]
    plan += [("rail.long%02d" % (i + 1), LONG_NAME[:-1] + LONG_TAILS[i]) for i in range(11)]
    out = {"plain": [], "long": []}
    for i, (local, name) in enumerate(plan):
        email = f"{local}@goodmit.co.kr"
        body = {"email": email, "display_name": name, "password": LOCAL_PASSWORD, "must_change_password": False,
                "department_id": dept_ids[i % len(dept_ids)], "title_id": title_ids[i % len(title_ids)]}
        st, j = api(host, base, "POST", "/api/admin/users", body)
        if st not in (200, 201, 409, 422):
            raise RuntimeError(f"계정을 만들지 못했다: {email} {st} {j}")
        sess = api_login(pw, base, email)
        out["long" if local.startswith("rail.long") else "plain"].append(sess)
    return out


def seed_rail_room(host: Actor, base: str, members: list[dict], chat: int, *, game: str = "random_draw", title: str,
                   lines: tuple = CHAT_SHORT) -> str:
    config = dict(next(g[1] for g in GAMES if g[0] == game))
    if game == "marble_race":
        config["participants"] = []  # 방 구성원이 참가자다 — 순위 판도 같은 사람들이다
    rid = create_room(host, base, game, config, title, max_players=50)
    for m in members:
        st, j = sess_api(m, "POST", f"/api/games/rooms/{rid}/join")
        if st != 200:
            raise RuntimeError(f"{m['email']} 입장 실패: {st} {j}")
    senders = [None] + members[:2]  # None = 방장(내 메시지는 오른쪽) — 세 사람이 돌아가며 말한다
    for i in range(chat):
        text = lines[i % len(lines)]
        who = senders[i % len(senders)]
        st, j = (api(host, base, "POST", f"/api/games/rooms/{rid}/chat", {"text": text}) if who is None
                 else sess_api(who, "POST", f"/api/games/rooms/{rid}/chat", {"text": text}))
        if st != 200:
            raise RuntimeError(f"채팅을 심지 못했다: {st} {j}")
    return rid


def touch_members(members: list[dict], rid: str) -> None:
    """구성원이 방을 보고 있다고 서버에 알린다(90초 안의 폴링) — 「자리 비움」 배지 없이 잰다."""
    for m in members:
        sess_api(m, "GET", f"/api/games/rooms/{rid}/state?since=0")


def rail_room_checks(geo: dict, vkey: str, n: int, chat: int, long_names: list[str], min_msgs: int = 3) -> dict:
    """채움 모드 한 장면의 판정 — 실패한 항목만 이름으로 남는다."""
    fails: list[str] = []
    rail_h = (geo["rail"] or {}).get("h") or 0
    top_h = (geo["top"] or {}).get("h") or 0
    ratio = round(top_h / rail_h, 3) if rail_h else None
    if geo["mode"] != "fill":
        fails.append(f"mode={geo['mode']}")
    if geo["docH"] > geo["vh"] + 1:
        fails.append(f"doc_scroll({geo['docH']}>{geo['vh']})")
    if geo["docW"] > geo["vw"] + 1:
        fails.append(f"h_overflow({geo['docW']}>{geo['vw']})")
    need_rows = min(n, RAIL_MIN_ROWS[vkey])
    if geo["visibleRows"] < need_rows:
        fails.append(f"members_visible({geo['visibleRows']}<{need_rows})")
    if chat and geo["visibleMsgs"] < min(chat, min_msgs):
        fails.append(f"chat_visible({geo['visibleMsgs']}<{min(chat, min_msgs)})")
    if not chat and not geo["emptyShown"]:
        fails.append("chat_empty_state_hidden")
    if not geo["composerInView"]:
        fails.append("composer_outside")
    if ratio is None or ratio > RAIL_TOP_MAX + 0.01:
        fails.append(f"top_ratio({ratio}>{RAIL_TOP_MAX})")
    heights = [r["h"] for r in geo["rowInfo"]]
    if heights and (max(heights) > RAIL_ROW_MAX_PX or max(heights) - min(heights) > 1):
        fails.append(f"row_heights({min(heights)}~{max(heights)})")
    if any(not r["title"] for r in geo["rowInfo"]):
        fails.append("row_title_missing")
    for name in long_names:
        row = next((r for r in geo["rowInfo"] if r["title"] and name in r["title"]), None)
        if row is None or not row["truncated"]:
            fails.append(f"long_name_not_truncated({name[:6]}…)")
            break
    return {"ratio": ratio, "top_h": round(top_h, 1), "rail_h": round(rail_h, 1), "fails": fails, "pass": not fails}


def run_rail(pw, base: str, out: Path) -> dict:
    chromium = pw.chromium.launch()
    host = open_actor(chromium, base, HOST_EMAIL, viewport=VP["1366"], theme="light", name="rail-host")
    storage = out / "host-storage.json"
    host.ctx.storage_state(path=str(storage))
    people = rail_accounts(pw, host, base)
    plain, longs = people["plain"], people["long"]
    log(f"[F] 계정 준비: 평범한 이름 {len(plain)} · 24자 이름 {len(longs)}")

    # 방 — 주 장면(12명 · 채팅 30, 추첨과 구슬), 24자 이름 12명, 그리고 인원 × 채팅 훑기.
    rooms: list[dict] = []

    def add(key, game, members, chat, long_names, lines=CHAT_SHORT):
        rid = seed_rail_room(host, base, members, chat, game=game, title=f"레일 {key}", lines=lines)
        rooms.append({"key": key, "game": game, "rid": rid, "n": len(members) + 1, "chat": chat, "members": members,
                      "long_names": long_names, "long_chat": lines is CHAT_LONG})

    add("primary", "random_draw", plain[:11], 30, [LONG_NAME])
    add("primary-marble", "marble_race", plain[:11], 30, [LONG_NAME])
    add("long12", "random_draw", longs[:11], 30, [s["name"] for s in longs[:11]])
    add("long-chat", "random_draw", plain[:11], 30, [LONG_NAME], lines=CHAT_LONG)
    for n in (2, 6, 12, 30):
        for chat in (0, 10, 50):
            add(f"sweep-{n}m-{chat}c", "random_draw", plain[:n - 1], chat, [LONG_NAME])
    log(f"[F] 방 {len(rooms)}개를 심었다")

    rows: list[dict] = []
    errors: list[str] = []
    for vkey in ("1920", "1366"):
        a = open_actor(chromium, base, HOST_EMAIL, viewport=VP[vkey], theme="light", name=f"rail-{vkey}", storage_state=str(storage))
        for room in rooms:
            touch_members(room["members"], room["rid"])
            goto_room(a, base, room["rid"])
            a.page.wait_for_function(RAIL_READY_JS, arg=[room["n"], room["chat"]], timeout=20_000)
            a.page.wait_for_timeout(700)
            geo = a.page.evaluate(RAIL_JS)
            min_msgs = CHAT_LONG_MIN_MSGS[vkey] if room["long_chat"] else 3
            verdict = rail_room_checks(geo, vkey, room["n"], room["chat"], room["long_names"], min_msgs)
            shot = out / f"rail-{room['key']}-{vkey}.png"
            a.page.screenshot(path=str(shot))
            if (room["key"].startswith("primary") or room["key"] in ("long12", "long-chat")) and geo["rail"]:
                rb = geo["rail"]
                a.page.screenshot(path=str(out / f"rail-{room['key']}-{vkey}-crop.png"),
                                  clip={"x": max(0, rb["l"] - 8), "y": max(0, rb["t"] - 8), "width": rb["w"] + 16, "height": min(geo["vh"], rb["h"] + 16)})
            rows.append({"room": room["key"], "rid": room["rid"], "game": room["game"], "viewport": vkey, "n": room["n"], "chat": room["chat"],
                         "visible_rows": geo["visibleRows"], "rows": geo["rows"], "visible_msgs": geo["visibleMsgs"], "msgs": geo["msgs"],
                         "composer_in_view": geo["composerInView"], "row_h": sorted({r["h"] for r in geo["rowInfo"]}),
                         "input": geo["input"], "file": shot.name, **verdict})
            log(f"[F] {room['key']:<16} {vkey}: 참여자 {geo['visibleRows']}/{geo['rows']} 줄 · 채팅 {geo['visibleMsgs']}/{geo['msgs']} · "
                f"위 판 {verdict['top_h']}/{verdict['rail_h']} ({verdict['ratio']}) · 입력 {'안' if geo['composerInView'] else '밖'} "
                f"→ {'PASS' if verdict['pass'] else 'FAIL ' + ','.join(verdict['fails'])}")
        errors += a.errors
        a.ctx.close()

    # 훑기 판정 — 같은 인원이면 채팅 수와 무관하게 위 판 높이가 같고(±2px), 인원이 늘면 위 판이 줄지 않는다(±1px). 24자 이름 12명은
    # 평범한 12명과 같은 높이다(줄이 한 줄이라 이름 길이가 높이를 바꾸지 않는다).
    stability: list[dict] = []
    for vkey in ("1920", "1366"):
        tops = {(r["n"], r["chat"]): r["top_h"] for r in rows if r["viewport"] == vkey and r["room"].startswith("sweep")}
        fails = []
        for n in (2, 6, 12, 30):
            vals = [tops[(n, c)] for c in (0, 10, 50)]
            if max(vals) - min(vals) > 2:
                fails.append(f"chat_squeezes_top(n={n}: {vals})")
        for c in (0, 10, 50):
            seq = [tops[(n, c)] for n in (2, 6, 12, 30)]
            if any(b < a - 1 for a, b in zip(seq, seq[1:])):
                fails.append(f"top_shrinks_with_members(chat={c}: {seq})")
        prim = next(r for r in rows if r["viewport"] == vkey and r["room"] == "primary")
        lng = next(r for r in rows if r["viewport"] == vkey and r["room"] == "long12")
        if abs(prim["top_h"] - lng["top_h"]) > 1:
            fails.append(f"long_names_change_top({prim['top_h']} vs {lng['top_h']})")
        stability.append({"viewport": vkey, "tops": {f"{n}m-{c}c": v for (n, c), v in sorted(tops.items())}, "fails": fails, "pass": not fails})
        log(f"[F] 훑기 {vkey}: {'PASS' if not fails else 'FAIL ' + '; '.join(fails)}")

    # 흐름(1024) · 모바일(390) — 주 장면 방에서 레일이 그대로 쓸 만한가.
    narrow: list[dict] = []
    prim_room = next(r for r in rooms if r["key"] == "primary")
    for vkey in ("1024", "390"):
        a = open_actor(chromium, base, HOST_EMAIL, viewport=VP[vkey], theme="light", name=f"rail-{vkey}", storage_state=str(storage))
        touch_members(prim_room["members"], prim_room["rid"])
        goto_room(a, base, prim_room["rid"])
        a.page.wait_for_function(RAIL_READY_JS, arg=[prim_room["n"], prim_room["chat"]], timeout=20_000)
        a.page.wait_for_timeout(700)
        # 흐름 · 모바일은 문서가 굴러가는 것이 설계다 — 참여자 판을 화면에 들여온 뒤 그 판 안의 줄을 센다.
        a.page.locator('[data-rail-top]' if vkey == "1024" else '[data-rail-pane="members"]').scroll_into_view_if_needed()
        a.page.wait_for_timeout(300)
        geo = a.page.evaluate(RAIL_JS)
        fails = []
        expect_mode = "flow" if vkey == "1024" else "mobile"
        if geo["mode"] != expect_mode:
            fails.append(f"mode={geo['mode']}")
        if geo["docW"] > geo["vw"] + 1:
            fails.append(f"h_overflow({geo['docW']}>{geo['vw']})")
        if geo["rows"] != prim_room["n"]:
            fails.append(f"rows={geo['rows']}")
        if geo["visibleRows"] < 4:
            fails.append(f"members_visible({geo['visibleRows']}<4)")
        heights = [r["h"] for r in geo["rowInfo"]]
        if heights and max(heights) > RAIL_ROW_MAX_PX:
            fails.append(f"row_heights({max(heights)})")
        if vkey == "390":
            a.page.click('[data-room-rail="mobile"] [role="tab"]:has-text("채팅")')
            a.page.wait_for_timeout(300)
        a.page.locator('input[aria-label="메시지 입력"]').scroll_into_view_if_needed()
        a.page.wait_for_timeout(300)
        geo2 = a.page.evaluate(RAIL_JS)
        if not geo2["composerInView"]:
            fails.append("composer_not_reachable")
        if geo2["visibleMsgs"] < 3:
            fails.append(f"chat_visible({geo2['visibleMsgs']})")
        shot = out / f"rail-primary-{vkey}.png"
        a.page.screenshot(path=str(shot))
        narrow.append({"viewport": vkey, "mode": geo["mode"], "rows": geo["rows"], "visible_rows": geo["visibleRows"],
                       "visible_msgs": geo2["visibleMsgs"], "composer_in_view": geo2["composerInView"], "file": shot.name,
                       "fails": fails, "pass": not fails})
        log(f"[F] 좁은 폭 {vkey}: mode={geo['mode']} 참여자 {geo['visibleRows']}/{geo['rows']} 채팅 {geo2['visibleMsgs']} "
            f"입력 {'안' if geo2['composerInView'] else '밖'} → {'PASS' if not fails else 'FAIL ' + ','.join(fails)}")
        errors += a.errors
        a.ctx.close()

    # 낮은 채움 레일(1280 × 640) — 채팅 바닥이 양보해 위 판이 두 줄 아래로 접히지 않고, 입력 줄은 화면 안이다.
    short: list[dict] = []
    a = open_actor(chromium, base, HOST_EMAIL, viewport=VP["1280s"], theme="light", name="rail-1280s", storage_state=str(storage))
    for room in [r for r in rooms if r["key"] in ("primary", "primary-marble")]:
        touch_members(room["members"], room["rid"])
        goto_room(a, base, room["rid"])
        a.page.wait_for_function(RAIL_READY_JS, arg=[room["n"], room["chat"]], timeout=20_000)
        a.page.wait_for_timeout(700)
        geo = a.page.evaluate(RAIL_JS)
        fails = []
        if geo["mode"] != "fill":
            fails.append(f"mode={geo['mode']}")
        if geo["docH"] > geo["vh"] + 1:
            fails.append(f"doc_scroll({geo['docH']}>{geo['vh']})")
        if geo["visibleRows"] < 2:
            fails.append(f"members_visible({geo['visibleRows']}<2)")
        if geo["visibleMsgs"] < 1:
            fails.append("chat_visible(0)")
        if not geo["composerInView"]:
            fails.append("composer_outside")
        shot = out / f"rail-{room['key']}-1280x640.png"
        a.page.screenshot(path=str(shot))
        short.append({"room": room["key"], "viewport": "1280x640", "rail_h": (geo["rail"] or {}).get("h"), "top_h": (geo["top"] or {}).get("h"),
                      "visible_rows": geo["visibleRows"], "visible_msgs": geo["visibleMsgs"], "composer_in_view": geo["composerInView"],
                      "file": shot.name, "fails": fails, "pass": not fails})
        log(f"[F] 낮은 레일 {room['key']:<16} 1280x640: 참여자 {geo['visibleRows']}/{geo['rows']} 채팅 {geo['visibleMsgs']} "
            f"위 판 {(geo['top'] or {}).get('h')}/{(geo['rail'] or {}).get('h')} 입력 {'안' if geo['composerInView'] else '밖'} "
            f"→ {'PASS' if not fails else 'FAIL ' + ','.join(fails)}")
    errors += a.errors
    a.ctx.close()

    for group in people.values():
        for s in group:
            s["req"].dispose()
    errors += host.errors
    host.ctx.close()
    chromium.close()
    return {"rows": rows, "stability": stability, "narrow": narrow, "short": short, "console_errors": errors,
            "pass": all(r["pass"] for r in rows) and all(s["pass"] for s in stability) and all(x["pass"] for x in narrow)
            and all(x["pass"] for x in short) and not errors}


# ── G. 구슬 레이스 맵 흐름(`--map`, D-593) ────────────────────────────────────
#
# 방장(Chromium)이 게임방 추가 창에서 처음 맵을 고르고, 대기 중 툴바 「맵 선택」으로 바꾸고, 경주 · 결과 · 다시 하기 · 새 판의 맵 바꾸기 ·
# 다시 경주까지 간다. 참가자(Firefox)는 같은 방을 본다. 단계마다 「고른 맵 == 툴바의 맵 이름 == 방 상태의 맵 == 캔버스가 그린 판」을 두
# 화면에서 대조한다(그린 판은 `MarbleStage` 의 그리기 함수가 적는 `data-drawn-map`). 참가자에게는 「맵 선택」이 없고, 참가자의 설정 PUT 은
# 403 이다. 경주 중에는 맵 선택이 막히고 까닭(「경주 중에는 맵을 바꿀 수 없습니다. …」)이 설명 · 툴팁으로 보인다.

MAP_LABELS = {"wheel": "운명의 바퀴", "pot": "탐욕의 항아리", "bubble": "비눗방울", "yoru": "밤을 달리다"}  # `stages/labels.js` 와 같다
MAP_REASON_RUNNING = "경주 중에는 맵을 바꿀 수 없습니다."
MAP_REASON_FINISHED = "'다시 하기'를 누른 뒤 변경할 수 있습니다."
MAP_SYNC_LIMIT_S = 3.0
MAP_PROBE_JS = r"""(labels) => {
  const facts = document.querySelector('[data-room-facts]');
  const text = facts ? facts.textContent : '';
  const canvas = document.querySelector('[data-marble-canvas]');
  const stage = document.querySelector('[data-marble-stage]');
  const picker = document.querySelector('[data-marble-map-picker]');
  const describedBy = picker ? picker.getAttribute('aria-describedby') : null;
  const reasonEl = describedBy ? document.getElementById(describedBy) : null;
  return {
    toolbar: Object.keys(labels).filter((k) => text.includes(labels[k])),
    drawn: canvas ? canvas.getAttribute('data-drawn-map') : null,
    phase: stage ? stage.getAttribute('data-marble-stage') : null,
    picker: picker ? picker.getAttribute('data-marble-map-picker') : null,
    pickerDisabled: picker ? picker.disabled : null,
    reason: reasonEl ? reasonEl.textContent : null,
    mapButtons: Array.from(document.querySelectorAll('button')).filter((b) => b.textContent.trim() === '맵 선택').length,
  };
}"""


def state_map(actor: Actor, base: str, rid: str) -> dict:
    """방 상태가 말하는 맵 — 대기 중에는 설정의 맵, 시작한 뒤에는 경주에 박힌 맵(`state.map`)."""
    j = room_state(actor, base, rid)
    st = j.get("state") or {}
    waiting = j["room"]["status"] == "waiting" or st.get("phase") in (None, "idle")
    return {"status": j["room"]["status"], "phase": st.get("phase"), "config_map": (st.get("config") or {}).get("map"),
            "race_map": st.get("map"), "map": (st.get("config") or {}).get("map") if waiting else st.get("map")}


def map_snapshot(actor: Actor, base: str, rid: str) -> dict:
    probe = actor.page.evaluate(MAP_PROBE_JS, MAP_LABELS)
    probe["state"] = state_map(actor, base, rid)
    return probe


def map_agrees(snap: dict, key: str) -> bool:
    return snap["toolbar"] == [key] and snap["drawn"] == key and snap["state"]["map"] == key


def wait_map(actor: Actor, base: str, rid: str, key: str, timeout_s: float) -> tuple[float | None, dict]:
    """두 표시(툴바 · 그린 판)와 방 상태가 모두 `key` 가 될 때까지 기다린다 — 걸린 초(시간 안에 안 되면 None)와 마지막 관측."""
    t0 = time.time()
    snap = map_snapshot(actor, base, rid)
    while not map_agrees(snap, key):
        if time.time() - t0 > timeout_s:
            return None, snap
        actor.page.wait_for_timeout(100)
        snap = map_snapshot(actor, base, rid)
    return round(time.time() - t0, 2), snap


def wait_both(host: Actor, part: Actor, base: str, rid: str, key: str, cap_s: float = 10.0) -> tuple[dict, dict]:
    """방장의 PUT 이 돌아온 직후부터 두 화면이 각각 `key` 에 맞을 때까지 — 각자 걸린 초(cap 안에 안 되면 None)와 마지막 관측."""
    t0 = time.time()
    done: dict = {"host": None, "participant": None}
    snaps: dict = {}
    while time.time() - t0 <= cap_s:
        for name, actor in (("host", host), ("participant", part)):
            if done[name] is None:
                snaps[name] = map_snapshot(actor, base, rid)
                if map_agrees(snaps[name], key):
                    done[name] = round(time.time() - t0, 2)
        if all(v is not None for v in done.values()):
            break
        time.sleep(0.1)
    return done, snaps


def pick_map_in_toolbar(page, key: str) -> None:
    page.click('[data-room-toolbar] [data-marble-map-picker="on"]')
    page.click(f'[role="menuitemradio"]:has-text("{MAP_LABELS[key]}")')


def run_map(pw, base: str, out: Path, participant_browser: str = "firefox") -> dict:
    chromium = pw.chromium.launch()
    other = getattr(pw, participant_browser).launch()
    vp = VP["1366"]
    host = open_actor(chromium, base, HOST_EMAIL, viewport=vp, theme="light", name="map-host(chromium)")
    part = open_actor(other, base, PART_EMAIL, viewport=vp, theme="light", name=f"map-participant({participant_browser})")
    steps: list[dict] = []

    def step(no: int, name: str, checks: dict, **data) -> None:
        ok = all(bool(v) for v in checks.values())
        steps.append({"step": no, "name": name, "checks": checks, "pass": ok, **data})
        log(f"[G] {no:>2}. {name}: {'PASS' if ok else 'FAIL'} " + " ".join(f"{k}={v}" for k, v in checks.items() if not v)
            + (f" {json.dumps(data, ensure_ascii=False)[:240]}" if data else ""))

    def shots(tag: str) -> None:
        host.page.screenshot(path=str(out / f"map-{tag}-host.png"))
        part.page.screenshot(path=str(out / f"map-{tag}-participant.png"))

    # 1 · 2 · 3 — 게임방 추가 창에서 구슬 레이스 · 처음 맵(탐욕의 항아리) · 2배속을 고르고 추가하면 방으로 들어간다(2배속 — 두 사람
    # 경주가 몇 초 안에 끝나 「경주 중」 관측이 빠듯해지지 않게).
    first, second, third = "pot", "bubble", "yoru"
    host.page.goto(f"{base}/#/games", wait_until="domcontentloaded")
    host.page.get_by_role("button", name="게임방 추가").first.click()
    dialog = host.page.locator('[role="dialog"]')
    dialog.locator("#gr-game").click()
    host.page.get_by_role("option", name="구슬 레이스").click()
    dialog.locator("#gr-title").fill("맵 흐름 구슬 레이스")
    dialog.locator("#gr-marble-map").click()
    host.page.get_by_role("option", name=MAP_LABELS[first]).click()
    dialog.locator("#gr-marble-speed").click()
    host.page.get_by_role("option", name="2배속").click()
    chosen_in_dialog = dialog.locator("#gr-marble-map").inner_text().strip()
    step(1, "게임방 추가 창 — 구슬 레이스", {"dialog_open": dialog.count() == 1})
    step(2, "추가 창에서 처음 맵 고르기", {"dialog_shows_choice": chosen_in_dialog == MAP_LABELS[first]}, chosen=first, dialog_text=chosen_in_dialog)
    dialog.get_by_role("button", name="추가", exact=True).click()
    host.page.wait_for_url(lambda u: "#/games/" in u, timeout=15_000)
    host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
    rid = host.page.url.split("#/games/")[1].split("?")[0].strip("/")
    secs, snap = wait_map(host, base, rid, first, 5)
    step(3, "방에 들어간다 — 처음 맵이 툴바 · 상태 · 그린 판에 같다", {"agree": secs is not None, "host_has_picker": snap["picker"] == "on"},
         room=rid, host=snap)

    # 참가자(다른 브라우저)가 들어온다 — 「맵 선택」이 없고, 설정 PUT 은 403 이다.
    goto_room(part, base, rid)
    part.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
    wait_state(host, base, rid, lambda s: s["room"]["member_count"] >= 2, 20)
    psecs, psnap = wait_map(part, base, rid, first, 5)
    st403, j403 = api(part, base, "PUT", f"/api/games/rooms/{rid}/marble/config", {"map": "wheel"})
    step(3, "참가자 화면 — 같은 맵, 맵 선택 없음, 참가자의 설정 PUT 403",
         {"agree": psecs is not None, "no_picker": psnap["picker"] is None and psnap["mapButtons"] == 0, "put_403": st403 == 403,
          "map_unchanged": state_map(host, base, rid)["map"] == first},
         participant=psnap, put_status=st403)
    shots("03-room")

    # 4 · 5 — 대기 중 툴바 「맵 선택」으로 바꾸면 참가자가 3초 안에 같은 맵을 본다.
    with host.page.expect_response(lambda r: "/marble/config" in r.url and r.request.method == "PUT") as resp:
        pick_map_in_toolbar(host.page, second)
    put_status = resp.value.status
    done, snaps = wait_both(host, part, base, rid, second)
    host.page.click('[data-room-toolbar] [data-marble-map-picker="on"]')
    checked = host.page.locator('[role="menuitemradio"][aria-checked="true"]').inner_text().strip()
    host.page.keyboard.press("Escape")
    step(4, "대기 중 툴바 「맵 선택」으로 맵 바꾸기", {"put_200": put_status == 200, "host_agree": done["host"] is not None,
                                                   "menu_checked": checked == MAP_LABELS[second]},
         seconds=done["host"], host=snaps["host"], menu_checked=checked)
    step(5, "참가자가 3초 안에 같은 맵을 본다", {"agree": done["participant"] is not None,
                                          "within_3s": done["participant"] is not None and done["participant"] <= MAP_SYNC_LIMIT_S},
         seconds=done["participant"], participant=snaps["participant"])
    shots("05-changed")

    def race_and_result(no_start: int, key: str, tag: str) -> None:
        host.page.click('[data-room-toolbar] button:has-text("경주 시작")')
        host.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
        part.page.wait_for_selector('[data-marble-stage="running"]', timeout=15_000)
        # 7 을 먼저 잰다 — 경주가 도는 동안이어야 뜻이 있다(짧은 경주가 끝나기 전에). 막히고 까닭이 보인다(설명 · 툴팁), 서버도 409.
        blocked = map_snapshot(host, base, rid)
        tip = None
        try:
            host.page.locator('[data-marble-map-picker="off"]').locator("xpath=..").hover()
            tip_el = host.page.locator('[role="tooltip"]')
            tip_el.wait_for(timeout=3_000)
            tip = tip_el.inner_text().strip()
        except Exception:
            tip = None
        st409, j409 = api(host, base, "PUT", f"/api/games/rooms/{rid}/marble/config", {"map": "wheel"})
        still = state_map(host, base, rid)
        host.page.mouse.move(5, 5)
        h_secs, h_snap = wait_map(host, base, rid, key, 5)
        p_secs, p_snap = wait_map(part, base, rid, key, 5)
        step(no_start, "경주 시작 — 경주에 박힌 맵이 고른 맵이고 두 화면이 그 판을 그린다",
             {"host_agree": h_secs is not None, "participant_agree": p_secs is not None, "race_map": h_snap["state"]["race_map"] == key},
             host=h_snap, participant=p_snap)
        step(no_start + 1, "경주 중에는 맵 선택이 막히고 까닭이 보인다",
             {"checked_while_running": blocked["state"]["phase"] == "running" and still["phase"] == "running",
              "picker_off": blocked["picker"] == "off" and blocked["pickerDisabled"] is True,
              "reason_text": bool(blocked["reason"]) and blocked["reason"].startswith(MAP_REASON_RUNNING),
              "tooltip_text": bool(tip) and tip.startswith(MAP_REASON_RUNNING), "server_409": st409 == 409,
              "map_unchanged": still["race_map"] == key},
             reason=blocked["reason"], tooltip=tip, server_status=st409, server_message=((j409 or {}).get("error") or {}).get("message"))
        shots(f"{tag}-running")
        # 8 — 경주가 끝난다(두 브라우저가 같은 지문 → 확정).
        t0 = time.time()
        st = wait_state(host, base, rid, lambda s: (s.get("state") or {}).get("phase") in ("finished", "abandoned"), 300)
        integ = (st["state"].get("integrity") or {}).get("status")
        step(no_start + 2, "경주가 끝난다", {"finished": st["state"].get("phase") == "finished", "confirmed": integ == "confirmed"},
             seconds=round(time.time() - t0, 1), integrity=integ)
        # 9 — 결과 대화 상자가 두 화면에 뜬다. 끝난 뒤의 맵 선택은 「다시 하기」 뒤에만 된다는 까닭을 말한다.
        host.page.wait_for_selector('[data-result-panel="revealed"]', timeout=60_000)
        part.page.wait_for_selector('[data-result-panel="revealed"]', timeout=60_000)
        h_end = map_snapshot(host, base, rid)
        p_end = map_snapshot(part, base, rid)
        step(no_start + 3, "결과 대화 상자 — 두 화면, 끝난 판도 같은 맵",
             {"host_dialog": host.page.locator("[data-result-dialog]").count() == 1, "participant_dialog": part.page.locator("[data-result-dialog]").count() == 1,
              "winners_same": winners_on(host.page) == winners_on(part.page) and bool(winners_on(host.page)),
              "host_agree": map_agrees(h_end, key), "participant_agree": map_agrees(p_end, key),
              "finished_reason": (h_end["reason"] or "") == MAP_REASON_FINISHED},
             winners=winners_on(host.page), reason=h_end["reason"])
        shots(f"{tag}-result")

    race_and_result(6, second, "06")

    # 10 · 11 — 다시 하기 뒤는 대기다. 맵은 그대로이고 다시 바꿀 수 있다.
    dialog_button(host.page, "다시 하기").click()
    host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=15_000)
    part.page.wait_for_selector('[data-marble-stage="idle"]', timeout=15_000)
    h_secs, h_snap = wait_map(host, base, rid, second, 5)
    step(10, "다시 하기 — 대기로 돌아가고 맵은 그대로다", {"host_agree": h_secs is not None, "picker_on": h_snap["picker"] == "on"}, host=h_snap)
    with host.page.expect_response(lambda r: "/marble/config" in r.url and r.request.method == "PUT") as resp:
        pick_map_in_toolbar(host.page, third)
    done, snaps = wait_both(host, part, base, rid, third)
    step(11, "새 판에서 맵 바꾸기 — 참가자가 3초 안에 같은 맵", {"put_200": resp.value.status == 200, "host_agree": done["host"] is not None,
                                                      "participant_within_3s": done["participant"] is not None and done["participant"] <= MAP_SYNC_LIMIT_S},
         seconds=done, host=snaps["host"], participant=snaps["participant"])
    shots("11-changed")

    # 12 — 다시 경주하면 새 맵을 쓴다(그리고 끝까지 같은 맵).
    race_and_result(12, third, "12")

    errors = {a.name: a.errors for a in (host, part)}
    result = {"room": rid, "maps": [first, second, third], "steps": steps, "console_errors": errors,
              "pass": all(s["pass"] for s in steps) and not any(errors.values())}
    for a in (host, part):
        a.ctx.close()
    chromium.close()
    other.close()
    return result


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--label", default="r1")
    ap.add_argument("--digest", action="store_true", help="기준 커밋과 엔진 · 판정 지문 대조 + 두 브라우저 지문 일치")
    ap.add_argument("--digest-base", default=DIGEST_BASE_DEFAULT, help="지문을 대조할 기준 커밋(기본: r23 회차 직전)")
    ap.add_argument("--digest-engine-only", action="store_true", help="--digest 에서 두 브라우저 경주를 건너뛴다(서버 없이 돈다)")
    ap.add_argument("--perf", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--layout", action="store_true")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--rail", action="store_true", help="레일 높이 배분(D-594)")
    ap.add_argument("--map", action="store_true", help="구슬 레이스 맵 흐름(D-593) — 방장 Chromium · 참가자 --participant-browser")
    ap.add_argument("--participant-browser", default="firefox", choices=["firefox", "chromium", "webkit"])
    # 예전의 `--map <판>` 은 `--map-key` 다(`--map` 은 맵 흐름 모드가 됐다).
    ap.add_argument("--map-key", default="wheel", choices=list(MAP_LABELS), help="--digest 의 두 브라우저 경주 · --perf 가 쓰는 판")
    ap.add_argument("--marble-n", type=int, default=12)
    ap.add_argument("--perf-n", type=int, nargs="+", default=[100])
    ap.add_argument("--perf-repeats", type=int, default=2)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    out = Path(args.out) / args.label
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    report = {"base_url": base, "label": args.label, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    modes = [m for m in ("layout", "fullscreen", "rail", "map", "digest", "perf", "capture") if getattr(args, m)]
    if args.digest:
        report["digest_engine"] = run_digest_compare(args.digest_base, out)
    browsers = args.layout or args.fullscreen or args.rail or args.map or args.perf or args.capture or (args.digest and not args.digest_engine_only)
    with (sync_playwright() if browsers else contextlib.nullcontext()) as pw:
        if args.layout:
            report["layout"] = run_layout(pw, base, out)
        if args.fullscreen:
            report["fullscreen"] = run_fullscreen(pw, base, out)
        if args.rail:
            report["rail"] = run_rail(pw, base, out)
        if args.map:
            report["map"] = run_map(pw, base, out, args.participant_browser)
        if args.digest and not args.digest_engine_only:
            report[f"digest_{args.map_key}"] = run_digest(pw, base, out, args.participant_browser, args.marble_n, args.map_key)
        if args.perf:
            report[f"perf_{args.map_key}"] = run_perf(pw, base, out, args.perf_n, args.perf_repeats, args.map_key)
        if args.capture:
            report["capture"] = run_capture(pw, base, out)
    verdicts = {k: v.get("pass") for k, v in report.items() if isinstance(v, dict) and "pass" in v}
    report["pass"] = all(verdicts.values()) if verdicts else False
    name = "report-" + "-".join(modes) + ".json" if modes else "report.json"
    (out / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[games_e2e] {verdicts} → {'PASS' if report['pass'] else 'FAIL'} ({out / name})")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
