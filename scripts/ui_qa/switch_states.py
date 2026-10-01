"""스위치의 상태를 실제 브라우저에서 만들어 찍고, 조작 계약을 판정한다 (D-525).

`kit_measure` 의 `switch_geometry` 는 화면을 **연 그대로** 잰다. 정지 화면에는 hover · 키보드 초점 · 누르는 중 같은
상태가 없고, 조작(Space · 라벨 클릭 · 누르는 자리 가장자리 · 비활성)은 치수로 판정할 수 없다. 이 하네스는 그 상태를
실제로 만들어 스위치 줄을 잘라 찍고, 그 상태에서 같은 `switch_geometry` 를 다시 재며, 조작 계약을 판정한다.

## 쓰는 법

    python -m scripts.ui_qa.local_capture --harness switch_states \\
        --viewports 1920x1080@2x 2560x1440 3840x2160 --switch-themes light dark --switch-label switch-after

`--label` · `--themes` 는 `local_capture` 가 먹는 이름이라 `--switch-label` · `--switch-themes` 를 쓴다.

## 무엇을 판정하나

- 갤러리(`/#/kit` 「조작기의 상태」): 꺼짐 · 켜짐 · hover · 키보드 초점 · 누르는 중 · 비활성 꺼짐 · 비활성 켜짐을 줄
  단위로 찍는다. Space 가 상태를 바꾸고 초점이 남는가, 라벨을 누르면 바뀌는가, 트랙 위 9px(옛 34 상자의 밖, 누르는 자리
  44 의 안)을 누르면 바뀌는가, 비활성은 클릭 · 라벨 클릭에 그대로인가, 키보드 초점 링이 트랙에 서고 루트 안에 들어오는가.
- 내 프로필(`/#/profile`): 알림 판 전체를 찍고(밀도), 첫 스위치를 실제로 바꿔 **저장이 도는 동안 다른 스위치가 비활성으로
  바뀌지 않고 누른 스위치는 바로 바뀌는가**를 본다. 저장 시간을 벌리려고 네트워크 지연 500ms 를 건다. 끝나면 원래 값으로
  되돌린다.
- 메일(`/admin#/mail`) · AI 연결(`/admin#/ai-connection`): 스위치 판을 찍고 hover · 키보드 초점만 만든다(저장하지 않는다).

## 판정 규율

못 만든 상태는 통과가 아니다 — `skipped` 로 이유와 함께 적는다. 판정이 하나라도 실패하면 종료 코드 1, 실패는 없지만 못 만든
상태가 있으면 2 다. 누르는 중(active) 은 스위치 위에서 누르고 **줄의 빈 자리에서 뗀다** — 같은 요소 위에서 떼지 않으면
click 이 생기지 않으므로 아무것도 저장되지 않는다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_BASE = REPO_ROOT / "dist" / "ui-qa"

# 갤러리 견본의 접근 가능한 이름(`KitGallery.jsx` 「조작기의 상태」). 이름이 바뀌면 여기와 함께 바꾼다.
KIT = {
    "on": "새 댓글 알림",         # 조작 가능 — 누르면 바뀐다
    "off": "주간 요약 메일",       # 꺼짐 — 눌러도 그대로다(onChange 가 아무것도 하지 않는다)
    "focus": "키보드 초점 견본",    # 초점 표시를 클래스로 얹은 정지 견본
    "disabled_on": "관리자가 끈 알림",
    "disabled_off": "관리자가 막은 메일",
}

# 쓰기 지킴 — 이 하네스가 일부러 저장하는 자리는 내 프로필의 저장 판정 하나뿐이다(바꾼 뒤 원래 값으로 되돌린다).
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ALLOWED_WRITES = {"profile": (("PATCH", "/api/me/preferences"),)}

ROOT_XPATH = "xpath=ancestor::span[contains(concat(' ', normalize-space(@class), ' '), ' MuiSwitch-root ')][1]"
ROW_XPATH = "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' k-settingrow ')][1]"
CARD_XPATH = "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' MuiCard-root ')][1]"

# 키보드 초점의 증거 — 링이 **트랙**에 서고(switchBase 의 링은 꺼짐), 링의 바깥 끝이 루트 안에 들어오는가.
RING_JS = r"""
(root) => {
  const track = root.querySelector('.MuiSwitch-track');
  const base = root.querySelector('.MuiSwitch-switchBase');
  const ts = getComputedStyle(track);
  const bs = getComputedStyle(base);
  const R = root.getBoundingClientRect();
  const T = track.getBoundingClientRect();
  const width = parseFloat(ts.outlineWidth) || 0;
  const offset = parseFloat(ts.outlineOffset) || 0;
  const reach = width + offset;
  const e = 0.5;
  const inside = T.left - reach >= R.left - e && T.right + reach <= R.right + e
    && T.top - reach >= R.top - e && T.bottom + reach <= R.bottom + e;
  return {
    focusVisible: base.classList.contains('Mui-focusVisible'),
    trackOutline: ts.outlineStyle, width, offset, color: ts.outlineColor,
    baseOutline: bs.outlineStyle, inside,
  };
}
"""

# 저장이 도는 동안의 표본 — 배지 알림 스위치 중 비활성인 것의 수와 첫 스위치의 상태.
SAVE_PROBE_JS = r"""
() => {
  const els = [...document.querySelectorAll('input[role="switch"]')]
    .filter((el) => /배지 알림$/.test(el.getAttribute('aria-label') || ''));
  return { disabled: els.filter((el) => el.disabled).length, first: els.length ? els[0].checked : null, total: els.length };
}
"""


class Skip(RuntimeError):
    """상태를 만들 대상을 못 찾았다 — 통과가 아니라 미실행이다."""


def _goto(page, base: str, route_id: str, settle_ms: int) -> None:
    from scripts.ui_qa import capture as cap, routes as routes_mod

    route = routes_mod.BY_ID[route_id]
    page.goto(route.url(base, route.hash_path), wait_until="domcontentloaded", timeout=45_000)
    cap._settle(page, settle_ms=settle_ms, timeout_ms=45_000)
    page.mouse.move(0, 0)


def _switch(page, name):
    loc = page.get_by_role("switch", name=name, exact=True)
    if loc.count() == 0:
        raise Skip(f"스위치 없음: {name}")
    return loc.first


def _root(inp):
    return inp.locator(ROOT_XPATH)


def _row(inp):
    row = inp.locator(ROW_XPATH)
    return row if row.count() else _root(inp)


def _checked(inp) -> bool:
    return bool(inp.evaluate("el => el.checked"))


def _scale(page) -> float:
    return float(page.evaluate("() => (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16) / 16"))


def _geometry(page, inp) -> dict:
    """그 스위치 하나만 `kit_measure.MEASURE_JS` 의 `switch_geometry` 로 잰다."""
    from scripts.ui_qa.kit_measure import CONTRACT, MEASURE_JS

    root = _root(inp)
    root.evaluate("el => el.parentElement.setAttribute('data-switch-probe', '')")
    try:
        got = page.evaluate(MEASURE_JS, {**CONTRACT, "scope": "[data-switch-probe]"})
    finally:
        root.evaluate("el => el.parentElement.removeAttribute('data-switch-probe')")
    return got.get("switch_geometry") or {"checked": 0, "failed": 0, "bad": []}


def _keyboard_focus(page, inp) -> None:
    """브라우저가 `:focus-visible` 로 보는 초점을 **진짜 Tab 으로** 만든다.

    `el.focus()` 만으로는 `:focus-visible` 도 `Mui-focusVisible` 도 안 서는 일이 잦다(`brand.py` · `nav_e2e.py` 가 같은
    교훈을 적어 두었다). 그 자리에 둔 뒤 Shift+Tab 으로 한 칸 물러났다가 Tab 으로 돌아온다 — 키보드로 도착한 초점이다."""
    page.mouse.move(0, 0)
    inp.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    page.wait_for_timeout(250)
    if not inp.evaluate("el => el === document.activeElement && el.matches(':focus-visible')"):
        raise Skip("키보드 초점을 만들지 못했다")


def _hover(page, inp) -> None:
    """트랙 한가운데에 포인터를 둔다. `locator.hover()` 는 쓰지 않는다 — 트랙 위에는 숨은 input 이 덮여 있어
    Playwright 가 「다른 요소가 포인터를 가로챈다」며 끝까지 기다린다(그 input 이 진짜 누르는 자리다)."""
    box = _root(inp).locator(".MuiSwitch-track").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(250)


def _blur(page) -> None:
    page.evaluate("() => document.activeElement && document.activeElement.blur && document.activeElement.blur()")
    page.mouse.move(0, 0)
    page.wait_for_timeout(250)


def _press_and_hold(page, inp) -> None:
    box = _root(inp).locator(".MuiSwitch-track").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(250)


def _release_away(page, inp) -> None:
    """줄의 왼쪽 위 빈 자리에서 뗀다 — 누른 요소와 뗀 요소가 달라 click 이 생기지 않는다."""
    box = _row(inp).bounding_box()
    page.mouse.move(box["x"] + 2, box["y"] + 2)
    page.mouse.up()
    page.mouse.move(0, 0)
    page.wait_for_timeout(250)


class Run:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.records: list[dict] = []

    def shot(self, el, theme: str, vp: str, name: str) -> str:
        path = self.out_dir / "switch" / theme / vp / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        el.screenshot(path=str(path), animations="disabled")
        try:
            return path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return str(path)

    def add(self, **record) -> None:
        self.records.append(record)
        verdict = "SKIPPED — " + record["skipped"] if record.get("skipped") else ("ok" if record.get("ok", True) else "FAIL")
        print(f"[switch] {record['theme']:<5} {record['viewport']:<14} {record['state']:<28} {verdict}", flush=True)


def _state(run: Run, page, theme: str, vp: str, name: str, fn) -> None:
    """상태 하나를 만들고 찍고 잰다. `fn` 은 (찍을 요소, 잴 스위치, 추가 판정 dict) 를 낸다."""
    try:
        el, inp, extra = fn()
        geo = _geometry(page, inp)
        ok = not geo.get("failed") and all(v is not False for k, v in (extra or {}).items() if k.endswith("_ok"))
        run.add(theme=theme, viewport=vp, state=name, ok=ok, shot=run.shot(el, theme, vp, name),
                geometry={"checked": geo.get("checked", 0), "failed": geo.get("failed", 0), "bad": geo.get("bad", [])[:2]},
                **(extra or {}))
    except Skip as exc:
        run.add(theme=theme, viewport=vp, state=name, skipped=str(exc))
    except Exception as exc:  # noqa: BLE001 — 하나가 죽어도 나머지 상태는 잰다. 죽은 것은 실패로 남는다.
        run.add(theme=theme, viewport=vp, state=name, ok=False, error=f"{type(exc).__name__}: {exc}"[:300])


def _check(run: Run, theme: str, vp: str, name: str, fn) -> None:
    """조작 판정 하나. `fn` 은 (통과 여부, 근거 dict) 를 낸다."""
    try:
        ok, detail = fn()
        run.add(theme=theme, viewport=vp, state=name, ok=bool(ok), check=True, detail=detail)
    except Skip as exc:
        run.add(theme=theme, viewport=vp, state=name, skipped=str(exc), check=True)
    except Exception as exc:  # noqa: BLE001 — 하나가 죽어도 나머지 판정은 한다. 죽은 것은 실패로 남는다.
        run.add(theme=theme, viewport=vp, state=name, ok=False, check=True, error=f"{type(exc).__name__}: {exc}"[:300])


# ── 갤러리 ──────────────────────────────────────────────────────────────────

def kit_states(run: Run, page, base: str, theme: str, vp: str, settle: int) -> None:
    _goto(page, base, "user_kit", settle)
    section = page.locator("#kit-control-states")
    if section.count():
        section.scroll_into_view_if_needed()

    def rest(key):
        def fn():
            inp = _switch(page, KIT[key])
            _row(inp).scroll_into_view_if_needed()
            _blur(page)
            return _row(inp), inp, {"checked": _checked(inp)}
        return fn

    def hover(key):
        def fn():
            inp = _switch(page, KIT[key])
            _row(inp).scroll_into_view_if_needed()
            _blur(page)
            _hover(page, inp)
            return _row(inp), inp, {"checked": _checked(inp)}
        return fn

    def focus(key):
        def fn():
            inp = _switch(page, KIT[key])
            _row(inp).scroll_into_view_if_needed()
            _keyboard_focus(page, inp)
            ring = _root(inp).evaluate(RING_JS)
            ring_ok = ring["focusVisible"] and ring["trackOutline"] == "solid" and ring["width"] >= 2 \
                and ring["baseOutline"] == "none" and ring["inside"]
            return _row(inp), inp, {"ring": ring, "ring_ok": ring_ok}
        return fn

    def active(key):
        """누른 채로 찍고 잰 뒤 줄의 빈 자리에서 뗀다 — 상태가 그대로여야 한다(click 이 생기지 않았다)."""
        name = f"kit.{key}-active"
        try:
            inp = _switch(page, KIT[key])
        except Skip as exc:
            run.add(theme=theme, viewport=vp, state=name, skipped=str(exc))
            return
        _row(inp).scroll_into_view_if_needed()
        _blur(page)
        was = _checked(inp)
        _press_and_hold(page, inp)
        try:
            shot = run.shot(_row(inp), theme, vp, name)
            geo = _geometry(page, inp)
        finally:
            _release_away(page, inp)
        unchanged = _checked(inp) == was
        run.add(theme=theme, viewport=vp, state=name, ok=not geo.get("failed") and unchanged, shot=shot,
                geometry={"checked": geo.get("checked", 0), "failed": geo.get("failed", 0), "bad": geo.get("bad", [])[:2]},
                unchanged_after_release=unchanged)

    for key in ("off", "on", "disabled_off", "disabled_on"):
        _state(run, page, theme, vp, f"kit.{key}", rest(key))
    for key in ("off", "on"):
        _state(run, page, theme, vp, f"kit.{key}-hover", hover(key))
        _state(run, page, theme, vp, f"kit.{key}-focus", focus(key))
        active(key)
    _state(run, page, theme, vp, "kit.focus-sample", rest("focus"))

    def space_toggles():
        inp = _switch(page, KIT["on"])
        _row(inp).scroll_into_view_if_needed()
        was = _checked(inp)
        _keyboard_focus(page, inp)
        page.keyboard.press("Space")
        page.wait_for_timeout(250)
        flipped = _checked(inp) != was
        kept_focus = bool(inp.evaluate("el => el === document.activeElement"))
        page.keyboard.press("Space")
        page.wait_for_timeout(250)
        restored = _checked(inp) == was
        _blur(page)
        return flipped and kept_focus and restored, {"flipped": flipped, "kept_focus": kept_focus, "restored": restored}

    def label_click_toggles():
        inp = _switch(page, KIT["on"])
        row = _row(inp)
        row.scroll_into_view_if_needed()
        was = _checked(inp)
        label = row.get_by_text(KIT["on"], exact=True).first
        label.click()
        page.wait_for_timeout(250)
        flipped = _checked(inp) != was
        if flipped:
            label.click()
            page.wait_for_timeout(250)
        restored = _checked(inp) == was
        _blur(page)
        tag = label.evaluate("el => el.tagName.toLowerCase() + (el.getAttribute('for') ? '[for]' : '')")
        return flipped and restored, {"flipped": flipped, "restored": restored, "label": tag}

    def edge_click_toggles():
        inp = _switch(page, KIT["on"])
        _row(inp).scroll_into_view_if_needed()
        _blur(page)
        was = _checked(inp)
        track = _root(inp).locator(".MuiSwitch-track").bounding_box()
        y = track["y"] - 9 * _scale(page)
        page.mouse.click(track["x"] + track["width"] / 2, y)
        page.wait_for_timeout(250)
        flipped = _checked(inp) != was
        if flipped:
            page.mouse.click(track["x"] + track["width"] / 2, y)
            page.wait_for_timeout(250)
        restored = _checked(inp) == was
        _blur(page)
        root = _root(inp).bounding_box()
        return flipped and restored, {"flipped": flipped, "restored": restored,
                                      "hit_h": round(root["height"], 1), "probe_dy": round(track["y"] - y, 1)}

    def disabled_ignores():
        results = {}
        for key in ("disabled_on", "disabled_off"):
            inp = _switch(page, KIT[key])
            row = _row(inp)
            row.scroll_into_view_if_needed()
            was = _checked(inp)
            # 둘 다 `force` 다 — Playwright 는 비활성 컨트롤과 그 컨트롤의 `<label for>` 를 「누를 수 없음」으로 보고
            # 끝까지 기다린다. 눌러도 바뀌지 않는지를 보려는 것이므로 클릭을 그대로 보내고 브라우저의 판단을 본다.
            inp.click(force=True)
            page.wait_for_timeout(200)
            label = row.get_by_text(re.compile(r"^관리자가 "), exact=False).first
            if label.count():
                label.click(force=True)
                page.wait_for_timeout(200)
            inp.focus()
            focused = bool(inp.evaluate("el => el === document.activeElement"))
            results[key] = {"disabled": bool(inp.evaluate("el => el.disabled")), "unchanged": _checked(inp) == was,
                            "focusable": focused}
        ok = all(v["disabled"] and v["unchanged"] and not v["focusable"] for v in results.values())
        _blur(page)
        return ok, results

    _check(run, theme, vp, "kit.space-toggles", space_toggles)
    _check(run, theme, vp, "kit.label-click-toggles", label_click_toggles)
    _check(run, theme, vp, "kit.edge-click-toggles", edge_click_toggles)
    _check(run, theme, vp, "kit.disabled-ignores", disabled_ignores)


# ── 실제 화면 ────────────────────────────────────────────────────────────────

def _panel(run: Run, page, theme: str, vp: str, name: str, inp) -> None:
    card = inp.locator(CARD_XPATH)
    el = card if card.count() else _row(inp)
    el.scroll_into_view_if_needed()
    _blur(page)
    run.add(theme=theme, viewport=vp, state=name, ok=True, shot=run.shot(el, theme, vp, name))


def _hover_and_focus(run: Run, page, theme: str, vp: str, prefix: str, inp) -> None:
    def hover():
        _row(inp).scroll_into_view_if_needed()
        _blur(page)
        _hover(page, inp)
        return _row(inp), inp, {}

    def focus():
        _row(inp).scroll_into_view_if_needed()
        _keyboard_focus(page, inp)
        ring = _root(inp).evaluate(RING_JS)
        ring_ok = ring["focusVisible"] and ring["trackOutline"] == "solid" and ring["width"] >= 2 \
            and ring["baseOutline"] == "none" and ring["inside"]
        return _row(inp), inp, {"ring": ring, "ring_ok": ring_ok}

    _state(run, page, theme, vp, f"{prefix}.hover", hover)
    _state(run, page, theme, vp, f"{prefix}.focus", focus)
    _blur(page)


def profile_states(run: Run, ctx, page, base: str, theme: str, vp: str, settle: int) -> None:
    _goto(page, base, "user_profile", settle)
    badge = page.get_by_role("switch", name=re.compile(r"배지 알림$"))
    if badge.count() < 2:
        run.add(theme=theme, viewport=vp, state="profile.panel", skipped="배지 알림 스위치가 둘보다 적다")
        return
    first = badge.first
    _panel(run, page, theme, vp, "profile.panel", first)
    mail = page.get_by_role("switch", name=re.compile(r"메일로 받기$"))
    if mail.count():
        # 메일을 끈 동안의 유형 스위치 — 실제 화면의 「비활성 켜짐」 견본이다.
        run.add(theme=theme, viewport=vp, state="profile.mail-row", ok=True,
                shot=run.shot(_row(mail.first), theme, vp, "profile.mail-row"),
                disabled=bool(mail.first.evaluate("el => el.disabled")), checked=_checked(mail.first))
    _hover_and_focus(run, page, theme, vp, "profile", first)

    def save_keeps_others_enabled():
        first.scroll_into_view_if_needed()
        _blur(page)
        was = _checked(first)
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.emulateNetworkConditions",
                 {"offline": False, "latency": 500, "downloadThroughput": -1, "uploadThroughput": -1})
        try:
            first.click()
            samples = []
            for _ in range(30):
                samples.append(page.evaluate(SAVE_PROBE_JS))
                page.wait_for_timeout(30)
        finally:
            cdp.send("Network.emulateNetworkConditions",
                     {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
        page.wait_for_timeout(1500)
        max_disabled = max(s["disabled"] for s in samples)
        # 누른 순간(첫 표본 셋 안, ~100ms) 상태가 바뀌었는가 — 응답(500ms 뒤)을 기다리지 않는가.
        immediate = any(s["first"] is not None and s["first"] != was for s in samples[:3])
        # 되돌린다 — 저장이 끝나 활성인 뒤에 누른다.
        for _ in range(40):
            if not first.evaluate("el => el.disabled"):
                break
            page.wait_for_timeout(100)
        if _checked(first) != was:
            first.click()
            page.wait_for_timeout(1500)
        restored = _checked(first) == was
        total = samples[0]["total"] if samples else 0
        return max_disabled == 0 and immediate and restored, {
            "max_disabled_during_save": max_disabled, "of": total, "immediate": immediate, "restored": restored}

    _check(run, theme, vp, "profile.save-keeps-others-enabled", save_keeps_others_enabled)


def admin_states(run: Run, page, base: str, theme: str, vp: str, settle: int) -> None:
    for route_id, pattern, prefix in (
        ("admin_mail", re.compile(r"메일 허용$"), "mail"),
        ("admin_ai-connection", re.compile(r"^AI 도우미$"), "ai"),
    ):
        try:
            _goto(page, base, route_id, settle)
            loc = page.get_by_role("switch", name=pattern)
            if loc.count() == 0:
                raise Skip("스위치 없음")
            first = loc.first
            _panel(run, page, theme, vp, f"{prefix}.panel", first)
            _hover_and_focus(run, page, theme, vp, prefix, first)
        except Skip as exc:
            run.add(theme=theme, viewport=vp, state=f"{prefix}.panel", skipped=str(exc))


def run(args) -> int:
    from playwright.sync_api import sync_playwright

    from scripts.ui_qa import capture as cap, tls
    from scripts.ui_qa.auth import ensure_session

    base = (args.base_url or cap.DEFAULT_BASE_URL).rstrip("/")
    insecure = tls.apply_default_https_context(cli_insecure=bool(getattr(args, "insecure", False)))
    out_root = Path(args.out_root) if args.out_root else OUT_BASE
    out_dir = out_root / args.switch_label
    out_dir.mkdir(parents=True, exist_ok=True)
    auth_dir = Path(args.auth_dir) if args.auth_dir else OUT_BASE / "auth-states"
    viewports = cap.resolve_viewports(args.viewports or ["1920x1080"])
    themes = args.switch_themes or ["light"]
    result = Run(out_dir)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            session = ensure_session(browser, base, auth_dir, insecure=insecure, log=print)
            for theme in themes:
                for viewport in viewports:
                    ctx = cap.new_context(browser, storage_state=session.storage_state, user_id=session.user_id,
                                          theme=theme, viewport=viewport, insecure=insecure)
                    try:
                        for fn in ("kit", "profile", "admin"):
                            page = ctx.new_page()
                            writes: list[tuple[str, str]] = []
                            page.on("request", lambda req, w=writes: w.append((req.method, req.url.split("?")[0]))
                                    if req.method in WRITE_METHODS and "/api/" in req.url else None)
                            try:
                                if fn == "kit":
                                    kit_states(result, page, base, theme, viewport.name, args.settle_ms)
                                elif fn == "profile":
                                    profile_states(result, ctx, page, base, theme, viewport.name, args.settle_ms)
                                else:
                                    admin_states(result, page, base, theme, viewport.name, args.settle_ms)
                            except Exception as exc:  # noqa: BLE001
                                result.add(theme=theme, viewport=viewport.name, state=f"{fn}.error",
                                           ok=False, error=f"{type(exc).__name__}: {exc}"[:300])
                            finally:
                                page.close()
                            # 쓰기 지킴 — 저장을 일부러 하는 자리(내 프로필의 저장 판정) 말고는 쓰기 요청이 0 이어야 한다.
                            allowed = ALLOWED_WRITES.get(fn, ())
                            unexpected = [w for w in writes if not any(w[0] == m and w[1].endswith(p) for m, p in allowed)]
                            result.add(theme=theme, viewport=viewport.name, state=f"{fn}.write-guard", ok=not unexpected,
                                       check=True, detail={"writes": len(writes), "unexpected": unexpected[:10]})
                    finally:
                        ctx.close()
        finally:
            browser.close()
    records = result.records
    (out_dir / "switch_states.json").write_text(json.dumps({"base": base, "records": records}, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    failed = [r for r in records if not r.get("skipped") and r.get("ok") is False]
    skipped = [r for r in records if r.get("skipped")]
    print("")
    print(f"상태·판정 {len(records)}개 · 실패 {len(failed)} · 못 만듦 {len(skipped)} · {out_dir / 'switch_states.json'}")
    if failed:
        for r in failed[:20]:
            print(f"  FAIL {r['theme']} {r['viewport']} {r['state']} — "
                  + json.dumps({k: v for k, v in r.items() if k in ('detail', 'ring', 'geometry', 'error', 'unchanged_after_release')},
                               ensure_ascii=False)[:300])
        print("SWITCH_STATES_FAILED")
        return 1
    if skipped:
        print("SWITCH_STATES_INCOMPLETE (못 만든 상태): " + ", ".join(sorted({r['state'] for r in skipped})))
        return 2
    print("SWITCH_STATES_OK")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="스위치 상태를 찍고 조작 계약을 판정한다")
    ap.add_argument("--viewports", nargs="*", default=None)
    ap.add_argument("--routes", nargs="*", default=None, help="(local_capture 호환용 — 쓰지 않는다)")
    ap.add_argument("--switch-themes", nargs="*", default=None)
    ap.add_argument("--switch-label", default="switch-states")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--settle-ms", type=int, default=600)
    ap.add_argument("--insecure", action="store_true", help="자체서명 인증서를 신뢰한다(설치처를 겨눌 때)")
    ap.add_argument("--out-root", default=None)
    ap.add_argument("--auth-dir", default=None)
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
