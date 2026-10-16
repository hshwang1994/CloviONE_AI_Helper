"""랩 구슬 레이스 맵 흐름 — 사용자 계정 하나(방장)로 「[검증] 맵 선택」 방의 방장 경로를 돈다 (r23 W8 · D-593).

두 브라우저 동기화와 참가자 권한(403)은 로컬 `games_e2e --map` 이 맡는다(씨앗 계정 둘). 랩에는 사용자 계정 하나뿐이라 이 하네스는
방장 경로만 잰다. 참가자는 방장 + 자유 이름 둘이다 — 혼자서도 경주가 서고 결과는 「방장 결과만」(`host_only`)으로 발표된다.

  1 게임방 추가(구슬 레이스 · 처음 맵 탐욕의 항아리 · 2배속) → 방에 들어간다(툴바 · 방 상태 · 그린 판이 같은 맵)
  2 참가자 — 자유 이름 둘을 더한다(「[검증]」 표지)
  3 대기 중 툴바 「맵 선택」으로 비눗방울
  4 경주 시작 → 경주에 박힌 맵이 비눗방울, 맵 선택이 막히고 까닭이 보인다, 서버도 409
  5 경주가 끝난다 → 결과 대화 상자, 끝난 판도 같은 맵
  6 다시 하기 → 대기로 돌아가고 맵은 그대로
  7 새 판에서 맵을 밤을 달리다로 → 다시 경주 → 경주 맵이 밤을 달리다 → 결과
  8 정리 — 게임방 종료(방 상태 404)

자격은 `dist/ops/user.env` 의 AI_TRUTH_EMAIL · AI_TRUTH_PASSWORD 를 읽는다(값은 찍지 않는다). 만든 방은 끝에 언제나 종료한다.

    python -m scripts.ui_qa.lab_marble_check --base https://clovirassist.goodmit.co.kr --out dist/ui-qa/r23-lab-marble
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

from scripts.ui_qa.ai_lab_common import read_env_file  # noqa: E402
from scripts.ui_qa.games_e2e import (  # noqa: E402
    MAP_LABELS, MAP_REASON_FINISHED, MAP_REASON_RUNNING, Actor, api, dialog_button, map_snapshot, pick_map_in_toolbar,
    state_map, wait_map, wait_state, winners_on,
)

KST = timezone(timedelta(hours=9))
ENV_KEYS = ("AI_TRUTH_EMAIL", "AI_TRUTH_PASSWORD")


def log(msg: str) -> None:
    print(msg, flush=True)


def open_lab_actor(browser, base: str, creds: dict) -> Actor:
    ctx = browser.new_context(viewport={"width": 1366, "height": 768}, ignore_https_errors=True, locale="ko-KR",
                              timezone_id="Asia/Seoul")
    r = ctx.request.post(f"{base}/login", data={"email": creds["AI_TRUTH_EMAIL"], "password": creds["AI_TRUTH_PASSWORD"]})
    if r.status != 200:
        ctx.close()
        raise SystemExit(f"로그인 실패({r.status})")
    me = ctx.request.get(base + "/api/me").json()
    page = ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    return Actor(name="lab-host", ctx=ctx, page=page, csrf=me["csrf_token"], user_id=me["user"]["id"], errors=errors)


def run(base: str, out: Path, creds: dict) -> dict:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%m%d-%H%M")
    title = f"[검증] 맵 선택 {stamp}"
    steps: list[dict] = []
    rid = None

    def step(no: int, name: str, checks: dict, **data) -> None:
        ok = all(bool(v) for v in checks.values())
        steps.append({"step": no, "name": name, "checks": checks, "pass": ok, **data})
        log(f"[L] {no}. {name}: {'PASS' if ok else 'FAIL'} " + " ".join(f"{k}={v}" for k, v in checks.items() if not v))

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        host = open_lab_actor(browser, base, creds)
        try:
            first, second, third = "pot", "bubble", "yoru"
            host.page.goto(f"{base}/#/games", wait_until="domcontentloaded")
            host.page.get_by_role("button", name="게임방 추가").first.click()
            dialog = host.page.locator('[role="dialog"]')
            dialog.locator("#gr-game").click()
            host.page.get_by_role("option", name="구슬 레이스").click()
            dialog.locator("#gr-title").fill(title)
            dialog.locator("#gr-marble-map").click()
            host.page.get_by_role("option", name=MAP_LABELS[first]).click()
            dialog.locator("#gr-marble-speed").click()
            host.page.get_by_role("option", name="2배속").click()
            dialog.get_by_role("button", name="추가", exact=True).click()
            host.page.wait_for_url(lambda u: "#/games/" in u, timeout=20_000)
            host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=30_000)
            rid = host.page.url.split("#/games/")[1].split("?")[0].strip("/")
            secs, snap = wait_map(host, base, rid, first, 8)
            step(1, "게임방 추가 → 방(처음 맵이 툴바 · 상태 · 그린 판에 같다)", {"agree": secs is not None, "picker_on": snap["picker"] == "on"},
                 room=rid, title=title, snap=snap)

            names = [{"name": "[검증] 구슬 1"}, {"name": "[검증] 구슬 2"}]
            st, body = api(host, base, "PUT", f"/api/games/rooms/{rid}/marble/participants", {"participants": names})
            step(2, "참가자 — 자유 이름 둘", {"put_200": st == 200}, status=st)

            with host.page.expect_response(lambda r: "/marble/config" in r.url and r.request.method == "PUT") as resp:
                pick_map_in_toolbar(host.page, second)
            secs, snap = wait_map(host, base, rid, second, 8)
            step(3, "대기 중 툴바 「맵 선택」 → 비눗방울", {"put_200": resp.value.status == 200, "agree": secs is not None}, snap=snap)
            host.page.screenshot(path=str(out / "lab-marble-03-changed.png"))

            def race(no: int, key: str, tag: str) -> None:
                host.page.click('[data-room-toolbar] button:has-text("경주 시작")')
                host.page.wait_for_selector('[data-marble-stage="running"]', timeout=20_000)
                blocked = map_snapshot(host, base, rid)
                st409, _ = api(host, base, "PUT", f"/api/games/rooms/{rid}/marble/config", {"map": "wheel"})
                still = state_map(host, base, rid)
                step(no, "경주 시작 — 경주 맵이 고른 맵, 맵 선택이 막히고 까닭이 보인다, 서버 409",
                     {"race_map": still.get("race_map") == key, "picker_off": blocked["picker"] == "off",
                      "reason": (blocked.get("reason") or "").startswith(MAP_REASON_RUNNING), "server_409": st409 == 409},
                     reason=blocked.get("reason"), server_status=st409)
                host.page.screenshot(path=str(out / f"lab-marble-{tag}-running.png"))
                t0 = time.time()
                st = wait_state(host, base, rid, lambda s: (s.get("state") or {}).get("phase") in ("finished", "abandoned"), 300)
                integ = ((st.get("state") or {}).get("integrity") or {}).get("status")
                host.page.wait_for_selector('[data-result-panel="revealed"]', timeout=90_000)
                end = map_snapshot(host, base, rid)
                step(no + 1, "경주가 끝난다 — 결과 대화 상자, 끝난 판도 같은 맵",
                     {"finished": (st.get("state") or {}).get("phase") == "finished", "dialog": host.page.locator("[data-result-dialog]").count() == 1,
                      "winners": bool(winners_on(host.page)), "same_map": end["state"].get("map") == key,
                      "finished_reason": (end.get("reason") or "") == MAP_REASON_FINISHED},
                     seconds=round(time.time() - t0, 1), integrity=integ, winners=winners_on(host.page))
                host.page.screenshot(path=str(out / f"lab-marble-{tag}-result.png"))

            race(4, second, "04")
            dialog_button(host.page, "다시 하기").click()
            host.page.wait_for_selector('[data-marble-stage="idle"]', timeout=20_000)
            secs, snap = wait_map(host, base, rid, second, 8)
            step(6, "다시 하기 — 대기로 돌아가고 맵은 그대로", {"agree": secs is not None, "picker_on": snap["picker"] == "on"})
            with host.page.expect_response(lambda r: "/marble/config" in r.url and r.request.method == "PUT") as resp:
                pick_map_in_toolbar(host.page, third)
            secs, snap = wait_map(host, base, rid, third, 8)
            step(7, "새 판에서 맵 바꾸기 → 밤을 달리다", {"put_200": resp.value.status == 200, "agree": secs is not None})
            race(8, third, "08")
        finally:
            if rid:
                st, _ = api(host, base, "POST", f"/api/games/rooms/{rid}/disband", {})
                gone = host.ctx.request.get(f"{base}/api/games/rooms/{rid}/state").status
                step(10, "정리 — 게임방 종료", {"disband_ok": st in (200, 204), "state_404": gone == 404}, disband_status=st, state_status=gone)
            errors = list(host.errors)
            host.ctx.close()
            browser.close()
    result = {"base": base, "room": rid, "title": title, "steps": steps, "console_errors": errors,
              "pass": bool(steps) and all(s["pass"] for s in steps) and not errors}
    (out / "report-lab-marble.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    log(("LAB_MARBLE_PASS" if result["pass"] else "LAB_MARBLE_FAIL") + f" → {out / 'report-lab-marble.json'}")
    return result


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", default=str(ROOT / "dist" / "ui-qa" / "r23-lab-marble"))
    ap.add_argument("--env-file", default=str(ROOT / "dist" / "ops" / "user.env"))
    args = ap.parse_args()
    creds = read_env_file(args.env_file, ENV_KEYS)
    if not all(creds.get(k) for k in ENV_KEYS):
        log("자격이 없습니다 — env 파일에 AI_TRUTH_EMAIL · AI_TRUTH_PASSWORD 가 있어야 합니다.")
        return 2
    res = run(args.base.rstrip("/"), Path(args.out), creds)
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
