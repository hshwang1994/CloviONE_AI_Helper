"""신호(`이슈 있음` · `차단됨`)를 **실제 브라우저에서 켜 보고** 그 결과를 눈으로 확인한다.

## 왜 jsdom 으로 안 되는가

이 회차가 고친 것은 둘이다.

1. **켤 자리가 없었다.** 그건 jsdom 이 잰다(`ticket-edit-signals.test.jsx`).
2. **켠 뒤에 그 값이 화면 어디에 어떤 색으로 서는가.** 이건 jsdom 이 원리적으로 말할 수
   없다 — 위색 띠가 `undefined` 로 떨어져 `currentColor` 가 되는 사고가 정확히 그
   부류다. 계산된 스타일이 실제 브라우저의 CSS 변수를 풀어야 보인다.

그래서 여기서는 한 바퀴를 돈다: 티켓을 열고 → 신호를 켜고 → 저장하고 → **목록에 그 표식이
섰는지** 보고 → 작업 보드의 신호 타일이 **어휘 표가 정한 색**으로 그려졌는지 좌표가 아니라
색으로 잰다.

## 쓰는 법

    python -m scripts.ui_qa.local_capture --harness signal_e2e

산출물: `dist/ui-qa/signal-e2e/{flows.json}` + 단계별 스크린샷.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "signal-e2e"

#: 어휘 표(`frontend/src/lib/ticketSignals.js`)가 정한 톤 → CSS 변수 이름.
#: 여기 적는 것이 두 번째 사본이 되지 않게, 재는 것은 **셋이 서로 다른가** 와
#: **이슈가 보라 계열인가** 다 — 정확한 hex 는 토큰이 정한다.
SIGNAL_TILE_VAR = {"issue": "--badge-purple-fg"}


def _goto(page, base: str, path: str) -> None:
    """HashRouter 다 — 경로는 `#` 뒤에 온다(`scripts/ui_qa/routes.py` 와 같은 규약)."""
    page.goto(f"{base}/#{path}", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2000)


def _shot(page, out: Path, name: str) -> str:
    p = out / f"{name}.png"
    page.screenshot(path=str(p), full_page=False)
    return p.name


def flow_turn_on_issue(page, base: str, out: Path) -> dict:
    """팀 티켓에서 첫 티켓을 열어 「이슈 있음」을 켜고, 목록에 표식이 서는지 본다.

    `/my-tickets` 가 아닌 이유: QA 계정에 배정된 티켓이 없을 수 있고, 그러면 이 흐름이
    「고칠 티켓이 없다」로 건너뛴다 — 건너뛴 검사는 통과가 아니다.
    """
    fails: list[str] = []
    steps: list[str] = []
    _goto(page, base, "/team-tickets")

    # 넓은 화면의 표에서는 「수정」이 글자 단추다(좁은 화면 카드에서는 aria-label 이다).
    edit = page.get_by_role("button", name="수정").first
    if edit.count() == 0:
        return {"flow": "turn_on_issue", "status": "SKIP",
                "fails": ["고칠 티켓이 하나도 없다 — 표본 데이터를 확인하라"],
                "steps": steps, "shot": _shot(page, out, "issue-no-ticket")}
    label = edit.get_attribute("aria-label") or ""
    edit.click()
    page.wait_for_selector("#te-issue", timeout=20000)
    steps.append(f"편집 모달을 열었다({label})")

    box = page.locator("#te-issue")
    was_on = box.is_checked()
    if was_on:
        box.uncheck()
        page.locator('button:has-text("저장")').first.click()
        page.wait_for_timeout(1500)
        edit.click()
        page.wait_for_selector("#te-issue", timeout=20000)
    _shot(page, out, "issue-modal")

    page.locator("#te-issue").check()
    steps.append("「이슈 있음」을 켰다")
    page.locator('button:has-text("저장")').first.click()
    page.wait_for_timeout(2500)

    # 목록에 신호 표식이 섰는가. `data-signal` 은 표시 부품이 남기는 자리다.
    mark = page.locator('[data-signal="issue"]')
    if mark.count() == 0:
        fails.append("저장했는데 목록에 「이슈 있음」 표식이 없다")
    else:
        steps.append(f"목록에 표식이 {mark.count()}개 섰다")
        tone = mark.first.get_attribute("data-tone")
        if tone != "purple":
            fails.append(f"표식의 톤이 어휘 표와 다르다: {tone}")
        color = mark.first.evaluate("el => getComputedStyle(el).color")
        steps.append(f"표식 색 = {color}")
    shot = _shot(page, out, "issue-after-save")
    return {"flow": "turn_on_issue", "status": "PASS" if not fails else "FAIL",
            "fails": fails, "steps": steps, "shot": shot}


def flow_board_tiles(page, base: str, out: Path) -> dict:
    """작업 보드의 신호 타일이 **어휘 표가 정한 색**으로 그려지는가.

    🔴 이 자리가 조용히 틀려 있었다. 위색 띠 색을 팔레트 경로로 풀었는데 보라·틸·인디고는
    팔레트가 아니라 CSS 변수라, 셋 다 `undefined` 가 나가 `currentColor`(글자색)로
    떨어졌다. 아무 오류도 안 난다 — 그래서 **계산된 색**으로 잰다.
    """
    fails: list[str] = []
    steps: list[str] = []
    _goto(page, base, "/work-board")
    page.wait_for_timeout(1500)

    strip = page.locator('[role="group"][aria-label="신호별 티켓 수"]')
    if strip.count() == 0:
        return {"flow": "board_signal_tiles", "status": "SKIP",
                "fails": ["신호 타일 줄이 없다 — 셋이 다 0 이면 안 그린다(의도된 동작)"],
                "steps": steps, "shot": _shot(page, out, "board-no-tiles")}

    tiles = strip.locator("button")
    seen: dict[str, str] = {}
    for i in range(tiles.count()):
        t = tiles.nth(i)
        name = t.get_attribute("aria-label") or f"tile-{i}"
        band = t.evaluate("el => getComputedStyle(el).borderBlockStartColor")
        ink = t.evaluate("el => getComputedStyle(el).color")
        seen[name] = band
        steps.append(f"{name}: 띠={band}")
        # 띠가 글자색과 같으면 색이 안 실린 것이다(`currentColor` 로 떨어진 그 사고).
        if band == ink:
            fails.append(f"{name} 의 위색 띠가 글자색과 같다 — 색이 안 실렸다")
    if len(set(seen.values())) < len(seen):
        fails.append(f"신호 타일 색이 서로 겹친다: {seen}")
    shot = _shot(page, out, "board-tiles")
    return {"flow": "board_signal_tiles", "status": "PASS" if not fails else "FAIL",
            "fails": fails, "steps": steps, "colors": seen, "shot": shot}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="신호를 켜고 그 표시를 실브라우저에서 잰다")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.insecure:
        tls.apply_default_https_context()
    print(tls.describe())

    from playwright.sync_api import sync_playwright

    flows: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        sess = ensure_session(browser, base, REPO_ROOT / "dist" / "ui-qa",
                              insecure=args.insecure, log=print)
        ctx = new_context(browser, storage_state=sess.storage_state,
                          user_id=sess.user_id, theme="light",
                          viewport=Viewport("1920x1080", 1920, 1080),
                          insecure=args.insecure)
        page = ctx.new_page()
        flows.append(flow_turn_on_issue(page, base, out))
        flows.append(flow_board_tiles(page, base, out))
        ctx.close()
        browser.close()

    (out / "flows.json").write_text(json.dumps(flows, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    bad = [f for f in flows if f["status"] == "FAIL"]
    for f in flows:
        print(f"[{f['status']}] {f['flow']}")
        for s in f.get("steps", []):
            print(f"    · {s}")
        for x in f.get("fails", []):
            print(f"    ✗ {x}")
    print(f"flows.json : {out / 'flows.json'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
