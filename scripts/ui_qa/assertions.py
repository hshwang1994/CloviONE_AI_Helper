"""Per-page geometry / DOM / console assertions.

Everything that needs the live DOM is collected in one ``page.evaluate`` pass
(``PROBE_JS``) so a page is only measured once; the Python side turns those raw
measurements into pass / fail / skip verdicts per assertion class.

Assertion classes (these strings are what ``--fail-on`` accepts):

  auth_ok                 the route actually rendered, not a /login bounce
  theme_applied           <html data-theme> matches the theme we forced
  horizontal_overflow     documentElement.scrollWidth <= clientWidth + 1
  console_errors          console.error / console message type "error"
  page_errors             uncaught exceptions (Playwright "pageerror")
  broken_images           <img> with naturalWidth === 0 after load
  duplicate_ids           the same id used by more than one element
  tiny_text               (width >= 2200 only) rendered text under 12 CSS px
  narrow_main             (width >= 3840 only) content column < 60% of viewport
  vertical_text_collapse  글자가 3자 미만/줄로 끊겨 세로로 흐르는 상태(줄 수로 직접 측정)
"""

from __future__ import annotations

import re
from typing import Any

# Only applied at very wide viewports — a 12px floor is a HiDPI/4K legibility
# rule, not something to enforce on a 390px phone.
TINY_TEXT_MIN_VIEWPORT = 2200
TINY_TEXT_MIN_PX = 12.0
# The "4K에서 양옆이 텅 빈다" check.
NARROW_MAIN_MIN_VIEWPORT = 3840
NARROW_MAIN_MIN_RATIO = 0.60

CLASSES = (
    "auth_ok", "theme_applied", "horizontal_overflow", "console_errors", "page_errors",
    "broken_images", "duplicate_ids", "tiny_text", "narrow_main", "vertical_text_collapse",
)

MAX_SAMPLES = 5

