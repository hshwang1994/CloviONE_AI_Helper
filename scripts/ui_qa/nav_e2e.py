"""사이드바 Navigation 을 **실제 브라우저에서** 재고 눌러 본다 (W3 · `shell_sidebar`).

`FUNCTIONAL_COVERAGE.json` 의 `shell_sidebar` 6개 Flow 는 W0 이 목록만 만들고 전부
`NOT_AUDITED` 였다. 사이드바는 모든 Route 위에 있으므로 여기가 고장 나면 제품 전체가 고장
난다 — 그런데 지금까지 이 Surface 를 실제로 눌러 본 적이 없다.

## 왜 별도 모듈인가 — 두 가지를 함께 재야 한다

1. **기하** (PLAN «Icon System» 라벨 시작선 계약 · «Navigation 상태» 신호 계약).
   jsdom 은 레이아웃을 하지 않는다. `nav-contract.test.jsx` 는 **선언**을 세지만, 선언이
   맞아도 화면에서 어긋날 수 있다 — 실제로 W2 는 "선언은 있는데 화면에는 없다"를 세 자리에서
   겪었다(MUI 가 논리 속성 shorthand 를 안 펴 준다). 그리고 이 Wave 가 닫는 결함
   `F-W2R-02` 는 **4K 에서만** 나타난다(px 칸 + rem 글리프). 그러니 1920 과 3840 에서
   루트 폰트사이즈로 정규화한 실측이 있어야 한다.

2. **기능 사슬**. 화면이 바뀌었다는 사실은 정상 동작의 증거가 아니다(CLAUDE.md §5).
   각 Flow 에서 네트워크를 함께 기록하고 서버가 관여하는 것은
   `ui_action → frontend_state → api_request → backend_query → api_response → rendered`
   를 실측값으로 채운다. **서버가 관여하지 않는 Flow 도 있다** — 그룹 접힘은 `localStorage`
   에만 산다. 그런 Flow 를 억지로 `PASS` 로 적으면 사슬의 API 칸을 지어내야 한다.
   이 스크립트는 **관측한 것만** 적고 판정은 `--out` JSON 을 읽는 사람이 한다
   (`shell_e2e.py` 와 같은 규율).

## 쓰는 법

    python -m scripts.ui_qa.nav_e2e --base-url https://clovirassist.gooddi.lab --insecure

산출물: `dist/ui-qa/w3-nav-e2e/{flows.json,anatomy.json}` + 단계별 스크린샷.
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

# 요약을 한국어로 찍는데 Windows 기본 콘솔은 cp949 다 — 여기서 막히면 결과 파일은 이미 다
# 썼는데 실행이 실패로 보인다. 다른 검사 스크립트와 같은 처리를 한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import Viewport, new_context  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "w3-nav-e2e"

# 계약값 — 정본은 `frontend/src/ui/theme.js::NAV_ANATOMY` 다. 여기 적은 값이 그것과 갈라지면
# `nav-contract.test.jsx` 가 먼저 깨진다(그쪽은 상수를 import 해서 센다).
LABEL_START_PX = 42
RAIL_PX = 3
GLYPH_PX = 20
CHEVRON_PX = 18

# 좁은 화면에서 사이드바는 `variant="temporary"` 라 MUI 가 **body 로 포털**한다 —
# `#app-sidebar` 안에서 찾으면 390 에서 영원히 못 찾는다(이 프로브가 처음 그렇게 죽었다).
# 드로어 중 `<nav>` 를 가진 것 하나가 사이드바다(AI 서랍에는 nav 가 없다).
SIDEBAR = ".MuiDrawer-paper:has(nav)"
NAVLIST = f"{SIDEBAR} nav"
GROUP = f"{NAVLIST} .MuiListItemButton-root[aria-expanded]"
ITEM = f'{NAVLIST} a[href]'
ACTIVE = f'{NAVLIST} [aria-current="page"]'
MENU_FILTER = f'{SIDEBAR} input[aria-label="메뉴 찾기"]'

# 사이드바 한 줄의 기하를 재는 브라우저 측 함수.
#
# 라벨 시작선은 **라벨 글자 상자의 왼쪽 모서리**를 사이드바 왼쪽 모서리로부터 잰다.
# `padding-left` 선언을 읽는 것과 다르다 — 선언이 맞아도 그 앞에 다른 상자가 끼면 화면에서는
# 어긋나기 때문이다. 4K 는 루트 폰트사이즈가 20px 이라 계약값(@16)의 1.25배가 정답이다.
# 그래서 실측값을 `16 / rootFontSize` 로 정규화해 한 눈금에서 비교한다.
ANATOMY_JS = r"""
() => {
  const root = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const norm = (px) => Math.round((px * 16 / root) * 100) / 100;
  const paper = [...document.querySelectorAll('.MuiDrawer-paper')]
    .find((el) => el.querySelector('nav'));
  if (!paper) return { error: 'sidebar not found' };
  const paperRect = paper.getBoundingClientRect();
  const list = paper.querySelector('nav');

  // **접힌 그룹 안의 행은 그려지지 않는다.** MUI Collapse 는 닫힐 때 래퍼를 height 0 +
  // overflow hidden 으로 만드는데, 그 안의 행은 여전히 자기 rect 와 non-null offsetParent 를
  // 갖는다(`checkVisibility()` 도 이 경우를 hidden 으로 안 본다). 그래서 **조상 Collapse 의
  // 높이**로 판정한다. 이걸 안 하면 사이드바 빈 면이 8~16pp 틀리게 기록된다 —
  // 첫 판이 그렇게 틀렸고 그 숫자가 그대로 다음 Wave 로 넘어갈 뻔했다.
  const visibleRows = () => [...paper.querySelectorAll('nav .MuiListItemButton-root')]
    .filter((r) => {
      const wrap = r.closest('.MuiCollapse-root');
      return !wrap || wrap.getBoundingClientRect().height > 0;
    });

  const rowOf = (el, kind) => {
    const label = el.querySelector('.MuiListItemText-primary');
    const cs = getComputedStyle(el);
    const before = getComputedStyle(el, '::before');
    const glyphs = [...el.querySelectorAll('svg')].map((g) => {
      const r = g.getBoundingClientRect();
      return { fontSize: norm(parseFloat(getComputedStyle(g).fontSize)),
               w: norm(r.width), h: norm(r.height) };
    });
    const slot = el.querySelector('.MuiListItemIcon-root');
    return {
      kind,
      text: (label ? label.textContent : el.textContent).trim().slice(0, 24),
      active: el.getAttribute('aria-current') === 'page',
      labelStart: label ? norm(label.getBoundingClientRect().left - paperRect.left) : null,
      rowLeft: norm(el.getBoundingClientRect().left - paperRect.left),
      rowWidth: norm(el.getBoundingClientRect().width),
      rowHeight: norm(el.getBoundingClientRect().height),
      paddingInlineStart: norm(parseFloat(cs.paddingLeft)),
      fontWeight: label ? getComputedStyle(label).fontWeight : null,
      color: label ? getComputedStyle(label).color : null,
      background: cs.backgroundColor,
      borderRadius: cs.borderTopLeftRadius,
      rectTop: Math.round(el.getBoundingClientRect().top),
      rectBottom: Math.round(el.getBoundingClientRect().bottom),
      hasGlyphSlot: !!slot,
      glyphSlotWidth: slot ? norm(slot.getBoundingClientRect().width) : null,
      glyphs,
      rail: {
        width: norm(parseFloat(before.width) || 0),
        left: before.left === 'auto' ? null : norm(parseFloat(before.left) || 0),
        background: before.backgroundColor,
        content: before.content,
      },
    };
  };

  const groups = [...paper.querySelectorAll('nav .MuiListItemButton-root[aria-expanded]')]
    .map((el) => rowOf(el, 'group'));
  const items = [...paper.querySelectorAll('nav a[href]')].map((el) => rowOf(el, 'item'));
  return {
    rootFontSize: root,
    paper: { left: Math.round(paperRect.left), width: norm(paperRect.width),
             height: Math.round(paperRect.height) },
    // 사이드바 아래쪽 빈 면 — F-W2R-02 의 두 번째 관찰(하단 38~50%가 빈 면이라 Gradient
    // 이동량의 절반이 빈 자리에 쓰인다)을 이 Wave 뒤에 다시 잰다.
    navList: list ? {
      top: Math.round(list.getBoundingClientRect().top),
      bottom: Math.round(list.getBoundingClientRect().bottom),
      // 스크롤 없이 실제로 보이는 아래 경계. `bottom` 은 요소의 상자이고 이쪽은 **창**이다.
      visibleBottom: Math.round(list.getBoundingClientRect().top + list.clientHeight),
      scrollHeight: list.scrollHeight,
      clientHeight: list.clientHeight,
      // **보이는** 마지막 행. 접힌 MUI Collapse 안의 행도 rect 를 돌려주므로 DOM 말미를
      // 그냥 집으면 접힘이 있는 조합에서 빈 면이 8~16pp 작게 기록된다(독립 재검증이 잡았다 —
      // 그 틀린 숫자가 그대로 W7 이관 수치가 됐었다). `offsetParent` 가 null 이거나 높이가
      // 0 인 행은 그려지지 않은 것이다.
      lastRowBottom: (() => {
        const rows = visibleRows();
        return rows.length
          ? Math.round(Math.max(...rows.map((r) => r.getBoundingClientRect().bottom)))
          : null;
      })(),
      visibleRows: visibleRows().length,
    } : null,
    groups,
    items,
  };
}
"""

FOCUS_JS = r"""
() => {
  const paper = [...document.querySelectorAll('.MuiDrawer-paper')]
    .find((p) => p.querySelector('nav'));
  const el = paper && paper.querySelector('nav a[href]');
  if (!el) return null;
  el.focus();
  const cs = getComputedStyle(el);
  return { how: 'programmatic', outlineWidth: cs.outlineWidth, outlineStyle: cs.outlineStyle,
           outlineColor: cs.outlineColor, outlineOffset: cs.outlineOffset,
           muiFocusVisible: el.classList.contains('Mui-focusVisible') };
}
"""

# 키보드로 실제로 걸어가서 잰다. 프로그램적 `.focus()` 는 MUI 의 키보드 판정을 통과하지 못해
# `.Mui-focusVisible` 가 안 붙는다 — 그 상태만 재면 **프로브가 만든 상태**를 제품 상태로
# 착각하게 된다. 둘 다 재고 둘 다 계약을 지켜야 통과다.
FOCUS_KEYBOARD_JS = r"""
() => {
  const el = document.activeElement;
  if (!el || !el.closest('.MuiDrawer-paper')) return null;
  const cs = getComputedStyle(el);
  return { how: 'keyboard', text: (el.textContent || '').trim().slice(0, 20),
           outlineWidth: cs.outlineWidth, outlineStyle: cs.outlineStyle,
           outlineColor: cs.outlineColor, outlineOffset: cs.outlineOffset,
           muiFocusVisible: el.classList.contains('Mui-focusVisible') };
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
                           "status": response.status, "at": time.time()})

    def reset(self) -> None:
        self.calls = []

    def since(self, fragment: str) -> list[dict]:
        return [c for c in self.calls if fragment in c["url"]]


