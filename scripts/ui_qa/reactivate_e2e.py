"""같은 메뉴를 두 번 누르면 「500」 화면이 선다 — 그 예외를 재현해 스택까지 잡는 하네스 (P0).

## 왜 필요한가

사용자가 작업 보드 메뉴를 빠르게 두 번 누르면 「500」 팻말을 든 클로비가 선다고 알렸다. 서버 기록(14일치
nginx · 앱 journal)에는 `/api/work/*` 5xx 가 한 건도 없고, 재현 흔적의 응답은 전부 200 이었다. 그 그림은
`ui/kit.jsx::ErrorState` 가 401 · 403 · 404 · 오프라인이 아닌 모든 실패에 쓰는 `serverError` 이고, 렌더 예외
폴백(`AppShell.jsx::ShellErrorFallback`)도 같은 그림을 쓴다. 그러니 그 화면은 **프런트의 렌더 예외**일 가능성이
가장 크다. 코드 읽기로 확정한 결함은 둘이다.

1. 활성 항목을 다시 누르면 질의 없는 주소로 이동하는데 화면은 다시 마운트되지 않는다. 팀 자동 선택은 다시
   돌지만 회차 자동 선택은 다시 무장되지 않아, 두 번 누른 끝 상태가 한 번 누른 끝 상태와 다르다.
2. 목록이 한 화면에 안 들어가는 폭에서는 활성 그룹만 강제로 펴진다. 다른 그룹의 항목을 누르면 방금까지
   활성이던 그룹이 약 300ms 에 걸쳐 접히며 아래 줄이 올라가고, 더블클릭의 둘째 클릭이 다른 자리에 떨어진다.

던지는 줄은 코드 읽기로 못 짚었다. 이 하네스가 그 줄을 재현하고 스택을 남긴다. 처음 잡은 것은 작업 보드의
회차 없는 판이었다 — 끌기 판에 `disabled={null}` 이 넘어가 dnd-kit `SortableContext` 가 `null.draggable` 을 읽었다
(두 브라우저 모두 같은 자리, 커밋 47cc6b33 이 고쳤다).

## 무엇을 재는가

두 콘솔 × 뷰포트 × 브라우저(Chromium · Firefox — 재현 흔적을 남긴 브라우저가 Firefox 다) × **사이드바의 모든
항목**(렌더된 DOM 에서 읽는다). 항목마다 한 번 누른 끝 상태(해시+질의 · `h1` · `aria-current`)를 기준으로
삼고 네 가지 두 번 누르기를 견준다.

- `dblclick` — 항목에 dblclick 을 보낸다.
- `mouse2` — 같은 좌표를 0 · 50 · 150 · 400ms 간격으로 두 번 누른다. 목록이 밀리면 둘째 클릭이 다른 자리에 떨어진다.
- `element2` — 같은 요소를 같은 간격으로 두 번 누른다. 요소가 움직여도 따라가므로 「같은 대상 재활성화」만 남는다.
- `settled2` — 화면이 선 뒤 다시 누른다. 작업 보드의 실제 재현 흔적이 이 모양이다.

`mouse2` 와 `element2` 를 갈라야 「밀림」과 「같은 대상 재활성화」가 구분된다. `--stress` 는 다섯 모양을 더 돈다.
화면이 설 때마다 다섯 번 다시 누르고, 질의 캐시가 낡은 뒤(31초) 다시 누르고, 요청이 오가는 중에 다시 누르고,
탭을 오가거나 본문을 굴린 뒤 다시 누른다.

실패로 세는 것은 폴백(문구 · `[ErrorBoundary]` 콘솔 줄 · `[data-error-boundary]`) · `pageerror` · 기대 밖
`console.error`(D-494 의 `Route.expected_console`) · 응답 ≥ 500 · 끝 상태 ≠ 기준 · 첫 클릭 뒤 0~500ms 동안 누른
자리의 항목이 바뀜(`mouse2`) · 사이드바를 눌렀는데 문서가 새로 열림이다. 429 는 따로 센다.

## 쓰는 법

    python -m scripts.ui_qa.reactivate_e2e --selftest                 # 합성 페이지 반례(Chromium · Firefox)
    python -m scripts.ui_qa.reactivate_e2e --selftest --logic-only    # 판정 규칙 반례(브라우저 없이)
    python -m scripts.ui_qa.local_capture --harness reactivate_e2e    # 로컬 서버에 대고 전 행렬
    python -m scripts.ui_qa.local_capture --harness reactivate_e2e \\
        --console user --browsers firefox --routes work-board sprint --stress
    python -m scripts.ui_qa.reactivate_e2e --summary                  # 조각만 다시 합쳐 요약을 찍는다

`--routes` 는 항목 주소나 이름의 일부다. 빗금으로 시작하게 적지 않는다 — Git Bash 가 `/approvals` 를
`C:/Program Files/Git/approvals` 로 바꿔 넘겨 아무 항목도 안 고른다(그러면 실행은 「못 돈 조합」으로 끝난다).

산출물은 `dist/ui-qa/reactivate-e2e/{runs.json,crashes.json}` 과 실패마다 한 장의 스크린샷(`shots/`)이다. 한 번의
실행은 `parts/` 에 조각을 남기고, 두 파일은 조각 전부를 합쳐 다시 쓴다. 그래서 긴 행렬을 `--console` ·
`--browsers` · `--routes` 로 나눠 돌려도 결과가 한 벌로 모인다(`--fresh` 는 옛 조각을 지운다).
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 요약을 한국어로 찍는데 Windows 기본 콘솔은 cp949 다. 여기서 막히면 결과 파일은 이미 다 썼는데 실행이 실패로
# 보인다 — 다른 하네스와 같이 처리한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from scripts.ui_qa import capture as cap  # noqa: E402
from scripts.ui_qa import tls  # noqa: E402
from scripts.ui_qa.nav_e2e import NAVLIST  # noqa: E402
from scripts.ui_qa.routes import (  # noqa: E402
    ADMIN_ROUTES, ADMIN_SHELL, BY_ID, USER_ROUTES, USER_SHELL,
)

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "reactivate-e2e"
ASSETS_DIR = REPO_ROOT / "app" / "static" / "react" / "assets"

# 폴백을 알아보는 세 표식. 문구는 `AppShell.jsx::ShellErrorFallback`, 콘솔 줄은 `App.jsx::ErrorBoundary`
# 의 `componentDidCatch` 가 남긴다. 셋째 표식은 뒤 묶음(P4)이 폴백에 달 속성이라 지금은 없어도 된다.
FALLBACK_TEXT = "화면을 표시하는 중 문제가 발생했습니다"
BOUNDARY_PREFIX = "[ErrorBoundary]"
FALLBACK_MARK = "[data-error-boundary]"

START_PATH = {"user": "/me", "admin": "/dashboard"}
SHELL = {"user": USER_SHELL, "admin": ADMIN_SHELL}

SAMPLE_AT_MS = (0, 50, 150, 300, 500)
DOUBLE_DELAYS_MS = (0, 50, 150, 400)
GROUP_OPEN_WAIT_MS = 400
SETTLE_MS = 1500
START_SETTLE_MS = 300
QUIET_MS = 500
QUIET_CAP_MS = 10_000
STALE_REQUEST_S = 12.0
SETTLE_ROUNDS = 3
CLICK_TIMEOUT_MS = 8_000
INFLIGHT_CAP_MS = 3_000
# 질의 캐시가 낡는 시간(`frontend/src/main.jsx` 의 `staleTime: 30 * 1000`) + 1초. 재현 흔적에는 재클릭 뒤
# `GET /api/work/sprints`(팀 없음)가 찍혀 있다 — 캐시가 아직 싱싱하면 그 요청이 안 나가므로, 사람이 판을
# 한참 보다가 다시 누른 모양은 이만큼 기다려야 선다.
STALE_WAIT_MS = 31_000

DEFAULT_VIEWPORTS = ("1920x1080", "1366x768")
DEFAULT_BROWSERS = ("chromium", "firefox")
DOUBLE_MODES = ("dblclick", "mouse2", "element2", "settled2")
STRESS_MODES = ("settled5", "stale2", "inflight", "tabs", "scrolled")
ALL_MODES = ("baseline",) + DOUBLE_MODES + STRESS_MODES

MODE_LABEL = {
    "baseline": "한 번 누름(기준)",
    "dblclick": "dblclick",
    "mouse2": "같은 좌표 두 번",
    "element2": "같은 요소 두 번",
    "settled2": "선 뒤 다시 누름",
    "settled5": "선 뒤 다시 누름 ×5",
    "stale2": "캐시가 낡은 뒤 다시 누름",
    "inflight": "요청 중 다시 누름",
    "tabs": "탭 오간 뒤 다시 누름",
    "scrolled": "굴린 뒤 다시 누름",
}

# 「요청이 오가는 중」에 다시 누를 때 기다리는 요청. 작업 보드 · 스프린트 회의는 자동 선택이 두 단계라
# 앞 요청(회차 목록)과 뒤 요청(판 · 회의) 각각의 도중을 따로 본다. 나머지 화면은 첫 API 요청의 도중이다.
INFLIGHT_TARGETS = {
    "/work-board": ("/api/work/sprints", "/api/work/board"),
    "/sprint": ("/api/work/sprints", "/meeting"),
}

FAIL_TYPES = ("crash", "pageerror", "console", "http5xx", "state", "pointer", "reload", "start", "harness")
FAIL_LABEL = {
    "crash": "폴백", "pageerror": "페이지오류", "console": "콘솔", "http5xx": "5xx", "state": "상태",
    "pointer": "포인터", "reload": "새로고침", "start": "시작화면", "harness": "하네스", "http429": "429",
}
STATE_KEYS = ("href", "h1", "current")

# 원격 설치처를 겨누면 로컬 번들이 화면에 있던 번들이 아닐 수 있다. 그때는 스택 줄의 코드 발췌를 안 붙인다.
_EXCERPT_FROM_LOCAL = True


class HarnessError(RuntimeError):
    """제품이 아니라 하네스가 이 실행을 끝까지 몰지 못했다 — 결과에 「하네스」로 남고 통과로 세지 않는다."""


# --------------------------------------------------------------------------- #
# 페이지 안에서 도는 조각
# --------------------------------------------------------------------------- #
# 문서마다 제일 먼저 도는 관찰자다. 경계가 남기는 `[ErrorBoundary]` 줄의 **인자 자체**(오류 객체와 컴포넌트
# 스택)를 받아 둔다 — Playwright 의 콘솔 이벤트는 인자를 글자로 바꾸는 방식이 브라우저마다 달라 Firefox 에서는
# 스택이 빠질 수 있다. 폴백이 선 순간도 적는다. 둘째 클릭이 다른 항목으로 가면 경계가 경로 키로 리셋돼 폴백이
# 사라지므로, 끝 화면만 보면 방금 난 예외를 놓친다.
INIT_JS = r"""
(() => {
  if (window.__rxCrash) return;
  const cfg = __RX_CFG__;
  const crash = { boundary: [], errors: [], fallback: [], urls: [] };
  window.__rxCrash = crash;
  const now = () => Math.round(performance.now());
  // 주소가 언제 어떻게 바뀌었는지(push · replace · 뒤로) — 끝 상태가 갈렸을 때 자동 선택이 돌았는지, 둘째 클릭이
  // 그것을 지웠는지를 이 줄이 말한다.
  for (const how of ['pushState', 'replaceState']) {
    const original = history[how];
    history[how] = function rxHistory(...args) {
      const out = original.apply(this, args);
      try { crash.urls.push({ t: now(), how: how === 'pushState' ? 'push' : 'replace', href: location.href }); }
      catch (e) { /* 관찰이 제품 동작을 바꾸면 안 된다 */ }
      return out;
    };
  }
  window.addEventListener('popstate', () => crash.urls.push({ t: now(), how: 'pop', href: location.href }));
  const describe = (v) => {
    try {
      if (v && typeof v === 'object' && 'message' in v && 'stack' in v) {
        return { kind: 'error', name: String(v.name || ''), message: String(v.message || ''),
                 stack: String(v.stack || '').slice(0, 12000) };
      }
      if (typeof v === 'string') return { kind: 'string', text: v.slice(0, 12000) };
      return { kind: typeof v, text: String(v).slice(0, 2000) };
    } catch (e) {
      return { kind: 'unreadable' };
    }
  };
  const original = console.error;
  console.error = function rxConsoleError(...args) {
    try {
      if (typeof args[0] === 'string' && args[0].indexOf(cfg.prefix) === 0) {
        crash.boundary.push({ t: now(), href: location.href, args: args.slice(1).map(describe) });
      }
    } catch (e) { /* 관찰이 제품 동작을 바꾸면 안 된다 */ }
    return original.apply(this, args);
  };
  window.addEventListener('error', (ev) => {
    crash.errors.push({ t: now(), href: location.href, kind: 'error', message: String(ev.message || ''),
      source: String(ev.filename || ''), line: ev.lineno || 0, col: ev.colno || 0,
      stack: ev.error && ev.error.stack ? String(ev.error.stack).slice(0, 12000) : '' });
  });
  window.addEventListener('unhandledrejection', (ev) => {
    const r = ev.reason;
    crash.errors.push({ t: now(), href: location.href, kind: 'rejection',
      message: r && r.message ? String(r.message) : String(r),
      stack: r && r.stack ? String(r.stack).slice(0, 12000) : '' });
  });
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const fallbackNow = () => {
    if (document.querySelector(cfg.mark)) return 'mark';
    for (const el of document.querySelectorAll('[role="alert"]')) {
      if ((el.textContent || '').indexOf(cfg.text) >= 0 && shown(el)) return 'text';
    }
    return null;
  };
  window.__rxFallbackNow = fallbackNow;
  let queued = false;
  const check = () => {
    queued = false;
    const how = fallbackNow();
    const last = crash.fallback[crash.fallback.length - 1];
    if (how && (!last || last.gone !== null)) {
      crash.fallback.push({ t: now(), href: location.href, how, gone: null });
    } else if (!how && last && last.gone === null) {
      last.gone = now();
    }
  };
  new MutationObserver(() => {
    if (!queued) { queued = true; setTimeout(check, 0); }
  }).observe(document, { childList: true, subtree: true });
})();
"""

# 첫 클릭의 순간부터 0 · 50 · 150 · 300 · 500ms 에 **누른 자리 아래** 무엇이 있는지 페이지 안에서 잰다. 파이썬에서
# 시간을 맞춰 물으면 왕복 지연이 표본 시각을 흔든다. 클릭마다 무엇을 눌렀는지도 적는다 — 둘째 클릭이 같은
# 항목이었는지, 다른 항목이나 그룹 머리였는지가 「밀림」의 직접 증거다.
SAMPLER_JS = r"""
({ x, y, at, nav }) => {
  const text = (n) => ((n && n.textContent) || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  // 항목도 그룹 머리도 아닌 자리(그룹 사이 여백 · 목록 아래)는 글자를 안 적는다 — 감싼 상자의 글자는 목록 전체다.
  const hit = () => {
    const el = document.elementFromPoint(x, y);
    const a = el && el.closest ? el.closest('a[href]') : null;
    const g = !a && el && el.closest ? el.closest('[aria-expanded]') : null;
    return { href: a ? a.getAttribute('href') : null, groupHeader: !!g,
             text: a || g ? text(a || g) : '', tag: el ? el.tagName.toLowerCase() : null };
  };
  const rx = { x, y, clickAt: null, samples: [], clicks: [] };
  window.__rx = rx;
  // 레일은 목록을 감싼 서랍 판 전체다 — 목록 아래 빈 자리에 떨어진 클릭도 「사이드바에 떨어진 클릭」이다.
  const navRoot = document.querySelector(nav);
  const rail = navRoot ? (navRoot.closest('.MuiDrawer-paper') || navRoot) : null;
  document.addEventListener('click', (ev) => {
    const t = performance.now();
    const target = ev.target && ev.target.closest ? ev.target : null;
    const a = target ? target.closest('a[href]') : null;
    const g = !a && target ? target.closest('[aria-expanded]') : null;
    rx.clicks.push({ t: rx.clickAt === null ? 0 : Math.round(t - rx.clickAt), detail: ev.detail,
      x: Math.round(ev.clientX), y: Math.round(ev.clientY),
      inRail: !!(rail && target && rail.contains(target)),
      href: a ? a.getAttribute('href') : null, groupHeader: !!g, text: a || g ? text(a || g) : '',
      tag: target ? target.tagName.toLowerCase() : null });
    if (rx.clickAt !== null) return;
    rx.clickAt = t;
    for (const d of at) {
      setTimeout(() => rx.samples.push(Object.assign(
        { at: d, t: Math.round(performance.now() - rx.clickAt) }, hit())), d);
    }
  }, true);
  return { hit: hit(), now: performance.now() };
}
"""

# 끝 상태. `page.url` 은 같은 문서 안의 `history.replaceState`(자동 선택의 주소 고쳐 쓰기)를 한 박자 늦게 본다 —
# 주소는 페이지 안에서 읽는다.
STATE_JS = r"""
(nav) => {
  const shown = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  const heads = (root) => [...root.querySelectorAll('h1')].filter(shown)
    .map((h) => (h.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
  const main = document.getElementById('main-content');
  let h1 = main ? heads(main) : [];
  if (!h1.length) h1 = heads(document);
  const current = [...document.querySelectorAll(nav + ' [aria-current="page"]')]
    .map((a) => a.getAttribute('href') || '').filter(Boolean);
  return { href: location.href, hash: location.hash, h1: h1.join(' | '), current: current.join(' '),
           fallback: window.__rxFallbackNow ? window.__rxFallbackNow() : null, title: document.title };
}
"""

# 사이드바 항목 전부. 접힌 그룹의 항목도 DOM 에 있다(`Collapse unmountOnExit={false}`). 그룹 이름은 항목을 감싼
# Collapse 의 id 를 가리키는 머리(`aria-controls`)에서 읽는다.
ITEMS_JS = r"""
(nav) => {
  const text = (n) => ((n && n.textContent) || '').replace(/\s+/g, ' ').trim();
  const headers = [...document.querySelectorAll(nav + ' [aria-controls]')];
  return [...document.querySelectorAll(nav + ' a[href]')].map((a) => {
    const col = a.closest('.MuiCollapse-root');
    const header = col ? headers.find((h) => h.getAttribute('aria-controls') === col.id) : null;
    const label = a.querySelector('.MuiListItemText-primary');
    return { href: a.getAttribute('href') || '', label: text(label || a),
             group: header ? text(header) : '', groupId: col ? col.id : '' };
  });
}
"""

GROUP_STATE_JS = r"""
({ nav, href }) => {
  const a = [...document.querySelectorAll(nav + ' a[href]')].find((el) => el.getAttribute('href') === href);
  if (!a) return { found: false };
  const col = a.closest('.MuiCollapse-root');
  if (!col) return { found: true, collapsed: false, groupId: '' };
  const header = [...document.querySelectorAll(nav + ' [aria-controls]')]
    .find((h) => h.getAttribute('aria-controls') === col.id);
  return { found: true, groupId: col.id, collapsed: col.getBoundingClientRect().height < 1,
           expanded: header ? header.getAttribute('aria-expanded') : null };
}
"""

INPAGE_JS = "() => ({ rx: window.__rx || null, crash: window.__rxCrash || null })"

# 다시 누르기 전에 화면 제목 노드에 표를 달아 둔다. 다시 누른 뒤 그 표가 없으면 화면이 새로 마운트된 것이다(새 진입).
# 표가 그대로면 같은 화면 인스턴스가 질의만 바뀐 주소를 받았다 — 「진입 때 한 번」 상태가 되살지 않는 모양이다.
MARK_JS = r"""
() => {
  const main = document.getElementById('main-content');
  const h = main && [...main.querySelectorAll('h1')].find((el) => el.getBoundingClientRect().height > 0);
  if (!h) return false;
  h.setAttribute('data-rx-mark', '1');
  return true;
}
"""
REMOUNT_JS = "() => !document.querySelector('[data-rx-mark]')"

# 본문의 굴릴 수 있는 상자를 전부 끝까지 굴린다(칸반 열 · 백로그 표 · 창).
SCROLL_JS = r"""
() => {
  const main = document.getElementById('main-content') || document.body;
  let moved = 0;
  for (const el of [main, ...main.querySelectorAll('*')]) {
    if (el.scrollHeight <= el.clientHeight + 4 && el.scrollWidth <= el.clientWidth + 4) continue;
    const cs = getComputedStyle(el);
    if (!/(auto|scroll)/.test(cs.overflowY + ' ' + cs.overflowX)) continue;
    el.scrollTop = el.scrollHeight;
    el.scrollLeft = el.scrollWidth;
    moved += 1;
  }
  window.scrollTo(0, document.documentElement.scrollHeight);
  return moved;
}
"""


def init_script() -> str:
    return INIT_JS.replace("__RX_CFG__", json.dumps(
        {"text": FALLBACK_TEXT, "prefix": BOUNDARY_PREFIX, "mark": FALLBACK_MARK}, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# 자료
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Item:
    href: str
    label: str
    group: str = ""
    group_id: str = ""

    @property
    def path(self) -> str:
        raw = self.href[1:] if self.href.startswith("#") else self.href
        return raw.split("?", 1)[0]


@dataclass(frozen=True)
class RunCfg:
    console: str
    browser: str
    browser_version: str
    viewport: str
    role: str
    start_url: str
    settle_ms: int = SETTLE_MS
    start_settle_ms: int = START_SETTLE_MS


_ROUTES_BY_PATH = {
    **{("user", r.hash_path): r for r in USER_ROUTES if not r.is_detail},
    **{("admin", r.hash_path): r for r in ADMIN_ROUTES if not r.is_detail},
}


def route_for(console: str, path: str):
    """사이드바 항목 → 하네스 라우트 표의 그 화면. D-494 의 기대 콘솔 줄이 거기 있다."""
    return _ROUTES_BY_PATH.get((console, path))


def split_console(route, messages: list[str]) -> tuple[list[str], list[str]]:
    """(이 화면이 일부러 내는 줄, 판정에 세는 줄). 라우트 표에 없는 화면은 전부 센다."""
    if route is None:
        return [], list(messages)
    return cap.split_expected_console(route, messages)


def run_key(cfg: RunCfg, item: Item, mode: str, param, rep: int) -> str:
    return "|".join([cfg.console, cfg.role, cfg.browser, cfg.viewport, item.href, mode,
                     "" if param is None else str(param), str(rep)])


def _ms_since(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- #
# 관찰
# --------------------------------------------------------------------------- #
class Observer:
    """한 페이지에서 오간 것 — 콘솔 오류 · 잡히지 않은 예외 · 400 이상 응답 · 진행 중인 요청 · 문서 이동.

    진행 중인 요청을 직접 센다. `wait_for_load_state("networkidle")` 는 문서마다 한 번만 서는 신호라, SPA 안에서
    이동한 뒤에는 새 요청이 날아가는 중에도 곧바로 돌아온다.
    """

    IGNORED_TYPES = frozenset({"websocket", "eventsource", "manifest"})

    def __init__(self, page) -> None:
        self.page = page
        self.inflight: dict[int, tuple[object, float]] = {}
        self.last_activity = time.monotonic()
        self.watch: tuple[str, ...] = ()
        self.reset()
        page.on("console", self._on_console)
        page.on("pageerror", self._on_pageerror)
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_finished)
        page.on("requestfailed", self._on_failed)
        page.on("response", self._on_response)

    def reset(self) -> None:
        self.t0 = time.monotonic()
        self.console: list[dict] = []
        self.page_errors: list[dict] = []
        self.responses: list[dict] = []
        self.failed: list[dict] = []
        self.documents: list[dict] = []
        self.watched: list[dict] = []

    def take(self) -> dict:
        got = {"console": self.console, "page_errors": self.page_errors, "responses": self.responses,
               "failed": self.failed, "documents": self.documents, "watched": self.watched}
        self.reset()
        return got

    def ms(self) -> int:
        return _ms_since(self.t0)

    def busy(self) -> bool:
        """오래 매달린 요청(`STALE_REQUEST_S`)은 조용함을 막지 않는다 — 기록만 남는다."""
        now = time.monotonic()
        return any(now - started < STALE_REQUEST_S for _, started in self.inflight.values())

    def _on_console(self, msg) -> None:
        try:
            if msg.type != "error":
                return
            loc = msg.location or {}
            self.console.append({"t": self.ms(), "text": msg.text, "url": loc.get("url", ""),
                                 "line": loc.get("lineNumber"), "col": loc.get("columnNumber")})
        except Exception:  # noqa: BLE001 — 관찰이 실행을 죽이면 안 된다
            pass

    def _on_pageerror(self, err) -> None:
        self.page_errors.append({"t": self.ms(), "name": getattr(err, "name", "") or "",
                                 "message": getattr(err, "message", "") or str(err),
                                 "stack": getattr(err, "stack", "") or ""})

    def _on_request(self, req) -> None:
        self.last_activity = time.monotonic()
        try:
            if req.is_navigation_request() and req.frame == self.page.main_frame:
                self.documents.append({"t": self.ms(), "url": req.url})
            if req.resource_type in self.IGNORED_TYPES:
                return
            self.inflight[id(req)] = (req, time.monotonic())
            if self.watch and any(frag in req.url for frag in self.watch):
                self.watched.append({"t": self.ms(), "url": req.url, "done": None})
        except Exception:  # noqa: BLE001
            pass

    def _done(self, req) -> None:
        self.last_activity = time.monotonic()
        self.inflight.pop(id(req), None)
        for w in self.watched:
            if w["done"] is None and w["url"] == req.url:
                w["done"] = self.ms()
                break

    def _on_finished(self, req) -> None:
        self._done(req)

    def _on_failed(self, req) -> None:
        self._done(req)
        try:
            self.failed.append({"t": self.ms(), "url": req.url, "type": req.resource_type,
                                "failure": req.failure})
        except Exception:  # noqa: BLE001
            pass

    def _on_response(self, resp) -> None:
        try:
            if resp.status >= 400:
                self.responses.append({"t": self.ms(), "status": resp.status, "url": resp.url,
                                       "method": resp.request.method})
        except Exception:  # noqa: BLE001
            pass


def _href(page) -> str:
    try:
        return page.evaluate("() => location.href")
    except Exception:  # noqa: BLE001 — 문서가 바뀌는 중이면 빈 값으로 한 번 넘긴다
        return ""


def read_state(page) -> dict:
    return page.evaluate(STATE_JS, NAVLIST)


def quiet(page, obs: Observer, *, idle_ms: int = QUIET_MS, cap_ms: int = QUIET_CAP_MS) -> bool:
    """진행 중인 요청이 없고 `idle_ms` 동안 새 요청도 없을 때까지 기다린다. 끝내 안 조용하면 False 다."""
    deadline = time.monotonic() + cap_ms / 1000
    while time.monotonic() < deadline:
        page.wait_for_timeout(50)
        if not obs.busy() and (time.monotonic() - obs.last_activity) * 1000 >= idle_ms:
            return True
    return False


def settle(page, obs: Observer, *, settle_ms: int) -> dict:
    """요청이 멎고 주소가 `settle_ms` 동안 그대로일 때 화면이 섰다고 본다. 자동 선택이 주소를 고쳐 쓰기 때문이다."""
    t0 = time.monotonic()
    calm = False
    for rounds in range(1, SETTLE_ROUNDS + 1):
        calm = quiet(page, obs)
        before = _href(page)
        page.wait_for_timeout(settle_ms)
        if _href(page) == before:
            return {"rounds": rounds, "quiet": calm, "ms": _ms_since(t0)}
    return {"rounds": SETTLE_ROUNDS, "quiet": calm, "ms": _ms_since(t0), "unstable": True}


def wait_inflight(page, obs: Observer, *, cap_ms: int) -> dict:
    """지켜보는 요청이 날아가기 시작할 때까지 기다린다. 이미 끝났으면 그 사실을 적고 그대로 누른다."""
    deadline = time.monotonic() + cap_ms / 1000
    while time.monotonic() < deadline:
        if obs.watched:
            open_ = [w for w in obs.watched if w["done"] is None]
            first = (open_ or obs.watched)[0]
            return {"seen": True, "open_at_check": bool(open_), "url": first["url"], "clicked_at": obs.ms()}
        page.wait_for_timeout(5)
    return {"seen": False, "open_at_check": False, "url": None, "clicked_at": obs.ms()}


def enumerate_items(page, obs: Observer, start_url: str) -> list[Item]:
    page.goto("about:blank", wait_until="domcontentloaded", timeout=30_000)
    page.goto(start_url, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_selector(f"{NAVLIST} a[href]", state="attached", timeout=30_000)
    quiet(page, obs)
    rows = page.evaluate(ITEMS_JS, NAVLIST)
    obs.take()
    seen: set[str] = set()
    items: list[Item] = []
    for row in rows:
        href = row.get("href") or ""
        if not href.startswith("#/") or href in seen:
            continue
        seen.add(href)
        items.append(Item(href=href, label=row.get("label") or href, group=row.get("group") or "",
                          group_id=row.get("groupId") or ""))
    return items


# --------------------------------------------------------------------------- #
# 한 번의 실행
# --------------------------------------------------------------------------- #
def perform(page, obs: Observer, cfg: RunCfg, mode: str, param, link, x: int, y: int, rec: dict) -> None:
    if mode == "baseline":
        page.mouse.click(x, y)
    elif mode == "dblclick":
        link.dblclick(timeout=CLICK_TIMEOUT_MS)
    elif mode == "mouse2":
        page.mouse.click(x, y)
        if param:
            page.wait_for_timeout(param)
        page.mouse.click(x, y)
    elif mode == "element2":
        handle = link.element_handle(timeout=CLICK_TIMEOUT_MS)
        handle.click(timeout=CLICK_TIMEOUT_MS)
        if param:
            page.wait_for_timeout(param)
        try:
            handle.click(timeout=CLICK_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001 — 핸들이 끊기면 같은 항목을 다시 찾아 누르고 그 사실을 적는다
            rec["notes"].append("둘째 클릭에서 요소 핸들이 끊겨 같은 항목을 다시 찾아 눌렀다: %s" % str(exc)[:160])
            link.click(timeout=CLICK_TIMEOUT_MS)
    elif mode in ("settled2", "settled5"):
        link.click(timeout=CLICK_TIMEOUT_MS)
        rec["between"] = []
        for i in range(1 if mode == "settled2" else 5):
            rec["between"].append({"settle": settle(page, obs, settle_ms=cfg.settle_ms),
                                   "state": read_state(page)})
            if i == 0:
                rec["marked"] = page.evaluate(MARK_JS)
            link.click(timeout=CLICK_TIMEOUT_MS)
    elif mode == "stale2":
        link.click(timeout=CLICK_TIMEOUT_MS)
        rec["between"] = [{"settle": settle(page, obs, settle_ms=cfg.settle_ms), "state": read_state(page)}]
        page.wait_for_timeout(STALE_WAIT_MS)
        rec["marked"] = page.evaluate(MARK_JS)
        link.click(timeout=CLICK_TIMEOUT_MS)
    elif mode == "inflight":
        link.click(timeout=CLICK_TIMEOUT_MS)
        rec["inflight"] = wait_inflight(page, obs, cap_ms=INFLIGHT_CAP_MS)
        link.click(timeout=CLICK_TIMEOUT_MS)
    elif mode == "tabs":
        link.click(timeout=CLICK_TIMEOUT_MS)
        rec["between"] = [{"settle": settle(page, obs, settle_ms=cfg.settle_ms), "state": read_state(page)}]
        tabs = page.locator("#main-content [role='tab']")
        if tabs.count() < 2:
            rec["notes"].append("본문에 탭이 둘 이상 없어 탭 오가기를 건너뛰었다")
        else:
            for idx in (1, 0):
                tabs.nth(idx).click(timeout=CLICK_TIMEOUT_MS)
                rec["between"].append({"tab": idx, "settle": settle(page, obs, settle_ms=cfg.settle_ms),
                                       "state": read_state(page)})
        rec["marked"] = page.evaluate(MARK_JS)
        link.click(timeout=CLICK_TIMEOUT_MS)
    elif mode == "scrolled":
        link.click(timeout=CLICK_TIMEOUT_MS)
        rec["between"] = [{"settle": settle(page, obs, settle_ms=cfg.settle_ms), "state": read_state(page)}]
        rec["scrolled_boxes"] = page.evaluate(SCROLL_JS)
        page.wait_for_timeout(400)
        rec["marked"] = page.evaluate(MARK_JS)
        link.click(timeout=CLICK_TIMEOUT_MS)
    else:
        raise HarnessError("모르는 방식이다: %s" % mode)


def collect(page, obs: Observer, rec: dict, since) -> None:
    """페이지 안 기록과 이벤트를 실행 기록에 옮긴다. `since` 는 첫 클릭 직전의 페이지 시각(ms)이다."""
    try:
        inpage = page.evaluate(INPAGE_JS) or {}
    except Exception:  # noqa: BLE001 — 페이지가 망가져 못 읽어도 파이썬 쪽 이벤트는 남는다
        inpage = {}
    cut = since if since is not None else float("inf")
    crash = inpage.get("crash") or {}
    rx = inpage.get("rx") or {}

    def split(rows):
        rows = rows or []
        return [r for r in rows if (r.get("t") or 0) < cut], [r for r in rows if (r.get("t") or 0) >= cut]

    boundary_before, boundary_after = split(crash.get("boundary"))
    errors_before, errors_after = split(crash.get("errors"))
    fallback_before, fallback_after = split(crash.get("fallback"))
    # 스택 줄과 번들 발췌는 **지금** 뽑아 둔다. 조각을 나중에 합칠 때는 번들이 이미 다시 빌드돼 그 칸의 코드가
    # 없을 수 있다(실제로 그랬다 — 합치는 사이에 `app/static/react` 가 새 빌드로 바뀌었다).
    for entry in boundary_after:
        for arg in entry.get("args") or []:
            if arg.get("kind") == "error" and "frames" not in arg:
                arg["frames"] = top_frames(arg.get("stack") or "")
    start = rec.setdefault("start_events", {})
    start["boundary"] = boundary_before
    start["errors"] = errors_before
    # 누르기 전부터 서 있던 폴백은 시작 화면의 문제다(누르기 전에 사라졌으면 기록만 남긴다).
    start["fallback"] = [f for f in fallback_before if f.get("gone") is None]
    rec["crash"] = {"boundary": boundary_after, "errors": errors_after, "fallback": fallback_after}
    rec["pointer"] = {"samples": rx.get("samples") or [], "clicks": rx.get("clicks") or []}
    # 첫 클릭부터의 주소 이력과 폴백 시각. 첫 클릭의 순간을 0 으로 다시 잰다 — 클릭 기록과 같은 눈금이라
    # 「둘째 클릭이 자동 선택을 지웠다」 같은 순서를 한 줄로 읽을 수 있다.
    zero = rx.get("clickAt") if isinstance(rx.get("clickAt"), (int, float)) else cut
    rec["click_zero"] = zero if zero != float("inf") else None
    rec["url_timeline"] = [
        {"t": int(u.get("t", 0) - zero), "how": u.get("how"), "hash": _hash_of(u.get("href") or "")}
        for u in split(crash.get("urls"))[1]
    ][:40]

    events = obs.take()
    rec["console_errors"] = events["console"]
    texts = [str(c.get("text") or "") for c in events["console"] if not str(c.get("text") or "").startswith(BOUNDARY_PREFIX)]
    expected, counted = split_console(route_for(rec["console"], rec["item"]["path"]), texts)
    rec["console_expected"] = expected
    rec["console_counted"] = counted
    rec["page_errors"] = [{**e, "frames": top_frames(e.get("stack") or "")} for e in events["page_errors"]]
    responses = events["responses"]
    rec["http"] = {
        "5xx": [r for r in responses if r["status"] >= 500],
        "429": [r for r in responses if r["status"] == 429],
        "4xx": [r for r in responses if 400 <= r["status"] < 500 and r["status"] != 429][:12],
    }
    rec["request_failed"] = events["failed"][:12]
    rec["documents"] = events["documents"]
    if rec.get("inflight"):
        watched = events["watched"]
        clicked = rec["inflight"].get("clicked_at")
        first = watched[0] if watched else None
        rec["inflight"]["watched"] = watched[:6]
        rec["inflight"]["hit"] = bool(first) and clicked is not None and (
            first["done"] is None or first["done"] >= clicked)


def state_diff(base: dict, got: dict) -> list[dict]:
    return [{"key": k, "baseline": base.get(k) or "", "got": got.get(k) or ""}
            for k in STATE_KEYS if (base.get(k) or "") != (got.get(k) or "")]


def judge(run: dict, baseline: dict | None) -> tuple[list[str], list[dict], dict]:
    """실행 기록 하나 → (실패 종류, 사람이 읽는 이유, 검사별 판정). 측정과 떨어진 순수 함수다 — 브라우저 없이 반례를 돈다."""
    fails: list[str] = []
    why: list[dict] = []
    checks: dict = {}

    def add(kind: str, text: str) -> None:
        if kind not in fails:
            fails.append(kind)
        why.append({"kind": kind, "text": text})

    if run.get("harness_error"):
        add("harness", "하네스가 이 실행을 끝까지 몰지 못했다 — %s" % run["harness_error"])
    start = run.get("start_events") or {}
    if start.get("page_errors") or start.get("boundary") or start.get("fallback") \
            or (run.get("start") or {}).get("fallback"):
        add("start", "누르기 전 시작 화면에서 이미 예외가 났다")

    crash = run.get("crash") or {}
    boundary_lines = [c for c in run.get("console_errors") or []
                      if str(c.get("text") or "").startswith(BOUNDARY_PREFIX)]
    final = run.get("final") or {}
    if crash.get("boundary") or crash.get("fallback") or boundary_lines or final.get("fallback"):
        how = []
        if crash.get("boundary") or boundary_lines:
            how.append("[ErrorBoundary] 줄")
        if crash.get("fallback") or final.get("fallback"):
            how.append("폴백 화면")
        add("crash", "렌더 예외 폴백이 섰다(%s)" % " · ".join(how))
    if run.get("page_errors"):
        first = run["page_errors"][0]
        add("pageerror", "잡히지 않은 예외가 났다: %s" % (first.get("message") or "")[:160])
    if run.get("console_counted"):
        add("console", "기대 밖 console.error %d줄: %s" % (len(run["console_counted"]),
                                                       str(run["console_counted"][0])[:160]))
    http = run.get("http") or {}
    if http.get("5xx"):
        first = http["5xx"][0]
        add("http5xx", "응답 %s %s" % (first.get("status"), first.get("url")))
    if run.get("documents"):
        add("reload", "사이드바를 눌렀는데 문서가 새로 열렸다: %s" % run["documents"][0].get("url"))

    mode = run.get("mode")
    if mode == "baseline":
        checks["state"] = "baseline"
    elif run.get("harness_error"):
        checks["state"] = "skip"
    elif not baseline or baseline.get("harness_error") or not baseline.get("final"):
        checks["state"] = "skip"
        add("harness", "기준 실행의 끝 상태가 없어 견줄 수 없다")
    else:
        diffs = state_diff(baseline["final"], final)
        checks["state"] = "fail" if diffs else "pass"
        if diffs:
            run["state_diff"] = diffs
            add("state", "두 번 누른 끝 상태가 한 번 누른 끝 상태와 다르다: " + "; ".join(
                "%s %s → %s" % (d["key"], d["baseline"][-90:], d["got"][-90:]) for d in diffs))

    if mode == "mouse2" and not run.get("harness_error"):
        samples = (run.get("pointer") or {}).get("samples") or []
        want = (run.get("item") or {}).get("href")
        if len(samples) < len(SAMPLE_AT_MS):
            checks["pointer"] = "unmeasured %d/%d" % (len(samples), len(SAMPLE_AT_MS))
            add("harness", "누른 자리 표본이 모자라 밀림을 판정하지 못했다(%d/%d)" % (len(samples), len(SAMPLE_AT_MS)))
        else:
            off = [s for s in samples if s.get("href") != want]
            checks["pointer"] = "%s %d/%d" % ("fail" if off else "pass", len(samples) - len(off), len(samples))
            if off:
                add("pointer", "첫 클릭 뒤 누른 자리의 항목이 바뀌었다: " + ", ".join(
                    "%sms %s" % (s.get("at"), s.get("href") or ("그룹 머리 «%s»" % s.get("text")
                                                              if s.get("groupHeader") else "빈 자리(%s)" % s.get("tag")))
                    for s in off))
    return fails, why, checks


def second_target(run: dict) -> str | None:
    """둘째 이후의 사이드바 클릭이 어디에 떨어졌는가 — same · other-item · group-header · empty."""
    if run.get("mode") == "baseline":
        return None
    clicks = [c for c in (run.get("pointer") or {}).get("clicks") or [] if c.get("inRail", True)]
    if len(clicks) < 2:
        return None
    want = (run.get("item") or {}).get("href")
    for c in clicks[1:]:
        if c.get("href") == want:
            continue
        if c.get("href"):
            return "other-item"
        return "group-header" if c.get("groupHeader") else "empty"
    return "same"


def screenshot(page, shots: Path, key: str) -> str | None:
    shots.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^0-9A-Za-z._-]+", "_", key).strip("_")[:160] + ".png"
    path = shots / name
    try:
        page.screenshot(path=str(path), full_page=False, timeout=15_000)
    except Exception:  # noqa: BLE001 — 스크린샷을 못 찍어도 기록은 남는다
        return None
    return _rel(path)


def run_one(page, obs: Observer, cfg: RunCfg, item: Item, mode: str, param, rep: int,
            baseline: dict | None, shots: Path) -> dict:
    """새 문서에서 시작해 한 방식으로 누르고, 선 뒤의 상태와 그 사이에 난 일을 기록한다."""
    rec: dict = {
        "key": run_key(cfg, item, mode, param, rep),
        "console": cfg.console, "role": cfg.role, "browser": cfg.browser,
        "browser_version": cfg.browser_version, "viewport": cfg.viewport,
        "item": {"href": item.href, "label": item.label, "group": item.group, "path": item.path},
        "mode": mode, "mode_label": MODE_LABEL.get(mode, mode), "param": param, "rep": rep,
        "start_url": cfg.start_url, "notes": [],
    }
    t0 = time.monotonic()
    since = None
    obs.watch = (param,) if mode == "inflight" and isinstance(param, str) else ()
    try:
        # 1. 새 문서에서 시작한다. 같은 문서 안 이동은 앞 실행의 화면 상태와 질의 캐시를 그대로 들고 온다.
        page.goto("about:blank", wait_until="domcontentloaded", timeout=30_000)
        obs.reset()
        page.goto(cfg.start_url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_selector(f"{NAVLIST} a[href]", state="attached", timeout=30_000)
        rec["start_quiet"] = quiet(page, obs)
        page.wait_for_timeout(cfg.start_settle_ms)
        rec["start"] = read_state(page)
        start_events = obs.take()
        rec["start_events"] = {"page_errors": start_events["page_errors"],
                               "console": [c["text"][:300] for c in start_events["console"]][:8]}

        # 2. 항목을 누를 수 있게 한다. 접힌 그룹 안에 있으면 사람이 하듯 머리를 눌러 편다.
        group = page.evaluate(GROUP_STATE_JS, {"nav": NAVLIST, "href": item.href})
        if not group.get("found"):
            raise HarnessError("사이드바에서 이 항목을 못 찾았다")
        if group.get("collapsed"):
            header = page.locator(f'{NAVLIST} [aria-controls="{group["groupId"]}"]').first
            header.click(timeout=CLICK_TIMEOUT_MS)
            page.wait_for_timeout(GROUP_OPEN_WAIT_MS)
            rec["group_opened"] = True
        link = page.locator(f'{NAVLIST} a[href="{item.href}"]').first
        link.scroll_into_view_if_needed(timeout=CLICK_TIMEOUT_MS)
        page.wait_for_timeout(120)
        box = link.bounding_box()
        if not box:
            raise HarnessError("항목의 상자를 못 읽었다(보이지 않는다)")
        x = round(box["x"] + box["width"] / 2)
        y = round(box["y"] + box["height"] / 2)
        rec["point"] = {"x": x, "y": y}
        armed = page.evaluate(SAMPLER_JS, {"x": x, "y": y, "at": list(SAMPLE_AT_MS), "nav": NAVLIST})
        since = armed.get("now")
        hit = armed.get("hit") or {}
        if hit.get("href") != item.href:
            raise HarnessError("누를 자리에 이 항목이 없다(%s)" % (hit.get("href") or hit.get("text")))

        # 3. 누른다. 첫 클릭 직전부터 센다.
        obs.reset()
        perform(page, obs, cfg, mode, param, link, x, y, rec)

        # 4. 화면이 선 뒤의 끝 상태.
        rec["settle"] = settle(page, obs, settle_ms=cfg.settle_ms)
        rec["final"] = read_state(page)
        if rec.get("marked"):
            rec["remounted"] = page.evaluate(REMOUNT_JS)
    except HarnessError as exc:
        rec["harness_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 — 한 실행의 실패가 행렬 전체를 끊지 않는다
        rec["harness_error"] = ("%s: %s" % (type(exc).__name__, exc))[:800]
    obs.watch = ()
    collect(page, obs, rec, since)
    rec["fails"], rec["why"], rec["checks"] = judge(rec, baseline)
    rec["second_target"] = second_target(rec)
    if "crash" in rec["fails"] and "remounted" in rec:
        # 폴백이 화면을 갈아 끼우면 제목 노드도 사라진다 — 새 마운트인지 판정할 수 없다.
        rec["remounted"] = None
    if baseline is not None and mode != "baseline":
        base_fails = set(baseline.get("fails") or [])
        rec["fails_beyond_baseline"] = [f for f in rec["fails"] if f not in base_fails]
    if rec.get("between") and baseline and baseline.get("final"):
        first = (rec["between"][0] or {}).get("state") or {}
        if state_diff(baseline["final"], first):
            rec["notes"].append("첫 클릭의 끝 상태부터 기준과 달랐다(한 번 누르기가 비결정적이다)")
    if rec["fails"]:
        rec["screenshot"] = screenshot(page, shots, rec["key"])
    rec["elapsed_ms"] = _ms_since(t0)
    rec["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return rec


# --------------------------------------------------------------------------- #
# 예외 기록
# --------------------------------------------------------------------------- #
_V8_FRAME = re.compile(r"^\s*at\s+(?:(?P<fn>.+?)\s+\()?(?P<loc>[^()\s]+?):(?P<line>\d+):(?P<col>\d+)\)?\s*$")
_SM_FRAME = re.compile(r"^(?P<fn>[^@\s]*)@(?P<loc>.+?):(?P<line>\d+):(?P<col>\d+)\s*$")


@functools.lru_cache(maxsize=64)
def _asset_lines(name: str) -> tuple[str, ...]:
    path = ASSETS_DIR / name
    if not path.is_file():
        return ()
    try:
        return tuple(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return ()


def excerpt(name: str, line: int, col: int, span: int = 140) -> str:
    """최소화 번들의 그 칸 앞뒤. 문자열 · 속성 이름이 남아 있어 원본 자리를 grep 으로 찾을 수 있다."""
    if not _EXCERPT_FROM_LOCAL or not name.endswith(".js"):
        return ""
    lines = _asset_lines(name)
    if not 1 <= line <= len(lines):
        return ""
    text = lines[line - 1]
    i = max(0, col - 1)
    return text[max(0, i - span): i] + "▶" + text[i: i + span]


def top_frames(stack: str, limit: int = 6) -> list[dict]:
    """V8(`at fn (url:줄:칸)`)과 SpiderMonkey(`fn@url:줄:칸`) 두 모양의 스택 줄을 읽는다."""
    frames: list[dict] = []
    for raw in (stack or "").splitlines():
        m = _V8_FRAME.match(raw) or _SM_FRAME.match(raw.strip())
        if not m:
            continue
        loc = m.group("loc")
        name = loc.rsplit("/", 1)[-1].split("?", 1)[0]
        frame = {"fn": (m.group("fn") or "").strip(), "file": name,
                 "line": int(m.group("line")), "col": int(m.group("col"))}
        snippet = excerpt(name, frame["line"], frame["col"])
        if snippet:
            frame["excerpt"] = snippet
        frames.append(frame)
        if len(frames) >= limit:
            break
    return frames


def component_names(component_stack: str, limit: int = 14) -> list[str]:
    names = []
    for raw in (component_stack or "").splitlines():
        m = re.match(r"^\s*at\s+([^\s(]+)", raw) or re.match(r"^\s*([^@\s]+)@", raw)
        if m:
            names.append(m.group(1))
        if len(names) >= limit:
            break
    return names


def steps_for(run: dict) -> list[str]:
    item = run.get("item") or {}
    label = item.get("label") or item.get("href")
    param = run.get("param")
    steps = ["%s %s · %s 창으로 %s 을 새로 연다." % (run.get("browser"), run.get("browser_version") or "",
                                                 run.get("viewport"), run.get("start_url"))]
    if run.get("group_opened"):
        steps.append("사이드바 «%s» 그룹 머리를 눌러 편다." % item.get("group"))
    mode = run.get("mode")
    if mode == "baseline":
        steps.append("«%s» 을 한 번 누른다." % label)
    elif mode == "dblclick":
        steps.append("«%s» 을 두 번 빠르게 누른다(dblclick)." % label)
    elif mode == "mouse2":
        steps.append("«%s» 자리를 누르고 %sms 뒤 같은 좌표를 다시 누른다." % (label, param))
    elif mode == "element2":
        steps.append("«%s» 을 누르고 %sms 뒤 같은 항목을 다시 누른다(항목이 움직이면 따라간다)." % (label, param))
    elif mode in ("settled2", "settled5"):
        times = "한 번" if mode == "settled2" else "다섯 번"
        steps.append("«%s» 을 누르고, 화면이 설 때마다(요청이 멎고 주소가 1.5초 동안 그대로) 같은 항목을 다시 누르기를 %s 한다."
                     % (label, times))
    elif mode == "stale2":
        steps.append("«%s» 을 누르고 화면이 선 뒤 %d초를 기다려(질의 캐시가 낡는다) 같은 항목을 다시 누른다."
                     % (label, STALE_WAIT_MS // 1000))
    elif mode == "inflight":
        steps.append("«%s» 을 누르고 %s 요청이 오가는 중에 같은 항목을 다시 누른다." % (label, param))
    elif mode == "tabs":
        steps.append("«%s» 을 누르고 화면이 선 뒤 둘째 탭 → 첫째 탭을 누른 다음 사이드바 항목을 다시 누른다." % label)
    elif mode == "scrolled":
        steps.append("«%s» 을 누르고 화면이 선 뒤 본문을 끝까지 굴린 다음 같은 항목을 다시 누른다." % label)
    if "crash" in (run.get("fails") or []):
        steps.append("본문에 「%s」 폴백이 선다." % FALLBACK_TEXT)
    return steps


def crash_record(run: dict) -> dict:
    crash = run.get("crash") or {}
    zero = run.get("click_zero")
    boundary = []
    for entry in crash.get("boundary") or []:
        args = entry.get("args") or []
        err = next((a for a in args if a.get("kind") == "error"), {})
        comp = next((a.get("text") or "" for a in args if a.get("kind") == "string"), "")
        boundary.append({
            "t": entry.get("t"),
            "after_first_click_ms": (int(entry["t"] - zero) if isinstance(zero, (int, float))
                                     and isinstance(entry.get("t"), (int, float)) else None),
            "href": entry.get("href"), "name": err.get("name"),
            "message": err.get("message") or next((a.get("text") for a in args if a.get("text")), ""),
            # 실행 때 뽑아 둔 줄(발췌 포함)이 있으면 그것을 쓴다 — 지금 번들로 다시 뽑으면 발췌가 빈다.
            "stack": err.get("stack") or "", "top_frames": err.get("frames") or top_frames(err.get("stack") or ""),
            "component_stack": comp, "components": component_names(comp),
        })
    page_errors = [{**e, "top_frames": e.get("frames") or top_frames(e.get("stack") or "")}
                   for e in run.get("page_errors") or []]
    item = run.get("item") or {}
    return {
        "key": run.get("key"), "console": run.get("console"), "role": run.get("role"),
        "browser": run.get("browser"), "browser_version": run.get("browser_version"),
        "viewport": run.get("viewport"), "route": item.get("path"), "label": item.get("label"),
        "mode": run.get("mode"), "mode_label": run.get("mode_label"), "param": run.get("param"),
        "rep": run.get("rep"), "boundary": boundary, "page_errors": page_errors,
        "in_page_errors": crash.get("errors") or [],
        "console_lines": [str(c.get("text") or "")[:3000] for c in run.get("console_errors") or []][:10],
        "fallback": crash.get("fallback") or [], "final": run.get("final"),
        "url_timeline": run.get("url_timeline") or [], "clicks": (run.get("pointer") or {}).get("clicks") or [],
        "screenshot": run.get("screenshot"), "steps": steps_for(run),
    }


# --------------------------------------------------------------------------- #
# 산출물
# --------------------------------------------------------------------------- #
def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.tmp-%d" % (path.name, os.getpid()))
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def write_part(out: Path, name: str, meta: dict, runs: list[dict]) -> Path:
    path = out / "parts" / ("%s.json" % name)
    _write_json(path, {"meta": meta, "runs": runs})
    return path


def summary_rows(runs: list[dict]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for r in runs:
        key = "%s|%s|%s" % (r.get("console"), r.get("browser"), r.get("viewport"))
        row = rows.setdefault(key, {"runs": 0, "failed": 0, **{t: 0 for t in FAIL_TYPES}, "http429": 0})
        row["runs"] += 1
        if r.get("fails"):
            row["failed"] += 1
        for t in r.get("fails") or []:
            row[t] = row.get(t, 0) + 1
        if (r.get("http") or {}).get("429"):
            row["http429"] += 1
    return rows


def merge_outputs(out: Path) -> dict:
    """조각 전부를 한 벌로 합쳐 `runs.json` · `crashes.json` 을 다시 쓴다. 같은 실행 키는 나중 것이 이긴다."""
    metas: list[dict] = []
    by_key: dict[str, dict] = {}
    for path in sorted((out / "parts").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = dict(data.get("meta") or {})
        meta["part"] = path.name
        metas.append(meta)
        for run in data.get("runs") or []:
            key = run.get("key")
            prev = by_key.get(key)
            if prev is None or str(run.get("ended_at", "")) >= str(prev.get("ended_at", "")):
                by_key[key] = run
    runs = list(by_key.values())
    crashes = [crash_record(r) for r in runs if "crash" in (r.get("fails") or [])]
    bundles = {json.dumps(m.get("bundle"), sort_keys=True) for m in metas if m.get("bundle")}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    summary = {"runs": len(runs), "failed": sum(1 for r in runs if r.get("fails")),
               "bundles": len(bundles), "rows": summary_rows(runs)}
    _write_json(out / "runs.json", {"generated_at": stamp, "parts": metas, "summary": summary, "runs": runs})
    _write_json(out / "crashes.json", {"generated_at": stamp, "crashes": crashes})
    return {"runs": runs, "crashes": crashes, "metas": metas, "bundles": len(bundles)}


def _hash_of(href: str) -> str:
    return href.split("#", 1)[1] if "#" in (href or "") else (href or "")


def _why(entry) -> tuple[str, str]:
    """(실패 종류, 이유). 이유를 글자 한 줄로만 적던 앞 조각도 함께 읽는다."""
    if isinstance(entry, dict):
        return str(entry.get("kind") or ""), str(entry.get("text") or "")
    return "", str(entry or "")


def print_summary(merged: dict, this_runs: list[dict], not_run: list[str]) -> None:
    runs = merged["runs"]
    print()
    print("== REACTIVATE_E2E 요약 — 조각 %d개를 합친 %d 실행(이번 실행 %d) =="
          % (len(merged["metas"]), len(runs), len(this_runs)))
    if merged["bundles"] > 1:
        print("  [주의] 조각의 번들 지문이 %d가지다. 서로 다른 빌드를 잰 조각이 섞여 있다(--fresh 로 비운다)."
              % merged["bundles"])
    cols = list(FAIL_TYPES) + ["http429"]
    print("  %-30s %5s %5s  %s" % ("콘솔 · 브라우저 · 뷰포트", "실행", "실패",
                                 " ".join("%s" % FAIL_LABEL[c] for c in cols)))
    for key, row in summary_rows(runs).items():
        print("  %-30s %5d %5d  %s" % (key.replace("|", " · "), row["runs"], row["failed"],
                                     " ".join("%*d" % (len(FAIL_LABEL[c]), row[c]) for c in cols)))

    crashes = merged["crashes"]
    print("\n  폴백(렌더 예외) %d건" % len(crashes))
    for c in crashes[:40]:
        b = (c.get("boundary") or [{}])[0]
        frame = ((b.get("top_frames") or [{}])[0]) if b else {}
        print("   · %s %s %s «%s» %s%s — %s: %s @ %s:%s:%s" % (
            c["console"], c["browser"], c["viewport"], c["label"], c["mode_label"],
            "" if c.get("param") is None else " %s" % c["param"], b.get("name") or "-",
            (b.get("message") or "")[:120], frame.get("file", "-"), frame.get("line", "-"), frame.get("col", "-")))

    def grouped(kind: str, keyf):
        out: dict = {}
        for r in runs:
            if kind in (r.get("fails") or []):
                out.setdefault(keyf(r), []).append(r)
        return out

    states = grouped("state", lambda r: (r["console"], r["item"]["label"], r["mode_label"], r.get("param"),
                                         r.get("second_target") or "-"))
    print("\n  상태 갈림 %d건 (둘째 클릭이 같은 항목이면 «같은 대상 재활성화», 아니면 «밀림의 결과»)"
          % sum(len(v) for v in states.values()))
    for (console, label, mode, param, target), rs in list(states.items())[:60]:
        diff = (rs[0].get("state_diff") or [{}])
        href = next((d for d in diff if d.get("key") == "href"), None)
        what = ("%s → %s" % (_hash_of(href["baseline"]), _hash_of(href["got"]))) if href else \
            "; ".join("%s %s → %s" % (d.get("key"), d.get("baseline"), d.get("got")) for d in diff)
        kind = "같은 대상 재활성화" if target == "same" else ("밀림의 결과(%s)" % target)
        print("   · %s «%s» %s%s [%s] %s — %s" % (
            console, label, mode, "" if param is None else " %s" % param, kind,
            ",".join(sorted({"%s/%s" % (r["browser"], r["viewport"]) for r in rs})), what[:200]))

    # 새 마운트 여부는 실패가 아니라 관측이다 — 「다시 누르면 새 진입」 규칙이 실제로 도는지 보는 자리다.
    mounts: dict = {}
    for r in runs:
        if r.get("remounted") is not None:
            row = mounts.setdefault((r["console"], r["item"]["label"]), [0, 0])
            row[0 if r["remounted"] else 1] += 1
    if mounts:
        print("\n  다시 누른 뒤 화면이 새로 마운트됐는가(선 뒤 다시 누르는 방식들, 폴백이 선 실행은 뺀다)")
        for (console, label), (yes, no) in sorted(mounts.items()):
            print("   · %s «%s» 새 마운트 %d · 같은 인스턴스 %d" % (console, label, yes, no))

    pointers = grouped("pointer", lambda r: (r["console"], r["browser"], r["viewport"]))
    print("\n  포인터 밀림 %d건" % sum(len(v) for v in pointers.values()))
    for (console, browser, viewport), rs in pointers.items():
        labels = sorted({r["item"]["label"] for r in rs})
        print("   · %s %s %s — 항목 %d개: %s" % (console, browser, viewport, len(labels), ", ".join(labels)[:220]))

    for kind in ("pageerror", "console", "http5xx", "reload", "start", "harness"):
        rs = [r for r in runs if kind in (r.get("fails") or [])]
        if not rs:
            continue
        steady = [r for r in rs if r.get("mode") == "baseline" or kind not in (r.get("fails_beyond_baseline") or [kind])]
        print("\n  %s %d건 (그중 기준 실행에서도 나는 것 %d건)" % (FAIL_LABEL[kind], len(rs), len(steady)))
        for r in rs[:12]:
            reason = next((_why(w)[1] for w in r.get("why") or [] if _why(w)[0] == kind), "")
            print("   · %s %s %s «%s» %s%s — %s" % (
                r["console"], r["browser"], r["viewport"], r["item"]["label"], r["mode_label"],
                "" if r.get("param") is None else " %s" % r["param"], reason[:200]))
    if not_run:
        print("\n  못 돈 조합 %d개" % len(not_run))
        for line in not_run:
            print("   · %s" % line)
    failed = [r for r in this_runs if r.get("fails")]
    if failed:
        print("\nREACTIVATE_E2E FAILED (이번 실행 실패 %d/%d)" % (len(failed), len(this_runs)))
    elif not_run or not this_runs:
        print("\nREACTIVATE_E2E INCOMPLETE (돈 실행 %d · 못 돈 조합 %d)" % (len(this_runs), len(not_run)))
    else:
        print("\nREACTIVATE_E2E OK (%d 실행)" % len(this_runs))


# --------------------------------------------------------------------------- #
# 행렬
# --------------------------------------------------------------------------- #
def _split(values) -> list[str]:
    out: list[str] = []
    for raw in values or []:
        for part in str(raw).split(","):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def plan_for(item: Item, modes: list[str], stress: bool) -> list[tuple[str, object]]:
    wanted = list(modes) + [m for m in (STRESS_MODES if stress else ()) if m not in modes]
    plan: list[tuple[str, object]] = []
    for mode in wanted:
        if mode == "baseline":
            continue
        if mode in ("mouse2", "element2"):
            plan += [(mode, d) for d in DOUBLE_DELAYS_MS]
        elif mode == "inflight":
            plan += [(mode, frag) for frag in INFLIGHT_TARGETS.get(item.path, ("/api/",))]
        else:
            plan.append((mode, None))
    return plan


def _print_item(item: Item, runs: list[dict]) -> None:
    failed = [r for r in runs if r.get("fails")]
    counts: dict[str, int] = {}
    for r in failed:
        for f in r["fails"]:
            counts[f] = counts.get(f, 0) + 1
    print("  «%s» (%s) %d 실행 · 실패 %d%s" % (
        item.label, item.group or "-", len(runs), len(failed),
        (" — " + " · ".join("%s %d" % (FAIL_LABEL[k], v) for k, v in counts.items())) if counts else ""),
        flush=True)
    for r in failed:
        print("      · %s%s: %s — %s" % (r["mode_label"], "" if r.get("param") is None else " %s" % r["param"],
                                         ",".join(FAIL_LABEL[f] for f in r["fails"]),
                                         _why((r.get("why") or [""])[0])[1][:180]), flush=True)


def _sessions(browser, base: str, auth_dir: Path, insecure: bool, consoles: list[str], user_role: str) -> dict:
    """저장 상태를 **읽어 둔 값**으로 넘긴다 — 파일 경로를 넘기면 다른 실행이 같은 파일을 고쳐 쓴 뒤에 읽힌다."""
    from scripts.ui_qa.auth import ensure_session

    admin = ensure_session(browser, base, auth_dir, insecure=insecure, log=print)
    admin_state = json.loads(Path(admin.storage_state).read_text(encoding="utf-8"))
    out = {"admin": (admin, admin_state), "user": (admin, admin_state)}
    if "user" in consoles and user_role and user_role != admin.role:
        user = ensure_session(browser, base, auth_dir / ("role-" + user_role), insecure=insecure, log=print,
                              role=user_role)
        out["user"] = (user, json.loads(Path(user.storage_state).read_text(encoding="utf-8")))
    return out


def run_matrix(args) -> int:
    from playwright.sync_api import sync_playwright

    from scripts.ui_qa.auth import is_local_target

    global _EXCERPT_FROM_LOCAL
    base = args.base_url.rstrip("/")
    insecure = tls.apply_default_https_context(cli_insecure=args.insecure, cli_verify=args.verify_tls)
    print(tls.describe(cli_insecure=args.insecure, cli_verify=args.verify_tls))
    _EXCERPT_FROM_LOCAL = is_local_target(base)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.fresh:
        for old in list((out / "parts").glob("*.json")) + list((out / "shots").glob("*.png")):
            old.unlink(missing_ok=True)
    consoles = ["user", "admin"] if args.console == "both" else [args.console]
    browsers = _split(args.browsers) or list(DEFAULT_BROWSERS)
    viewports = cap.resolve_viewports(_split(args.viewports) or list(DEFAULT_VIEWPORTS))
    wanted = _split(args.routes)
    modes = _split(args.modes) or list(DOUBLE_MODES)
    unknown = [m for m in modes if m not in ALL_MODES]
    if unknown:
        print("[FATAL] 모르는 방식이다: %s (받는 값: %s)" % (", ".join(unknown), ", ".join(ALL_MODES)))
        return 2
    part = "%s-%d" % (time.strftime("%Y%m%dT%H%M%S"), os.getpid())
    meta = {
        "base_url": base, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "consoles": consoles,
        "browsers": browsers, "viewports": [v.name for v in viewports], "routes": wanted, "modes": modes,
        "stress": bool(args.stress), "repeat": args.repeat, "user_role": args.user_role or "",
        "bundle": cap.build_fingerprint(base_url=base, insecure=insecure), "browser_versions": {},
        "settle_ms": SETTLE_MS, "sample_at_ms": list(SAMPLE_AT_MS), "delays_ms": list(DOUBLE_DELAYS_MS),
    }
    runs: list[dict] = []
    not_run: list[str] = []
    shots = out / "shots"
    auth_dir = out / "auth" / (re.sub(r"[^0-9A-Za-z.-]+", "-", urlsplit(base).netloc) or "local")
    with sync_playwright() as pw:
        sessions = None
        for bname in browsers:
            launcher = getattr(pw, bname, None)
            if launcher is None:
                not_run.append("%s: 모르는 브라우저다" % bname)
                continue
            try:
                browser = launcher.launch()
            except Exception as exc:  # noqa: BLE001 — 설치 안 된 브라우저는 그 사실을 남기고 나머지를 돈다
                not_run.append("%s: 띄우지 못했다 — %s" % (bname, str(exc).strip().splitlines()[0][:200]))
                print("[경고] %s 를 띄우지 못했다. 나머지 브라우저만 돈다." % bname, flush=True)
                continue
            meta["browser_versions"][bname] = browser.version
            if sessions is None:
                sessions = _sessions(browser, base, auth_dir, insecure, consoles, args.user_role)
            for console in consoles:
                sess, state = sessions[console]
                for vp in viewports:
                    ctx = cap.new_context(browser, storage_state=state, user_id=sess.user_id, theme="light",
                                          viewport=vp, insecure=insecure)
                    ctx.add_init_script(init_script())
                    page = ctx.new_page()
                    obs = Observer(page)
                    start_url = "%s%s#%s" % (base, SHELL[console], START_PATH[console])
                    cfg = RunCfg(console=console, browser=bname, browser_version=browser.version,
                                 viewport=vp.name, role=sess.role, start_url=start_url)
                    try:
                        items = enumerate_items(page, obs, start_url)
                    except Exception as exc:  # noqa: BLE001
                        not_run.append("%s %s %s: 사이드바를 못 읽었다 — %s" % (console, bname, vp.name, str(exc)[:200]))
                        ctx.close()
                        continue
                    every = len(items)
                    items = [it for it in items if not wanted or any(w in it.href or w in it.label for w in wanted)]
                    print("\n== %s · %s %s · %s — 항목 %d개 ==" % (console, bname, browser.version, vp.name,
                                                               len(items)), flush=True)
                    if wanted and every and not items:
                        # Git Bash 는 `/approvals` 같은 인자를 `C:/Program Files/Git/approvals` 로 바꿔 넘긴다 — 빗금 없이 적는다.
                        not_run.append("%s %s %s: --routes %s 가 사이드바 항목 %d개 중 하나도 고르지 못했다"
                                       % (console, bname, vp.name, wanted, every))
                    if args.list_items:
                        for it in items:
                            print("  %-26s %-14s %s" % (it.href, it.group, it.label))
                        ctx.close()
                        continue
                    for item in items:
                        baseline = run_one(page, obs, cfg, item, "baseline", None, 0, None, shots)
                        item_runs = [baseline]
                        for rep in range(max(1, args.repeat)):
                            for mode, param in plan_for(item, modes, args.stress):
                                item_runs.append(run_one(page, obs, cfg, item, mode, param, rep, baseline, shots))
                        runs.extend(item_runs)
                        _print_item(item, item_runs)
                        meta["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                        write_part(out, part, meta, runs)
                    ctx.close()
            browser.close()
    if args.list_items:
        return 0 if not not_run else 2
    meta["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_part(out, part, meta, runs)
    merged = merge_outputs(out)
    print("REACTIVATE_E2E_WRITTEN %s · %s" % (_rel(out / "runs.json"), _rel(out / "crashes.json")))
    print_summary(merged, runs, not_run)
    if any(r.get("fails") for r in runs):
        return 1
    if not_run or not runs:
        return 2
    return 0


# --------------------------------------------------------------------------- #
# 반례 (CLAUDE.md §7 — 제품을 판정하기 전에 프로브부터 증명한다)
# --------------------------------------------------------------------------- #
def _case(name: str, expect, got, ok: bool | None = None) -> dict:
    return {"name": name, "expect": expect, "got": got, "ok": (expect == got) if ok is None else ok}


def logic_cases() -> list[dict]:
    """판정 규칙을 합성 관측값으로 양방향 증명한다. 브라우저가 없어도 돌아 `static_checks.sh` 가 매번 부른다."""
    item = {"href": "#/work-board", "label": "작업 보드", "group": "팀 업무", "path": "/work-board"}
    final = {"href": "http://x/#/work-board?team=a&sprint=b", "h1": "작업 보드", "current": "#/work-board",
             "fallback": None}
    baseline = {"mode": "baseline", "item": item, "final": dict(final), "fails": []}
    five = [{"at": a, "href": "#/work-board"} for a in SAMPLE_AT_MS]

    def rec(**kw) -> dict:
        base = {"mode": "settled2", "console": "user", "item": item, "final": dict(final), "crash": {},
                "pointer": {"samples": [], "clicks": []}, "http": {"5xx": [], "429": []}}
        base.update(kw)
        return base

    def kinds(run: dict, ref=baseline) -> list[str]:
        return judge(run, ref)[0]

    rows = [
        _case("state/같은 끝 상태는 통과한다", [], kinds(rec())),
        _case("state/질의만 달라도 상태 갈림이다(작업 보드 재클릭의 모양)", ["state"],
              kinds(rec(final={**final, "href": "http://x/#/work-board?team=a"}))),
        _case("state/활성 표시만 달라도 상태 갈림이다", ["state"], kinds(rec(final={**final, "current": ""}))),
        _case("state/기준이 없으면 통과가 아니라 하네스 실패다", ["harness"], kinds(rec(), None)),
        _case("crash/폴백 표식(data-error-boundary)은 렌더 예외다", ["crash"],
              kinds(rec(crash={"fallback": [{"t": 5, "how": "mark", "gone": None}]}))),
        _case("crash/[ErrorBoundary] 콘솔 줄만 있어도 렌더 예외다", ["crash"],
              kinds(rec(console_errors=[{"text": BOUNDARY_PREFIX + " TypeError: x"}]))),
        _case("crash/끝 화면의 폴백 문구도 렌더 예외다", ["crash"],
              kinds(rec(final={**final, "fallback": "text"}))),
        _case("pointer/같은 자리 표본 다섯은 통과한다", [],
              kinds(rec(mode="mouse2", pointer={"samples": five, "clicks": []}))),
        _case("pointer/표본 하나가 다른 항목이면 밀림이다", ["pointer"],
              kinds(rec(mode="mouse2", pointer={"samples": five[:4] + [{"at": 500, "href": "#/sprint"}]}))),
        _case("pointer/그룹 머리에 떨어져도 밀림이다", ["pointer"],
              kinds(rec(mode="mouse2", pointer={"samples": five[:3] + [
                  {"at": 300, "href": None, "groupHeader": True, "text": "팀 공간"},
                  {"at": 500, "href": None, "groupHeader": True, "text": "팀 공간"}]}))),
        _case("pointer/표본이 모자라면 통과가 아니다(아무것도 안 재고 통과 금지)", ["harness"],
              kinds(rec(mode="mouse2", pointer={"samples": five[:2]}))),
        _case("pointer/element2 에는 밀림 판정을 걸지 않는다", [],
              kinds(rec(mode="element2", pointer={"samples": [{"at": 0, "href": "#/sprint"}]}))),
        _case("http/500 은 실패다", ["http5xx"], kinds(rec(http={"5xx": [{"status": 500, "url": "u"}], "429": []}))),
        _case("http/429 는 따로 세고 실패로 치지 않는다", [], kinds(rec(http={"5xx": [], "429": [{"status": 429}]}))),
        _case("reload/사이드바를 눌렀는데 문서가 새로 열리면 실패다", ["reload"],
              kinds(rec(documents=[{"url": "http://x/"}]))),
        _case("console/기대 밖 콘솔 줄은 실패다", ["console"], kinds(rec(console_counted=["boom"]))),
        _case("start/시작 화면의 예외는 따로 센다", ["start"],
              kinds(rec(start_events={"page_errors": [{"message": "x"}]}))),
    ]
    legacy = BY_ID.get("user_legacy-doc-redirect")
    line404 = "Failed to load resource: the server responded with a status of 404 (Not Found)"
    rows.append(_case("console/D-494 기대 줄은 세지 않는다", [], split_console(legacy, [line404])[1]))
    rows.append(_case("console/기대 줄이 없는 화면은 같은 줄도 센다", [line404],
                      split_console(route_for("user", "/work-board"), [line404])[1]))
    rows.append(_case("console/라우트 표에 없는 화면은 전부 센다", ["x"], split_console(None, ["x"])[1]))
    v8 = top_frames("TypeError: a is undefined\n    at Kb (http://h/static/react/assets/WorkBoard.X.js:3:1234)\n"
                    "    at http://h/static/react/assets/react.Y.js:1:99")
    rows.append(_case("stack/V8 스택 줄을 읽는다", [("Kb", "WorkBoard.X.js", 3, 1234), ("", "react.Y.js", 1, 99)],
                      [(f["fn"], f["file"], f["line"], f["col"]) for f in v8]))
    sm = top_frames("Kb@http://h/static/react/assets/WorkBoard.X.js:3:1234\n@http://h/static/react/assets/react.Y.js:1:99\n")
    rows.append(_case("stack/SpiderMonkey 스택 줄을 읽는다", [("Kb", "WorkBoard.X.js", 3, 1234), ("", "react.Y.js", 1, 99)],
                      [(f["fn"], f["file"], f["line"], f["col"]) for f in sm]))
    record = crash_record({**rec(), "fails": ["crash"], "crash": {"boundary": [{"t": 1, "href": "h", "args": [
        {"kind": "error", "name": "TypeError", "message": "boom", "stack": "TypeError: boom\n    at Fn (u.js:1:2)"},
        {"kind": "string", "text": "\n    at WorkBoard (u.js:1:1)\n    at Suspense"}]}]}})
    b = record["boundary"][0]
    rows.append(_case("crash/경계 인자에서 메시지 · 스택 · 컴포넌트 스택을 뽑는다",
                      ("boom", "Fn", ["WorkBoard", "Suspense"]),
                      (b["message"], (b["top_frames"] or [{}])[0].get("fn"), b["components"])))
    rows.append(_case("crash/재현 순서를 문장으로 남긴다", True, len(record["steps"]) >= 2))
    target = {"mode": "mouse2", "item": item, "pointer": {"clicks": [
        {"href": "#/work-board", "inRail": True}, {"href": None, "groupHeader": True, "inRail": True}]}}
    rows.append(_case("pointer/둘째 클릭이 그룹 머리에 떨어진 것을 가른다", "group-header", second_target(target)))
    target["pointer"]["clicks"][1] = {"href": None, "groupHeader": False, "inRail": True}
    rows.append(_case("pointer/둘째 클릭이 목록 아래 빈 자리에 떨어진 것을 가른다", "empty", second_target(target)))
    target["pointer"]["clicks"][1] = {"href": "#/work-board", "inRail": True}
    target["pointer"]["clicks"].insert(1, {"href": None, "inRail": False, "text": "백로그"})
    rows.append(_case("pointer/본문 클릭(탭)은 둘째 사이드바 클릭으로 세지 않는다", "same", second_target(target)))
    return rows


# 합성 페이지. 제품 셀렉터(`.MuiDrawer-paper:has(nav) nav` · `a[href]` · `aria-controls` · `.MuiCollapse-root`)를 그대로
# 흉내 내 **제품 실행과 같은 함수**가 돈다. `page.set_content` 대신 가짜 주소에 싣는다 — 그래야 문서마다 도는 관찰자
# (init script)와 해시 이동이 제품 실행과 같은 길을 탄다.
SELFTEST_ORIGIN = "http://reactivate-selftest.invalid"
SELFTEST_TARGET = "#/b2"
SELFTEST_HTML = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>reactivate selftest</title>
<style>
  body { margin: 0; font: 14px sans-serif; display: flex; }
  .MuiDrawer-paper { width: 240px; height: 100vh; overflow: auto; background: #eef; flex: none; }
  nav { display: block; padding: 8px 0; }
  .MuiListItemButton-root { display: flex; align-items: center; height: 40px; padding: 0 16px;
    box-sizing: border-box; cursor: pointer; color: #222; text-decoration: none; }
  .MuiCollapse-root { overflow: hidden; transition: height 300ms ease; }
  a[aria-current="page"] { background: #ccd; }
  main { flex: 1; padding: 24px; }
  [role="alert"] { padding: 16px; border: 1px solid #c00; }
</style></head>
<body>
<div class="MuiDrawer-paper"><nav id="nav"></nav></div>
<main id="main-content" tabindex="-1"><h1 id="title"></h1><div id="body"></div></main>
<script>
(() => {
  const variant = new URLSearchParams(location.search).get('variant') || 'good';
  const GROUPS = [['가', ['a1', 'a2', 'a3', 'a4', 'a5']], ['나', ['b1', 'b2', 'b3']], ['다', ['c1', 'c2', 'c3']]];
  const opened = {};
  const entries = {};
  const armed = {};
  const nav = document.getElementById('nav');
  const pathOf = () => location.hash.slice(1).split('?')[0] || '/a1';
  const groupOf = (p) => GROUPS.find(([, items]) => items.includes(p.slice(1)));
  const isOpen = (name) => {
    const g = groupOf(pathOf());
    const active = !!g && g[0] === name;
    // 밀리는 목록: 활성이라서만 펴진 그룹은 활성을 잃는 순간 접힌다. 안 움직이는 목록: 늘 펴져 있다.
    if (variant === 'shift') return active || opened[name] === true;
    return opened[name] !== false;
  };
  const render = () => {
    const p = pathOf();
    for (const [name] of GROUPS) {
      const col = document.getElementById('grp-' + name);
      const open = isOpen(name);
      document.querySelector('[aria-controls="grp-' + name + '"]').setAttribute('aria-expanded', String(open));
      col.style.height = open ? col.scrollHeight + 'px' : '0px';
    }
    for (const a of nav.querySelectorAll('a[href]')) {
      if (a.getAttribute('href') === '#' + p) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    }
    document.getElementById('title').textContent = p.slice(1).toUpperCase() + ' 화면';
  };
  const enter = () => {
    const p = pathOf();
    entries[p] = (entries[p] || 0) + 1;
    const body = document.getElementById('body');
    body.textContent = '';
    if (variant === 'remount') {
      // 들어올 때마다 화면을 새로 그린다 — 제목 노드가 새 노드로 바뀐다(재진입 = 새 마운트의 모양). `cloneNode` 는
      // 달아 둔 표까지 옮겨 붙이므로 쓰지 않는다 — React 의 새 마운트도 옛 노드의 속성을 들고 오지 않는다.
      const fresh = document.createElement('h1');
      fresh.id = 'title';
      document.getElementById('title').replaceWith(fresh);
    }
    if (variant === 'crash' && entries[p] >= 2) {
      const box = document.createElement('div');
      box.setAttribute('role', 'alert');
      box.textContent = '불러오지 못했습니다. 화면을 표시하는 중 문제가 발생했습니다. 새로고침해 주세요.';
      body.appendChild(box);
      console.error('[ErrorBoundary]', new Error('selftest boom'), '\n    at Boom (selftest.js:1:1)\n    at Board');
    }
    if (variant === 'pageerror' && entries[p] >= 2) setTimeout(() => { throw new Error('selftest uncaught'); }, 0);
    if (variant === 'state' && !location.hash.includes('?')) {
      // 진입 때 한 번만 무장하는 자동 선택 — 다시 들어오면 팀만 고르고 회차는 비운다.
      setTimeout(() => {
        const q = armed[p] ? '?team=1' : '?team=1&sprint=2';
        armed[p] = true;
        history.replaceState(null, '', '#' + p + q);
        render();
      }, 60);
    }
    if (variant === 'http') {
      fetch('/api/selftest/500').catch(() => {});
      fetch('/api/selftest/429').catch(() => {});
    }
    render();
  };
  for (const [name, items] of GROUPS) {
    const box = document.createElement('div');
    const hdr = document.createElement('div');
    hdr.className = 'MuiListItemButton-root';
    hdr.setAttribute('role', 'button');
    hdr.setAttribute('aria-controls', 'grp-' + name);
    hdr.textContent = name + ' 그룹';
    hdr.addEventListener('click', () => { opened[name] = !isOpen(name); render(); });
    const col = document.createElement('div');
    col.className = 'MuiCollapse-root';
    col.id = 'grp-' + name;
    for (const it of items) {
      const a = document.createElement('a');
      a.className = 'MuiListItemButton-root';
      a.href = '#/' + it;
      const s = document.createElement('span');
      s.className = 'MuiListItemText-primary';
      s.textContent = it.toUpperCase() + ' 항목';
      a.appendChild(s);
      col.appendChild(a);
    }
    box.appendChild(hdr);
    box.appendChild(col);
    nav.appendChild(box);
  }
  nav.addEventListener('click', (ev) => {
    const a = ev.target.closest('a[href]');
    if (!a) return;
    ev.preventDefault();
    history.pushState(null, '', a.getAttribute('href'));
    enter();
  });
  enter();
})();
</script>
</body></html>
"""

VARIANT_LABEL = {
    "good": "안 움직이는 목록", "shift": "클릭 때 위 블록이 접히는 목록", "crash": "둘째 클릭이 폴백을 세우는 화면",
    "state": "둘째 클릭이 질의를 바꾸는 화면", "pageerror": "둘째 클릭이 잡히지 않은 예외를 던지는 화면",
    "http": "500 · 429 를 받는 화면", "remount": "다시 들어오면 새로 그리는 화면",
}

# (변형, 방식, 인자, 꼭 있어야 하는 실패, 깨끗해야 하는가)
SELFTEST_CASES = (
    ("good", "baseline", None, (), True),
    ("good", "dblclick", None, (), True),
    ("good", "mouse2", 0, (), True),
    ("good", "mouse2", 150, (), True),
    ("good", "mouse2", 400, (), True),
    ("good", "element2", 0, (), True),
    ("good", "element2", 400, (), True),
    ("good", "settled2", None, (), True),
    ("shift", "baseline", None, (), True),
    ("shift", "mouse2", 150, ("pointer",), False),
    ("shift", "mouse2", 400, ("pointer",), False),
    ("crash", "baseline", None, (), True),
    ("crash", "settled2", None, ("crash",), False),
    ("crash", "element2", 150, ("crash",), False),
    ("crash", "dblclick", None, ("crash",), False),
    ("state", "baseline", None, (), True),
    ("state", "settled2", None, ("state",), False),
    ("pageerror", "baseline", None, (), True),
    ("pageerror", "settled2", None, ("pageerror",), False),
    ("http", "baseline", None, ("http5xx",), False),
    ("remount", "baseline", None, (), True),
    ("remount", "settled2", None, (), True),
)


def _selftest_route(route) -> None:
    url = route.request.url
    if "/api/selftest/500" in url:
        route.fulfill(status=500, body="{}", content_type="application/json")
    elif "/api/selftest/429" in url:
        route.fulfill(status=429, body="{}", content_type="application/json")
    elif "/api/" in url:
        route.fulfill(status=200, body="{}", content_type="application/json")
    else:
        route.fulfill(status=200, body=SELFTEST_HTML, content_type="text/html; charset=utf-8")


def _selftest_extra(variant: str, mode: str, run: dict) -> tuple[bool, str]:
    """실패 종류만 맞으면 안 된다 — 잡은 것의 **내용**도 맞아야 한다."""
    if variant == "good" and mode == "mouse2":
        samples = (run.get("pointer") or {}).get("samples") or []
        ok = len(samples) == len(SAMPLE_AT_MS) and str((run.get("checks") or {}).get("pointer", "")).startswith("pass")
        return ok, "표본 %d/%d · %s" % (len(samples), len(SAMPLE_AT_MS), (run.get("checks") or {}).get("pointer"))
    # 새 마운트 판정의 양방향 — 같은 노드를 쓰는 화면은 「아니다」, 다시 그리는 화면은 「그렇다」여야 한다.
    if mode == "settled2" and variant in ("good", "remount"):
        want = variant == "remount"
        return run.get("remounted") is want, "새 마운트 %s" % run.get("remounted")
    if variant == "crash" and "crash" in (run.get("fails") or []):
        b = (crash_record(run).get("boundary") or [{}])[0]
        ok = b.get("message") == "selftest boom" and "Boom" in (b.get("component_stack") or "") \
            and bool(b.get("top_frames"))
        return ok, "메시지 %r · 컴포넌트 스택 %s · 스택 줄 %d" % (
            b.get("message"), "있음" if "Boom" in (b.get("component_stack") or "") else "없음",
            len(b.get("top_frames") or []))
    if variant == "state" and mode != "baseline":
        return "crash" not in (run.get("fails") or []), "폴백 없이 상태만 갈린다"
    if variant == "http":
        n = len((run.get("http") or {}).get("429") or [])
        return n >= 1, "429 %d건을 따로 셌다" % n
    return True, ""


def dom_selftest(browsers: list[str]) -> list[dict]:
    from playwright.sync_api import sync_playwright

    rows: list[dict] = []
    shots = OUT_DEFAULT / "selftest-shots"
    with sync_playwright() as pw:
        for bname in browsers:
            launcher = getattr(pw, bname, None)
            try:
                browser = launcher.launch() if launcher else None
            except Exception as exc:  # noqa: BLE001
                browser = None
                reason = str(exc).strip().splitlines()[0][:160]
            else:
                reason = "모르는 브라우저다" if launcher is None else ""
            if browser is None:
                rows.append({"name": "%s/브라우저를 띄운다" % bname, "expect": "실행", "got": reason,
                             "ok": False, "fatal": True})
                continue
            ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="ko-KR")
            ctx.add_init_script(init_script())
            ctx.route(SELFTEST_ORIGIN + "/**", _selftest_route)
            page = ctx.new_page()
            obs = Observer(page)
            items = enumerate_items(page, obs, "%s/?variant=good#/a1" % SELFTEST_ORIGIN)
            target = next((it for it in items if it.href == SELFTEST_TARGET), None)
            rows.append(_case("%s/사이드바 항목과 그룹을 읽는다" % bname, "11개 · «나 그룹»",
                              "%d개 · «%s»" % (len(items), target.group if target else "-")))
            if target is None:
                ctx.close()
                browser.close()
                continue
            baselines: dict[str, dict] = {}
            for variant, mode, param, must, clean in SELFTEST_CASES:
                cfg = RunCfg(console="selftest", browser=bname, browser_version=browser.version,
                             viewport="1280x800", role="-", start_url="%s/?variant=%s#/a1" % (SELFTEST_ORIGIN, variant),
                             settle_ms=600, start_settle_ms=350)
                run = run_one(page, obs, cfg, target, mode, param, 0, baselines.get(variant), shots)
                if mode == "baseline":
                    baselines[variant] = run
                got = list(run.get("fails") or [])
                kinds_ok = (not got) if clean else set(must) <= set(got)
                extra_ok, extra = _selftest_extra(variant, mode, run)
                label = "%s%s" % (MODE_LABEL[mode], "" if param is None else " %sms" % param)
                expect = "통과" if clean else "잡힘(%s)" % ",".join(FAIL_LABEL[m] for m in must)
                shown = ",".join(FAIL_LABEL.get(f, f) for f in got) or "통과"
                rows.append({"name": "%s/%s · %s" % (bname, VARIANT_LABEL[variant], label), "expect": expect,
                             "got": shown + (" · " + extra if extra else ""), "ok": kinds_ok and extra_ok,
                             "why": run.get("why")})
            ctx.close()
            browser.close()
    return rows


def selftest_main(args) -> int:
    rows = logic_cases()
    if not args.logic_only:
        rows += dom_selftest(_split(args.browsers) or list(DEFAULT_BROWSERS))
    for r in rows:
        print("[%s] %s — 기대 %s · 실제 %s" % ("OK " if r["ok"] else "NG ", r["name"], r["expect"], r["got"]))
        if not r["ok"] and r.get("why"):
            print("      %s" % " / ".join(_why(w)[1] for w in r["why"])[:400])
    bad = [r for r in rows if not r["ok"]]
    if any(r.get("fatal") for r in rows):
        print("REACTIVATE_SELFTEST_UNRUNNABLE (브라우저를 띄우지 못한 조합이 있다 — %d/%d 어긋남)" % (len(bad), len(rows)))
        return 2
    if bad:
        print("REACTIVATE_SELFTEST_FAILED (%d/%d)" % (len(bad), len(rows)))
        return 1
    print("REACTIVATE_SELFTEST_OK (%d 사례%s — 결함은 잡히고 정상은 안 잡힌다)"
          % (len(rows), " · 로직만" if args.logic_only else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="같은 메뉴 두 번 누르기 재현 하네스 (P0)")
    # 기본 대상은 `capture.DEFAULT_BASE_URL` 한 곳이 정한다. `local_capture` 가 그 값을 임시 서버로 바꿔 둔 뒤에
    # 이 함수를 부르므로 **부를 때** 읽는다.
    ap.add_argument("--base-url", default=None)
    tls.add_arguments(ap)
    ap.add_argument("--console", choices=("user", "admin", "both"), default="both")
    ap.add_argument("--browsers", nargs="+", default=None, help="chromium,firefox (쉼표나 빈칸으로 나눈다)")
    ap.add_argument("--viewports", nargs="+", default=None, help="기본 1920x1080 1366x768")
    ap.add_argument("--routes", nargs="+", default=None, help="항목 주소나 이름의 일부(예: work-board 작업)")
    ap.add_argument("--modes", nargs="+", default=None,
                    help="dblclick mouse2 element2 settled2(기본 넷) · settled5 inflight tabs scrolled")
    ap.add_argument("--stress", action="store_true", help="settled5 · inflight · tabs · scrolled 를 더한다")
    ap.add_argument("--repeat", type=int, default=1, help="기준을 뺀 계획을 몇 번 되풀이하는가")
    ap.add_argument("--user-role", default="", help="사용자 콘솔을 이 역할의 계정으로 돈다(기본은 관리자 계정)")
    ap.add_argument("--selftest", action="store_true", help="합성 페이지로 판정을 먼저 증명한다")
    ap.add_argument("--logic-only", action="store_true", help="--selftest 와 함께 쓴다 — 브라우저 없이 판정 규칙만 본다")
    ap.add_argument("--list-items", action="store_true", help="사이드바 항목만 읽어 찍고 끝낸다")
    ap.add_argument("--fresh", action="store_true", help="옛 조각(parts/)과 스크린샷을 지우고 시작한다")
    ap.add_argument("--summary", action="store_true",
                    help="브라우저를 띄우지 않고 조각을 합쳐 두 파일을 다시 쓴 뒤 요약만 찍는다")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    if args.base_url is None:
        args.base_url = cap.DEFAULT_BASE_URL
    if args.selftest:
        return selftest_main(args)
    if args.summary:
        merged = merge_outputs(Path(args.out))
        print("REACTIVATE_E2E_WRITTEN %s · %s" % (_rel(Path(args.out) / "runs.json"), _rel(Path(args.out) / "crashes.json")))
        print_summary(merged, merged["runs"], [])
        return 1 if any(r.get("fails") for r in merged["runs"]) else 0
    return run_matrix(args)


if __name__ == "__main__":
    raise SystemExit(main())
