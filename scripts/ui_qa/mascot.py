"""클로비가 **화면에서 실제로 얼마나 크게 보이는지** 잰다 — 상자 크기가 아니라 캐릭터 크기다.

CSS 박스 크기 검사로는 절대 안 보이는 축이다. 포즈 PNG 는 사방에 투명 여백을 두고 있어서
상자 크기와 보이는 캐릭터 크기가 다르다. `app/static/brand/mascot/` 자산을 실측하면 세로 잉크
비율이 0.707~1.000 로 자산마다 30%p 가까이 벌어진다 — `Mascot.jsx` 의 상단바 `size={28}` 상자는
`clovi-idle`(0.828)이면 23.2px, `clovi-wave`(0.748)면 21.0px, `clovi-button`(0.707)이면 19.8px 다.
**같은 상자인데 어떤 포즈를 넣느냐로 기준을 넘기도 하고 못 넘기도 한다.** 상자만 재는 검사는
이 차이를 영원히 못 본다. 사용자 지시 §7 이 요구한 것은 "CSS Box 크기가 아니라 실제 Browser
에서 보이는 캐릭터의 얼굴·표정·존재감" 이다.

    visibleH = 렌더된 이미지 높이 × (자산의 알파 bbox 높이 / 자산 원본 높이)

알파 bbox 는 `<canvas>` + `getImageData` 로 브라우저 안에서 계산한다. 자산마다 한 번이면
충분하므로 **실행당 1회** 계산하고 `dist/ui-qa/<label>/mascot-ink.json` 에 캐시한다 —
route × theme × viewport 마다 다시 재면 같은 답을 수백 번 계산한다.

context 별 최소 높이(위 식의 visibleH 기준):

    topbar 22 · fab 40 · sidebar 36 · avatar 24 · inline 28 · hero 140
    empty_state 96 이면서 동시에 그 빈 화면 컨테이너 높이의 40% 이하

**실패 note 가 원인을 구분한다.** `inkFrac < 0.45` 면 자산이 여백투성이라는 뜻이고 고칠 곳은
자산 프레이밍이다. 그보다 크면 자산은 멀쩡하고 렌더 박스가 작은 것이다. 이 구분이 없으면
"그럼 크기를 키우자"는 잘못된 수리로 가서, 여백까지 같이 커진 거대한 상자가 남는다.

## 대상 범위

`/static/brand/mascot/` 아래 자산(= `lib/assets.js` 의 `MASCOT`)과, `data-mascot-context`
속성으로 화면이 **직접 선언한** 이미지만 본다. `ART`·`SPOT`·`MISC` 삽화는 마스코트 포즈가
아니라 상태 일러스트라 기본 대상이 아니다 — 포함시키고 싶으면 그 화면이 속성으로 선언한다.
추론으로 범위를 넓히지 않는 이유는 분류가 판정을 결정해 버리기 때문이다(아래 hero 참고).
"""

from __future__ import annotations

import json
from pathlib import Path

# context 별 최소 visibleH(CSS px). 렌더 박스가 아니라 **보이는 캐릭터**의 높이다.
MIN_VISIBLE_H = {
    "topbar": 22.0,
    "fab": 40.0,
    "sidebar": 36.0,
    "avatar": 24.0,
    "empty_state": 96.0,
    "hero": 140.0,
    "inline": 28.0,
}
# 빈 화면에서 클로비가 화면을 때우는 것도 결함이다(지시 18 · §7). 위아래 양쪽으로 잰다.
EMPTY_STATE_MAX_CONTAINER_RATIO = 0.40
# 이 아래면 자산 여백 문제다. 0.45 는 "그림이 상자의 절반도 못 채운다"는 뜻이다.
INK_FRAC_ASSET_MARGIN = 0.45

# 알파가 이보다 크면 잉크로 센다. 0 으로 두면 PNG 안티에일리어싱의 거의 투명한 후광까지
# 세어서 bbox 가 원본 전체로 부풀고, 그러면 이 검사는 아무 것도 못 잡는다.
INK_ALPHA_MIN = 8
# bbox 는 비율만 필요하므로 축소해서 스캔한다 — 원본 그대로 훑으면 자산 한 장에 100만 픽셀이다
# (마스코트 자산은 1024×1024). 축소가 값을 흔들지 않는지는 실측으로 확인했다: 12개 자산 전부
# 원본 스캔과 256px 스캔의 inkFracH 차이가 0.004 이하다.
INK_SAMPLE_MAX_SIDE = 256

CACHE_VERSION = 1
CACHE_NAME = "mascot-ink.json"
MAX_SAMPLES = 5

