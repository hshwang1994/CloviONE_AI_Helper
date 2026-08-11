"""Navigate, settle, probe and screenshot one route × theme × viewport.

Theme forcing is not a guess: App.jsx applies the theme at module scope with
``applyTheme(initialTheme())`` reading ``localStorage["clovirone_theme"]``, and
``UserMenu`` later re-applies the *per-account* key
``clovirone_theme:<userId>`` when one exists. Both keys therefore have to be
seeded, and we seed them through ``context.add_init_script`` so they are in
place before the bundle's first line runs on every navigation. After load we
assert ``<html data-theme>`` actually equals what we asked for
(``assertions.theme_applied``) rather than assuming it worked.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from . import assertions, interact
from .routes import Route

# The SPA shell served by app/admin/router.py and app/chat/router.py.
REACT_INDEX = Path(__file__).resolve().parents[2] / "app" / "static" / "react" / "index.html"


def build_fingerprint(index_path: Path = REACT_INDEX) -> dict:
    """Identify the frontend bundle a run measured.

    A PRE/POST comparison is worthless if the bundle changed underneath the run
    (``npm run build`` overwrites app/static/react/ in place), so every run
    records the shell's hash and its hashed asset names, and ``run.py``
    re-checks it at the end.
    """
    if not index_path.exists():
        return {"error": f"{index_path} 없음 — frontend를 빌드하세요 (cd frontend && npm run build)"}
    raw = index_path.read_bytes()
    text = raw.decode("utf-8", "replace")
    return {
        "index_sha256": hashlib.sha256(raw).hexdigest()[:16],
        "index_mtime": datetime.fromtimestamp(index_path.stat().st_mtime).isoformat(
            timespec="seconds"),
        "assets": sorted(set(re.findall(r"/static/react/assets/([A-Za-z0-9._-]+)", text))),
    }


@dataclass(frozen=True)
class Viewport:
    name: str
    width: int
    height: int
    scale: float = 1.0


# The matrix from the QA brief: phone, tablet, laptop, FHD, QHD, 3K, 4K, plus a
# FHD pass at dsf=2 which is what a 4K panel at 200% OS scaling actually reports.
#
# ⚠️ `1200x900` 은 나중에 **결함을 실제로 잡아서** 추가했다. 원래 목록은 768 다음이 1366 이라
# 그 사이가 통째로 비어 있었는데, 표가 카드로 접히는 폭(≤899.95px)과 열이 넉넉해지는 폭(1366)
# **사이**에서만 `vertical_text_collapse` 가 난다. 1199·1201 양쪽에서 재현되므로 브레이크포인트
# 교차 문제가 아니라 "그 근처 폭에서는 표가 좁다" 는 문제이고, 노트북·반쪽 창에서 가장 흔한
# 폭이다. 경계에서 먼 안전한 값만 재면 이런 것은 영원히 안 보인다.
VIEWPORTS: tuple[Viewport, ...] = (
    Viewport("390x844", 390, 844),
    Viewport("768x1024", 768, 1024),
    Viewport("1200x900", 1200, 900),
    Viewport("1366x768", 1366, 768),
    Viewport("1920x1080", 1920, 1080),
    Viewport("2560x1440", 2560, 1440),
    Viewport("3072x1728", 3072, 1728),
    Viewport("3840x2160", 3840, 2160),
    Viewport("1920x1080@2x", 1920, 1080, 2.0),
)
VIEWPORTS_BY_NAME = {v.name: v for v in VIEWPORTS}

THEMES = ("light", "dark")

DEFAULT_NAV_TIMEOUT_MS = 30_000
DEFAULT_SETTLE_MS = 300

# App.jsx: THEME_KEY / themeKey(userId), NAV_COLLAPSE_KEY / navCollapseKey(userId).
# BrowserContext.add_init_script() in the Python API takes no argument payload,
# so the two values are JSON-embedded into the source instead.
_INIT_SCRIPT_TEMPLATE = """
(() => {
  var seed = %s;
  try {
    localStorage.setItem('clovirone_theme', seed.theme);
    localStorage.setItem('clovirone_nav_collapsed', '{}');
    if (seed.userId) {
      localStorage.setItem('clovirone_theme:' + seed.userId, seed.theme);
      localStorage.setItem('clovirone_nav_collapsed:' + seed.userId, '{}');
    }
  } catch (e) { /* about:blank etc. — no storage for this origin yet */ }
})();
"""


def theme_init_script(theme: str, user_id: str) -> str:
    return _INIT_SCRIPT_TEMPLATE % json.dumps({"theme": theme, "userId": user_id or ""})


def resolve_viewports(selectors: Iterable[str] | None) -> list[Viewport]:
    if not selectors:
        return list(VIEWPORTS)
    out: list[Viewport] = []
    for raw in selectors:
        name = raw.strip()
        if not name:
            continue
        if name.lower() == "all":
            out.extend(v for v in VIEWPORTS if v not in out)
            continue
        if name not in VIEWPORTS_BY_NAME:
            # 이름표에 없는 폭도 받는다. **브레이크포인트 '사이'가 진짜 위험한 구간**이라
            # 그렇다 — 목록에 박힌 8개는 전부 경계에서 멀리 떨어진 안전한 값이고,
            # 실제 사고는 `xl`(1200~1536)처럼 지정이 가장 적은 띠나 `xxl`(2200)·`uhd`(3000)·
            # 사이드바 서랍 전환(860) **바로 양옆**에서 난다. 그 폭을 재려고 매번 이 파일을
            # 고치게 하면 아무도 안 잰다.
            vp = _parse_viewport(name)
            if vp is None:
                raise SystemExit(
                    f"알 수 없는 뷰포트: {raw}\n"
                    f"이름표: {', '.join(VIEWPORTS_BY_NAME)}\n"
                    f"또는 임의 크기: 1440x900, 2201x1200, 1440x900@2x")
        else:
            vp = VIEWPORTS_BY_NAME[name]
        if vp not in out:
            out.append(vp)
    return out


_VIEWPORT_RE = re.compile(r"^(\d{2,5})x(\d{2,5})(?:@(\d+(?:\.\d+)?)x)?$", re.I)


def _parse_viewport(name: str) -> Viewport | None:
    """`1440x900` / `2201x1200@2x` 를 Viewport 로. 못 읽으면 None."""
    m = _VIEWPORT_RE.match(name)
    if not m:
        return None
    width, height = int(m.group(1)), int(m.group(2))
    # Chromium 이 거부하는 값을 그대로 넘기면 실패가 캡처 중간에 터진다 — 여기서 막는다.
    if not (200 <= width <= 8192 and 200 <= height <= 8192):
        return None
    scale = float(m.group(3)) if m.group(3) else 1.0
    return Viewport(name, width, height, scale)


def resolve_themes(selectors: Iterable[str] | None) -> list[str]:
    if not selectors:
        return list(THEMES)
    out: list[str] = []
    for raw in selectors:
        theme = raw.strip().lower()
        if theme == "all":
            out.extend(t for t in THEMES if t not in out)
        elif theme in THEMES:
            if theme not in out:
                out.append(theme)
        elif theme:
            raise SystemExit(f"알 수 없는 테마: {raw} (light|dark)")
    return out


def new_context(browser, *, storage_state: str | None, user_id: str, theme: str,
                viewport: Viewport, insecure: bool = False):
    """``storage_state=None`` 이면 로그인하지 않은 브라우저다 — 로그인 화면 촬영용.

    ``insecure`` 는 자체서명 인증서를 쓰는 설치처(사내 서버)를 겨눌 때만 켠다.
    """
    context = browser.new_context(
        storage_state=storage_state,
        viewport={"width": viewport.width, "height": viewport.height},
        device_scale_factor=viewport.scale,
        color_scheme=theme,  # matches App.jsx prefersDark() fallback
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        reduced_motion="reduce",
        ignore_https_errors=insecure,
    )
    context.add_init_script(theme_init_script(theme, user_id))
    context.set_default_timeout(DEFAULT_NAV_TIMEOUT_MS)
    return context


# --------------------------------------------------------------------------- #
# detail-route id discovery
# --------------------------------------------------------------------------- #
def _first_id(payload) -> str | None:
    """Find the first object id in a list/envelope response, without guessing
    a single response shape (the APIs use bare lists, {items:[]} and {data:[]})."""
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("id") not in (None, ""):
                return str(item["id"])
        return None
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "rows", "posts", "rooms", "tickets", "documents"):
            found = _first_id(payload.get(key))
            if found:
                return found
        # last resort: any list-valued field
        for value in payload.values():
            if isinstance(value, list):
                found = _first_id(value)
                if found:
                    return found
    return None


def discover_detail_hash(context, base_url: str, route: Route, log=print) -> tuple[str | None, str]:
    """Return ``(hash_path, note)`` for a detail route, or ``(None, reason)``.

    🔴 이유를 **뭉개지 않는다**. 예전에는 403 도 "표시할 데이터가 없어…" 라고 적었다.
    역할 매트릭스 실행에서 그 문장은 치명적이다 — "이 역할이 못 본다"와 "기능에 행이 없다"는
    정반대의 사실이고, 역할 조사에서 가장 알고 싶은 차이가 바로 그것이다.
    (`auditor` 는 `CONSOLE_OPS_ROLES` 밖이라 `/api/admin/jobs` 가 403 인데 "데이터 없음"으로
    보고됐다 — BACKLOG `QA-11`.)
    """
    statuses: list[str] = []
    for endpoint in route.discover:
        url = f"{base_url.rstrip('/')}{endpoint}"
        try:
            response = context.request.get(url, timeout=15_000)
        except Exception as exc:
            log(f"[capture] {route.id}: {endpoint} 호출 실패 ({exc})")
            statuses.append(f"{endpoint}→호출실패")
            continue
        if response.status != 200:
            log(f"[capture] {route.id}: {endpoint} -> HTTP {response.status}")
            statuses.append(f"{endpoint}→HTTP {response.status}")
            continue
        try:
            payload = response.json()
        except Exception:
            statuses.append(f"{endpoint}→JSON 아님")
            continue
        found = _first_id(payload)
        if found:
            return route.hash_template.format(id=found), f"{endpoint} 첫 항목 id={found}"
        statuses.append(f"{endpoint}→200, 항목 0건")

    denied = [s for s in statuses if "HTTP 401" in s or "HTTP 403" in s]
    if denied:
        return None, "이 계정 권한으로는 조회할 수 없습니다 (" + ", ".join(denied) + ")"
    return None, "표시할 데이터가 없어 상세 id를 찾지 못했습니다 (" + ", ".join(statuses) + ")"


# --------------------------------------------------------------------------- #
# navigation + capture
# --------------------------------------------------------------------------- #
def _settle(page, *, settle_ms: int, timeout_ms: int, spa: bool = True) -> dict:
    """Wait for the SPA to stop moving. Every wait is best-effort: a screen that
    polls forever must not abort the run, it just gets captured as-is.

    ``spa=False`` 는 서버가 그리는 Jinja 화면(로그인)이다 — #main-content 도
    스켈레톤도 없으므로 그 둘을 기다리면 매번 타임아웃 절반씩을 헛되이 쓴다.
    """
    notes = {}
    if spa:
        try:
            page.wait_for_selector("#main-content", state="attached", timeout=timeout_ms // 2)
        except Exception:
            notes["main_content"] = "#main-content 가 나타나지 않음"
        try:
            page.wait_for_function("() => !document.querySelector('.k-skel')",
                                   timeout=timeout_ms // 2)
        except Exception:
            notes["skeleton"] = "스켈레톤(.k-skel)이 계속 남아 있음"
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms // 2)
    except Exception:
        notes["networkidle"] = "네트워크가 조용해지지 않음(폴링 화면일 수 있음)"
    try:
        page.evaluate("() => document.fonts ? document.fonts.ready.then(() => true) : true")
    except Exception:
        pass
    page.wait_for_timeout(settle_ms)
    return notes


_SCROLL_METRICS_JS = """
() => {
  const de = document.documentElement;
  let extra = 0, container = null;
  for (const sel of ['#main-content', 'main', '.c-content', '.c-chat-embed']) {
    for (const el of document.querySelectorAll(sel)) {
      const over = el.scrollHeight - el.clientHeight;
      if (over > extra) { extra = over; container = sel; }
    }
  }
  return {
    docScrolls: de.scrollHeight > de.clientHeight + 1,
    extra: Math.round(extra), container,
  };
}
"""

# Some screens are taller than any sane screenshot; stop growing at this point.
MAX_EXPANDED_HEIGHT = 8000


def expand_for_full_capture(page, viewport: Viewport) -> int | None:
    """Grow the viewport so an app-shell layout still yields a full-content shot.

    ``.c-app`` pins itself to the viewport and lets ``#main-content`` scroll
    internally, so ``full_page=True`` alone only ever captures the first fold.
    Growing the *viewport* (rather than hacking CSS) lets the real responsive
    layout do the work. Assertions have already been measured at the nominal
    size before this runs, so the numbers are unaffected.
    """
    metrics = page.evaluate(_SCROLL_METRICS_JS)
    if metrics.get("docScrolls") or metrics.get("extra", 0) <= 1:
        return None
    target = min(viewport.height + int(metrics["extra"]) + 8, MAX_EXPANDED_HEIGHT)
    if target <= viewport.height:
        return None
    page.set_viewport_size({"width": viewport.width, "height": target})
    page.wait_for_timeout(200)
    return target


def capture_route(page, *, base_url: str, route: Route, hash_path: str, theme: str,
                  viewport: Viewport, out_root: Path, full_page: bool = True,
                  settle_ms: int = DEFAULT_SETTLE_MS, timeout_ms: int = DEFAULT_NAV_TIMEOUT_MS,
                  ignores=None, interact_modals: bool = False) -> dict:
    """Navigate to one screen and return its full result record.

    `interact_modals` 를 켜면 스크린샷·검사를 마친 뒤 **화면을 눌러 본다** — 모달을 열어
    검사한다. 이게 없던 동안 하네스는 클릭을 0회 했고, 그래서 관리자 상세 모달 28개가
    깨진 채로 992페이지 100% 통과 아래 살아남았다(`interact.py` 주석 참조).
    화면 상태를 바꾸므로 **반드시 다른 모든 측정이 끝난 뒤**에 한다.
    """
    console_errors: list[str] = []
    page_errors: list[str] = []

    def on_console(message):
        if message.type == "error":
            console_errors.append(f"{message.text}")

    def on_pageerror(error):
        page_errors.append(str(error).strip().splitlines()[0] if str(error) else "unknown error")

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)

    target = route.url(base_url, hash_path)
    record: dict = {
        "route": route.id, "label": route.label, "console_kind": route.console,
        "hash_path": hash_path, "theme": theme, "viewport": viewport.name,
        "viewport_width": viewport.width, "viewport_height": viewport.height,
        "device_scale_factor": viewport.scale, "url": target,
    }
    try:
        # HashRouter: a goto that only changes the fragment would be an in-page
        # navigation and would keep the previous screen's React state. Force a
        # real document load so every capture starts from the same place.
        page.goto("about:blank", wait_until="domcontentloaded", timeout=timeout_ms)
        console_errors.clear()
        page_errors.clear()
        response = page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
        record["http_status"] = response.status if response else None
        record["settle_notes"] = _settle(page, settle_ms=settle_ms, timeout_ms=timeout_ms,
                                         spa=not route.is_public)
        record["final_url"] = page.url
        probe = assertions.evaluate(page, expected_theme=theme, viewport_width=viewport.width)
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["final_url"] = page.url
        record["assertions"] = {
            "auth_ok": {"status": "fail", "count": 1, "note": record["error"]},
        }
        page.remove_listener("console", on_console)
        page.remove_listener("pageerror", on_pageerror)
        return record

    shot_dir = out_root / theme / viewport.name
    shot_dir.mkdir(parents=True, exist_ok=True)
    shot_path = shot_dir / f"{route.id}.png"
    expanded = None
    try:
        if full_page:
            expanded = expand_for_full_capture(page, viewport)
            if expanded:
                record["expanded_height"] = expanded
        page.screenshot(path=str(shot_path), full_page=full_page, animations="disabled",
                        timeout=timeout_ms)
        record["screenshot"] = str(shot_path.relative_to(out_root)).replace("\\", "/")
        record["screenshot_bytes"] = shot_path.stat().st_size
    except Exception as exc:
        record["screenshot"] = None
        record["screenshot_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if expanded:
            page.set_viewport_size({"width": viewport.width, "height": viewport.height})

    overflow = probe.get("overflow") or {}
    record["probe"] = {
        "main": probe.get("main"),
        "overflow_scroll_width": overflow.get("scrollWidth"),
        "overflow_client_width": overflow.get("clientWidth"),
        "empty_title": probe.get("emptyTitle"),
        "still_loading": probe.get("stillLoading"),
    }
    record["assertions"] = assertions.classify(
        probe, expected_theme=theme, viewport_width=viewport.width,
        final_url=page.url, console_errors=console_errors, page_errors=page_errors,
        ignores=ignores, public=route.is_public,
    )

    # CTR-05: 대비(WCAG) 측정을 이 캡처 루프에 얹는다 — 추가 네비게이션 없이 같은 페이지에서
    # 한 번 더 evaluate만 돈다. contrast 모듈이 capture 모듈을 import하므로(순환 방지) 여기서는
    # 지연 import한다.
    try:
        from .contrast import contrast_verdict, evaluate_contrast

        record["assertions"]["contrast"] = contrast_verdict(evaluate_contrast(page))
    except Exception as exc:  # noqa: BLE001 — 대비 측정 실패가 캡처 결과 전체를 버리게 하면 안 된다
        record["assertions"]["contrast"] = {
            "status": "skip", "count": 0, "note": f"{type(exc).__name__}: {exc}",
        }

    # 모달 검사는 맨 마지막이다 — 클릭이 화면을 바꾸므로 그 앞의 어떤 측정도 오염되면 안 된다.
    if interact_modals and not route.is_public:
        try:
            modals = interact.open_modals(page)
            record["modals"] = modals
            if modals:
                record["assertions"].update(interact.classify_modals(modals))
        except Exception as exc:  # noqa: BLE001 — 모달 탐색 실패가 캡처 결과를 버리게 하면 안 된다
            record["modal_error"] = f"{type(exc).__name__}: {exc}"

    page.remove_listener("console", on_console)
    page.remove_listener("pageerror", on_pageerror)
    return record


def write_manifest(out_root: Path, payload: dict) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    path = out_root / "results.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
