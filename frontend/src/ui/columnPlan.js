/* 표 열 폭 배분 (F3 · D-529) — 한 열이 남는 폭을 혼자 먹지 않는다.
 *
 * ## 왜 다시 짰나
 *
 * 예전 배치는 `table-layout: fixed` 에서 폭 없는 `title` 열(없으면 마지막 산문 열)이 **남는 폭 전부**를 먹고, 나머지 열은 타입의
 * 바닥 rem 이 곧 폭이었다(`columnTypes.columnLayoutWidth`). 그래서 1920 에서 조직 구성원 이름 열 500px 대부분이 비고 이메일은
 * 잘렸고, 프롬프트 이름 열이 600px, AI 통계 다섯 글자 열이 800px 이었다. 1366 에서는 열 바닥 합이 판 폭을 넘어 표가 판 밖으로
 * 나가 상태 · 역할 열이 보이지 않았다. 열 폭에 「바닥」 하나만 있고 비중 · 상한 · 내용 길이가 없었기 때문이다.
 *
 * ## 규칙
 *
 * 열마다 바닥 · 비중 · 상한을 타입이 정하고(`columnTypes.COLUMN_TYPES`), 짧은 값 열은 머리글과 값 길이로 폭을 정한다. 목표는 가로
 * 스크롤을 없애는 것이 아니라 **중요한 값이 읽히는 것**이다.
 *
 *   늘어나는 글   title {14, 3, 36} · text {12, 3, 48} · name {9, 2, 18} · identifier {11, 2, 22} · path {10, 2, 24}
 *                 (바닥 rem, 비중, 상한 rem) — 남는 폭을 비중대로 상한까지 나눈다(물 채우기)
 *   내용 길이     status 6 · enum 6.5 · code 6.5 바탕 — 폭 = max(바탕, 머리글 필요 폭, 값 필요 폭)
 *   고정          count 6 · number 7 · percent · score 6 · date 8.5 · datetime 11 · select 2.5 · actions 30n + 8(n−1) + 32px
 *
 * 머리글 필요 폭 = 12px 글 폭 + 칸 여백 32 + 정렬 · 필터 표지마다 22. 값 필요 폭 = 열의 `values`(선택지 라벨 전부) 또는 받은 행의
 * 화면 낱말(`value(row)` · `hint(row)` · 글 값) 가운데 가장 긴 것(14px) + 32. 둘 다 0.5rem 단위로 올린다. 크기는 전부 rem 이라
 * 루트 글자(2560 에서 18px)를 따라 자란다.
 *
 * 열 등급(`tier`): `essential`(숨기지 않는다) · `secondary`(좁으면 숨긴다) · `context`(화면이 이미 말해 주는 값, 가장 먼저 숨긴다).
 * 식별 열(title · name · identifier · code)과 지금 정렬 중인 열은 언제나 `essential` 이다. 등급을 안 적은 열은 옛 `hideNarrow` 를
 * 따른다(있으면 secondary, 없으면 essential). 숨기는 순서는 context → secondary 이고 같은 등급 안에서는 `priority` 가 낮은 것 ·
 * 오른쪽 것부터다. `essential` 바닥 합이 칸보다 크면 더 숨기지 않고 표가 바닥 합 폭으로 서서 표 상자 안에서 가로로 굴러간다
 * (`scroll`) — 필수 값이 잘리거나 사라지는 것보다 굴리는 편이 낫다.
 *
 * 남는 폭: 늘어나는 열에 비중대로 상한까지 나누고, 모두 상한이면 남는 폭을 보이는 열(선택 · 동작 칸 제외)에 **지금 폭 비율로**
 * 나눈다. 마지막에 정수 px 로 올려 합이 칸 폭과 정확히 같게 한다(큰 나머지 순).
 */
import { COLUMN_TYPES, assignLeftoverWidth, lengthToPx, resolveColumn } from "./columnTypes.js";

/* 글 폭 계산의 바탕(rem). 표 머리 글자 12 · 표 칸 글자 14 · 칸 좌우 여백 16 + 16 · 정렬 · 필터 표지 22. */
export const HEADER_FONT_REM = 0.75;
export const VALUE_FONT_REM = 0.875;
export const CELL_PAD_REM = 2;
export const GLYPH_REM = 1.375;
export const STEP_REM = 0.5;
/* 행 동작 칸 — 단추 30 · 사이 8 · 칸 여백 32. */
export const ACTION_BUTTON_REM = 1.875;
export const ACTION_GAP_REM = 0.5;
/* 받은 행에서 값 길이를 잴 때 보는 행 수 상한 — 무한 받기 목록이 길어져도 계산이 커지지 않는다. */
export const VALUE_SAMPLE_ROWS = 200;