PROBE_JS = r"""
(config) => {
  const de = document.documentElement;
  const MAX = config.maxSamples || 5;
  const out = {
    url: location.href,
    theme: de.getAttribute('data-theme'),
    viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio },
  };

  // --- small helpers -------------------------------------------------------
  function cssPath(el) {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 4) {
      let part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift(part + '#' + node.id); break; }
      const cls = (node.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
      if (cls.length) part += '.' + cls.join('.');
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  }
  function snippet(el) {
    return (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  }
  function visible(el, rect) {
    if (rect.width <= 0 || rect.height <= 0) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  }
  // Real "1ch" per distinct font shorthand, measured once and cached — the
  // 2ch threshold is meaningless if we guess it from font-size alone.
  const chCache = new Map();
  const meter = document.createElement('span');
  meter.setAttribute('aria-hidden', 'true');
  meter.style.cssText = 'position:absolute;left:-9999px;top:-9999px;white-space:pre;visibility:hidden';
  document.body && document.body.appendChild(meter);
  function chWidth(fontShorthand) {
    if (chCache.has(fontShorthand)) return chCache.get(fontShorthand);
    let w = 8;
    try {
      meter.style.font = fontShorthand;
      meter.textContent = '00000000';
      w = meter.getBoundingClientRect().width / 8;
    } catch (e) { /* keep fallback */ }
    if (!isFinite(w) || w <= 0) w = 8;
    chCache.set(fontShorthand, w);
    return w;
  }

  // --- horizontal overflow -------------------------------------------------
  out.overflow = {
    scrollWidth: de.scrollWidth,
    clientWidth: de.clientWidth,
    bodyScrollWidth: document.body ? document.body.scrollWidth : 0,
    offenders: [],
  };
  if (de.scrollWidth > de.clientWidth + 1) {
    const limit = de.clientWidth + 1;
    const all = document.body ? document.body.querySelectorAll('*') : [];
    for (const el of all) {
      const r = el.getBoundingClientRect();
      if (!visible(el, r)) continue;
      const right = r.right + window.scrollX;
      if (right > limit) {
        out.overflow.offenders.push({
          selector: cssPath(el), right: Math.round(right),
          width: Math.round(r.width), text: snippet(el),
        });
        if (out.overflow.offenders.length >= MAX) break;
      }
    }
  }

  // --- main content width (4K empty-sides check) ---------------------------
  // #main-content fills the space next to the sidebar, so measuring only that
  // never sees the cap that actually strands the pixels. The column users read
  // is capped further in: the legacy shell caps .c-content at
  // max-width:min(2040px,100%) and the MUI shell caps a class-less <Box>.
  // "usedWidth" — the union of every visible, non-fixed box inside the main
  // region — measures the horizontal extent the layout actually occupies and
  // does not depend on any class name, so it survives the redesign.
  const mainEl = document.querySelector('#main-content') || document.querySelector('main');
  const contentEl = mainEl
    ? (mainEl.querySelector('.c-content') || mainEl.querySelector('.c-chat-embed'))
    : document.querySelector('.c-content');
  function widthOf(el) { return el ? Math.round(el.getBoundingClientRect().width) : null; }
  let minLeft = Infinity, maxRight = -Infinity, counted = 0;
  if (mainEl) {
    for (const el of mainEl.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') continue;
      if (cs.position === 'fixed') continue;  // modals/drawers are not the column
      minLeft = Math.min(minLeft, r.left);
      maxRight = Math.max(maxRight, r.right);
      counted++;
    }
  }
  out.main = {
    found: !!mainEl,
    mainSelector: mainEl ? cssPath(mainEl) : null,
    mainWidth: widthOf(mainEl),
    contentSelector: contentEl ? cssPath(contentEl) : null,
    contentWidth: widthOf(contentEl),
    usedWidth: counted ? Math.round(maxRight - minLeft) : null,
    usedElements: counted,
    viewportWidth: window.innerWidth,
  };

  // --- duplicate ids -------------------------------------------------------
  const idCounts = new Map();
  for (const el of document.querySelectorAll('[id]')) {
    const id = el.id;
    if (!id) continue;
    idCounts.set(id, (idCounts.get(id) || 0) + 1);
  }
  out.duplicateIds = [...idCounts.entries()]
    .filter(([, n]) => n > 1)
    .map(([id, n]) => ({ id, count: n }))
    .slice(0, MAX * 2);

  // --- broken images -------------------------------------------------------
  out.brokenImages = [];
  for (const img of document.images) {
    const src = img.currentSrc || img.getAttribute('src') || '';
    if (!src) continue;
    if (img.complete && img.naturalWidth === 0) {
      out.brokenImages.push({ src: src.slice(0, 160), selector: cssPath(img) });
      if (out.brokenImages.length >= MAX) break;
    }
  }

  // --- text walk: tiny text + vertical collapse ----------------------------
  out.tinyText = [];
  out.verticalCollapse = [];
  const wantTiny = window.innerWidth >= config.tinyTextMinViewport;
  const all = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of all) {
    const tag = el.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'SVG') continue;
    // Only leaf-ish text holders: at least one direct non-blank text node.
    let ownText = '';
    for (const node of el.childNodes) {
      if (node.nodeType === 3) ownText += node.nodeValue;
    }
    ownText = ownText.replace(/\s+/g, ' ').trim();
    if (!ownText) continue;
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) continue;
    const cs = getComputedStyle(el);
    const fontSize = parseFloat(cs.fontSize) || 0;

    if (wantTiny && fontSize > 0 && fontSize < config.tinyTextMinPx) {
      if (out.tinyText.length < MAX) {
        out.tinyText.push({
          selector: cssPath(el), fontSize: Math.round(fontSize * 100) / 100,
          text: ownText.slice(0, 60),
        });
      }
      out.tinyTextCount = (out.tinyTextCount || 0) + 1;
    }

    // Vertical collapse: 글자가 몇 자씩 끊겨 세로로 흐르는 상태.
    //
    // 처음에는 '폭이 2자 미만인 상자'만 봤는데, 실제 사례를 놓쳤다 — 표의 한 열이 몇 px로
    // 굶으면서 셀마다 2~3자씩 줄바꿈되고 페이지가 3,896px까지 늘어났는데도 30/30 통과로
    // 보고했다. 폭 임계값은 증상을 짐작하는 방식이라 이런 걸 놓친다.
    //
    // 그래서 증상을 직접 잰다: 텍스트에 Range를 씌워 줄 상자 개수를 세고 '줄당 글자 수'를
    // 구한다. 그게 사람이 보는 것이고, 폰트나 여백이나 폭이 어디서 사라졌는지 가정할 필요가 없다.
    if (ownText.length >= 2) {
      const ch = chWidth(cs.font || (cs.fontSize + ' ' + cs.fontFamily));
      const lineHeight = parseFloat(cs.lineHeight) || fontSize * 1.2;
      let charsPerLine = null;
      let lines = 0;
      if (ownText.length >= 6) {
        try {
          const range = document.createRange();
          range.selectNodeContents(el);
          lines = range.getClientRects().length;
          if (lines > 1) charsPerLine = ownText.length / lines;
        } catch (e) { /* 측정 불가면 아래 폭 기준으로만 판단한다 */ }
      }
      const narrowBox = rect.width > 0 && rect.width < ch * 2 && rect.height >= lineHeight * 2;
      const shredded = charsPerLine != null && lines >= 3 && charsPerLine < 3;
      if (narrowBox || shredded) {
        if (out.verticalCollapse.length < MAX) {
          out.verticalCollapse.push({
            selector: cssPath(el), width: Math.round(rect.width * 10) / 10,
            ch: Math.round(ch * 10) / 10, height: Math.round(rect.height),
            lines: lines,
            charsPerLine: charsPerLine == null ? null : Math.round(charsPerLine * 10) / 10,
            text: ownText.slice(0, 40),
          });
        }
        out.verticalCollapseCount = (out.verticalCollapseCount || 0) + 1;
      }
    }
  }
  out.tinyTextCount = out.tinyTextCount || 0;
  out.verticalCollapseCount = out.verticalCollapseCount || 0;
  out.tinyTextChecked = wantTiny;

  // --- app-level state worth recording (not a failure by itself) -----------
  const denied = document.querySelector('.k-empty-title');
  out.emptyTitle = denied ? snippet(denied) : null;
  out.hasErrorState = !!document.querySelector('.k-error, .k-errorstate');
  out.stillLoading = !!document.querySelector('.k-skel');

  meter.remove && meter.remove();
  return out;
}
"""