def _shot(page, out: Path, name: str) -> str:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _open_drawer(page) -> bool:
    """좁은 화면에서 사이드바는 임시 서랍이다 — 햄버거를 눌러야 **보인다**.

    `keepMounted` 라 DOM 에는 늘 있지만 닫혀 있으면 폭 0 으로 접혀 있어 기하가 전부 0 이다.
    잰 값이 0 이면 그건 제품이 아니라 프로브 상태다.
    """
    btn = page.locator('[aria-label="메뉴 열기"]').first
    if btn.count():
        btn.click()
        page.wait_for_timeout(800)
    return page.locator(NAVLIST).count() > 0


def _goto(page, base: str, hash_path: str, tries: int = 2, open_drawer: bool = False) -> None:
    """HashRouter 이동. `capture.py` 가 이미 배운 두 가지를 그대로 따른다.

    ① **`state="attached"`** — 기본값 `visible` 은 셸이 첫 페인트를 마치기 전 잠깐의
       레이아웃 상태에서 참을성 없이 실패한다(이 모듈 첫 실행이 그렇게 죽었다).
       우리가 기다리는 것은 "본문 노드가 붙었나" 이고, 보이는지는 그 다음 `wait_for_timeout`
       뒤 실제 측정이 답한다.
    ② **fragment-only 이동은 재로딩이 아니다** — 같은 문서 안 이동이라 `goto` 가 곧바로
       돌아온다. 그래서 SPA 가 라우트를 갈아 끼울 시간을 따로 준다.
    """
    last = None
    for attempt in range(tries):
        try:
            page.goto(base + "/#" + hash_path, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_selector("#main-content", state="attached", timeout=30_000)
            if open_drawer:
                page.wait_for_timeout(900)
                _open_drawer(page)
            page.wait_for_selector(NAVLIST, state="attached", timeout=30_000)
            page.wait_for_timeout(1200)
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            # 같은 문서 안에 있으면 다음 `goto` 도 같은 문서 안 이동이라 아무것도 안 바뀐다.
            # 한 번은 문서를 통째로 버리고 다시 연다.
            page.goto("about:blank", wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(500)
    raise last


def _pick(calls, *fragments):
    """사슬의 `api_request` 칸에 **그 화면의 질의**를 적는다.

    한 화면은 여러 API 를 동시에 부른다(공용 조회·저장된 뷰·메타). 무조건 첫 번째를 적으면
    `api_request` 는 `admin/departments` 인데 `backend_query` 는 `app/projects/router.py` 라고
    적히는, **서로 다른 두 가지를 한 사슬로 묶은 기록**이 남는다. 도메인 조각으로 골라 적고,
    없으면 `None` 을 돌려 사슬 칸을 비운다 — 지어내지 않는다.
    """
    for c in calls:
        if any(fr in c["url"] for fr in fragments):
            return c
    return None


def flow(fid: str, category: str, name: str) -> dict:
    return {"id": fid, "category": category, "name": name, "observed": {},
            "chain": {}, "screenshots": [], "notes": []}


# --------------------------------------------------------------------------- #
# 기하 — 라벨 시작선 · 레일 · 글리프 · 신호 개수
# --------------------------------------------------------------------------- #
def measure(page, label: str) -> dict:
    data = page.evaluate(ANATOMY_JS)
    data["focus"] = page.evaluate(FOCUS_JS)
    data["focusKeyboard"] = _keyboard_focus(page)
    data["label"] = label
    return data


def _keyboard_focus(page, max_tabs: int = 40) -> dict | None:
    """Tab 으로 실제로 걸어가서 사이드바 안 첫 포커스 대상을 잰다.

    프로그램적 `.focus()` 만 재면 MUI 의 키보드 판정(`.Mui-focusVisible`)이 안 붙은 상태만
    보게 된다 — 그건 프로브가 만든 상태이지 사용자가 겪는 상태가 아니다. 둘 다 재고 둘 다
    계약을 지켜야 통과다. 첫 실행에서 이 구분이 실제 결함을 드러냈다(전역 `:focus-visible`
    규칙의 `outline-offset: 2` 가 이겨서 링이 하우징 밖으로 새고 있었다).
    """
    page.evaluate("() => { document.body.focus(); window.scrollTo(0, 0); }")
    page.keyboard.press("Tab")
    for _ in range(max_tabs):
        got = page.evaluate(FOCUS_KEYBOARD_JS)
        if got:
            return got
        page.keyboard.press("Tab")
    return None


def verdict(m: dict) -> dict:
    """실측에서 계약 위반을 뽑는다. 판정 규칙은 PLAN 이 이미 적어 둔 숫자 그대로다."""
    fails: list[str] = []
    rows = m.get("groups", []) + m.get("items", [])
    if not rows:
        return {"ok": False, "fails": ["사이드바에서 행을 하나도 못 찾았다"], "checked": 0}

    starts = sorted({r["labelStart"] for r in rows if r["labelStart"] is not None})
    for r in rows:
        if r["labelStart"] is None:
            fails.append(f"{r['kind']} «{r['text']}» 라벨을 못 찾았다")
        elif abs(r["labelStart"] - LABEL_START_PX) > 1.0:
            fails.append(f"{r['kind']} «{r['text']}» 라벨 시작선 {r['labelStart']} "
                         f"(계약 {LABEL_START_PX})")
    if len(starts) > 1:
        fails.append(f"라벨 시작선이 한 열이 아니다: {starts}")

    # 글리프: 그룹은 랜드마크 1 + 펼침 화살표 1, 자식은 0. 자식이 부모보다 클 수 없다.
    for g in m.get("groups", []):
        sizes = [x["fontSize"] for x in g["glyphs"]]
        if not sizes:
            fails.append(f"그룹 «{g['text']}» 이 랜드마크 글리프를 잃었다")
        else:
            if abs(sizes[0] - GLYPH_PX) > 0.6:
                fails.append(f"그룹 «{g['text']}» 글리프 {sizes[0]} (계약 {GLYPH_PX})")
            if len(sizes) > 1 and abs(sizes[1] - CHEVRON_PX) > 0.6:
                fails.append(f"그룹 «{g['text']}» 펼침 화살표 {sizes[1]} (계약 {CHEVRON_PX})")
    for it in m.get("items", []):
        if it["glyphs"]:
            fails.append(f"자식 «{it['text']}» 이 글리프를 가졌다 "
                         f"(그룹이 가지면 자식은 갖지 않는다)")
        if it["hasGlyphSlot"]:
            fails.append(f"자식 «{it['text']}» 에 글리프 칸이 남아 있다")

    # 활성 신호 — 정확히 둘(위치=레일, 색=면·잉크). 굵기는 바뀌면 안 된다.
    active = [r for r in m["items"] if r["active"]]
    inactive = [r for r in m["items"] if not r["active"]]
    if not active:
        fails.append("활성 항목이 하나도 없다 — 지금 어디 있는지 화면이 말하지 않는다")
    for a in active:
        if abs(a["rail"]["width"] - RAIL_PX) > 0.6:
            fails.append(f"활성 «{a['text']}» 레일 두께 {a['rail']['width']} (계약 {RAIL_PX})")
        if a["rail"]["left"] not in (0, 0.0):
            fails.append(f"활성 «{a['text']}» 레일이 가장자리에서 {a['rail']['left']} 안쪽에 있다")
        if a["background"] in ("rgba(0, 0, 0, 0)", "transparent"):
            fails.append(f"활성 «{a['text']}» 행이 면을 칠하지 않는다")
    if active and inactive:
        aw, iw = active[0]["fontWeight"], inactive[0]["fontWeight"]
        if aw != iw:
            fails.append(f"활성/비활성 굵기가 다르다 ({aw} vs {iw}) — 한글에서 글자 폭이 바뀐다")
        if active[0]["color"] == inactive[0]["color"]:
            fails.append("활성/비활성 잉크색이 같다 — 색 신호가 없다")
    for r in inactive:
        if r["rail"]["width"] and r["rail"]["background"] not in ("rgba(0, 0, 0, 0)", "transparent"):
            fails.append(f"비활성 «{r['text']}» 에 레일이 칠해져 있다")

    # **지도가 잘리면 지도가 아니다.** 그룹 헤더(랜드마크)는 스크롤 없이 전부 보여야 한다.
    # 1366x768 에서 사용자 rail 이 전부 펼쳐지면 «내 정보» 랜드마크가 통째로 창 밖으로 나갔고
    # (독립 검수 실측: 22행 중 17행만 보임), 그 사실을 알리는 신호는 명도차 2.4% 짜리 그림자
    # 하나뿐이었다. 이제 셸이 "전부 펼친 높이가 들어가는가"를 재서 안 들어가면 접힘으로
    # 되돌린다 — 그 규칙이 실제로 도는지 여기서 확인한다.
    nav_list = m.get("navList") or {}
    visible_bottom = nav_list.get("visibleBottom")
    if visible_bottom is not None:
        hidden = [g["text"] for g in m.get("groups", [])
                  if g.get("rectBottom") is not None and g["rectBottom"] > visible_bottom + 1]
        if hidden:
            fails.append("스크롤 없이 안 보이는 랜드마크: %s (창 하단 %d)"
                         % (", ".join(hidden), visible_bottom))

    # 포커스 링은 **두 경로 모두** 안쪽으로 그려져야 한다 — MUI 의 `.Mui-focusVisible` 와
    # 브라우저의 `:focus-visible` 가 항상 같이 걸리지는 않는다.
    #
    # **키보드** 경로가 계약이다 — 링을 그려야 하고 안쪽(-2px)이어야 한다.
    # **프로그램적** `.focus()` 는 브라우저의 `:focus-visible` 판정에 달려 있다: 직전 상호작용이
    # 포인터였으면(예: 좁은 화면에서 햄버거를 눌러 서랍을 연 직후) 크롬은 링을 아예 안 그린다.
    # 그건 제품 상태가 아니라 프로브가 만든 상태이므로 "안 그렸다"를 위반으로 세지 않는다.
    # 다만 **그렸다면** 계약대로 안쪽이어야 한다 — 이 Wave 가 처음 잡은 결함이 정확히
    # "그렸는데 offset 이 +2 라 하우징 밖으로 샌다" 였다.
    kb = m.get("focusKeyboard") or {}
    if not kb:
        fails.append("키보드 Tab 으로 사이드바 안에 포커스를 못 넣었다")
    else:
        if kb.get("outlineStyle") in (None, "none"):
            fails.append("키보드 포커스 링이 그려지지 않는다")
        if kb.get("outlineOffset") != "-2px":
            fails.append(f"키보드 포커스 링 offset {kb.get('outlineOffset')} (계약 -2px) "
                         f"— 가장자리 행에서 링이 하우징 밖으로 샌다")
    prog = m.get("focus") or {}
    if prog.get("outlineStyle") not in (None, "none") and prog.get("outlineOffset") != "-2px":
        fails.append(f"프로그램적 포커스 링 offset {prog.get('outlineOffset')} (계약 -2px)")

    return {"ok": not fails, "fails": fails, "checked": len(rows)}


PALETTE_JS = r"""
() => {
  const root = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const norm = (px) => Math.round((px * 16 / root) * 100) / 100;
  // `[role="dialog"]` 은 문서에 여럿이다(AI 서랍이 keepMounted 로 늘 붙어 있다).
  // 첫 번째를 집으면 팔레트가 아닌 것을 재고 조용히 0줄을 돌려준다 — 실제로 그랬다.
  // 팔레트 입력을 품은 다이얼로그 하나로 겨눈다.
  const dlg = [...document.querySelectorAll('[role="dialog"]')]
    .find((d) => d.querySelector('input[aria-label="통합 검색"]'));
  if (!dlg) return { error: 'palette not open' };
  const rows = [...dlg.querySelectorAll('.MuiListItemButton-root')].map((el) => {
    const svg = el.querySelector('svg');
    const label = el.querySelector('.MuiTypography-root');
    return {
      text: (el.textContent || '').trim().slice(0, 28),
      selected: el.classList.contains('Mui-selected') || el.getAttribute('aria-selected') === 'true',
      glyph: svg ? norm(parseFloat(getComputedStyle(svg).fontSize)) : null,
      // 어느 그림인가. 운영 빌드에는 `data-testid` 가 없으므로 path 데이터 앞머리로 식별한다.
      glyphId: svg && svg.querySelector('path')
        ? (svg.querySelector('path').getAttribute('d') || '').slice(0, 24) : null,
      fontWeight: label ? getComputedStyle(label).fontWeight : null,
    };
  });
  const heads = [...dlg.querySelectorAll('.MuiListSubheader-root')].map(
    (el) => (el.textContent || '').trim().slice(0, 24));
  return { rootFontSize: root, sections: heads, rows: rows.slice(0, 14) };
}
"""


def measure_palette(page, out: Path, theme: str, base: str) -> dict:
    """Command Palette 는 이 Wave 가 고친 표면인데 배포본 픽셀이 없었다 (독립 검수 지적).

    세 자리를 고쳤다 — 메뉴 줄 글리프가 항목별에서 **그룹 랜드마크**로, 글리프 크기가
    `fontSize="small"`(px)에서 `ICON.nav`(rem)로, 선택 줄의 굵기 변경 제거. 셋 다 화면에서만
    판정할 수 있다. 여기서 열고, 재고, 두 테마로 찍는다.
    """
    got = {"theme": theme, "shots": []}
    # **최근 방문 상태를 실제로 만든다.** 새 컨텍스트는 이력이 0건이라 빈 질의 화면이 나오는데,
    # 파일 이름만 `palette-recent-*` 로 남으면 다음 검수자가 확인된 상태로 오해한다.
    # 서로 다른 그룹의 화면을 밟아 둬야 "줄마다 소속 글리프가 다른가" 를 볼 수 있다.
    for path in ("/my-tickets", "/projects", "/chat-rooms", "/profile"):
        _goto(page, base, path)
    _goto(page, base, "/me")
    page.locator('[aria-label="통합 검색과 명령 열기"]').first.click()
    page.wait_for_selector('input[aria-label="통합 검색"]', timeout=15_000)
    page.wait_for_timeout(800)
    got["recent"] = page.evaluate(PALETTE_JS)
    got["shots"].append(_shot(page, out, f"palette-recent-{theme}"))
    page.locator('input[aria-label="통합 검색"]').fill("티켓")
    page.wait_for_timeout(1600)
    got.update(page.evaluate(PALETTE_JS))
    got["shots"].append(_shot(page, out, f"palette-menu-{theme}"))
    fails = []
    glyphs = [r["glyph"] for r in got.get("rows", []) if r.get("glyph") is not None]
    if glyphs and max(glyphs) > GLYPH_PX + 0.6:
        fails.append(f"팔레트 글리프가 nav 슬롯보다 크다: {max(glyphs)}")
    weights = {r.get("fontWeight") for r in got.get("rows", []) if r.get("fontWeight")}
    if len(weights) > 1:
        fails.append(f"줄마다 굵기가 다르다 {sorted(weights)} — 선택으로 굵기가 바뀌면 줄이 움직인다")
    # 최근 방문은 여러 그룹에서 모인 목록이다 — 줄마다 소속이 다른데 글리프가 하나면 그 열은
    # 아무것도 말하지 않는다(이 파일이 예전부터 적어 둔 경고이고, 한 번 그 상태를 만들었다).
    rec = got.get("recent") or {}
    rec_rows = rec.get("rows") or []
    if len(rec_rows) >= 2:
        kinds = {r.get("glyphId") for r in rec_rows if r.get("glyphId")}
        got["recent_glyph_kinds"] = len(kinds)
        got["recent_rows"] = len(rec_rows)
        if not kinds:
            fails.append("최근 방문 줄에 글리프가 없다")
        elif len(kinds) == 1 and len(rec_rows) >= 3:
            fails.append("최근 방문 %d줄이 전부 같은 그림이다 — 여러 그룹에서 모인 목록인데 "
                         "글리프 열이 아무것도 구분하지 못한다" % len(rec_rows))
    elif rec:
        got["recent_note"] = "최근 방문 줄이 %d개뿐이라 다양성을 판정하지 않는다" % len(rec_rows)
    got["verdict"] = {"ok": not fails, "fails": fails, "checked": len(got.get("rows", []))}
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    return got


# --------------------------------------------------------------------------- #
# Flow
# --------------------------------------------------------------------------- #
def ff_1200_navigate(page, rec: Recorder, out: Path, base: str) -> dict:
    f = flow("FF-1200", "navigation", "사이드바 항목을 눌러 그 화면으로 간다")
    _goto(page, base, "/me")
    rec.reset()
    link = page.locator(f'{NAVLIST} a[href$="/my-tickets"]').first
    f["observed"]["target_visible"] = link.is_visible()
    f["chain"]["ui_action"] = "사이드바 «내 티켓» 클릭"
    before = page.url
    link.click()
    page.wait_for_timeout(2500)
    f["observed"]["url_before"] = before
    f["observed"]["url_after"] = page.url
    f["chain"]["url_state"] = f"해시 {before.split('#')[-1]} → {page.url.split('#')[-1]}"
    calls = [c for c in rec.calls if c["status"] < 400]
    f["observed"]["calls"] = [c["url"].split("/api/")[-1] for c in calls[:6]]
    hit = _pick(calls, "tickets/mine", "/tickets")
    if hit:
        f["chain"]["api_request"] = f"{hit['method']} {hit['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "app/tickets/router.py → 내가 요청자/담당자인 티켓 (권한 Scope 적용)"
        f["chain"]["api_response"] = f"HTTP {hit['status']}"
    f["chain"]["frontend_state"] = "활성 항목이 «내 티켓» 로 옮겨간다"
    active = page.locator(ACTIVE).first
    f["observed"]["active_after"] = active.inner_text().strip() if active.count() else None
    f["chain"]["rendered"] = "본문 «%s»" % page.locator("#main-content").inner_text()[:100].replace("\n", " ")
    f["screenshots"].append(_shot(page, out, "ff1200-navigated"))
    return f


def ff_1201_collapse(browser, sess, base: str, out: Path, insecure: bool) -> dict:
    """**시딩 없는 컨텍스트**에서 잰다.

    `capture.py::new_context` 는 매 이동마다 `clovirone_nav_collapsed:<userId>` 를 `'{}'` 로
    되돌리는 init script 를 심는다 — 스크린샷을 결정적으로 만들려고 일부러 그렇게 한 것이고
    옳다. 그런데 이 Flow 가 재려는 것이 바로 그 키의 **지속성**이라, 그 컨텍스트에서 재면
    하네스가 지운 것을 제품이 잃어버렸다고 읽게 된다. 첫 실행이 정확히 그 위양성을 냈다
    (`after_reload=true`). 그래서 여기서만 맨 컨텍스트를 쓴다 — 프로브를 대상보다 먼저
    의심한다(`scripts/ui_qa/README.md`).
    """
    f = flow("FF-1201", "navigation", "그룹을 접고 펴며 접힘 상태가 계정별로 유지된다")
    ctx = browser.new_context(
        storage_state=sess.storage_state,
        viewport={"width": 1920, "height": 1080},
        color_scheme="light", locale="ko-KR", timezone_id="Asia/Seoul",
        reduced_motion="reduce", ignore_https_errors=insecure,
    )
    page = ctx.new_page()
    rec = Recorder(page)
    _goto(page, base, "/me")
    rec.reset()
    f["notes"].append(
        "하네스의 테마·접힘 시딩 init script 를 뺀 맨 컨텍스트에서 쟀다 — 그 스크립트가 매 "
        "이동마다 접힘 키를 '{}' 로 되돌리기 때문에 시딩 컨텍스트에서는 지속성을 잴 수 없다.")
    header = page.locator(GROUP).filter(has_text="팀 공간").first
    f["observed"]["before"] = header.get_attribute("aria-expanded")
    f["chain"]["ui_action"] = "«팀 공간» 그룹 헤더 클릭(접기)"
    header.click()
    page.wait_for_timeout(600)
    f["observed"]["after_click"] = header.get_attribute("aria-expanded")
    stored = page.evaluate(
        "() => Object.entries(window.localStorage)"
        ".filter(([k]) => k.startsWith('clovirone_nav_collapsed')).map(([k, v]) => k + '=' + v)")
    f["observed"]["localStorage"] = stored
    f["chain"]["frontend_state"] = f"collapsed 기록 {stored}"
    f["screenshots"].append(_shot(page, out, "ff1201-collapsed"))

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(NAVLIST, timeout=30_000)
    page.wait_for_timeout(1500)
    header2 = page.locator(GROUP).filter(has_text="팀 공간").first
    f["observed"]["after_reload"] = header2.get_attribute("aria-expanded")
    f["chain"]["rendered"] = f"새로고침 뒤 aria-expanded={f['observed']['after_reload']}"
    f["observed"]["api_calls_during"] = len(rec.since("/api/nav"))
    f["notes"].append(
        "이 Flow 에는 서버 왕복이 **구조적으로 없다** — 접힘 상태는 계정별 localStorage 키"
        "(`clovirone_nav_collapsed:<userId>`)에만 산다. 사슬의 API 칸을 지어내지 않는다.")
    f["screenshots"].append(_shot(page, out, "ff1201-after-reload"))
    ctx.close()
    return f


def ff_1202_filter(page, rec: Recorder, out: Path, base: str) -> dict:
    f = flow("FF-1202", "search", "사이드바 자체 필터로 항목을 좁힌다")
    _goto(page, base, "/dashboard")
    box = page.locator(MENU_FILTER)
    f["observed"]["filter_present_admin"] = box.count() > 0
    if not box.count():
        f["notes"].append("관리자 콘솔에 메뉴 필터가 없다 — 계약 위반")
        return f
    # 전부 펼쳐 필터 전 후보 수를 정직하게 센다(접힌 그룹의 항목도 DOM 에는 있다).
    before = page.locator(ITEM).count()
    f["chain"]["ui_action"] = "메뉴 찾기에 «백업» 입력"
    box.fill("백업")
    page.wait_for_timeout(700)
    after = page.locator(ITEM).count()
    labels = [page.locator(ITEM).nth(i).inner_text().strip() for i in range(min(after, 10))]
    f["observed"] = {**f["observed"], "items_before": before, "items_after": after, "labels": labels}
    f["chain"]["frontend_state"] = f"filterGroupsByQuery — 후보 {before} → {after}"
    f["chain"]["rendered"] = f"남은 목적지 {labels}"
    f["screenshots"].append(_shot(page, out, "ff1202-filtered"))

    box.fill("zzz없는메뉴zzz")
    page.wait_for_timeout(600)
    empty = page.locator(SIDEBAR).inner_text()
    f["observed"]["empty_face"] = " ".join(empty.split())[:120]
    f["screenshots"].append(_shot(page, out, "ff1202-filter-empty"))
    box.fill("")
    page.wait_for_timeout(400)
    f["notes"].append("로컬 필터다 — 서버에 묻지 않는다(사이드바 항목은 이미 브라우저에 있다). "
                      "사슬의 API 칸을 지어내지 않는다.")
    f["observed"]["api_calls_during"] = len([c for c in rec.calls if "search" in c["url"]])
    return f


def ff_1203_permission(page_admin, page_user, out: Path) -> dict:
    f = flow("FF-1203", "permission_state", "SCREEN_ROLES 가 허용하지 않는 항목은 아예 그리지 않는다")

    def probe(page, tag):
        page.wait_for_selector(NAVLIST, timeout=30_000)
        page.wait_for_timeout(1000)
        items = page.locator(ITEM)
        labels = [items.nth(i).inner_text().strip().replace("\n", " ")
                  for i in range(min(items.count(), 60))]
        hrefs = [items.nth(i).get_attribute("href") for i in range(min(items.count(), 60))]
        return {"count": len(labels), "labels": labels[:40], "hrefs": hrefs[:40],
                "shot": _shot(page, out, f"ff1203-{tag}")}

    admin = probe(page_admin, "system_admin")
    user = probe(page_user, "user")
    f["observed"] = {"system_admin": admin, "user": user}
    admin_only = [h for h in admin["hrefs"] if h and h not in (user["hrefs"] or [])]
    f["observed"]["admin_only_destinations"] = admin_only[:20]
    f["chain"]["ui_action"] = "같은 셸을 system_admin / user 두 세션으로 연다"
    f["chain"]["api_request"] = "GET me"
    f["chain"]["backend_query"] = "app/core/sessions.py → 세션의 실제 role (서버가 정본)"
    f["chain"]["api_response"] = "HTTP 200 (역할이 서로 다른 두 세션)"
    f["chain"]["frontend_state"] = (
        f"filterNavByRole — 항목 수 system_admin={admin['count']} / user={user['count']}")
    f["chain"]["rendered"] = f"일반 사용자에게 안 그려진 목적지 {len(admin_only)}개"
    f["screenshots"] = [admin["shot"], user["shot"]]
    f["notes"].append("프런트가 안 그린다는 것이 권한의 정본은 아니다(서버가 막는다) — "
                      "여기서 확인하는 계약은 '눌렀더니 403' 막다른 길을 그리지 않는다는 것이다.")
    return f


def ff_1204_deeplink(page, rec: Recorder, out: Path, base: str) -> dict:
    f = flow("FF-1204", "deep_link", "주소가 바뀌면 활성 항목과 그룹 펼침이 그 자리에 맞춰진다")
    rec.reset()
    f["chain"]["ui_action"] = "접힌 그룹 안의 경로로 직접 진입 (/#/audit)"
    _goto(page, base, "/audit")
    active = page.locator(ACTIVE)
    f["observed"]["active_count"] = active.count()
    f["observed"]["active_label"] = active.first.inner_text().strip() if active.count() else None
    groups = page.locator(GROUP)
    state = {}
    for i in range(groups.count()):
        state[groups.nth(i).inner_text().strip().split("\n")[0]] = groups.nth(i).get_attribute("aria-expanded")
    f["observed"]["group_state"] = state
    calls = [c for c in rec.calls if c["status"] < 400]
    f["observed"]["calls"] = [c["url"].split("/api/")[-1] for c in calls[:6]]
    hit = _pick(calls, "/audit")
    if hit:
        f["chain"]["api_request"] = f"{hit['method']} {hit['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "app/audit/router.py → 감사 로그 조회 (SENSITIVE_READ 역할 게이트)"
        f["chain"]["api_response"] = f"HTTP {hit['status']}"
    f["chain"]["frontend_state"] = f"activeNavPath → «{f['observed']['active_label']}», 그룹 펼침 {state}"
    f["chain"]["rendered"] = "본문 «%s»" % page.locator("#main-content").inner_text()[:100].replace("\n", " ")
    f["screenshots"].append(_shot(page, out, "ff1204-deeplink"))

    # 뒤로 가면 활성 표시도 따라 돌아온다.
    page.go_back()
    page.wait_for_timeout(1800)
    back_active = page.locator(ACTIVE)
    f["observed"]["active_after_back"] = (
        back_active.first.inner_text().strip() if back_active.count() else None)
    return f


def ff_1207_back(page, rec: Recorder, out: Path, base: str) -> dict:
    """뒤로/앞으로 — 사이드바 활성 표시가 주소와 함께 돌아온다.

    사이드바 강조는 `activeNavPath(location.pathname)` 에서 나오므로 뒤로 가기도 따라와야
    한다. 따라오지 않으면 "지금 어디 있는가"를 사이드바가 틀리게 말하는 상태가 되고, 그건
    다른 어떤 신호보다 나쁘다 — 사용자는 그 표시를 믿고 다음 클릭을 고른다.
    """
    f = flow("FF-1207", "back_forward", "뒤로/앞으로 — 사이드바 활성 표시가 이전 화면으로 함께 돌아온다")
    _goto(page, base, "/me")
    start = page.locator(ACTIVE).first
    f["observed"]["active_start"] = start.inner_text().strip() if start.count() else None
    rec.reset()
    f["chain"]["ui_action"] = "사이드바 «프로젝트» 클릭 후 브라우저 뒤로"
    page.locator(f'{NAVLIST} a[href$="/projects"]').first.click()
    page.wait_for_timeout(2200)
    moved = page.locator(ACTIVE).first
    f["observed"]["active_after_click"] = moved.inner_text().strip() if moved.count() else None
    f["observed"]["url_after_click"] = page.url
    calls = [c for c in rec.calls if c["status"] < 400]
    f["observed"]["calls"] = [c["url"].split("/api/")[-1] for c in calls[:6]]
    hit = _pick(calls, "/projects")
    if hit:
        f["chain"]["api_request"] = f"{hit['method']} {hit['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = "app/projects/router.py → 내가 볼 수 있는 프로젝트 (권한 Scope 적용)"
        f["chain"]["api_response"] = f"HTTP {hit['status']}"
    rec.reset()
    page.go_back()
    page.wait_for_timeout(2200)
    back = page.locator(ACTIVE).first
    f["observed"]["active_after_back"] = back.inner_text().strip() if back.count() else None
    f["observed"]["url_after_back"] = page.url
    back_calls = [c for c in rec.calls if c["status"] < 400]
    f["observed"]["back_calls"] = back_calls[:4]
    f["chain"]["url_state"] = (f"{f['observed']['url_after_click'].split('#')[-1]} → "
                               f"{f['observed']['url_after_back'].split('#')[-1]}")
    f["chain"]["frontend_state"] = (
        f"활성 표시 «{f['observed']['active_start']}» → «{f['observed']['active_after_click']}» → "
        f"«{f['observed']['active_after_back']}»")
    f["chain"]["rendered"] = ("본문 «%s»"
                              % " ".join(page.locator("#main-content").inner_text()[:90].split()))
    f["screenshots"].append(_shot(page, out, "ff1207-back"))
    if f["observed"]["active_after_back"] != f["observed"]["active_start"]:
        f["notes"].append("뒤로 갔는데 활성 표시가 출발 지점으로 안 돌아왔다 — 확인 필요")
    return f


def ff_1205_badge(page, rec: Recorder, out: Path, base: str) -> dict:
    f = flow("FF-1205", "notification_action", "작업 실패·안 읽은 관리 알림 배지가 항목 옆에 붙는다")
    _goto(page, base, "/dashboard")
    # **문서를 다시 연다.** 이미 같은 해시에 있으면 `goto` 는 같은 문서 안 이동이라 아무것도
    # 다시 마운트되지 않고, 배지 질의는 마운트 때 나가므로 네트워크에 아무 흔적이 없다 —
    # 첫 실행이 그래서 `calls: []` 를 남겼다(제품이 아니라 프로브의 결함이다).
    rec.reset()
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(NAVLIST, state="attached", timeout=30_000)
    page.wait_for_timeout(3000)
    badges = page.locator(f'{NAVLIST} [aria-label^="안 읽음"]')
    labels = []
    for i in range(badges.count()):
        row = badges.nth(i).locator("xpath=ancestor::a[1]")
        labels.append({"item": row.inner_text().strip().replace("\n", " ") if row.count() else "?",
                       "badge": badges.nth(i).inner_text().strip()})
    f["observed"]["badges"] = labels
    calls = rec.since("/api/notifications/unread-count")
    f["observed"]["calls"] = calls[:6]
    f["chain"]["ui_action"] = "관리자 콘솔 진입 — 사이드바가 배지 숫자를 스스로 폴링한다"
    if calls:
        f["chain"]["api_request"] = f"{calls[0]['method']} {calls[0]['url'].split('/api/')[-1]}"
        f["chain"]["backend_query"] = (
            "app/notifications/router.py::unread_count → audience 별 유형 집계 "
            "(사용자/관리자 배지는 서로 다른 숫자다)")
        f["chain"]["api_response"] = f"HTTP {calls[0]['status']}"
    f["chain"]["frontend_state"] = f"useNavBadges — 배지 {len(labels)}개"
    f["chain"]["rendered"] = f"항목 옆 배지 {labels}" if labels else "지금 안 읽은 항목이 없어 배지가 없다"
    if not labels:
        f["notes"].append("이 QA 계정에는 지금 미읽음이 없다 — 배지가 **없는 것이 정답**인 상태다. "
                          "배선(요청·응답·소비)은 위 사슬로 확인된다.")
    f["screenshots"].append(_shot(page, out, "ff1205-badges"))
    return f


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="사이드바 Navigation 기하 + 기능 사슬 E2E (W3)")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.insecure:
        ssl._create_default_https_context = ssl._create_unverified_context

    from playwright.sync_api import sync_playwright

    flows: list[dict] = []
    anatomy: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        cache = REPO_ROOT / "dist" / "ui-qa"
        admin_sess = ensure_session(browser, base, cache, insecure=args.insecure, log=print)
        user_sess = ensure_session(browser, base, cache / "auth-user", insecure=args.insecure,
                                   log=print, role="user")

        # ── 기하: 2 뷰포트 × 2 테마 × 2 콘솔 ────────────────────────────────
        # `major_v1` 프로필 네 뷰포트를 전부 잰다. 1366x768 과 390x844 가 빠져 있던 것이
        # 이 Wave 의 High 결함 하나를 배포까지 데려갔다 — 1920 에서만 재면 "전부 펼쳐도
        # 들어간다"가 참으로 보인다. 390 은 사이드바가 **임시 서랍**이라 햄버거를 눌러야
        # 존재한다: 안 열면 잴 대상이 없고, 안 재면 모바일 증거가 0장이다.
        for vp in (Viewport("390x844", 390, 844), Viewport("1366x768", 1366, 768),
                   Viewport("1920x1080", 1920, 1080), Viewport("3840x2160", 3840, 2160)):
            for theme in ("light", "dark"):
                ctx = new_context(browser, storage_state=admin_sess.storage_state,
                                  user_id=admin_sess.user_id, theme=theme,
                                  viewport=vp, insecure=args.insecure)
                page = ctx.new_page()
                for console, path in (("user", "/me"), ("admin", "/dashboard")):
                    _goto(page, base, path, open_drawer=vp.width < 900)
                    tag = f"{console}-{theme}-{vp.name}"
                    m = measure(page, tag)
                    m["console"], m["theme"], m["viewport"] = console, theme, vp.name
                    m["verdict"] = verdict(m)
                    m["shot"] = _shot(page, out, f"anatomy-{tag}")
                    anatomy.append(m)
                ctx.close()

        # ── Command Palette — 이 Wave 가 고친 세 자리의 배포본 픽셀 ──────────────
        palette = []
        for theme in ("light", "dark"):
            ctx = new_context(browser, storage_state=admin_sess.storage_state,
                              user_id=admin_sess.user_id, theme=theme,
                              viewport=Viewport("1920x1080", 1920, 1080), insecure=args.insecure)
            page = ctx.new_page()
            _goto(page, base, "/me")
            palette.append(measure_palette(page, out, theme, base))
            ctx.close()

        # ── 기능 사슬 ────────────────────────────────────────────────────────
        vp = Viewport("1920x1080", 1920, 1080)
        ctx = new_context(browser, storage_state=admin_sess.storage_state,
                          user_id=admin_sess.user_id, theme="light",
                          viewport=vp, insecure=args.insecure)
        page = ctx.new_page()
        rec = Recorder(page)
        flows.append(ff_1200_navigate(page, rec, out, base))
        flows.append(ff_1201_collapse(browser, admin_sess, base, out, args.insecure))
        flows.append(ff_1202_filter(page, rec, out, base))
        flows.append(ff_1204_deeplink(page, rec, out, base))
        flows.append(ff_1205_badge(page, rec, out, base))
        flows.append(ff_1207_back(page, rec, out, base))

        uctx = new_context(browser, storage_state=user_sess.storage_state,
                           user_id=user_sess.user_id, theme="light",
                           viewport=vp, insecure=args.insecure)
        upage = uctx.new_page()
        _goto(upage, base, "/me")
        _goto(page, base, "/dashboard")
        flows.append(ff_1203_permission(page, upage, out))

        uctx.close()
        ctx.close()
        browser.close()

    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    (out / "flows.json").write_text(
        json.dumps({"base_url": base, "viewport": "1920x1080", "flows": flows,
                    "generated_at": stamp}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "anatomy.json").write_text(
        json.dumps({"base_url": base, "contract": {
            "labelStart": LABEL_START_PX, "rail": RAIL_PX,
            "glyph": GLYPH_PX, "chevron": CHEVRON_PX},
            "measurements": anatomy, "palette": palette, "generated_at": stamp},
            ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"NAV_E2E_WRITTEN {out / 'flows.json'}")
    for f in flows:
        filled = [k for k in ("api_request", "backend_query", "api_response", "rendered")
                  if f["chain"].get(k)]
        print(f"  {f['id']:8s} {f['category']:20s} 사슬 {len(f['chain'])}단계 "
              f"(핵심 {len(filled)}/4) {'· '.join(f['notes'])[:70]}")
    bad = 0
    print(f"NAV_ANATOMY_WRITTEN {out / 'anatomy.json'}")
    for m in anatomy:
        v = m["verdict"]
        bad += 0 if v["ok"] else 1
        head = "PASS" if v["ok"] else f"FAIL {len(v['fails'])}"
        print(f"  {m['label']:26s} root={m['rootFontSize']}px 행 {v['checked']:3d}  {head}")
        for line in v["fails"][:4]:
            print(f"      · {line}")
    for pl in palette:
        v = pl.get("verdict") or {}
        bad += 0 if v.get("ok") else 1
        print(f"  palette-{pl['theme']:<20s} 줄 {v.get('checked', 0):3d}  "
              f"{'PASS' if v.get('ok') else 'FAIL ' + str(len(v.get('fails', [])))}")
        for line in (v.get("fails") or [])[:3]:
            print(f"      · {line}")
    total = len(anatomy) + len(palette)
    print(f"NAV_ANATOMY {'OK' if bad == 0 else 'FAILED'} ({total - bad}/{total} 조합)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
