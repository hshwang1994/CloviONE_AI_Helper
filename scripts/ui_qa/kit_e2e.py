"""공유 Layout Primitive 를 **실제 브라우저에서** 재고 눌러 본다 (W4 · `kit_primitives`).

## 왜 별도 모듈인가

`frontend/src/ui/kit.jsx` 는 화면 60여 개가 전부 가져다 쓰는 층이다. 그런데 이 층에는
두 가지가 겹쳐 있어 어느 한쪽 도구만으로는 검증되지 않는다.

1. **면(Surface) 계약은 레이아웃 문제다.** jsdom 은 레이아웃을 하지 않는다 — `kit.test.jsx`
   가 "판 안의 판은 내려간다" 를 단언해도, 그것이 **배포본에서 실제로 어떤 픽셀이 되는지**는
   말하지 못한다. 이 저장소는 그 간극에서 같은 결함을 세 번 밟았다: `borderInlineStart: 1` 은
   시험도 콘솔도 아무 말을 안 하는데 화면에는 선이 없다(F-W2R-01). 그래서 **배포된 CSS 가
   계산한 값**을 브라우저에서 직접 읽는다.

2. **부품의 상호작용은 기능이다.** 모달이 열린다·더티 가드가 묻는다·판독 칸이 목록을
   거른다는 것은 렌더 시험이 아니라 사슬이다. 서버가 관여하는 것은 네트워크와 함께 기록하고,
   **관여하지 않는 것은 지어내지 않는다** — 사슬의 API 칸을 비워 두고 `IN_PROGRESS` 로
   남긴다(`shell_e2e.py`·`nav_e2e.py` 가 세운 규율).

## 이 모듈이 재는 계약

  · 판 안의 판이 몇 자리인가 (`data-surface="plate>none"`)
  · 판독 줄(`MetricStrip`)이 판을 갖지 않는가, 칸 구분선이 **실제로 그려지는가**,
    라벨이 한 기준선에서 시작하는가(F-W1R-27 이 24px 어긋남으로 잡은 그 값), 판독 슬롯이
    묶음당 하나인가, 활성 칸의 레일이 보이는가
  · 속성 줄(`MetaBar`)도 같은 두 가지
  · 안내(`Callout`)의 앞머리 실선이 그려지는가, 전폭 상자가 아닌가
  · 보조 버튼 테두리가 본문 잉크가 아닌가, **파괴 버튼 테두리가 3:1 을 넘는가**,
    채운 error 면이 대화상자 밖에 없는가
  · 잉크 3단의 실제 분리도

## 쓰는 법

    python -m scripts.ui_qa.kit_e2e --insecure        # 대상은 UI_QA_BASE_URL 또는 --base-url

산출물: `dist/ui-qa/w4-kit-e2e/{flows.json,surfaces.json}` + 단계별 스크린샷.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, Viewport, new_context  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "w4-kit-e2e"

# 계약값 — 정본은 `frontend/src/ui/kit.jsx` 다. 여기 적은 값이 그것과 갈라지면
# `kit.test.jsx` 가 먼저 깨진다(그쪽은 상수를 import 해서 센다).
STRIP_DIVIDER_PX = 1
SURFACE_EDGE_PX = 3     # brandTint 앞머리 edge
CALLOUT_EDGE_PX = 2     # Callout 앞머리 실선
READOUT_RAIL_PX = 2     # 활성 판독 칸의 레일
INK_SEPARATION_MIN = 1.45   # secondary vs faint

# **`[role="dialog"]` 만으로는 모자란다.** AI 서랍(`클로비 AI 도우미`)이 `MuiDrawer` 인데
# 같은 role 을 갖고 DOM 에 상주한다 — 그래서 첫 판이 "2 elements, 첫 번째는 안 보인다" 로
# 15초를 기다리다 죽었다. 이 저장소가 W3 에서 밟은 것과 같은 형태의 프로브 결함이다
# (포털된 임시 Drawer 를 사이드바 안에서 찾았다). 중앙 모달만 고른다.
DIALOG = '.MuiDialog-container [role="dialog"]'


SURFACE_JS = r"""
() => {
  const num = (v) => Number.parseFloat(v) || 0;
  const cs = (el) => getComputedStyle(el);
  const painted = (s) =>
    (s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== 'transparent')
    || (num(s.borderTopWidth) > 0 && s.borderTopStyle !== 'none')
    || s.boxShadow !== 'none';
  const clear = (c) => !c || c === 'transparent' || c === 'rgba(0, 0, 0, 0)';
  const lum = (c) => {
    const m = (c || '').match(/[\d.]+/g);
    if (!m) return null;
    const f = (v) => { const x = Number(v) / 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(m[0]) + 0.7152 * f(m[1]) + 0.0722 * f(m[2]);
  };
  const ratio = (a, b) => {
    const [la, lb] = [lum(a), lum(b)];
    if (la == null || lb == null) return null;
    return Math.round(((Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)) * 1000) / 1000;
  };
  const root = cs(document.documentElement);
  const rootPx = num(root.fontSize) || 16;
  /* `norm` 은 **rem 으로 저술된 값**을 한 눈금에서 비교하려고 쓴다(4K 는 루트 20px 이라
     같은 rem 이 1.25배로 계산된다). 테두리 폭은 그 대상이 **아니다** — 이 저장소의 레일과
     앞머리 실선은 `"2px"` 문자열로 저술돼 루트 폰트와 무관하게 2px 다. 첫 판이 그것까지
     정규화해서 4K 에서 2px 레일을 `1.6` 으로 적고 계약 위반이라고 불렀다 — 대상이 아니라
     프로브가 틀린 것이다. 폭은 `raw` 로 그대로 읽는다. */
  const norm = (px) => Math.round((px * 16 / rootPx) * 100) / 100;
  const raw = (px) => Math.round(px * 100) / 100;

  const out = {
    rootFontSize: rootPx,
    ink: {
      primary: root.getPropertyValue('--color-text').trim(),
      secondary: root.getPropertyValue('--color-muted').trim(),
      faint: root.getPropertyValue('--color-faint').trim(),
    },
    nestedPlates: [],
    strips: [],
    metabars: [],
    callouts: [],
    buttons: { defaultOutlined: [], dangerOutlined: [],
               containedErrorOutsideDialog: 0, containedErrorInDialog: 0 },
  };

  /* ① 판 안의 판. 부품이 자동으로 내려보내면서 그 사실을 DOM 에 남긴다 — 조용히 고치면
        몇 자리가 그랬는지 아무도 모른다. */
  for (const el of document.querySelectorAll('[data-surface="plate>none"]')) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    out.nestedPlates.push({
      box: Math.round(r.width) + 'x' + Math.round(r.height),
      text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
    });
  }

  /* ② 판독 줄. 판이 없어야 하고, 칸 구분선은 **실제로 그려져야** 하며, 라벨은 한
        기준선에서 시작해야 한다. */
  for (const strip of document.querySelectorAll('.k-metrics')) {
    const s = cs(strip);
    const cells = [...strip.querySelectorAll('.k-readout')];
    const rows = cells.map((c) => {
      const cst = cs(c);
      // 칸의 두 번째 자식이 라벨 줄이다(첫째는 값 줄). 라벨 잉크의 시작 y 를 잰다.
      const labelBox = c.children[1];
      const valueBox = c.children[0];
      const lr = labelBox ? labelBox.getBoundingClientRect() : null;
      const vr = valueBox ? valueBox.getBoundingClientRect() : null;
      /* 값의 글자 크기는 **값 상자 안에서 가장 큰 것**으로 잰다. 첫 판은
         `valueBox.querySelector('div')` 로 첫 자식을 짚었는데 그건 baseline 정렬용
         래퍼라 글자 크기를 물려받기만 한다(15px) — 그 결과 판독 칸이 40px 이어도
         전 칸이 같은 값으로 읽혀 `readoutCount` 가 **구조적으로 항상 0** 이었다.
         검사는 통과하고 있었지만 아무것도 재지 않았다. 독립 검수가 지목했다. */
      const valueText = valueBox
        ? [...valueBox.querySelectorAll('*')].reduce(
            (big, e) => (big && num(cs(big).fontSize) >= num(cs(e).fontSize) ? big : e), null)
        : null;
      const cr = c.getBoundingClientRect();
      return {
        /* 칸이 몇 번째 줄에 있는가. 좁은 화면에서 판독 줄은 **접힌다**(flex-wrap) —
           다른 줄의 라벨이 같은 y 에서 시작할 이유가 없다. 첫 판이 전 칸을 한 줄로 보고
           390 에서 72~96px 어긋남을 «계약 위반» 이라고 적었다. 8px 버킷으로 줄을 센다
           (`vertical_text_collapse` 가 이미 쓰는 기법). */
        rowIndex: Math.round(cr.top / 8),
        labelTop: lr ? Math.round(lr.top * 100) / 100 : null,
        valueHeight: vr ? Math.round(vr.height * 100) / 100 : null,
        valueFontPx: valueText ? Math.round(num(cs(valueText).fontSize) * 100) / 100 : null,
        dividerStyle: cst.borderInlineStartStyle,
        dividerWidth: raw(num(cst.borderInlineStartWidth)),
        railStyle: cst.borderBlockEndStyle,
        railWidth: raw(num(cst.borderBlockEndWidth)),
        railClear: clear(cst.borderBlockEndColor),
        pressed: c.getAttribute('aria-pressed'),
      };
    });
    // 줄마다 따로 재고 **가장 큰 어긋남**을 남긴다.
    const byRow = new Map();
    for (const r of rows) {
      if (r.labelTop == null) continue;
      if (!byRow.has(r.rowIndex)) byRow.set(r.rowIndex, []);
      byRow.get(r.rowIndex).push(r.labelTop);
    }
    let spread = null;
    for (const list of byRow.values()) {
      if (list.length < 2) continue;
      const d = Math.max(...list) - Math.min(...list);
      spread = spread == null ? d : Math.max(spread, d);
    }
    const tops = rows.map((r) => r.labelTop).filter((v) => v != null);
    const fonts = rows.map((r) => r.valueFontPx).filter((v) => v != null);
    out.strips.push({
      plate: painted(s),
      background: s.backgroundColor,
      borderTopWidth: raw(num(s.borderTopWidth)),
      cells: rows.length,
      labelTopSpread: spread == null ? null : Math.round(spread * 100) / 100,
      rows: byRow.size,
      readoutCount: fonts.length ? fonts.filter((f) => f >= Math.max(...fonts) && Math.max(...fonts) > Math.min(...fonts)).length : 0,
      maxValueFont: fonts.length ? norm(Math.max(...fonts)) : null,
      minValueFont: fonts.length ? norm(Math.min(...fonts)) : null,
      /* CSS 규칙은 `& > *:not(:first-of-type)` 이라 **첫 칸 하나만** 선을 안 갖는다
         (줄바꿈된 둘째 줄의 첫 칸도 선을 갖는다 — 알려진 절충이고 계약대로다).
         그래서 기대값은 `칸 수 - 1` 이고 대상은 첫 칸을 뺀 나머지다. */
      dividersDrawn: rows.slice(1).filter((r) => r.dividerStyle === 'solid' && r.dividerWidth > 0).length,
      dividersExpected: Math.max(0, rows.length - 1),
      activeRail: rows.filter((r) => r.pressed === 'true').map((r) => ({
        style: r.railStyle, width: r.railWidth, clear: r.railClear })),
      inactiveRailWidths: [...new Set(rows.filter((r) => r.pressed !== 'true').map((r) => r.railWidth))],
      emptyMarker: strip.getAttribute('data-metrics-empty'),
    });
  }

  /* ③ 속성 줄. 같은 두 가지. */
  for (const bar of document.querySelectorAll('.k-metabar')) {
    const s = cs(bar);
    const cells = [...bar.querySelectorAll('.k-metacell')];
    const drawn = cells.slice(1).filter((c) => {
      const cst = cs(c);
      return cst.borderInlineStartStyle === 'solid' && num(cst.borderInlineStartWidth) > 0;
    }).length;
    out.metabars.push({
      plate: painted(s), cells: cells.length,
      dividersDrawn: drawn, dividersExpected: Math.max(0, cells.length - 1),
    });
  }

  /* ④ 안내. 앞머리 실선이 그려지는가, 네 면 상자가 아닌가. */
  for (const el of document.querySelectorAll('.k-callout')) {
    const s = cs(el);
    out.callouts.push({
      tone: el.getAttribute('data-tone'),
      inline: el.tagName === 'P',
      edgeStyle: s.borderInlineStartStyle,
      edgeWidth: raw(num(s.borderInlineStartWidth)),
      edgeClear: clear(s.borderInlineStartColor),
      topWidth: raw(num(s.borderTopWidth)),
      rightWidth: raw(num(s.borderRightWidth)),
      bottomWidth: raw(num(s.borderBottomWidth)),
      background: s.backgroundColor,
    });
  }

  /* ⑤ 버튼 강도. 보조 테두리가 본문 잉크면 위계가 뒤집힌다. */
  /* 판 색은 **실제 요소**에서 읽는다. 처음에는 `--color-card` 를 `:root` 에서 읽었는데
     그 변수가 거기 없어 빈 문자열이 나왔고, 대비 계산이 `NaN`/`null` 로 **조용히 사라졌다** —
     검사는 통과했지만 아무것도 재지 않은 상태였다("모르면 모른다고 한다" 규율 위반).
     판이 없는 화면도 있으므로 캔버스(body)를 폴백으로 둔다. */
  const plateEl = document.querySelector('.MuiCard-root, [data-surface="plate"]');
  const plate = plateEl ? cs(plateEl).backgroundColor : cs(document.body).backgroundColor;
  out.plateSample = plate;
  /* 파괴적 동작의 테두리도 **잰다**. 첫 판은 `outlinedError` 를 건너뛰었는데, 바로 그
     자리가 W4 가 채운 빨강에서 외곽선으로 내린 자리다 — 자기가 바꾼 곳을 안 보는
     프로브였다. 테두리는 비텍스트 경계라 두 종류 다 3:1 이 하한이다. */
  for (const b of document.querySelectorAll('button.MuiButton-outlined')) {
    if (b.className.includes('outlinedPrimary')) continue;
    const s = cs(b);
    const row = {
      borderColor: s.borderTopColor,
      vsPlate: ratio(s.borderTopColor, plate),
      label: (b.textContent || '').trim().slice(0, 16),
    };
    (b.className.includes('outlinedError')
      ? out.buttons.dangerOutlined : out.buttons.defaultOutlined).push(row);
  }
  for (const b of document.querySelectorAll('button.MuiButton-containedError')) {
    if (b.closest('[role="dialog"]')) out.buttons.containedErrorInDialog += 1;
    else out.buttons.containedErrorOutsideDialog += 1;
  }
  const hexToRgb = (h) => {
    const m = /^#?([0-9a-f]{6})$/i.exec((h || '').trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
  };
  const sec = hexToRgb(out.ink.secondary) || out.ink.secondary;
  const fnt = hexToRgb(out.ink.faint) || out.ink.faint;
  out.ink.separation = ratio(sec, fnt);
  out.ink.faintVsPlate = ratio(fnt, plate);
  return out;
}
"""


class Recorder:
    """이 단계 동안 오간 요청·응답. 사슬의 `api_request`/`api_response` 는 여기서 나온다."""

    def __init__(self, page):
        self.calls: list[dict] = []
        page.on("response", self._on_response)

    def _on_response(self, response):
        if "/api/" not in response.url:
            return
        self.calls.append({"method": response.request.method, "url": response.url,
                           "status": response.status})

    def reset(self) -> None:
        self.calls = []


def _shot(page, out: Path, name: str) -> str:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _goto(page, base: str, hash_path: str, tries: int = 2) -> None:
    """HashRouter 이동. `capture.py`·`nav_e2e.py` 가 이미 배운 두 가지를 그대로 따른다."""
    last = None
    for _ in range(tries):
        try:
            page.goto(base + "/#" + hash_path, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_selector("#main-content", state="attached", timeout=30_000)
            page.wait_for_timeout(1600)
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            page.goto("about:blank", wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(400)
    raise last


def flow(fid: str, category: str, name: str) -> dict:
    return {"id": fid, "category": category, "name": name, "observed": {},
            "chain": {}, "screenshots": [], "notes": []}


# --------------------------------------------------------------------------- #
# 판정 — 계약값과 실측을 대조한다. 판정 규칙은 여기 한 곳에만 있다.
# --------------------------------------------------------------------------- #
def verdict(m: dict) -> dict:
    fails: list[str] = []
    checked = 0

    for i, s in enumerate(m.get("strips") or []):
        checked += 1
        if s["plate"]:
            fails.append(f"판독 줄 {i}: 판을 갖는다 (bg={s['background']}, "
                         f"테두리 {s['borderTopWidth']}px) — PLAN 하드 금지")
        if s["dividersDrawn"] != s["dividersExpected"]:
            fails.append(f"판독 줄 {i}: 칸 구분선 {s['dividersDrawn']}/{s['dividersExpected']} "
                         f"만 그려진다 (선언만 있고 안 그려지는 상태 — F-W2R-01)")
        if s["labelTopSpread"] is not None and s["labelTopSpread"] > 1.5:
            fails.append(f"판독 줄 {i}: 라벨 기준선이 {s['labelTopSpread']}px 어긋난다 (F-W1R-27)")
        if s["readoutCount"] > 1:
            fails.append(f"판독 줄 {i}: 판독 슬롯이 {s['readoutCount']}개다 — 묶음당 하나여야 한다")
        for rail in s["activeRail"]:
            if rail["clear"] or rail["style"] != "solid" or rail["width"] < READOUT_RAIL_PX:
                fails.append(f"판독 줄 {i}: 활성 칸의 레일이 안 보인다 "
                             f"({rail['style']} {rail['width']}px, 색 없음={rail['clear']})")
        if len(s["inactiveRailWidths"]) > 1 or (
                s["inactiveRailWidths"] and s["inactiveRailWidths"][0] != READOUT_RAIL_PX):
            fails.append(f"판독 줄 {i}: 비활성 칸 레일 폭이 {s['inactiveRailWidths']} — "
                         f"활성/비활성 폭이 다르면 선택할 때 줄 높이가 튄다")

    for i, b in enumerate(m.get("metabars") or []):
        checked += 1
        if b["plate"]:
            fails.append(f"속성 줄 {i}: 판을 갖는다 — PLAN 하드 금지")
        if b["dividersDrawn"] != b["dividersExpected"]:
            fails.append(f"속성 줄 {i}: 칸 구분선 {b['dividersDrawn']}/{b['dividersExpected']}")

    for i, c in enumerate(m.get("callouts") or []):
        checked += 1
        if c["inline"]:
            if c["topWidth"] or c["rightWidth"] or c["bottomWidth"] or c["edgeWidth"]:
                fails.append(f"안내 {i}(inline): 상자를 갖는다 — 문장 흐름 안의 한 줄이어야 한다")
            continue
        if c["edgeStyle"] != "solid" or c["edgeWidth"] < CALLOUT_EDGE_PX or c["edgeClear"]:
            fails.append(f"안내 {i}: 앞머리 실선이 안 그려진다 "
                         f"({c['edgeStyle']} {c['edgeWidth']}px, 색 없음={c['edgeClear']})")
        if c["topWidth"] or c["rightWidth"] or c["bottomWidth"]:
            fails.append(f"안내 {i}: 네 면 테두리 상자다 (위 {c['topWidth']} / 오른쪽 "
                         f"{c['rightWidth']} / 아래 {c['bottomWidth']}) — C5 가 폐기한 형태")

    btn = m.get("buttons") or {}
    for b in btn.get("defaultOutlined") or []:
        checked += 1
        if b["vsPlate"] is not None and b["vsPlate"] > 8:
            fails.append(f"보조 버튼 «{b['label']}» 테두리 대비 {b['vsPlate']}:1 — "
                         f"본문 잉크(17:1)를 쓰고 있다. 주 행동을 이긴다")
        if b["vsPlate"] is not None and b["vsPlate"] < 3:
            fails.append(f"보조 버튼 «{b['label']}» 테두리 대비 {b['vsPlate']}:1 — "
                         f"비텍스트 3:1 미만이라 경계가 안 보인다")
    for b in btn.get("dangerOutlined") or []:
        checked += 1
        if b["vsPlate"] is not None and b["vsPlate"] < 3:
            fails.append(f"파괴 버튼 «{b['label']}» 테두리 대비 {b['vsPlate']}:1 — "
                         f"비텍스트 3:1 미만이다. 파괴적 동작이 제품에서 가장 약한 경계가 된다")

    if btn.get("containedErrorOutsideDialog"):
        checked += 1
        fails.append(f"대화상자 밖에 채운 error 버튼 {btn['containedErrorOutsideDialog']}개 — "
                     f"파괴적 동작은 외곽선이다(F-W1R-04)")

    ink = m.get("ink") or {}
    checked += 1
    sep = ink.get("separation")
    if sep is None or sep != sep:   # None 또는 NaN — 재지 못했다는 뜻이다
        fails.append("잉크 분리도를 재지 못했다 (secondary=%r faint=%r plate=%r) — "
                     "통과로 넘기지 않는다" % (ink.get("secondary"), ink.get("faint"),
                                              m.get("plateSample")))
    if ink.get("separation") is not None and ink["separation"] == ink["separation"]             and ink["separation"] < INK_SEPARATION_MIN:
        fails.append(f"잉크 분리도 {ink['separation']}:1 — 3단이 다시 2단이다 (F-W1R-03)")
    if ink.get("faintVsPlate") is not None and ink["faintVsPlate"] < 3.0:
        fails.append(f"faint 대비 {ink['faintVsPlate']}:1 — AA-large 3:1 미만")

    return {"ok": not fails, "checked": checked, "fails": fails,
            "nestedPlates": len(m.get("nestedPlates") or [])}


def measure(page, label: str) -> dict:
    data = page.evaluate(SURFACE_JS)
    data["label"] = label
    data["verdict"] = verdict(data)
    return data


# --------------------------------------------------------------------------- #
# 기능 사슬
# --------------------------------------------------------------------------- #
def ff_1400_metric_filter(page, rec: Recorder, out: Path, base: str) -> dict:
    """판독 칸을 눌러 아래 목록을 거른다 (`MetricStrip` 의 `onClick`/`aria-pressed`)."""
    f = flow("FF-1400", "filter", "판독 칸을 눌러 아래 목록을 거른다")
    _goto(page, base, "/me")
    rec.reset()
    cells = page.locator('.k-readout[aria-pressed]')
    if not cells.count():
        f["notes"].append("이 화면에 누를 수 있는 판독 칸이 없다 — 측정 대상 없음")
        f["status"] = "NOT_APPLICABLE"
        return f
    before = [cells.nth(i).get_attribute("aria-pressed") for i in range(cells.count())]
    target = next((i for i, v in enumerate(before) if v != "true"), 0)
    label = cells.nth(target).inner_text().replace("\n", " ")[:24]
    cells.nth(target).click()
    page.wait_for_timeout(900)
    after = [cells.nth(i).get_attribute("aria-pressed") for i in range(cells.count())]
    f["observed"] = {"cells": cells.count(), "before": before, "after": after, "clicked": label}
    f["chain"] = {
        "ui_action": f"판독 칸 «{label}» 클릭",
        "frontend_state": f"aria-pressed {before} -> {after}",
        "rendered": page.locator("#main-content").inner_text()[:160].replace("\n", " "),
    }
    calls = [c for c in rec.calls]
    if calls:
        f["chain"]["api_request"] = calls[0]["url"]
        f["chain"]["api_response"] = f"HTTP {calls[0]['status']}"
    else:
        f["notes"].append("서버 왕복이 **구조적으로 없다** — 이 판독 줄은 이미 받아 온 "
                          "데이터의 초점만 바꾼다. 사슬의 API 칸을 지어내지 않는다.")
    f["screenshots"].append(_shot(page, out, "ff1400-metric-filter"))
    f["status"] = "PASS" if after != before else "FAIL"
    return f


def ff_1401_modal_open(page, rec: Recorder, out: Path, base: str) -> dict:
    """주요 Action 을 눌러 모달이 열리고, 그 모달이 서버에서 참조 목록을 받아 온다."""
    f = flow("FF-1401", "modal_action", "주요 Action 이 모달을 열고 참조 목록을 받아 온다")
    _goto(page, base, "/users")
    rec.reset()
    trigger = page.locator('button:has-text("추가"), button:has-text("사용자 추가")').first
    if not trigger.count():
        f["notes"].append("이 화면에 모달을 여는 주요 Action 이 없다")
        f["status"] = "NOT_APPLICABLE"
        return f
    trigger.click()
    page.wait_for_selector(DIALOG, state="visible", timeout=15_000)
    page.wait_for_timeout(1200)
    dlg = page.locator(DIALOG).first
    box = dlg.bounding_box() or {}
    f["observed"] = {"width": round(box.get("width", 0)), "height": round(box.get("height", 0)),
                     "title": dlg.locator("h2, .MuiDialogTitle-root").first.inner_text()[:40]}
    f["chain"] = {
        "ui_action": "«추가» 클릭",
        "frontend_state": "role=dialog 가 열린다",
        "rendered": f"모달 {f['observed']['width']}x{f['observed']['height']}",
    }
    if rec.calls:
        f["chain"]["api_request"] = rec.calls[0]["url"]
        f["chain"]["backend_query"] = "폼의 참조 목록(부서·직책 등) 조회"
        f["chain"]["api_response"] = f"HTTP {rec.calls[0]['status']}"
    else:
        f["notes"].append("이 폼은 이미 받아 둔 참조 목록만 쓴다 — 서버 왕복이 없다.")
    f["screenshots"].append(_shot(page, out, "ff1401-modal-open"))
    f["status"] = "PASS" if rec.calls else "IN_PROGRESS"
    return f


def ff_1402_dirty_guard(page, out: Path) -> dict:
    """입력한 모달을 닫으려 하면 **묻는다** — 긴 폼이 한 번의 오조작으로 사라지지 않는다."""
    f = flow("FF-1402", "modal_action", "입력한 모달을 닫으려 하면 확인을 묻는다")
    dlg = page.locator(DIALOG).first
    if not dlg.count():
        f["notes"].append("앞 단계에서 모달이 열리지 않아 이어서 잴 수 없다")
        f["status"] = "NOT_APPLICABLE"
        return f
    field = dlg.locator("input:not([type=checkbox]):not([type=hidden])").first
    if not field.count():
        f["notes"].append("이 모달에 입력 칸이 없다")
        f["status"] = "NOT_APPLICABLE"
        return f
    field.fill("qa-dirty-guard")
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    page.wait_for_timeout(900)
    dialogs = page.locator(DIALOG)
    asked = page.locator(DIALOG + ':has-text("저장되지 않았습니다")').count() > 0
    f["observed"] = {"dialogs": dialogs.count(), "asked": asked}
    f["chain"] = {
        "ui_action": "입력 후 Esc",
        "frontend_state": f"확인 대화 {'열림' if asked else '없음'}",
        "rendered": f"열린 대화 {dialogs.count()}개",
    }
    f["notes"].append("서버 왕복이 **구조적으로 없다** — 더티 판정은 열릴 때의 값 스냅샷과 "
                      "지금 값을 비교하는 순수 계산이다.")
    f["screenshots"].append(_shot(page, out, "ff1402-dirty-guard"))
    f["status"] = "PASS" if asked else "FAIL"
    return f


def ff_1403_page_help(page, out: Path, base: str) -> dict:
    """페이지 도움말 토글 — 상시 안내 패널을 제목 옆으로 접어 둔 계약(C4)."""
    # `disclosure` 범주가 R-92 의 27개 목록에 없다 — 점진적 공개는 그 분류가 다루지 않는
    # 축이다. 가장 가까운 `read` 로 적고 그 사실을 여기 남긴다(분류를 늘리는 것은 W0 소유다).
    f = flow("FF-1403", "read", "페이지 도움말이 제목 옆에서 접히고 펴진다")
    # **앞 단계의 열린 모달을 확실히 치운다.** 더티 가드가 켜져 있으면 Esc 는 확인 대화를
    # 하나 더 열 뿐이고, 해시 이동(`_goto`)은 같은 문서 안이라 그 대화가 **그대로 남아**
    # backdrop 이 다음 클릭을 가로챈다 — 두 번째 실행이 정확히 그렇게 30초를 기다리다 죽었다.
    # Esc 로 겹친 대화를 걷어낸 뒤 문서를 통째로 버리고 다시 연다.
    for _ in range(4):
        if not page.locator(DIALOG).count():
            break
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    page.goto("about:blank", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(300)
    _goto(page, base, "/users")
    btn = page.locator('button[aria-label="도움말 보기"]').first
    if not btn.count():
        f["notes"].append("이 화면에 페이지 도움말이 없다")
        f["status"] = "NOT_APPLICABLE"
        return f
    before = btn.get_attribute("aria-expanded")
    btn.click()
    page.wait_for_timeout(700)
    after = page.locator('button[aria-label="도움말 닫기"]').first
    opened = after.count() > 0
    f["observed"] = {"before": before, "opened": opened}
    f["chain"] = {
        "ui_action": "제목 옆 «?» 클릭",
        "frontend_state": f"aria-expanded {before} -> {'true' if opened else before}",
        "rendered": page.locator(".k-callout").first.inner_text()[:120].replace("\n", " ")
        if page.locator(".k-callout").count() else "",
    }
    f["notes"].append("서버 왕복이 없다 — 접힘 상태는 컴포넌트 안에 산다.")
    f["screenshots"].append(_shot(page, out, "ff1403-page-help"))
    f["status"] = "PASS" if opened else "FAIL"
    return f


def ff_1404_overflow(page, out: Path, base: str) -> dict:
    """넘침 메뉴 — 파괴적 동작이 주 행동과 같은 줄에서 경쟁하지 않게 하는 자리(지시 11·12)."""
    f = flow("FF-1404", "overflow_action", "넘침 메뉴가 열리고 파괴적 항목이 갈라져 있다")
    # 라벨을 **정확히** 맞추려 했더니 못 찾았다. 호출부는 기본값을 거의 안 쓴다 —
    # `Users.jsx` 는 «사용자 작업 더 보기», `DataScreen.jsx` 는 «<화면 이름> 화면 작업 더
    # 보기» 를 준다(접근성상 그게 옳다: 한 화면에 «더 보기» 가 여럿이면 스크린리더가 구분을
    # 못 한다). 부분 일치로 찾고, 헤더 넘침 메뉴가 실제로 있는 화면을 골라 간다.
    OVERFLOW = 'button[aria-label*="더 보기"]'
    # 헤더 넘침 메뉴는 **조건부**다 — `DataScreen` 은 위험 표시(`confirm:`)가 붙은 헤더
    # 액션만 그리로 내린다. 그래서 아무 관리 화면이나 골라서는 못 만난다. 버튼 위계 전수
    # 조사가 "채운 primary 가 0개인 화면" 으로 지목한 넷을 먼저 들른다 — 그 화면들의 헤더
    # 액션이 전부 넘침 메뉴로 내려가 있다는 뜻이다.
    for path in ("/jobs", "/notion-mapping", "/backup", "/feature-flags",
                 "/announcements", "/users"):
        _goto(page, base, path)
        if page.locator(OVERFLOW).count():
            break
    btn = page.locator(OVERFLOW).first
    if not btn.count():
        f["notes"].append("들른 여섯 화면 어디에도 헤더 넘침 메뉴가 없다 — "
                          "이 실행에서는 측정 대상이 없었다")
        f["status"] = "NOT_APPLICABLE"
        return f
    btn.click()
    page.wait_for_timeout(700)
    menu = page.locator('[role="menu"]').first
    items = menu.locator('[role="menuitem"]')
    n = items.count()
    labels = [items.nth(i).inner_text().strip()[:14] for i in range(min(n, 8))]
    f["observed"] = {"items": n, "labels": labels}
    f["chain"] = {
        "ui_action": "«더 보기» 클릭",
        "frontend_state": f"role=menu 항목 {n}개",
        "rendered": " · ".join(labels),
    }
    f["notes"].append("서버 왕복이 없다 — 메뉴를 여는 것 자체는 표시 동작이다.")
    f["screenshots"].append(_shot(page, out, "ff1404-overflow"))
    f["status"] = "PASS" if n > 0 else "FAIL"
    page.keyboard.press("Escape")
    return f


def main() -> int:
    ap = argparse.ArgumentParser(description="공유 Layout Primitive 면 계약 + 기능 사슬 E2E (W4)")
    # 기본 대상은 `capture.DEFAULT_BASE_URL` 한 곳이 정한다 — 사용법 줄마다 호스트를
    # 적어 두면 이름이 바뀌는 날 그 줄들이 조용히 옛 제품을 가리킨다(W5 · F-W5D-129).
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.insecure:
        ssl._create_default_https_context = ssl._create_unverified_context

    from playwright.sync_api import sync_playwright

    surfaces: list[dict] = []
    flows: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        cache = REPO_ROOT / "dist" / "ui-qa"
        sess = ensure_session(browser, base, cache, insecure=args.insecure, log=print)

        # ── 면 계약: 4 뷰포트 × 2 테마 × 4 화면 ─────────────────────────────
        # 한 뷰포트만 재면 4K 에서만 나타나는 결함을 놓친다 — W2·W3 이 그렇게 한 번씩 겪었다.
        for vp in (Viewport("390x844", 390, 844), Viewport("1366x768", 1366, 768),
                   Viewport("1920x1080", 1920, 1080), Viewport("3840x2160", 3840, 2160)):
            for theme in ("light", "dark"):
                ctx = new_context(browser, storage_state=sess.storage_state,
                                  user_id=sess.user_id, theme=theme,
                                  viewport=vp, insecure=args.insecure)
                page = ctx.new_page()
                # `/chat-rooms` 는 **파괴적 외곽선 버튼(«나가기»)이 있는 화면**이라서 있다.
                # 앞의 넷에는 `outlinedError` 가 한 번도 나타나지 않아, 그 자리를 재기 시작한
                # 뒤에도 표본이 0개였다 — 검사를 고쳐 놓고 대상이 없는 곳에서만 돌린 셈이다.
                # 프로브는 자기가 검사하는 것이 실제로 존재하는 화면을 포함해야 한다.
                for name, path in (("me", "/me"), ("dashboard", "/dashboard"),
                                   ("users", "/users"), ("integrity", "/integrity"),
                                   ("chat-rooms", "/chat-rooms")):
                    try:
                        _goto(page, base, path)
                    except Exception as exc:  # noqa: BLE001
                        surfaces.append({"label": f"{name}-{theme}-{vp.name}",
                                         "error": str(exc)[:120],
                                         "verdict": {"ok": False, "checked": 0,
                                                     "fails": ["화면을 열지 못했다"],
                                                     "nestedPlates": 0}})
                        continue
                    tag = f"{name}-{theme}-{vp.name}"
                    m = measure(page, tag)
                    m["route"], m["theme"], m["viewport"] = path, theme, vp.name
                    if vp.name == "1920x1080" and theme == "light":
                        m["shot"] = _shot(page, out, f"surface-{tag}")
                    surfaces.append(m)
                ctx.close()

        # ── 기능 사슬 ────────────────────────────────────────────────────────
        vp = Viewport("1920x1080", 1920, 1080)
        ctx = new_context(browser, storage_state=sess.storage_state, user_id=sess.user_id,
                          theme="light", viewport=vp, insecure=args.insecure)
        page = ctx.new_page()
        rec = Recorder(page)
        # Flow 하나가 죽어도 **나머지와 면 계약 실측을 잃지 않는다.** 첫 실행이 그 반대여서
        # 32조합 측정을 다 해 놓고 모달 선택자 하나 때문에 아무 파일도 못 썼다.
        # 죽은 Flow 는 `status: ERROR` 로 남긴다 — 조용히 빠지면 그 Flow 는 없던 일이 된다.
        for fid, fn in (
            ("FF-1400", lambda: ff_1400_metric_filter(page, rec, out, base)),
            ("FF-1401", lambda: ff_1401_modal_open(page, rec, out, base)),
            ("FF-1402", lambda: ff_1402_dirty_guard(page, out)),
            ("FF-1403", lambda: ff_1403_page_help(page, out, base)),
            ("FF-1404", lambda: ff_1404_overflow(page, out, base)),
        ):
            try:
                flows.append(fn())
            except Exception as exc:  # noqa: BLE001
                bad = flow(fid, "unknown", "실행 중 예외")
                bad["status"] = "ERROR"
                bad["notes"].append("예외: %s" % " ".join(str(exc)[:200].split()))
                flows.append(bad)
                print("  [ERROR] %s — %s" % (fid, " ".join(str(exc)[:120].split())))
        ctx.close()
        browser.close()

    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    (out / "flows.json").write_text(
        json.dumps({"base_url": base, "viewport": "1920x1080", "flows": flows,
                    "generated_at": stamp}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "surfaces.json").write_text(
        json.dumps({"base_url": base, "contract": {
            "stripDivider": STRIP_DIVIDER_PX, "surfaceEdge": SURFACE_EDGE_PX,
            "calloutEdge": CALLOUT_EDGE_PX, "readoutRail": READOUT_RAIL_PX,
            "inkSeparationMin": INK_SEPARATION_MIN},
            "measurements": surfaces, "generated_at": stamp},
            ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"KIT_E2E_WRITTEN {out / 'flows.json'}")
    for f in flows:
        filled = [k for k in ("api_request", "backend_query", "api_response", "rendered")
                  if f["chain"].get(k)]
        print(f"  {f['id']:8s} {f['category']:16s} {f.get('status', '?'):15s} "
              f"사슬 핵심 {len(filled)}/4  {' · '.join(f['notes'])[:60]}")

    bad = 0
    nested = 0
    print(f"KIT_SURFACES_WRITTEN {out / 'surfaces.json'}")
    for m in surfaces:
        v = m["verdict"]
        bad += 0 if v["ok"] else 1
        nested += v.get("nestedPlates", 0)
        head = "PASS" if v["ok"] else f"FAIL {len(v['fails'])}"
        print(f"  {m['label']:34s} 검사 {v['checked']:3d}  판중첩 {v.get('nestedPlates', 0):2d}  {head}")
        for line in v["fails"][:3]:
            print(f"      · {line}")
    print(f"KIT_SURFACES {'OK' if bad == 0 else 'FAILED'} "
          f"({len(surfaces) - bad}/{len(surfaces)} 조합 · 판 안의 판 누적 {nested}자리)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
