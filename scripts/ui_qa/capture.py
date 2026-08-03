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

from . import assertions
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
VIEWPORTS: tuple[Viewport, ...] = (
    Viewport("390x844", 390, 844),
    Viewport("768x1024", 768, 1024),
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
            raise SystemExit(
                f"알 수 없는 뷰포트: {raw}\n사용 가능: {', '.join(VIEWPORTS_BY_NAME)}")
        vp = VIEWPORTS_BY_NAME[name]
        if vp not in out:
            out.append(vp)
    return out


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


def new_context(browser, *, storage_state: str, user_id: str, theme: str, viewport: Viewport):
    context = browser.new_context(
        storage_state=storage_state,
        viewport={"width": viewport.width, "height": viewport.height},
        device_scale_factor=viewport.scale,
        color_scheme=theme,  # matches App.jsx prefersDark() fallback
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        reduced_motion="reduce",
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
    """Return ``(hash_path, note)`` for a detail route, or ``(None, reason)``."""
    for endpoint in route.discover:
        url = f"{base_url.rstrip('/')}{endpoint}"
        try:
            response = context.request.get(url, timeout=15_000)
        except Exception as exc:
            log(f"[capture] {route.id}: {endpoint} 호출 실패 ({exc})")
            continue
        if response.status != 200:
            log(f"[capture] {route.id}: {endpoint} -> HTTP {response.status}")
            continue
        try:
            payload = response.json()
        except Exception:
            continue
        found = _first_id(payload)
        if found:
            return route.hash_template.format(id=found), f"{endpoint} 첫 항목 id={found}"
    return None, "표시할 데이터가 없어 상세 id를 찾지 못했습니다 (" + ", ".join(route.discover) + ")"


# --------------------------------------------------------------------------- #
# navigation + capture
# --------------------------------------------------------------------------- #
def _settle(page, *, settle_ms: int, timeout_ms: int) -> dict:
    """Wait for the SPA to stop moving. Every wait is best-effort: a screen that
    polls forever must not abort the run, it just gets captured as-is."""
    notes = {}
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
                  ignores=None) -> dict:
    """Navigate to one screen and return its full result record."""
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
        record["settle_notes"] = _settle(page, settle_ms=settle_ms, timeout_ms=timeout_ms)
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
        ignores=ignores,
    )
    page.remove_listener("console", on_console)
    page.remove_listener("pageerror", on_pageerror)
    return record


def write_manifest(out_root: Path, payload: dict) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    path = out_root / "results.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