export const TIERS = Object.freeze(["essential", "secondary", "context"]);
/* 숨기는 순서 — 화면이 이미 말해 주는 값(context)이 먼저, 보조(secondary)가 그다음이다. 필수는 숨기지 않는다. */
const HIDE_ORDER = ["context", "secondary"];
/* 남는 폭을 비율로 나눌 때 받지 않는 칸 — 선택 · 동작은 글이 아니라 누를 것이라 넓혀도 읽기가 나아지지 않는다. */
const NO_SPILL = new Set(["select", "actions"]);

const HANGUL = /[ᄀ-ᇿ㄰-㆏가-힣一-鿿]/;

/** 글 폭(em) 어림 — 한글 · 한자 1em, 빈칸 0.25em, 나머지(라틴 · 숫자 · 기호) 0.58em. 캔버스를 못 쓰는 자리(jsdom)의 값이다. */
export function approxTextEm(text) {
  let em = 0;
  for (const ch of String(text == null ? "" : text)) {
    if (ch === " ") em += 0.25;
    else if (HANGUL.test(ch)) em += 1;
    else em += 0.58;
  }
  return em;
}

let canvasCtx = null;
/* 실브라우저에서는 실제 글꼴로 잰다 — 어림은 Pretendard 의 라틴 글자 폭을 조금 넉넉히 잡는다. jsdom 은 캔버스가 없어
   `getContext` 가 콘솔 오류를 낸다 — 거기서는 부르지 않는다. */
function canvasEm(text, weight) {
  if (typeof document === "undefined" || typeof navigator === "undefined") return null;
  if (/jsdom/i.test(navigator.userAgent || "")) return null;
  try {
    if (!canvasCtx) {
      const c = document.createElement("canvas");
      canvasCtx = c.getContext ? c.getContext("2d") : null;
      if (!canvasCtx) return null;
    }
    const family = (typeof getComputedStyle === "function" && document.body
      ? getComputedStyle(document.body).fontFamily : "") || "sans-serif";
    canvasCtx.font = `${weight || 400} 100px ${family}`;
    return canvasCtx.measureText(String(text == null ? "" : text)).width / 100;
  } catch (e) {
    return null;
  }
}

/** 글 폭(rem) — 글자 크기 `fontRem` 에서. 실브라우저면 캔버스, 아니면 어림. */
export function textRem(text, fontRem, weight = 400) {
  const em = canvasEm(text, weight);
  return (em == null ? approxTextEm(text) : em) * fontRem;
}

/** 0.5rem 단위로 올린다. */
export function stepUp(rem) {
  return Math.ceil(rem / STEP_REM - 1e-9) * STEP_REM;
}

/** 머리글이 한 줄로 서는 폭(rem) — 이름 + 칸 여백 + 표지(정렬 · 필터)마다 22. */
export function headerNeedRem(label, glyphs = 0) {
  if (!label) return 0;
  return stepUp(textRem(label, HEADER_FONT_REM, 600) + CELL_PAD_REM + GLYPH_REM * Math.max(0, glyphs));
}

/** 가장 긴 값이 한 줄로 서는 폭(rem). */
export function valuesNeedRem(values) {
  let longest = 0;
  for (const v of values || []) {
    if (v == null || v === "") continue;
    longest = Math.max(longest, textRem(String(v), VALUE_FONT_REM));
  }
  return longest ? stepUp(longest + CELL_PAD_REM) : 0;
}

/** 칸에 그려지는 **화면 낱말** — `value(row)`(열의 글 값 정본) · `hint(row)`(그린 글자) · 글 · 수 원값 순서. 모르면 null. */
export function columnValueText(col, row) {
  const c = col || {};
  if (!row) return null;
  try {
    if (typeof c.value === "function") {
      const v = c.value(row);
      return v == null ? null : String(v);
    }
    if (typeof c.hint === "function") {
      const v = c.hint(row);
      if (v != null && v !== "") return String(v);
    }
  } catch (e) {
    return null;
  }
  const raw = row[c.key];
  if (typeof raw !== "string" && typeof raw !== "number") return null;
  const text = String(raw);
  /* id 는 화면 글이 아니다 — 부서 열은 부서 id(UUID)를 들고 이름을 그린다. 그 길이로 재면 열 바닥이 20rem 을 넘어 1366 프로젝트 표가
     가로로 굴렀다(P5 캡처). 그리는 함수(`render`)가 있는 열은 원래 값이 화면 글이 아닐 수 있어, 서버가 준 화면 낱말(`*_label` ·
     `*_name` · `*_title`)만 잰다. 다른 화면 글은 `value(row)` · `hint` 로 말한다. */
  if (OPAQUE_VALUE.test(text.trim())) return null;
  if (typeof c.render === "function" && !DISPLAY_KEY.test(String(c.key || ""))) return null;
  return text;
}

