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
  image_cropped           사용자가 올린 이미지를 object-fit:cover 로 잘라 보여줌
  content_clipped         스크롤할 수 없는 상자 안에서 내용이 넘쳐 잘림
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
    "fab_overlap", "image_cropped", "content_clipped",
)

# 사용자가 올린 이미지를 비율을 무시하고 잘라 보여주는 것을 잡는다.
# 실제 결함: 자유게시판 첨부 썸네일이 objectFit:"cover" + aspect-ratio:1/1 이라 정사각형이
# 아닌 이미지를 전부 잘라냈다("이미지가 잘리고 콘텐츠 영역만 보인다" — 사용자 지시 §5).
# 장식용 일러스트(마스코트·빈화면 그림)는 aria-hidden 이거나 alt="" 라 대상이 아니다.
IMAGE_CROP_MIN_LOSS = 0.15   # 원본 면적의 15% 넘게 잘리면 결함으로 본다

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

  // --- 내용이 잘려 보이는가(overflow:hidden 인데 안이 넘침) -------------------
  //
  // 사용자 지시 §7: "화면 일부가 잘리는 문제". 스크롤이 되면 잘린 것이 아니라 접힌 것이므로
  // **스크롤할 수 없는데 넘치는** 경우만 센다(overflow hidden/clip). 그게 사용자가 볼 방법이
  // 없는 상태다.
  //
  // 넘침을 1px 이 아니라 넉넉히 잡는 이유: 그림자·포커스 링·자간 반올림으로 1~2px 넘치는 것은
  // 흔하고 아무도 못 알아챈다. 한 줄(약 24px) 넘게 잘릴 때만 결함으로 본다.
  out.clipped = [];
  {
    const MIN_CLIP = 24;
    // button/header/footer/nav 도 본다. 이 앱은 카드형 버튼(Paper component="button")을
    // 쓰고, 셸의 고정 높이 상자들이 header/footer/nav 에 산다 — div 만 훑으면 그것들이
    // 검사 밖에 남는다.
    const nodes = document.querySelectorAll(
      'div, section, article, main, aside, li, td, p, button, header, footer, nav');
    for (const el of nodes) {
      if (out.clipped.length >= MAX) break;
      const cs = getComputedStyle(el);
      const hideY = cs.overflowY === 'hidden' || cs.overflowY === 'clip';
      const hideX = cs.overflowX === 'hidden' || cs.overflowX === 'clip';
      if (!hideY && !hideX) continue;
      const overY = hideY ? el.scrollHeight - el.clientHeight : 0;
      const overX = hideX ? el.scrollWidth - el.clientWidth : 0;
      if (overY < MIN_CLIP && overX < MIN_CLIP) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 24 || r.height < 24) continue;
      // 말줄임(ellipsis)은 **의도된** 자르기다 — 잘렸다는 사실이 …로 화면에 보이고 title 로
      // 원문을 준다. 결함이 아니라 설계다.
      if (cs.textOverflow === 'ellipsis') continue;
      const text = (el.innerText || '').trim();
      if (!text) continue;   // 그림·장식만 든 상자는 이 검사의 대상이 아니다
      out.clipped.push({
        selector: cssPath(el), overY: Math.round(overY), overX: Math.round(overX),
        box: Math.round(r.width) + 'x' + Math.round(r.height), text: text.slice(0, 50),
      });
    }
  }

  // --- 사용자 이미지가 잘려 보이는가 ---------------------------------------
  //
  // object-fit:cover 는 상자를 채우려고 **원본을 잘라낸다**. 아바타처럼 얼굴만 보이면 되는
  // 자리에서는 맞지만, 사용자가 올린 첨부·본문 이미지에 쓰면 내용이 잘려 나간다.
  // 실제로 자유게시판 첨부가 cover + 1:1 이라 정사각형이 아닌 그림을 전부 잘랐다.
  //
  // 장식(aria-hidden 이거나 alt="")은 제외한다 — 마스코트·빈화면 일러스트는 잘려도
  // 정보가 사라지지 않고, 오히려 꽉 채우는 편이 맞는 경우가 많다.
  out.croppedImages = [];
  for (const img of document.images) {
    if (out.croppedImages.length >= MAX) break;
    if (!img.naturalWidth || !img.naturalHeight) continue;
    if (img.getAttribute('aria-hidden') === 'true') continue;
    if (!(img.getAttribute('alt') || '').trim()) continue;   // 장식
    const cs = getComputedStyle(img);
    if (cs.objectFit !== 'cover') continue;
    const r = img.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    // cover 는 상자를 덮도록 확대한 뒤 넘치는 쪽을 자른다. 남는 비율을 면적으로 계산한다.
    const scale = Math.max(r.width / img.naturalWidth, r.height / img.naturalHeight);
    const shownW = Math.min(img.naturalWidth * scale, r.width);
    const shownH = Math.min(img.naturalHeight * scale, r.height);
    const lost = 1 - (shownW * shownH) / (img.naturalWidth * scale * img.naturalHeight * scale);
    if (lost < config.imageCropMinLoss) continue;
    out.croppedImages.push({
      selector: cssPath(img), alt: (img.getAttribute('alt') || '').slice(0, 40),
      natural: img.naturalWidth + 'x' + img.naturalHeight,
      box: Math.round(r.width) + 'x' + Math.round(r.height),
      lostPct: Math.round(lost * 100),
    });
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
      // '세로로 흐른다'는 것은 **좁은 상자**에서만 일어난다. 폭이 넉넉하면 줄당 글자 수가
      // 적게 나올 수 없다 — 그런 값이 나왔다면 레이아웃이 아니라 측정이 튄 것이다.
      // 실제로 폭 1918px(한 줄에 ~197자 들어감) 요소가 '3줄 2.7자/줄'로 잡혔다. 자식이
      // 세로로 쌓인 컨테이너였고, 그건 글자가 으스러진 것이 아니라 그냥 여러 줄이다.
      // 12자도 못 담는 상자만 후보로 둔다(원래 잡으려던 결함은 24px·8px/ch 였다).
      const couldHoldAWord = ch > 0 && rect.width >= ch * 12;
      const shredded = !couldHoldAWord && charsPerLine != null && lines >= 3 && charsPerLine < 3;
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
        // 겹치는 자리가 뷰포트 **밖**이면 애초에 아무도 못 누르는 지점이다. 그런데
        // elementFromPoint 는 화면 밖 좌표에 늘 null 을 돌려주므로, 걸러내지 않으면
        // "가려졌다"로 잘못 잡힌다. 실제로 스킵링크('본문 바로가기' — 평소 top:8 에
        // translateY(-200%) 로 화면 위에 숨어 있다)가 긴 목록의 맨 위 줄과 y<0 에서
        // 겹쳐 오탐이 났다. 눈에 보이지도, 눌리지도 않는 겹침은 결함이 아니다.
        if (px < 0 || py < 0 || px > innerWidth || py > innerHeight) continue;
        const coveredPct = Math.round((ox * oy) / (r.width * r.height) * 100);
        const hit = document.elementFromPoint(px, py);
        const stillClickable = !!(hit && (hit === el || el.contains(hit)));
        /* **제출 버튼이 크게 덮인 경우는 눌리더라도 결함이다.**
         *
         * 원래 규칙("겹치기만 하면 통과, 못 누르면 실패")은 옳다 — 긴 표의 어떤 행은 늘
         * FAB 밑을 지나가므로 겹침을 전부 실패로 세면 게이트가 곧 무시된다.
         *
         * 그런데 실측해 보니 새 티켓의 '티켓 만들기'가 1440 이하에서 **45px(약 47%) 덮이는데도**
         * 가운데가 남아 있어 이 검사를 통과했다. 사용자 눈에는 버튼이 반쯤 잘려 보이고, 덮인
         * 쪽을 누르면 엉뚱한 것이 눌린다. 이 저장소가 같은 함정을 이미 세 번 밟았고
         * (놀이방 '보내기', AI 채팅 '전송', 새 티켓 '티켓 만들기') 셋 다 제출 버튼이었다.
         *
         * 그래서 **제출 컨트롤에 한해** 면적 기준을 더한다. 한 페이지에 많아야 한둘이라
         * 소음이 되지 않고, 정확히 세 번 터진 그 자리를 짚는다. */
        const isSubmit = (el.getAttribute('type') || '').toLowerCase() === 'submit';
        const heavySubmit = isSubmit && coveredPct >= 25;
        if (stillClickable && !heavySubmit) continue;  // 여전히 눌리고 크게 가리지도 않는다
        const key = cssPath(el) + '|' + snippet(el);
        if (seenCovered.has(key)) continue;
        seenCovered.add(key);
        // **스크롤로 비켜낼 수 있는가**로 피해의 크기가 갈린다.
        //   못 비킨다 — 화면에 고정된 컨트롤이 영구히 안 눌린다. 사용자는 방법이 없다.
        //               (놀이방 채팅의 '보내기'가 그랬다: sticky 레일 맨 아래에 붙어 있었다.)
        //   비킬 수 있다 — 긴 표의 어떤 행이 잠시 FAB 밑에 놓인 것뿐이다. 조금 굴리면
        //               눌린다. 떠 있는 버튼을 쓰는 이상 어느 행인가는 늘 밑에 놓이므로,
        //               이걸 실패로 치면 '표가 긴 화면 = 영구 실패'가 되어 게이트가 죽는다.
        // 그래서 전자만 실패로 세고 후자는 기록만 한다.
        let pinned = true;
        for (let node = el; node && node !== document.body; node = node.parentElement) {
          const pos = getComputedStyle(node).position;
          if (pos === 'fixed' || pos === 'sticky') { pinned = true; break; }
          pinned = false;
        }
        const scrollable = de.scrollHeight > de.clientHeight + 1
          || Array.from(document.querySelectorAll('#main-content, main, .c-content'))
               .some((s) => s.scrollHeight > s.clientHeight + 1);
        out.fabOverlap.push({
          control: cssPath(el), text: snippet(el), floater: cssPath(f), where: where,
          coveredPct: coveredPct,
          at: [Math.round(px), Math.round(py)],
          // 못 누르거나(기존 규칙), 제출 버튼이 25% 넘게 덮였거나(새 규칙).
          unreachable: (!stillClickable && (pinned || !scrollable)) || heavySubmit,
          heavySubmit: heavySubmit,
        });
        break;
      }
    }
  }
  /* 제출 버튼이 떠 있는 요소의 **세로 통로**에 놓여 있는가 — 스크롤을 흉내내지 않고 판정한다.
   *
   * 스크롤해 가며 재는 방식은 근본적으로 표본추출이라, 70px 짜리 FAB 밑을 지나가는 버튼을
   * 지점 사이에서 놓친다(25% 간격이면 한 걸음이 수백 px 이다). 실제로 새 티켓의 '티켓 만들기'가
   * 그렇게 빠져나가 검사가 통과했다.
   *
   * 고정 요소는 뷰포트에 붙어 있고 컨트롤은 스크롤을 따라 움직인다. 그러니 **가로 범위가
   * 겹치고 페이지가 스크롤된다면**, 그 컨트롤은 어느 스크롤 위치에선가 반드시 그 요소 밑을
   * 지난다 — 지점을 찍어 볼 필요가 없다. 대상은 제출 컨트롤로 좁힌다(§scanCovered 주석 참고). */
  function scanSubmitBand() {
    // 실제로 스크롤하는 요소를 찾는다(이 앱은 문서가 아니라 #main-content 가 구르기도 한다).
    let sc = null, over = 0;
    for (const el of [de, document.body, ...document.querySelectorAll('#main-content, main, .c-content')]) {
      if (!el) continue;
      const o = el.scrollHeight - el.clientHeight;
      if (o > over) { over = o; sc = el; }
    }
    if (!sc || over <= 1) return;
    const isDoc = (sc === de || sc === document.body);
    const y = isDoc ? window.scrollY : sc.scrollTop;

    for (const el of document.querySelectorAll('button[type="submit"], input[type="submit"]')) {
      if (out.fabOverlap.length >= MAX) return;
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;
      for (const f of floaters) {
        if (f === el || f.contains(el) || el.contains(f)) continue;
        const fr = f.getBoundingClientRect();
        const ox = Math.min(r.right, fr.right) - Math.max(r.left, fr.left);
        if (ox <= 0) continue;
        const pct = Math.round((ox / r.width) * 100);
        if (pct < 25) continue;   // 살짝 스치는 정도는 세지 않는다

        /* **그 컨트롤이 정말 저 띠까지 내려올 수 있는가.**
         *
         * 가로가 겹친다고 다 걸리는 게 아니다. 페이지 맨 위에 있는 컨트롤(검색 폼의 '검색'
         * 버튼)은 스크롤하면 위로 사라질 뿐, 아래쪽 FAB 띠로는 절대 내려오지 않는다.
         * 첫 판에서 그걸 놓쳐 검색 화면 3개를 오탐으로 잡았다.
         *
         * 스크롤을 0..over 로 굴리면 이 컨트롤의 화면 y 는 [top-(over-y), top+y] 를 훑는다.
         * 그 구간이 띠와 만날 때만 실제로 덮인다. */
        const reachTop = r.top - (over - y);
        const reachBottom = r.bottom + y;
        if (reachBottom < fr.top || reachTop > fr.bottom) continue;

        const key = 'band|' + cssPath(el);
        if (seenCovered.has(key)) continue;
        seenCovered.add(key);
        out.fabOverlap.push({
          control: cssPath(el), text: snippet(el), floater: cssPath(f), where: '세로 통로',
          coveredPct: pct, at: [Math.round(fr.left + 1), Math.round(fr.top + 1)],
          unreachable: true, submitBand: true,
        });
        break;
      }
    }
  }
  scanSubmitBand();
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
    const setY = (y) => { if (isDoc) window.scrollTo(0, y); else scroller.scrollTop = y; };
    /* **중간 스크롤 위치까지 훑는다.**
     *
     * 예전에는 '현재 위치'와 '맨 아래' 두 곳만 쟀다. 그런데 셸이 본문 아래에 여백을 주기
     * 때문에 맨 아래에서는 FAB 밑이 비어 있고, 정작 덮이는 것은 **스크롤 중간**이다 —
     * 긴 폼의 제출 버튼이 화면 우하단을 지나가는 그 순간. 새 티켓 화면의 '티켓 만들기'가
     * 정확히 그랬는데 이 검사는 통과하고 있었다(거짓 통과).
     *
     * 25% 간격으로 네 지점을 더 본다. 촘촘히 훑으면 페이지당 시간이 늘고, 이보다 성기면
     * 화면 한 장 높이(=FAB 이 덮을 수 있는 구간)를 건너뛴다. */
    const stops = [0.25, 0.5, 0.75, 1.0];
    for (const f of stops) {
      if (out.fabOverlap.length >= MAX) break;
      setY(Math.round(maxOver * f));
      void de.getBoundingClientRect();  // 레이아웃 강제 반영
      scanCovered(f >= 1 ? '맨 아래' : ('스크롤 ' + Math.round(f * 100) + '%'));
    }
    setY(y0);  // 스크린샷이 뒤에 찍힌다 — 원래 위치로 되돌린다
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
        "imageCropMinLoss": IMAGE_CROP_MIN_LOSS,
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
             ignores: list[re.Pattern] | None = None, public: bool = False) -> dict:
    """Turn one page's raw measurements into per-class verdicts."""
    ignores = ignores or []
    results: dict[str, dict] = {}

    # auth_ok — a bounce to /login means the capture is worthless, say so loudly.
    # 로그인 화면 자체를 찍는 경우에는 /login 이 정상이고, 오히려 **거기 머물러야** 한다.
    if public:
        results["auth_ok"] = (
            _verdict("pass") if "/login" in final_url
            else _verdict("fail", 1, [final_url], "로그인 화면을 찍으려 했는데 다른 곳으로 갔다")
        )
    elif "/login" in final_url:
        results["auth_ok"] = _verdict("fail", 1, [final_url], "세션 없음 → 로그인 화면으로 튕김")
    elif "/change-password" in final_url:
        results["auth_ok"] = _verdict("fail", 1, [final_url], "비밀번호 변경 강제 상태")
    else:
        results["auth_ok"] = _verdict("pass")

    actual_theme = probe.get("theme")
    # 로그인 화면은 승인된 디자인 원본이 **라이트 고정**이다(브랜드 히어로 + 흰 폼 패널).
    # data-theme 이 정말 없으므로 pass 라고 하면 거짓말이고, fail 이라고 하면 고칠 것이 없는
    # 결함이 매번 뜬다 — 이유를 남기고 건너뛴다.
    if public:
        results["theme_applied"] = _verdict(
            "skip", 0, [], "로그인 화면은 라이트 고정(승인된 디자인 원본) — 테마를 따르지 않는다")
    else:
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

    # 사용자가 올린 이미지를 잘라 보여주는 자리. 장식(aria-hidden/alt="")은 프로브에서 이미 뺐다.
    # 스크롤로 볼 수 없는 잘림. 스크롤이 되면 접힌 것이지 잘린 것이 아니다.
    clipped = probe.get("clipped") or []
    results["content_clipped"] = (
        _verdict(
            "fail", len(clipped),
            [f"{c['selector']} 상자 {c['box']} 안에서"
             f"{' 세로 ' + str(c['overY']) + 'px' if c['overY'] else ''}"
             f"{' 가로 ' + str(c['overX']) + 'px' if c['overX'] else ''} 넘침 «{c['text']}»"
             for c in clipped],
            "overflow 가 hidden 이라 스크롤로도 볼 수 없다 — 사용자에게는 그냥 잘린 화면이다",
        )
        if clipped else _verdict("pass")
    )

    cropped = probe.get("croppedImages") or []
    results["image_cropped"] = (
        _verdict(
            "fail", len(cropped),
            [f"{c['selector']} «{c['alt']}» 원본 {c['natural']} → 상자 {c['box']}"
             f" (object-fit:cover 로 {c['lostPct']}% 잘림)" for c in cropped],
            "사용자가 올린 이미지가 잘려 보인다 — 상자를 채우려고 원본을 자르고 있다",
        )
        if cropped else _verdict("pass")
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
    # 스크롤로 비켜낼 수 없는 겹침만 실패다. 비킬 수 있는 것(긴 표의 한 행이 잠깐 FAB
    # 밑에 놓이는 경우)은 떠 있는 버튼을 쓰는 이상 늘 하나쯤 생기므로 note 로만 남긴다 —
    # 그걸 실패로 세면 '표가 긴 화면 = 영구 실패'가 되어 게이트가 곧 무시된다.
    overlap = probe.get("fabOverlap") or []
    blocking = [o for o in overlap if o.get("unreachable")]
    reachable = [o for o in overlap if not o.get("unreachable")]

    def _fmt(o: dict) -> str:
        return (
            f"[{o.get('where', '?')}] {o['control']} «{o['text']}» 를 {o['floater']} 가"
            f" {o['coveredPct']}% 덮음 (({o['at'][0]},{o['at'][1]}) 에서 클릭이 가로채짐)"
        )

    note = ""
    if reachable:
        note = (
            f"스크롤하면 비켜나는 겹침 {len(reachable)}건은 실패로 세지 않았다: "
            + " / ".join(f"«{o['text']}»" for o in reachable[:3])
        )
    results["fab_overlap"] = (
        _verdict("fail", len(blocking), [_fmt(o) for o in blocking],
                 "스크롤해도 비켜나지 않는다 — 사용자는 이 컨트롤을 누를 방법이 없다")
        if blocking else _verdict("pass", 0, None, note)
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