# 캐시는 두 겹이다. 디스크에는 **성공한 측정만** 남긴다 — 일시적 로드 실패를 파일에 굳히면
# 그 실행 내내, 그리고 다음 실행까지 같은 자산을 영원히 못 재게 된다. 실패는 프로세스 안에서만
# 기억해서 route 마다 재시도하는 낭비만 막는다.
_INK_CACHE: dict = {}
_INK_FAILED: dict = {}


MASCOT_PROBE_JS = r"""() => {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    return (parseFloat(st.opacity) || 0) > 0.05;
  };
  /* 떠 있는 **작은** 것만 FAB 이다.
     크기 조건이 없으면 position:fixed 인 것은 전부 FAB 이 된다 — 클로비 드로어(전체 높이
     패널)의 머리 마스코트가 FAB 기준 40px 로 판정돼 실패한다. 그건 FAB 이 아니라 패널
     머리글의 인라인 아바타다. FAB 은 화면 구석에 뜬 작은 원형 버튼이라 상자가 작다. */
  const FAB_MAX_SIDE = 120;
  const floatingButtonAncestor = (el) => {
    let n = el;
    while (n && n !== document.body) {
      const st = getComputedStyle(n);
      if (st.position === 'fixed') {
        const r = n.getBoundingClientRect();
        return r.width <= FAB_MAX_SIDE && r.height <= FAB_MAX_SIDE;
      }
      n = n.parentElement;
    }
    return false;
  };
  /* context 판정. 순서가 곧 규칙이다.
     · 화면이 선언한 것이 언제나 이긴다.
     · 상단바·사이드바를 fixed 검사보다 **먼저** 본다 — AppBar 와 Drawer 가 둘 다
       position:fixed 라, 순서를 바꾸면 상단바 클로비가 FAB 으로 분류된다.
     · `hero` 는 **추론하지 않는다**. 크기로 hero 를 정하면 큰 상자만 골라 가장 엄한 기준을
       적용하는 순환이 되고, 분류가 판정을 결정해 버린다. 화면이 선언해야 hero 다. */
  const contextOf = (img, src) => {
    const declared = img.closest('[data-mascot-context]');
    if (declared) {
      return { ctx: declared.getAttribute('data-mascot-context') || '', how: 'data-mascot-context' };
    }
    if (img.closest('.MuiAvatar-root') || /clovi-avatar\./.test(src)) {
      return { ctx: 'avatar', how: '아바타 자리' };
    }
    if (img.closest('header, [role="banner"], .MuiAppBar-root')) {
      return { ctx: 'topbar', how: '상단바 안' };
    }
    if (img.closest('nav, aside, [role="navigation"], #app-sidebar')) {
      return { ctx: 'sidebar', how: '내비게이션 안' };
    }
    if (img.closest('.MuiFab-root') || floatingButtonAncestor(img)) {
      return { ctx: 'fab', how: '떠 있는 버튼' };
    }
    if (img.closest('.k-empty')) {
      return { ctx: 'empty_state', how: '빈 화면(.k-empty) 안' };
    }
    return { ctx: 'inline', how: '본문 안' };
  };

  const items = [];
  for (const img of document.querySelectorAll('img')) {
    const src = img.currentSrc || img.getAttribute('src') || '';
    const declared = !!img.closest('[data-mascot-context]');
    if (!declared && !/\/static\/brand\/mascot\//.test(src)) continue;
    if (!vis(img)) continue;
    const r = img.getBoundingClientRect();
    const c = contextOf(img, src);
    const holder = img.closest('.k-empty');
    items.push({
      src, context: c.ctx, contextHow: c.how,
      boxW: r.width, boxH: r.height,
      natW: img.naturalWidth || 0, natH: img.naturalHeight || 0,
      objectFit: getComputedStyle(img).objectFit || 'fill',
      containerH: holder ? holder.getBoundingClientRect().height : null,
      alt: (img.getAttribute('alt') || '').slice(0, 24),
      ariaLabel: (img.closest('[aria-label]') || img).getAttribute('aria-label') || '',
    });
  }
  return { items, srcs: [...new Set(items.map((i) => i.src))] };
}"""


