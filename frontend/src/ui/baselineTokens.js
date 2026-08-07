/* 기준선 미리보기(design/baseline/preview-standalone.html)에서 디자인 토큰을 읽어 온다.
 *
 * 왜 파서를 두는가. 기준선 값을 테스트에 손으로 옮겨 적으면, 옮겨 적은 값과 theme.js 가
 * **같이** 틀렸을 때 테스트가 통과한다. 실제로 그 일이 있었다 - 토큰을 눈으로 비교하고
 * "이미 일치한다"고 결론 내렸는데 배포된 화면은 기준선과 달랐다. 그래서 기준선 파일을
 * 정본으로 두고 기계가 읽게 한다. 이 파일에는 색·크기 상수가 하나도 없다.
 *
 * 앱 코드는 이 파일을 import 하지 않는다(테스트 전용이라 번들에 들어가지 않는다).
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

// vitest 는 frontend/ 에서 돈다. jsdom 에서는 import.meta.url 이 file: 스킴이 아니라
// fileURLToPath 가 던지므로 cwd 기준이 안전하다(jsx-comments.test.js 와 같은 이유).
export const BASELINE_HTML = join(process.cwd(), "..", "design", "baseline", "preview-standalone.html");

/** 기준선 HTML 의 <style> 본문을 통째로 돌려준다. */
export function readBaselineCss(file = BASELINE_HTML) {
  const html = readFileSync(file, "utf8");
  const open = html.indexOf("<style>");
  const close = html.indexOf("</style>", open);
  if (open < 0 || close < 0) throw new Error(`기준선 HTML 에서 <style> 을 찾지 못했다: ${file}`);
  return html.slice(open + "<style>".length, close);
}

function stripComments(css) {
  let out = "";
  let i = 0;
  while (i < css.length) {
    if (css[i] === "/" && css[i + 1] === "*") {
      const end = css.indexOf("*/", i + 2);
      i = end < 0 ? css.length : end + 2;
      continue;
    }
    out += css[i];
    i += 1;
  }
  return out;
}

/* 최상위 규칙만 모은다.
 *
 * @media 안의 선언은 조건부다. 기준선에는 `@media (max-width:960px) { :root { --sidebar-w:248px } }`
 * 가 있어서, 단순 정규식으로 훑으면 사이드바 폭이 264 가 아니라 248 로 읽힌다.
 * 그래서 중괄호 깊이를 세어 at-rule 블록을 통째로 건너뛴다. */
export function topLevelRules(css) {
  const text = stripComments(css);
  const rules = [];
  let i = 0;
  let selectorStart = 0;
  while (i < text.length) {
    if (text[i] !== "{") {
      i += 1;
      continue;
    }
    const selector = text.slice(selectorStart, i).trim();
    const bodyStart = i + 1;
    let depth = 1;
    let j = bodyStart;
    while (j < text.length && depth > 0) {
      if (text[j] === "{") depth += 1;
      else if (text[j] === "}") depth -= 1;
      j += 1;
    }
    if (!selector.startsWith("@")) rules.push({ selector, body: text.slice(bodyStart, j - 1) });
    i = j;
    selectorStart = i;
  }
  return rules;
}

/** 규칙 본문을 { 속성: 값 } 으로. 값 안의 괄호에는 세미콜론이 없으므로 ; 로만 자른다. */
export function declarations(body) {
  const out = {};
  for (const chunk of body.split(";")) {
    const colon = chunk.indexOf(":");
    if (colon < 0) continue;
    const prop = chunk.slice(0, colon).trim();
    const value = chunk.slice(colon + 1).replace(/!important/g, "").trim();
    if (prop) out[prop] = value;
  }
  return out;
}

/* 선택자 목록에 sel 이 그대로 들어 있는 마지막 선언값. 뒤에 오는 규칙이 이긴다
 * (기준선은 같은 선택자를 여러 번 덮어쓴다 - 예: .topbar 그라데이션이 세 번 바뀐다). */
export function lastDeclaration(rules, sel, prop) {
  let found;
  for (const rule of rules) {
    if (!rule.selector.split(",").some((s) => s.trim() === sel)) continue;
    const value = declarations(rule.body)[prop];
    if (value !== undefined) found = value;
  }
  return found;
}

/** :root / [data-theme="dark"] 의 커스텀 프로퍼티를 선언 순서대로 합친다(뒤가 이긴다). */
export function rawTokens(rules) {
  const light = {};
  const dark = {};
  for (const { selector, body } of rules) {
    const sels = selector.split(",").map((s) => s.trim());
    const isRoot = sels.includes(":root");
    const isDark = sels.includes('[data-theme="dark"]');
    if (!isRoot && !isDark) continue;
    const target = isDark ? dark : light;
    for (const [prop, value] of Object.entries(declarations(body))) {
      if (prop.startsWith("--")) target[prop] = value;
    }
  }
  return { light, dark };
}

const NAMED = { white: [255, 255, 255, 1], black: [0, 0, 0, 1], transparent: [0, 0, 0, 0] };

function parseColor(text) {
  const value = text.trim().toLowerCase();
  if (NAMED[value]) return NAMED[value].slice();
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/.exec(value);
  if (short) return [1, 2, 3].map((n) => parseInt(short[n] + short[n], 16)).concat(1);
  const long = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/.exec(value);
  if (long) return [1, 2, 3].map((n) => parseInt(long[n], 16)).concat(1);
  const fn = /^rgba?\(([^)]+)\)$/.exec(value);
  if (fn) {
    const parts = fn[1].split(/[,/\s]+/).filter(Boolean).map(Number);
    if (parts.length < 3 || parts.some(Number.isNaN)) return null;
    return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
  }
  return null;
}