def _verdict(status: str, count: int = 0, samples: Any = None, note: str = "") -> dict:
    result = {"status": status, "count": count}
    if samples:
        result["samples"] = samples[:MAX_SAMPLES]
    if note:
        result["note"] = note
    return result


def evaluate(page, *, expected_theme: str, viewport_width: int) -> dict:
    """Run the probe in the page and return the raw measurement dict."""
    return page.evaluate(PROBE_JS, {
        "maxSamples": MAX_SAMPLES,
        "tinyTextMinViewport": TINY_TEXT_MIN_VIEWPORT,
        "tinyTextMinPx": TINY_TEXT_MIN_PX,
        "expectedTheme": expected_theme,
        "viewportWidth": viewport_width,
    })


def compile_ignores(patterns: list[str] | None) -> list[re.Pattern]:
    return [re.compile(p) for p in (patterns or [])]


def _filter_messages(messages: list[str], ignores: list[re.Pattern]) -> list[str]:
    if not ignores:
        return messages
    return [m for m in messages if not any(p.search(m) for p in ignores)]


def classify(probe: dict, *, expected_theme: str, viewport_width: int, final_url: str,
             console_errors: list[str], page_errors: list[str],
             ignores: list[re.Pattern] | None = None) -> dict:
    """Turn one page's raw measurements into per-class verdicts."""
    ignores = ignores or []
    results: dict[str, dict] = {}

    # auth_ok — a bounce to /login means the capture is worthless, say so loudly.
    if "/login" in final_url:
        results["auth_ok"] = _verdict("fail", 1, [final_url], "세션 없음 → 로그인 화면으로 튕김")
    elif "/change-password" in final_url:
        results["auth_ok"] = _verdict("fail", 1, [final_url], "비밀번호 변경 강제 상태")
    else:
        results["auth_ok"] = _verdict("pass")

    actual_theme = probe.get("theme")
    results["theme_applied"] = (
        _verdict("pass") if actual_theme == expected_theme
        else _verdict("fail", 1, [f"data-theme={actual_theme!r} (기대: {expected_theme!r})"])
    )

    overflow = probe.get("overflow") or {}
    scroll_w = overflow.get("scrollWidth", 0)
    client_w = overflow.get("clientWidth", 0)
    if scroll_w > client_w + 1:
        results["horizontal_overflow"] = _verdict(
            "fail", scroll_w - client_w,
            [f"{o['selector']} right={o['right']} w={o['width']} «{o['text']}»"
             for o in overflow.get("offenders", [])],
            f"scrollWidth={scroll_w} > clientWidth={client_w}",
        )
    else:
        results["horizontal_overflow"] = _verdict(
            "pass", 0, None, f"scrollWidth={scroll_w} <= clientWidth={client_w}+1")

    console_errors = _filter_messages(console_errors, ignores)
    page_errors = _filter_messages(page_errors, ignores)
    results["console_errors"] = (
        _verdict("fail", len(console_errors), console_errors) if console_errors
        else _verdict("pass")
    )
    results["page_errors"] = (
        _verdict("fail", len(page_errors), page_errors) if page_errors else _verdict("pass")
    )

    broken = probe.get("brokenImages") or []
    results["broken_images"] = (
        _verdict("fail", len(broken), [f"{b['selector']} src={b['src']}" for b in broken])
        if broken else _verdict("pass")
    )

    dupes = probe.get("duplicateIds") or []
    results["duplicate_ids"] = (
        _verdict("fail", len(dupes), [f"#{d['id']} x{d['count']}" for d in dupes])
        if dupes else _verdict("pass")
    )

    if viewport_width < TINY_TEXT_MIN_VIEWPORT:
        results["tiny_text"] = _verdict(
            "skip", 0, None, f"뷰포트 폭 {viewport_width} < {TINY_TEXT_MIN_VIEWPORT}")
    else:
        tiny = probe.get("tinyText") or []
        count = probe.get("tinyTextCount", len(tiny))
        results["tiny_text"] = (
            _verdict("fail", count,
                     [f"{t['selector']} {t['fontSize']}px «{t['text']}»" for t in tiny],
                     f"{TINY_TEXT_MIN_PX}px 미만 텍스트")
            if count else _verdict("pass", 0, None, f"{TINY_TEXT_MIN_PX}px 미만 없음")
        )

    main = probe.get("main") or {}
    if viewport_width < NARROW_MAIN_MIN_VIEWPORT:
        results["narrow_main"] = _verdict(
            "skip", 0, None, f"뷰포트 폭 {viewport_width} < {NARROW_MAIN_MIN_VIEWPORT}")
    elif not main.get("found"):
        results["narrow_main"] = _verdict("fail", 1, None, "#main-content / <main> 를 찾지 못함")
    else:
        vp = main.get("viewportWidth") or viewport_width
        widths = [w for w in (main.get("usedWidth"), main.get("contentWidth")) if w]
        measured = min(widths) if widths else (main.get("mainWidth") or 0)
        ratio = (measured / vp) if vp else 0.0
        note = (f"used={main.get('usedWidth')}px, content={main.get('contentWidth')}px "
                f"({main.get('contentSelector')}), main={main.get('mainWidth')}px, "
                f"viewport={vp}px, ratio={ratio:.2%}")
        results["narrow_main"] = (
            _verdict("pass", 0, None, note) if ratio >= NARROW_MAIN_MIN_RATIO
            else _verdict("fail", 1, None, note)
        )

    collapse = probe.get("verticalCollapse") or []
    collapse_count = probe.get("verticalCollapseCount", len(collapse))
    collapse_samples = [
        f"{c['selector']} w={c['width']}px (~{c['ch']}px/ch) h={c['height']}"
        f" lines={c.get('lines')} chars/line={c.get('charsPerLine')} «{c['text']}»"
        for c in collapse
    ]
    results["vertical_text_collapse"] = (
        _verdict("fail", collapse_count, collapse_samples)
        if collapse_count else _verdict("pass")
    )

    return results


def summarize(per_page: list[dict]) -> dict:
    """Aggregate ``{class: {pass, fail, skip}}`` over every captured page."""
    totals = {c: {"pass": 0, "fail": 0, "skip": 0} for c in CLASSES}
    for page_result in per_page:
        for name, verdict in (page_result.get("assertions") or {}).items():
            bucket = totals.setdefault(name, {"pass": 0, "fail": 0, "skip": 0})
            bucket[verdict.get("status", "skip")] = bucket.get(verdict.get("status", "skip"), 0) + 1
    return totals