INK_PROBE_JS = r"""(cfg) => {
  const load = (src) => new Promise((resolve) => {
    const im = new Image();
    im.onload = () => resolve(im);
    im.onerror = () => resolve(null);
    im.src = src;
  });
  return Promise.all(cfg.srcs.map(async (src) => {
    const im = await load(src);
    if (!im || !im.naturalWidth || !im.naturalHeight) {
      return { src, error: '자산을 불러오지 못함' };
    }
    const nw = im.naturalWidth, nh = im.naturalHeight;
    const scale = Math.min(1, cfg.maxSide / Math.max(nw, nh));
    const w = Math.max(1, Math.round(nw * scale));
    const h = Math.max(1, Math.round(nh * scale));
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const g = canvas.getContext('2d', { willReadFrequently: true });
    if (!g) return { src, error: 'canvas 2d 컨텍스트를 못 얻음' };
    g.clearRect(0, 0, w, h);
    g.drawImage(im, 0, 0, w, h);
    let data;
    try {
      data = g.getImageData(0, 0, w, h).data;
    } catch (e) {
      // 교차 출처 자산이면 캔버스가 오염돼 읽을 수 없다. 모른다고 말한다.
      return { src, error: 'getImageData 차단: ' + (e && e.name ? e.name : 'SecurityError') };
    }
    let minX = w, maxX = -1, minY = h, maxY = -1;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (data[(y * w + x) * 4 + 3] <= cfg.alphaMin) continue;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
    if (maxY < 0) return { src, error: '불투명 픽셀이 하나도 없음(빈 자산)' };
    return {
      src, natW: nw, natH: nh,
      inkFracH: (maxY - minY + 1) / h,
      inkFracW: (maxX - minX + 1) / w,
      sampledAt: w + 'x' + h,
    };
  }));
}"""