const OPAQUE_VALUE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|^[0-9a-f]{32}$/i;
const DISPLAY_KEY = /(_label|_name|_title)$/;

function toRem(token, rootPx) {
  if (token == null) return null;
  if (typeof token === "number") return token;
  const px = lengthToPx(token, rootPx);
  return px == null ? null : px / rootPx;
}

const remOf = (token) => toRem(token, 16);

/** 이 열의 등급 — 정렬 중인 열, 식별 타입, 적은 값, 옛 `keep`, 옛 `hideNarrow` 순서로 정한다. */
export function columnTier(col, sortKey) {
  const c = col || {};
  if (sortKey && c.key === sortKey) return "essential";
  const type = resolveColumn(c).type;
  if (type && COLUMN_TYPES[type] && COLUMN_TYPES[type].identifying) return "essential";
  if (c.tier && TIERS.includes(c.tier)) return c.tier;
  if (c.keep) return "essential";
  return c.hideNarrow ? "secondary" : "essential";
}

/**
 * 열 하나의 배분 명세(rem). `kind` 는 grow(남는 폭을 상한까지 받는다) · fixed(폭이 정해졌다).
 * 호출부가 적은 `width`(옛 덮어쓰기)는 고정 폭으로 지킨다. `min` · `max`(또는 옛 `minWidth`)는 타입의 바닥 · 상한을 덮는다.
 */
export function columnSpec(col, { rootPx = 16, glyphs = 0, sortKey, rows } = {}) {
  const c = col || {};
  const s = resolveColumn(c);
  const type = s.type;
  const typeSpec = (type && COLUMN_TYPES[type]) || null;
  const header = headerNeedRem(typeof c.label === "string" ? c.label : "", c.glyphs != null ? c.glyphs : glyphs);
  const base = { key: c.key, type, tier: columnTier(c, sortKey), priority: Number(c.priority) || 0 };
  const minOverride = toRem(c.min != null ? c.min : c.minWidth, rootPx);
  const maxOverride = toRem(c.max, rootPx);
  if (c.width != null && c.width !== "1%") {
    const w = toRem(c.width, rootPx);
    if (w != null) return { ...base, kind: "fixed", min: Math.max(w, minOverride || 0), weight: 0, max: w };
  }
  const growSpec = c.grow ? COLUMN_TYPES.text : (typeSpec && typeSpec.weight ? typeSpec : null);
  if (growSpec) {
    const min = Math.max(minOverride != null ? minOverride : remOf(growSpec.minWidth), header);
    const max = Math.max(min, maxOverride != null ? maxOverride : remOf(growSpec.maxWidth));
    return { ...base, kind: "grow", min, weight: growSpec.weight, max };
  }
  if (type === "actions") {
    const n = Math.max(1, Number(c.actionCount) || 1);
    const w = stepUp(ACTION_BUTTON_REM * n + ACTION_GAP_REM * (n - 1) + CELL_PAD_REM);
    return { ...base, kind: "fixed", min: Math.max(minOverride != null ? minOverride : w, header), weight: 0, max: null };
  }
  const floor = minOverride != null ? minOverride : (typeSpec ? remOf(typeSpec.minWidth) : (remOf(s.minWidth) || 4.5));
  let values = 0;
  if (!typeSpec || typeSpec.content) {
    const list = Array.isArray(c.values) ? c.values
      : (rows || []).slice(0, VALUE_SAMPLE_ROWS).map((r) => columnValueText(c, r));
    values = valuesNeedRem(list);
  }
  const w = Math.max(floor, header, values);
  return { ...base, kind: "fixed", min: maxOverride != null ? Math.min(w, Math.max(maxOverride, floor)) : w, weight: 0, max: null };
}

/* 정수 px 로 올리되 합이 `total` 과 정확히 같게 — 내림한 뒤 남는 1px 들을 큰 나머지 순으로 나눈다. */
function roundToTotal(values, total) {
  const floors = values.map((v) => Math.floor(v + 1e-9));
  let rest = total - floors.reduce((a, b) => a + b, 0);
  const order = values.map((v, i) => [v - Math.floor(v + 1e-9), i]).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  const out = floors.slice();
  for (let k = 0; rest > 0 && order.length; k = (k + 1) % order.length, rest -= 1) out[order[k][1]] += 1;
  return out;
}

