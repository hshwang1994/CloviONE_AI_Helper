"""다크 모드에서 부품이 **실제로 칠한 색**을 잰다 (핸드오프 ACCEPTANCE K2~K5 · 계획 F).

토큰 표(`ui/theme.js` 의 dark 항목)가 핸드오프 값과 같다는 것은 시험이 이미 말한다. 이 하네스가 묻는 것은 다른
질문이다 — **브라우저가 계산한 값**이 그 토큰에서 왔는가. 화면이 손으로 적은 색 · MUI 기본값 · 반투명 겹침은
토큰 표에 안 보이고 계산값에만 보인다.

## 재는 자리 (자리마다 표본을 모아 **값별 개수**로 적는다)

  K2  판 면 `.MuiCard-root` 배경 · 판 테두리 · 함몰면(메시지 박스 · 세그먼티드 · 상대 말풍선 · 카드 발) ·
      본문 잉크(페이지 제목) · 보조 잉크(페이지 머리 경로 · 화면 설명)
  K3  보조 단추(`outlined` + `colorInherit`) 면 · 테두리, 파괴 단추(`outlinedError`) 테두리 · 글자, 꺼진 단추 글자
  K4  클로비 그림과 그 틀의 `filter` · `mix-blend-mode`, 빈 상태 · 오류 상태 그림의 바탕(가장 가까운 칠한 조상)이 함몰면인가
      (핸드오프 README 다크 모드 절 · RULES §13 「클로비 자산은 다크에서 함몰면 위」)
  K5  상태 점(`[data-status-dot]`) · 메시지 박스 아이콘 — 판 위 3:1 이상(밝은 다크 값)
  (보조 단추 중 눌린 필터 토글 `aria-pressed` · `aria-expanded` 는 선택 상태라 쉼 상태 표본에서 빼고 따로 적는다)
  채팅 내 말풍선 글자와 면의 대비 4.5:1 이상, 상대 말풍선 면은 함몰면(K2 의 함몰면 표본에 들어간다)

## 쓰는 법

    python -m scripts.ui_qa.local_capture --harness dark_colors --selftest
    python -m scripts.ui_qa.local_capture --harness dark_colors \\
        --routes user_new-ticket user_knowledge user_chat-room-detail \\
        --viewports 1920x1080 1366x768 1200x900 --colors-label f-dark

판정은 `EXPECT` 표와 값별 개수를 대조한다. 표본 0 인 자리는 통과가 아니라 **미측정**으로 적는다.
`--selftest` 는 맞는 견본과 틀린 견본을 갤러리 위에 붙여 자리마다 한 번씩 잡히는지 먼저 본다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_BASE = REPO_ROOT / "dist" / "ui-qa"

# 핸드오프 ACCEPTANCE K2 · K3 의 다크 값(rgb 표기). 여기 숫자를 바꾸는 것은 계약을 바꾸는 일이다.
EXPECT = {
    "card_bg": "rgb(20, 24, 41)",            # #141829
    "card_border": "rgb(36, 42, 70)",        # #242A46
    "inset_bg": "rgb(28, 33, 54)",           # #1C2136
    "text_primary": "rgb(229, 232, 245)",    # #E5E8F5
    "text_secondary": "rgb(155, 164, 196)",  # #9BA4C4
    "secondary_border": "rgb(51, 59, 94)",   # #333B5E
    "secondary_bg": "rgba(0, 0, 0, 0)",      # 투명
    "danger_border": "rgb(95, 51, 48)",      # #5F3330
    "danger_text": "rgb(255, 138, 128)",     # #FF8A80
    "disabled_text": "rgb(75, 84, 120)",     # #4B5478
    "mascot_filter": "none",
    "mascot_blend": "normal",
    "mascot_ground": "rgb(28, 33, 54)",      # #1C2136 — 빈 상태 · 오류 상태 그림 바탕
}
PLATE = EXPECT["card_bg"]
# 판정에서 빼되 **따로 세어 보고하는** 자리 — (자리, 값, 화면 id, 이유). 조용히 통과시키지 않는다.
EXCEPTIONS = [
    ("status_dot", "rgb(51, 59, 94)", "user_my-stats",
     "보호 화면 내 업무량 요약 카드의 「남은 일 · 취소」 범례 점 — 비율 막대 조각과 같은 중립 선색(`dividerStrong`)이다. "
     "화면이 「색은 완료 하나만」으로 정한 기존 설계(라이트도 판 위 1.8:1)이고 점은 `aria-hidden` 이라 뜻은 낱말이 나른다. "
     "보호 화면 치환 목록 밖이라 두었다."),
    ("secondary_bg", "rgb(28, 33, 54)", "user_kit",
     "갤러리 「보조 버튼, 같은 넷」의 마우스 올림 견본 — 올림 상태(함몰면 + 강한 경계선)를 붙박이로 그린 것이다."),
]
# K5 · 채팅 — 값이 아니라 대비로 판정하는 자리.
MIN_RATIO = {"status_dot": 3.0, "callout_icon": 3.0}
CHAT_TEXT_MIN = 4.5

PROBE_JS = r"""
({ root, mascotRoot }) => {
  const shown = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none';
  };
  const all = (base, sel) => sel.split(',').flatMap((s) => [...document.querySelectorAll(`${base} ${s.trim()}`)]).filter(shown);
  const cs = (el) => getComputedStyle(el);
  const out = {};
  const put = (key, value) => { (out[key] = out[key] || []).push(value); };
  for (const el of all(root, '.MuiCard-root')) {
    const s = cs(el);
    put('card_bg', s.backgroundColor);
    if (s.borderTopStyle !== 'none' && parseFloat(s.borderTopWidth) > 0) put('card_border', s.borderTopColor);
  }
  for (const el of all(root, '.k-callout:not(p), .k-segmented, [data-chat-bubble="theirs"], [data-action-footer]')) put('inset_bg', cs(el).backgroundColor);
  for (const el of all(root, '.k-page-head h1')) put('text_primary', cs(el).color);
  for (const el of all(root, '.k-page-head .MuiTypography-caption, .k-page-desc')) put('text_secondary', cs(el).color);
  for (const el of all(root, '.MuiButton-outlined.MuiButton-colorInherit:not(.Mui-disabled)')) {
    const pressed = el.getAttribute('aria-pressed') === 'true' || el.getAttribute('aria-expanded') === 'true';
    put(pressed ? 'secondary_pressed_border' : 'secondary_border', cs(el).borderTopColor);
    put(pressed ? 'secondary_pressed_bg' : 'secondary_bg', cs(el).backgroundColor);
  }
  for (const el of all(root, '.MuiButton-outlinedError:not(.Mui-disabled)')) {
    put('danger_border', cs(el).borderTopColor);
    put('danger_text', cs(el).color);
  }
  for (const el of all(root, '.MuiButton-root.Mui-disabled')) put('disabled_text', cs(el).color);
  for (const el of all(mascotRoot, '[data-mascot-context], [data-mascot-context] img, [data-testid="mascot-mini"], [data-testid="mascot-mini"] img')) {
    put('mascot_filter', cs(el).filter);
    put('mascot_blend', cs(el).mixBlendMode);
  }
  /* 빈 상태 · 오류 상태 그림의 바탕 — 그림에서 위로 올라가며 처음 만나는 칠한 면. */
  for (const img of all(mascotRoot, '.k-empty img[data-mascot-context]')) {
    let ground = null;
    for (let el = img.parentElement; el; el = el.parentElement) {
      const bg = cs(el).backgroundColor;
      if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') { ground = bg; break; }
    }
    put('mascot_ground', ground || 'none');
  }
  for (const el of all(root, '[data-status-dot]')) put('status_dot', cs(el).backgroundColor);
  for (const el of all(root, '.k-callout svg')) put('callout_icon', cs(el).color);
  for (const el of all(root, '[data-chat-bubble="mine"]')) put('chat_mine', `${cs(el).color}|${cs(el).backgroundColor}`);
  return out;
}
"""

SELFTEST_HTML = r"""
() => {
  const img = 'data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==';
  const face = (c) => `
    <div class="MuiCard-root" style="width:40px;height:20px;background:${c.card};border:1px solid ${c.line}"></div>
    <div class="k-callout" style="width:40px;height:20px;background:${c.inset}"></div>
    <div class="k-page-head"><h1 style="color:${c.ink}">제목</h1><span class="MuiTypography-caption" style="display:block;color:${c.muted}">경로</span></div>
    <button class="MuiButton-root MuiButton-outlined MuiButton-colorInherit" style="background:${c.secBg};border:1px solid ${c.secLine}">보조</button>
    <button class="MuiButton-root MuiButton-outlinedError" style="background:transparent;border:1px solid ${c.dangerLine};color:${c.dangerInk}">삭제</button>
    <button class="MuiButton-root Mui-disabled" style="color:${c.disabled}">꺼짐</button>
    <span data-mascot-context="empty" style="display:inline-block;width:20px;height:20px;filter:${c.filter}"><img src="${img}" style="width:20px;height:20px;mix-blend-mode:${c.blend}"></span>
    <div class="k-empty" style="background:${c.ground};width:30px;height:30px"><img data-mascot-context="empty-region" src="${img}" style="width:20px;height:20px"></div>
    <span data-status-dot="" style="display:inline-block;width:8px;height:8px;background:${c.dot}"></span>
    <div class="k-callout" style="width:40px;height:20px;background:${c.inset}"><svg width="16" height="16" style="color:${c.icon}"></svg></div>
    <div data-chat-bubble="mine" style="width:40px;height:20px;background:${c.mineBg};color:${c.mineInk}">말</div>`;
  const good = { card: '#141829', line: '#242A46', inset: '#1C2136', ink: '#E5E8F5', muted: '#9BA4C4',
    secBg: 'transparent', secLine: '#333B5E', dangerLine: '#5F3330', dangerInk: '#FF8A80', disabled: '#4B5478',
    filter: 'none', blend: 'normal', ground: '#1C2136', dot: '#4ADE9B', icon: '#8AB4F8', mineBg: '#4038B8', mineInk: '#FFFFFF' };
  const bad = { card: '#FFFFFF', line: '#DCDFEC', inset: '#F5F6FB', ink: '#161A2C', muted: '#565E7A',
    secBg: '#FFFFFF', secLine: '#767FA2', dangerLine: '#FF8A80', dangerInk: '#B3261E', disabled: '#8C96B8',
    filter: 'invert(1)', blend: 'multiply', ground: '#141829', dot: '#1F2A44', icon: '#232A45', mineBg: '#A99CF5', mineInk: '#FFFFFF' };
  const host = document.createElement('div');
  host.id = 'dark-selftest';
  host.style.cssText = 'position:fixed;left:0;top:0;z-index:99999;display:flex;gap:8px;background:#0A0C16';
  host.innerHTML = `<div id="good">${face(good)}</div><div id="bad">${face(bad)}</div>`;
  document.body.appendChild(host);
}
"""


def _lum(rgb: str) -> float | None:
    nums = re.findall(r"[\d.]+", rgb or "")
    if len(nums) < 3:
        return None

    def ch(v: float) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (float(n) for n in nums[:3])
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _ratio(a: str, b: str) -> float | None:
    la, lb = _lum(a), _lum(b)
    if la is None or lb is None:
        return None
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def judge(totals: dict[str, Counter]) -> dict:
    """자리마다 판정한다. 표본 0 은 「미측정」이다 — 통과로 적지 않는다."""
    verdict: dict[str, dict] = {}
    for name, want in EXPECT.items():
        seen = totals.get(name)
        if not seen:
            verdict[name] = {"status": "미측정", "want": want}
            continue
        off = {v: n for v, n in seen.items() if v != want}
        verdict[name] = {"status": "통과" if not off else "어긋남", "want": want, "off": off,
                         "samples": sum(seen.values())}
    for name, floor in MIN_RATIO.items():
        seen = totals.get(name)
        if not seen:
            verdict[name] = {"status": "미측정", "want": f"판 위 {floor}:1 이상"}
            continue
        off = {v: _ratio(v, PLATE) for v in seen if (_ratio(v, PLATE) or 0) < floor}
        verdict[name] = {"status": "통과" if not off else "어긋남", "want": f"판 위 {floor}:1 이상", "off": off,
                         "samples": sum(seen.values())}
    seen = totals.get("chat_mine")
    if not seen:
        verdict["chat_mine"] = {"status": "미측정", "want": f"글자 대 면 {CHAT_TEXT_MIN}:1 이상"}
    else:
        ratios = {pair: _ratio(*pair.split("|")) for pair in seen}
        off = {pair: r for pair, r in ratios.items() if (r or 0) < CHAT_TEXT_MIN}
        verdict["chat_mine"] = {"status": "통과" if not off else "어긋남", "want": f"글자 대 면 {CHAT_TEXT_MIN}:1 이상",
                                "off": off, "ratios": ratios, "samples": sum(seen.values())}
    return verdict


def _launch(args):
    from scripts.ui_qa import capture as cap, tls
    from scripts.ui_qa.auth import ensure_session

    base = args.base_url or cap.DEFAULT_BASE_URL
    insecure = tls.apply_default_https_context()
    return cap, ensure_session, base, insecure


def selftest(args) -> int:
    from scripts.ui_qa import routes as routes_mod
    from playwright.sync_api import sync_playwright

    cap, ensure_session, base, insecure = _launch(args)
    route = routes_mod.BY_ID["user_kit"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            session = ensure_session(browser, base, OUT_BASE / "auth-measure", insecure=insecure, log=print)
            ctx = cap.new_context(browser, storage_state=session.storage_state, user_id=session.user_id,
                                  theme="dark", viewport=cap.resolve_viewports(["1920x1080"])[0], insecure=insecure)
            page = ctx.new_page()
            page.goto(route.url(base, route.hash_path), wait_until="domcontentloaded", timeout=45_000)
            cap._settle(page, settle_ms=600, timeout_ms=45_000)
            page.evaluate(SELFTEST_HTML)
            good = page.evaluate(PROBE_JS, {"root": "#dark-selftest #good", "mascotRoot": "#dark-selftest #good"})
            bad = page.evaluate(PROBE_JS, {"root": "#dark-selftest #bad", "mascotRoot": "#dark-selftest #bad"})
            ctx.close()
        finally:
            browser.close()
    good_v = judge({k: Counter(v) for k, v in good.items()})
    bad_v = judge({k: Counter(v) for k, v in bad.items()})
    problems = [f"맞는 견본을 잘못 판정: {n} → {v['status']} {v.get('off')}" for n, v in good_v.items() if v["status"] != "통과"]
    problems += [f"틀린 견본을 못 잡음: {n} → {v['status']}" for n, v in bad_v.items() if v["status"] != "어긋남"]
    if problems:
        for p in problems:
            print("[SELFTEST] " + p)
        print("DARK_COLORS_SELFTEST_FAILED")
        return 1
    print(f"DARK_COLORS_SELFTEST_OK (자리 {len(good_v)}종 — 맞는 견본 전부 통과, 틀린 견본 전부 어긋남)")
    return 0


def measure(args) -> int:
    from scripts.ui_qa import routes as routes_mod
    from playwright.sync_api import sync_playwright

    cap, ensure_session, base, insecure = _launch(args)
    routes = routes_mod.resolve(args.routes or ["user_kit"])
    viewports = cap.resolve_viewports(args.viewports or ["1920x1080"])
    out_dir = OUT_BASE / args.colors_label
    out_dir.mkdir(parents=True, exist_ok=True)
    totals: dict[str, Counter] = defaultdict(Counter)
    excepted: Counter = Counter()
    where: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    pages: dict[str, dict] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            session = ensure_session(browser, base, OUT_BASE / "auth-measure", insecure=insecure, log=print)
            probe = browser.new_context(storage_state=session.storage_state, ignore_https_errors=insecure)
            hashes: dict[str, str] = {}
            try:
                for route in routes:
                    if route.is_detail:
                        found, _note = cap.discover_detail_hash(probe, base, route, log=print)
                        if found:
                            hashes[route.id] = found
            finally:
                probe.close()
            for viewport in viewports:
                ctx = cap.new_context(browser, storage_state=session.storage_state, user_id=session.user_id,
                                      theme="dark", viewport=viewport, insecure=insecure)
                page = ctx.new_page()
                try:
                    for route in routes:
                        if route.is_public or not route.visible_to(session.role):
                            continue
                        if route.is_detail and route.id not in hashes:
                            continue
                        page.goto(route.url(base, hashes.get(route.id, route.hash_path)),
                                  wait_until="domcontentloaded", timeout=45_000)
                        cap._settle(page, settle_ms=600, timeout_ms=45_000)
                        got = page.evaluate(PROBE_JS, {"root": "#main-content", "mascotRoot": "body"})
                        key = f"{route.id}__dark__{viewport.name}"
                        pages[key] = {name: dict(Counter(values)) for name, values in got.items()}
                        for name, values in got.items():
                            waived = {v for (n, v, rid, _why) in EXCEPTIONS if n == name and rid == route.id}
                            for value in values:
                                if value in waived:
                                    excepted[(name, value, route.id)] += 1
                            values = [v for v in values if v not in waived]
                            totals[name].update(values)
                            for value in set(values):
                                if len(where[name][value]) < 12:
                                    where[name][value].append(key)
                        print(f"[colors] {key}", flush=True)
                finally:
                    page.close()
                    ctx.close()
        finally:
            browser.close()

    verdict = judge(totals)
    table = {name: dict(counter.most_common()) for name, counter in sorted(totals.items())}
    (out_dir / "dark_colors.json").write_text(json.dumps(
        {"expect": EXPECT, "verdict": verdict, "table": table,
         "where": {n: dict(v) for n, v in where.items()},
         "exceptions": [{"check": n, "value": v, "route": rid, "why": why, "count": excepted[(n, v, rid)]}
                        for (n, v, rid, why) in EXCEPTIONS],
         "pages": pages},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("")
    print(f"{'자리':<18} {'판정':<6} {'표본':>6}  기대 / 어긋난 값")
    for name, v in verdict.items():
        extra = "" if v["status"] != "어긋남" else f" / {v['off']}"
        print(f"{name:<18} {v['status']:<6} {v.get('samples', 0):>6}  {v['want']}{extra}")
        if v["status"] == "어긋남":
            for value in list(v["off"])[:4]:
                print(f"    {value} ← {where[name].get(value, [])[:4]}")
    for (n, v, rid, why) in EXCEPTIONS:
        print(f"예외 {n} {v} @ {rid} × {excepted[(n, v, rid)]} — {why}")
    for name in ("secondary_pressed_border", "secondary_pressed_bg"):
        if name in table:
            print(f"기록 {name}: {table[name]}")
    print(f"dark_colors.json : {out_dir / 'dark_colors.json'}")
    bad = [n for n, v in verdict.items() if v["status"] == "어긋남"]
    if bad:
        print("DARK_COLORS_MISMATCH: " + ", ".join(bad))
        return 1
    blind = [n for n, v in verdict.items() if v["status"] == "미측정"]
    print("DARK_COLORS_OK" + (f" (미측정: {', '.join(blind)})" if blind else ""))
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="다크 모드 계산 색 실측")
    ap.add_argument("--routes", nargs="*", default=None)
    ap.add_argument("--viewports", nargs="*", default=None)
    ap.add_argument("--colors-label", default="dark-colors")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    return selftest(args) if args.selftest else measure(args)


if __name__ == "__main__":
    raise SystemExit(main())