# --------------------------------------------------------------------------- #
# 잉크 bbox 캐시
# --------------------------------------------------------------------------- #
def _load_cache(path: Path) -> dict:
    key = str(path)
    if key in _INK_CACHE:
        return _INK_CACHE[key]
    entries: dict = {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("version") == CACHE_VERSION:
            entries = raw.get("entries") or {}
    except Exception:  # noqa: BLE001 — 캐시가 깨졌으면 그냥 다시 잰다
        entries = {}
    _INK_CACHE[key] = entries
    _INK_FAILED.setdefault(key, {})
    return entries


def _save_cache(path: Path, entries: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": CACHE_VERSION, "entries": entries},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception:  # noqa: BLE001 — 캐시를 못 써도 측정 자체는 성립한다
        pass


def _ensure_ink(page, srcs, cache_path: Path) -> dict:
    """캐시에 없는 자산만 브라우저에서 측정하고 캐시를 갱신한다."""
    entries = _load_cache(cache_path)
    failed = _INK_FAILED.setdefault(str(cache_path), {})
    missing = [s for s in srcs if s and s not in entries and s not in failed]
    if not missing:
        return entries
    results = page.evaluate(INK_PROBE_JS, {
        "srcs": missing, "alphaMin": INK_ALPHA_MIN, "maxSide": INK_SAMPLE_MAX_SIDE,
    }) or []
    changed = False
    for res in results:
        src = res.get("src")
        if not src:
            continue
        if res.get("error"):
            failed[src] = res["error"]
            continue
        entries[src] = {
            "natW": res.get("natW"), "natH": res.get("natH"),
            "inkFracH": res.get("inkFracH"), "inkFracW": res.get("inkFracW"),
            "sampledAt": res.get("sampledAt"),
        }
        changed = True
    if changed:
        _save_cache(cache_path, entries)
    return entries


# --------------------------------------------------------------------------- #
# 측정
# --------------------------------------------------------------------------- #
def evaluate_mascot(page, *, cache_path) -> dict:
    """이미 열려 있는 페이지에서 마스코트 이미지를 찾아 원시 측정치를 낸다."""
    probe = page.evaluate(MASCOT_PROBE_JS) or {}
    items = probe.get("items") or []
    if not items:
        return {"items": [], "ink": {}, "failed": {}}
    path = Path(cache_path)
    ink = _ensure_ink(page, probe.get("srcs") or [], path)
    return {
        "items": items,
        "ink": {s: ink[s] for s in (probe.get("srcs") or []) if s in ink},
        "failed": dict(_INK_FAILED.get(str(path), {})),
        "cache": str(path),
    }


def _rendered_height(item: dict, nat_w: float, nat_h: float):
    """`object-fit` 을 반영한 **실제로 그려진 이미지 높이**.

    상자 높이를 그대로 쓰면 안 된다. `contain` 은 상자보다 작게 그려지고(마스코트가 쓰는 값),
    `cover` 는 넘치는 부분이 잘려서 보이는 높이가 상자 높이로 묶인다.
    """
    box_w = float(item.get("boxW") or 0.0)
    box_h = float(item.get("boxH") or 0.0)
    fit = (item.get("objectFit") or "fill").lower()
    if fit in ("contain", "scale-down") and nat_w > 0 and nat_h > 0:
        scale = min(box_w / nat_w, box_h / nat_h)
        if fit == "scale-down":
            scale = min(scale, 1.0)
        return nat_h * scale
    return box_h


def _fmt(value: float) -> str:
    return f"{value:.0f}" if abs(value - round(value)) < 0.05 else f"{value:.1f}"


def mascot_verdict(probe: dict, *, max_samples: int = MAX_SAMPLES) -> dict:
    """`evaluate_mascot()` 의 원시 측정을 `assertions._verdict()` 와 같은 모양으로 바꾼다.

    Playwright 없이 dict 만으로 검증할 수 있게 측정과 분리했다(`contrast.py` 와 같은 구조).
    """
    items = probe.get("items") or []
    if not items:
        return {"status": "skip", "count": 0, "note": "이 화면에 마스코트가 없다"}

    ink = probe.get("ink") or {}
    failed = probe.get("failed") or {}
    violations, unmeasured, partial = [], [], []

    for item in items:
        src = item.get("src") or ""
        short = src.rsplit("/", 1)[-1] or src
        ctx = item.get("context") or ""
        entry = ink.get(src)
        if not entry:
            unmeasured.append(f"{short}: 잉크 bbox 없음 ({failed.get(src, '측정되지 않음')})")
            continue
        minimum = MIN_VISIBLE_H.get(ctx)
        if minimum is None:
            # 선언된 context 오타 등 — 기준을 모르면 판정하지 않는다.
            unmeasured.append(f"{short}: 알 수 없는 context {ctx!r} — 기준이 없어 판정 안 함")
            continue

        nat_w = float(item.get("natW") or entry.get("natW") or 0.0)
        nat_h = float(item.get("natH") or entry.get("natH") or 0.0)
        ink_frac = float(entry.get("inkFracH") or 0.0)
        if ink_frac <= 0:
            unmeasured.append(f"{short}: 잉크 높이 0")
            continue
        rendered_h = _rendered_height(item, nat_w, nat_h)
        visible_h = rendered_h * ink_frac

        # 원인 구분 — 이것이 없으면 "크기를 키우자"는 잘못된 수리로 간다.
        cause = (f"자산 여백 문제(재프레이밍 필요, 잉크가 자산의 {ink_frac:.0%})"
                 if ink_frac < INK_FRAC_ASSET_MARGIN
                 else f"렌더 박스 문제(그려진 높이 {_fmt(rendered_h)}px, 잉크 {ink_frac:.0%})")

        if visible_h < minimum:
            violations.append(
                f"{short} [{ctx}] 보이는 높이 {_fmt(visible_h)}px < 기준 {_fmt(minimum)}px"
                f" — {cause}")
            continue

        container_h = item.get("containerH")
        if ctx == "empty_state" and not container_h:
            # 아래쪽 절반(빈 공간을 캐릭터로 때우는가)은 컨테이너 높이가 있어야 잴 수 있다.
            # 잴 수 없으면 **통과라고 하지 않고** 못 쟀다고 말한다 — 조용히 넘어가면 규칙의
            # 절반이 영원히 안 도는데 결과는 pass 로 보인다.
            partial.append(f"{short} [{ctx}] 최소 높이만 확인함 —"
                           " 컨테이너(.k-empty)를 못 찾아 '화면을 때우는가'는 판정 못 함")
        if ctx == "empty_state" and container_h:
            limit = float(container_h) * EMPTY_STATE_MAX_CONTAINER_RATIO
            if visible_h > limit:
                violations.append(
                    f"{short} [{ctx}] 보이는 높이 {_fmt(visible_h)}px 가 컨테이너"
                    f" {_fmt(float(container_h))}px 의"
                    f" {EMPTY_STATE_MAX_CONTAINER_RATIO:.0%}({_fmt(limit)}px)를 넘는다"
                    " — 빈 공간을 캐릭터로 때우고 있다")

    measured = len(items) - len(unmeasured)
    note_parts = [f"마스코트 {len(items)}개 중 {measured}개 측정"]
    if unmeasured:
        note_parts.append("판정 못 한 것: " + "; ".join(unmeasured[:max_samples]))
    if partial:
        note_parts.append("절반만 판정한 것: " + "; ".join(partial[:max_samples]))

    if measured <= 0:
        # 하나도 못 쟀으면 통과가 아니라 skip 이다.
        return {"status": "skip", "count": 0, "note": " / ".join(note_parts)}
    return {
        "status": "fail" if violations else "pass",
        "count": len(violations),
        "samples": violations[:max_samples],
        "note": " / ".join(note_parts),
    }
