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
  fab_overlap             떠 있는 요소(마스코트 FAB 등)가 버튼·입력을 덮어 못 누르게 됨
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
    "fab_overlap",
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
      // 요소 전체 텍스트로 센다 — Range는 자식까지 덮으므로 직접 텍스트만 세면 분모가 틀린다.
      const fullText = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (fullText.length >= 6) {
        try {
          const range = document.createRange();
          range.selectNodeContents(el);
          // getClientRects()는 '줄'이 아니라 '텍스트 조각'마다 사각형을 준다. 한 줄에 인라인
          // 자식이 셋이면 사각형도 셋이라, 그대로 세면 멀쩡한 줄을 3줄로 오해한다(실제로
          // 폭 1000px짜리 항목이 3줄로 잡혔다). 같은 줄은 상단 좌표가 같으므로 그걸로 묶는다.
          const tops = new Set();
          for (const r of range.getClientRects()) {
            if (r.width > 0.5 && r.height > 0.5) tops.add(Math.round(r.top));
          }
          lines = tops.size;
          if (lines > 1) charsPerLine = fullText.length / lines;
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

  // --- 떠 있는 요소가 조작 컨트롤을 덮는가 ---------------------------------
  // 마스코트 FAB 같은 position:fixed 요소는 문서 흐름 밖에 있어서, 화면마다 하단 여백을
  // 얼마나 뒀는지와 무관하게 그 위에 얹힌다. 셸에 여백을 줘도 화면이 100vh 계산으로
  // 자체 높이를 잡으면 그 여백을 벗어난다 — 실제로 놀이방 채팅의 '보내기' 버튼이
  // FAB 밑에 깔렸다. 눈으로 보기 전에는 아무 검사도 이걸 잡지 못했다.
  //
  // 겹침 자체보다 **누를 수 없게 되는 것**이 문제이므로, 겹친 지점에서
  // elementFromPoint 가 그 컨트롤을 돌려주는지까지 본다. 살짝 스치기만 하고 여전히
  // 누를 수 있으면 통과다.
  //
  // 스크롤 맨 위에서만 재면 부족하다. 화면 하단에 붙는 컨트롤은 **끝까지 내렸을 때**
  // 비로소 FAB 과 만난다. 그래서 현재 위치와 맨 아래 두 지점에서 재고 합친다.
  // 프로브는 스크린샷보다 먼저 돌기 때문에(capture.py), 잰 뒤 스크롤을 정확히 되돌린다.
  out.fabOverlap = [];
  const floaters = Array.from(document.querySelectorAll('body *')).filter((el) => {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' || cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity || '1') < 0.1) return false;
    const r = el.getBoundingClientRect();
    // 전면 오버레이(모달 배경 등)는 대상이 아니다 — 덮는 게 목적인 요소다.
    return r.width > 8 && r.height > 8 && r.width < innerWidth * 0.5 && r.height < innerHeight * 0.5;
  });
  const seenCovered = new Set();
  function scanCovered(where) {
    const controls = document.querySelectorAll('button, a[href], input, select, textarea, [role="button"]');
    for (const el of controls) {
      if (out.fabOverlap.length >= MAX) return;
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;
      if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
      for (const f of floaters) {
        if (f === el || f.contains(el) || el.contains(f)) continue;
        const fr = f.getBoundingClientRect();
        const ox = Math.min(r.right, fr.right) - Math.max(r.left, fr.left);
        const oy = Math.min(r.bottom, fr.bottom) - Math.max(r.top, fr.top);
        if (ox <= 0 || oy <= 0) continue;
        // 겹친 영역의 한가운데를 눌러 본다. 그 컨트롤이 안 나오면 실제로 가려진 것이다.
        const px = Math.max(r.left, fr.left) + ox / 2;
        const py = Math.max(r.top, fr.top) + oy / 2;
        const hit = document.elementFromPoint(px, py);
        if (hit && (hit === el || el.contains(hit))) continue;  // 여전히 눌린다
        const key = cssPath(el) + '|' + snippet(el);
        if (seenCovered.has(key)) continue;
        seenCovered.add(key);
        out.fabOverlap.push({
          control: cssPath(el), text: snippet(el), floater: cssPath(f), where: where,
          coveredPct: Math.round((ox * oy) / (r.width * r.height) * 100),
          at: [Math.round(px), Math.round(py)],
        });
        break;
      }
    }
  }
  scanCovered('현재 위치');
  // 맨 아래로 내려 한 번 더.
  //
  // 문서가 스크롤한다고 가정하면 안 된다. 이 앱의 셸은 자신을 뷰포트에 고정하고
  // **#main-content 가 스크롤**한다(capture.py 의 _SCROLL_METRICS_JS 도 같은 이유로
  // 컨테이너를 따로 찾는다). window.scrollTo 만 부르면 아무 일도 일어나지 않아,
  // 검사가 통과했다고 착각하게 된다 — 실제로 그렇게 헛돌았다.
  let scroller = null, maxOver = 0;
  for (const el of [de, document.body, ...document.querySelectorAll('#main-content, main, .c-content')]) {
    if (!el) continue;
    const over = el.scrollHeight - el.clientHeight;
    if (over > maxOver) { maxOver = over; scroller = el; }
  }
  if (scroller && maxOver > 1 && out.fabOverlap.length < MAX) {
    const isDoc = (scroller === de || scroller === document.body);
    const y0 = isDoc ? window.scrollY : scroller.scrollTop;
    if (isDoc) window.scrollTo(0, de.scrollHeight); else scroller.scrollTop = scroller.scrollHeight;
    void de.getBoundingClientRect();  // 레이아웃 강제 반영
    scanCovered('맨 아래');
    if (isDoc) window.scrollTo(0, y0); else scroller.scrollTop = y0;  // 스크린샷이 뒤에 찍힌다
    void de.getBoundingClientRect();
  }
  out.fabScroller = scroller ? cssPath(scroller) : null;
  out.fabScrollOver = Math.round(maxOver);
  out.fabOverlapCount = out.fabOverlap.length;

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

    # 떠 있는 요소가 컨트롤을 덮어 **누를 수 없게** 만든 경우만 실패다. 살짝 스치기만 하고
    # 여전히 눌리면(elementFromPoint 가 그 컨트롤을 돌려주면) 프로브 단계에서 걸러진다.
    overlap = probe.get("fabOverlap") or []
    overlap_count = probe.get("fabOverlapCount", len(overlap))
    results["fab_overlap"] = (
        _verdict("fail", overlap_count, [
            f"[{o.get('where', '?')}] {o['control']} «{o['text']}» 를 {o['floater']} 가"
            f" {o['coveredPct']}% 덮음 (({o['at'][0]},{o['at'][1]}) 에서 클릭이 가로채짐)"
            for o in overlap
        ])
        if overlap_count else _verdict("pass")
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