function toHex([r, g, b]) {
  return `#${[r, g, b].map((n) => Math.round(n).toString(16).padStart(2, "0")).join("")}`;
}

/* color-mix(in srgb, A p%, B q%) 를 계산한다. srgb 는 감마 인코딩된 채널의 가중 평균이고,
 * 알파는 premultiply 후 나눈다(CSS Color 5 규칙). 기준선의 :root 에서 실제로 쓰이는 꼴은
 * `color-mix(in srgb, var(--primary) 78%, #17204d)` 처럼 한쪽에만 비율이 붙은 형태다. */
function mix(args) {
  const parts = splitTopLevel(args, ",").map((s) => s.trim());
  if (parts.length !== 3 || !/^in\s+srgb$/i.test(parts[0])) return null;
  const parsed = parts.slice(1).map((part) => {
    const pct = /\s([\d.]+)%$/.exec(part);
    const color = parseColor(pct ? part.slice(0, pct.index) : part);
    return color && { color, pct: pct ? Number(pct[1]) / 100 : null };
  });
  if (parsed.some((p) => !p)) return null;
  let [a, b] = parsed;
  if (a.pct === null && b.pct === null) a = { ...a, pct: 0.5 };
  if (a.pct === null) a = { ...a, pct: 1 - b.pct };
  if (b.pct === null) b = { ...b, pct: 1 - a.pct };
  const alpha = a.color[3] * a.pct + b.color[3] * b.pct;
  if (alpha === 0) return "rgba(0, 0, 0, 0)";
  const channel = (i) =>
    (a.color[i] * a.color[3] * a.pct + b.color[i] * b.color[3] * b.pct) / alpha;
  const rgb = [channel(0), channel(1), channel(2)];
  return alpha === 1 ? toHex(rgb) : `rgba(${rgb.map(Math.round).join(", ")}, ${alpha})`;
}

function splitTopLevel(text, sep) {
  const out = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === "(") depth += 1;
    else if (text[i] === ")") depth -= 1;
    else if (text[i] === sep && depth === 0) {
      out.push(text.slice(start, i));
      start = i + 1;
    }
  }
  out.push(text.slice(start));
  return out;
}

function resolveVars(value, scope, seen) {
  return value.replace(/var\(\s*(--[\w-]+)\s*(?:,([^)]*))?\)/g, (_, name, fallback) => {
    if (seen.has(name)) throw new Error(`기준선 토큰이 순환 참조한다: ${name}`);
    const raw = scope[name];
    if (raw === undefined) {
      if (fallback !== undefined) return fallback.trim();
      throw new Error(`기준선에 없는 토큰을 참조한다: ${name}`);
    }
    return resolveVars(raw, scope, new Set([...seen, name]));
  });
}

/* 가장 안쪽 color-mix 부터 계산해 올라온다. --primary-soft 처럼 var() 를 품은 것도
 * var 치환을 먼저 끝냈으므로 여기서는 색 리터럴만 남는다. */
function resolveColorMix(value) {
  let text = value;
  for (let guard = 0; guard < 20; guard += 1) {
    const open = text.lastIndexOf("color-mix(");
    if (open < 0) return text;
    let depth = 0;
    let close = -1;
    for (let i = open + "color-mix".length; i < text.length; i += 1) {
      if (text[i] === "(") depth += 1;
      else if (text[i] === ")") {
        depth -= 1;
        if (depth === 0) {
          close = i;
          break;
        }
      }
    }
    if (close < 0) return text;
    const mixed = mix(text.slice(open + "color-mix(".length, close));
    if (mixed === null) return text;
    text = text.slice(0, open) + mixed + text.slice(close + 1);
  }
  return text;
}

/** 한 스코프의 토큰을 var()·color-mix() 까지 풀어 구체값으로 만든다. */
export function resolveScope(raw) {
  const out = {};
  for (const name of Object.keys(raw)) {
    out[name] = resolveColorMix(resolveVars(raw[name], raw, new Set([name])));
  }
  return out;
}

/* 기준선 미리보기가 **실제로 그리는** 토큰 값.
 *
 * 미리보기는 render() 마다 `documentElement.style.setProperty('--primary', state.accent)` 로
 * :root 인라인 스타일을 쓴다. 인라인 스타일은 모든 스타일시트 규칙을 이기므로
 * `[data-theme="dark"] { --primary:#8ea0f4 }` 선언은 실행 중에는 적용되지 않는다 -
 * 두 모드 모두 --primary 는 사용자가 고른 강조색이고, --primary-strong/-soft 는
 * color-mix 로 거기서 다시 계산된다. 우리 테마도 강조색이 런타임 값이므로 조건이 같다. */
export function baselineScope(rules, { mode = "light", accent } = {}) {
  const { light, dark } = rawTokens(rules);
  const raw = mode === "dark" ? { ...light, ...dark } : { ...light };
  if (accent) {
    raw["--primary"] = accent;
    raw["--brand-accent"] = accent;
  }
  return resolveScope(raw);
}

/** 기준선 전체를 읽어 { rules, light, dark } 로. light/dark 는 선언된 그대로(강조색 미적용). */
export function baseline(file = BASELINE_HTML) {
  const rules = topLevelRules(readBaselineCss(file));
  return {
    rules,
    light: baselineScope(rules, { mode: "light" }),
    dark: baselineScope(rules, { mode: "dark" }),
  };
}