/**
 * 열 배분. 돌려주는 값:
 *   shown       그릴 열(표에 적힌 순서)
 *   hidden      숨긴 열(표에 적힌 순서)
 *   widths      { 열 키: px } — 칸 폭을 못 쟀으면 null(첫 그림은 옛 배치)
 *   tableWidth  표 폭(px) — 굴리는 경우 보이는 열 바닥 합, 아니면 칸 폭
 *   scroll      필수 열 바닥 합이 칸보다 커서 표 상자 안에서 가로로 굴러가는가
 *   meta        { 열 키: { tier, kind, content, min, max } } — 바닥 · 상한은 px(상한 없으면 null). 표가 `<col>` 과 `<table>` 의
 *               표식으로 내보내 QA 프로브(`column_balance`)가 「필수 열이 숨었나 · 한 열이 남는 폭을 혼자 먹나」를 잰다
 */
export function planColumns(columns, availPx, { rootPx = 16, sortKey, glyphsOf, rows } = {}) {
  const cols = (columns || []).filter(Boolean);
  /* 칸 폭을 아직 못 쟀으면(첫 그림) 아무 열도 숨기지 않고 옛 바닥 배치로 그린다 — 남는 폭은 제목 열이나 마지막 산문 열이
     받는다(`assignLeftoverWidth`). 한 프레임 넘치는 편이 열이 사라졌다 돌아오는 것보다 낫다. */
  if (!(availPx > 0)) return { shown: assignLeftoverWidth(cols), hidden: [], widths: null, tableWidth: null, scroll: false, meta: null };
  const root = rootPx > 0 ? rootPx : 16;
  const specs = new Map(cols.map((c) => [c, columnSpec(c, { rootPx: root, sortKey, rows, glyphs: glyphsOf ? glyphsOf(c) : 0 })]));
  const floorPx = (c) => specs.get(c).min * root;
  const meta = {};
  for (const [c, s] of specs) {
    const typeSpec = s.type && COLUMN_TYPES[s.type];
    meta[c.key] = {
      tier: s.tier, kind: s.kind, content: !!(typeSpec && typeSpec.content),
      min: Math.round(s.min * root), max: s.max != null ? Math.round(s.max * root) : null,
    };
  }
  const avail = Math.floor(availPx);

  let shown = cols.slice();
  let floor = shown.reduce((sum, c) => sum + floorPx(c), 0);
  const hidden = [];
  for (const tier of HIDE_ORDER) {
    if (floor <= avail) break;
    const candidates = shown
      .map((c, index) => ({ c, index, spec: specs.get(c) }))
      .filter((x) => x.spec.tier === tier)
      .sort((a, b) => a.spec.priority - b.spec.priority || b.index - a.index);
    for (const x of candidates) {
      if (floor <= avail) break;
      shown = shown.filter((c) => c !== x.c);
      hidden.push(x.c);
      floor -= floorPx(x.c);
    }
  }
  hidden.sort((a, b) => cols.indexOf(a) - cols.indexOf(b));

  const widthPx = new Map(shown.map((c) => [c, floorPx(c)]));
  if (floor > avail) {
    const widths = {};
    for (const c of shown) widths[c.key] = Math.ceil(widthPx.get(c) - 1e-9);
    const tableWidth = Object.values(widths).reduce((a, b) => a + b, 0);
    return { shown, hidden, widths, tableWidth, scroll: true, meta };
  }

  // 남는 폭 — 늘어나는 열에 비중대로, 상한까지(물 채우기).
  let left = avail - floor;
  const room = (c) => specs.get(c).max * root - widthPx.get(c);
  let open = shown.filter((c) => specs.get(c).kind === "grow" && room(c) > 1e-6);
  while (left > 1e-6 && open.length) {
    const weightSum = open.reduce((sum, c) => sum + specs.get(c).weight, 0);
    let step = left;
    for (const c of open) step = Math.min(step, room(c) * weightSum / specs.get(c).weight);
    for (const c of open) widthPx.set(c, widthPx.get(c) + step * specs.get(c).weight / weightSum);
    left -= step;
    open = open.filter((c) => room(c) > 1e-6);
  }
  // 모두 상한이면 남는 폭을 보이는 열에 지금 폭 비율로 — 한 열이 혼자 먹지 않는다.
  if (left > 1e-6) {
    const takers = shown.filter((c) => !NO_SPILL.has(specs.get(c).type));
    const total = takers.reduce((sum, c) => sum + widthPx.get(c), 0);
    if (total > 0) {
      for (const c of takers) widthPx.set(c, widthPx.get(c) + left * widthPx.get(c) / total);
      left = 0;
    }
  }
  const rounded = roundToTotal(shown.map((c) => widthPx.get(c)), avail);
  const widths = {};
  shown.forEach((c, i) => { widths[c.key] = rounded[i]; });
  return { shown, hidden, widths, tableWidth: avail, scroll: false, meta };
}
