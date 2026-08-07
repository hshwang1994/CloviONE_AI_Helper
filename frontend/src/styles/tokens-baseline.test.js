/* tokens.css 가 기준선(design/baseline/preview-standalone.html)의 값을 그대로 쓰는가.
 *
 * ## 왜 이 검사가 필요했나
 *
 * `ui/theme-baseline.test.js`가 MUI 쪽(theme.js)을 기준선과 대조하는 검사인데, 옛 plain
 * CSS 클래스(`.k-*` `.c-*` `.dash-*` 등, screens.css·kit.css·global.css)가 보는 tokens.css는
 * 아무도 대조하지 않고 있었다. 그 결과 카드·본문·테두리는 MUI 쪽만 새 팔레트를 따라가고,
 * tokens.css가 그리는 화면은 옛 팔레트(#333333 본문, 반지름 6/10/14px 등)에 머물러 있었다
 * (사용자 지적, 2026-08-07: "카드 색상이 안 바뀌었다, 여전히 하얗다"). 사이드바는 더 심했다
 * — tokens.css는 "디자인 시스템은 흰 사이드바다"라고 주석까지 달려 있었는데 실제 기준선은
 * 어두운 남색이었다("사이드바가 흰색인데 어두운 남색이어야 한다").
 *
 * ## 왜 값을 여기 적지 않는가
 *
 * theme-baseline.test.js와 같은 이유다 — 기준선 값을 손으로 옮겨 적으면, 옮긴 값과
 * tokens.css가 **같이** 틀렸을 때 통과한다. 이 파일에는 색·크기 리터럴이 없다. 전부
 * baselineTokens.js(기준선 파서, theme-baseline.test.js와 공유)로 기준선 HTML을 읽고,
 * 같은 파서로 tokens.css 자신도 읽어 대조한다 — topLevelRules/rawTokens/resolveScope는
 * 기준선 전용이 아니라 일반 CSS 텍스트를 받는 함수라 tokens.css에도 그대로 쓸 수 있다.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  baseline,
  lastDeclaration,
  rawTokens,
  resolveScope,
  topLevelRules,
} from "../ui/baselineTokens.js";

// vitest는 frontend/에서 돈다(baselineTokens.js와 같은 이유로 cwd 기준 경로를 쓴다).
const TOKENS_CSS_PATH = join(process.cwd(), "src", "styles", "tokens.css");
const APP_SHELL_PATH = join(process.cwd(), "src", "app", "AppShell.jsx");

function readTokensCss() {
  return readFileSync(TOKENS_CSS_PATH, "utf8");
}

/* tokens.css 자신의 :root/[data-theme="dark"]를 라이트·다크 원본(raw, var() 미해석)으로.
 * baselineTokens.js의 baselineScope()와 같은 규칙을 쓴다 - 다크는 :root 위에 다크 선언을
 * 덮어쓴 결과다(실제 CSS 상속과 같다). 이 병합 없이 dark 블록만 읽으면, dark에서 재선언하지
 * 않는 이름(예: --radius-sm, --sidebar-active-bg)이 전부 undefined로 잡힌다 - 처음 이
 * 파일을 쓸 때 실제로 이 실수를 했고 9개 검사가 잘못 실패했다. */
function tokensRaw() {
  const rules = topLevelRules(readTokensCss());
  const { light, dark } = rawTokens(rules);
  return { rules, light, dark: { ...light, ...dark } };
}

/* 색 문자열 비교용 정규화 — theme-baseline.test.js의 norm()에 두 가지를 더한다:
 *   1) 3자리 hex(#fff) -> 6자리(#ffffff). 기준선은 짧은 표기를 섞어 쓴다(.nav-item.is-active
 *      의 color:#fff 등).
 *   2) 소수점 앞 자리 없는 leading-zero(.05 vs 0.05). 기준선은 `.05`처럼 0을 생략하고
 *      tokens.css는 기존 문체(0.05)를 유지하므로, 이 차이만으로 대조가 깨지면 안 된다.
 */
function norm(value) {
  const expandHex = (v) =>
    v.replace(/#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])(?![0-9a-fA-F])/g, (_, r, g, b) => `#${r}${r}${g}${g}${b}${b}`);
  const stripLeadingZero = (v) => v.replace(/(^|[^\d])0\.(\d)/g, "$1.$2");
  return stripLeadingZero(expandHex(String(value).trim().toLowerCase().replace(/\s+/g, "")));
}

const { rules: baselineRules, light: baselineLight, dark: baselineDark } = baseline();
const tokens = tokensRaw();
const tokensResolved = { light: resolveScope(tokens.light), dark: resolveScope(tokens.dark) };
const baselineResolved = { light: baselineLight, dark: baselineDark };

/* 기준선 이름 -> tokens.css 이름. 1:1로 개념이 대응하는 것만 이 표에 올린다 — 개념이
 * 다른 것(예: primary-soft)은 아래에 별도 서술로 다룬다. */
const COLOR_MAP = [
  ["--primary", "--color-primary"],
  ["--primary-strong", "--color-primary-strong"],
  // 기준선 --primary-soft(옅은 배경 틴트)는 tokens.css의 --color-primary-tint가 맡는다.
  // 옛 --color-primary-soft는 이름은 비슷하지만 포커스 링 전용(진한 색)이라 여기서 뺀다
  // (아래 "포커스 링" 절 참고).
  ["--primary-soft", "--color-primary-tint"],
  // 기준선 --accent(라이트 #8e75e1)는 옛 --color-accent-purple과 값이 같다. MUI 쪽
  // secondary도 같은 소스라 여기서도 같은 이름으로 맞춰 둔다.
  ["--accent", "--color-accent-purple"],
  ["--cyan", "--color-accent-sky"],
  ["--bg", "--color-bg"],
  ["--surface", "--color-card"],
  ["--surface-2", "--color-surface-2"],
  ["--surface-3", "--color-surface-3"],
  ["--text", "--color-text"],
  ["--muted", "--color-muted"],
  ["--border", "--color-border"],
  ["--border-strong", "--color-border-strong"],
  ["--success", "--color-success"],
  ["--success-bg", "--color-success-bg"],
  ["--warning", "--color-warning"],
  ["--warning-bg", "--color-warning-bg"],
  // 기준선은 "danger", 이 파일은 예전부터 "error" — 이름은 다르지만 같은 상태다.
  ["--danger", "--color-error"],
  ["--danger-bg", "--color-error-bg"],
  ["--info", "--color-info"],
  ["--info-bg", "--color-info-bg"],
  ["--sidebar-text", "--sidebar-text"],
  ["--sidebar-muted", "--sidebar-muted"],
  ["--sidebar-hover", "--sidebar-hover"],
];

const SIZE_MAP = [
  ["--radius-sm", "--radius-sm"],
  ["--radius-md", "--radius-md"],
  ["--radius-lg", "--radius-lg"],
  // 옛 이름(--topbar-height)이 기준선(--topbar-h)과 다르다. 값도 56px로 어긋나 있었다
  // (실제로 global.css의 노티 팝오버가 8px 짧게 계산되는 버그였다 - tokens.css 주석 참고).
  ["--topbar-h", "--topbar-height"],
  ["--sidebar-w", "--sidebar-width"],
];

const SHADOW_MAP = [
  ["--shadow-sm", "--shadow-sm"],
  ["--shadow-md", "--shadow-md"],
  ["--shadow-lg", "--shadow-lg"],
];

describe.each(["light", "dark"])("%s 모드", (mode) => {
  const b = baselineResolved[mode];
  const t = tokensResolved[mode];

  it.each(COLOR_MAP)("색 %s -> %s", (baselineName, tokensName) => {
    expect(b[baselineName], `기준선에 ${baselineName} 이 없다`).toBeTruthy();
    expect(t[tokensName], `tokens.css에 ${tokensName} 이 없다`).toBeTruthy();
    expect(norm(t[tokensName])).toBe(norm(b[baselineName]));
  });

  it.each(SIZE_MAP)("크기 %s -> %s", (baselineName, tokensName) => {
    expect(norm(t[tokensName])).toBe(norm(b[baselineName]));
  });

  it.each(SHADOW_MAP)("그림자 %s -> %s", (baselineName, tokensName) => {
    expect(norm(t[tokensName])).toBe(norm(b[baselineName]));
  });

  it("옛 그림자 별칭(--shadow-card 등)이 새 --shadow-sm/-md/-lg 값과 같다", () => {
    expect(norm(t["--shadow-card"])).toBe(norm(t["--shadow-sm"]));
    expect(norm(t["--shadow-subtle"])).toBe(norm(t["--shadow-sm"]));
    expect(norm(t["--shadow-dropdown"])).toBe(norm(t["--shadow-md"]));
    expect(norm(t["--shadow-modal"])).toBe(norm(t["--shadow-lg"]));
  });
});

it("글꼴 스택은 기준선의 --font 와 같다(폴백 목록 글자 단위로 동일)", () => {
  expect(norm(tokensResolved.light["--font-stack"])).toBe(norm(baselineResolved.light["--font"]));
});

/* -------- 사이드바 배경 — 이 작업의 핵심 회귀 방지 -------- *
 *
 * 기준선의 --sidebar 커스텀 프로퍼티(#111831, 단색)를 그대로 믿으면 안 된다. 기준선
 * `.sidebar` 규칙은 :root 선언 한 번(background: var(--sidebar)), 그리고 "2026-07-31 full
 * rebuild" 구간에서 `.sidebar { background: linear-gradient(...) }`로 다시 한 번 나온다 —
 * 같은 명시도에서는 나중 선언이 이기므로, 기준선이 실제로 그리는 값은 그라디언트다.
 * lastDeclaration()이 바로 이 "나중 선언이 이긴다" 규칙으로 값을 고른다 — --sidebar 변수를
 * 직접 읽지 않고 반드시 이 함수로 재현해야 한다(사람이 손으로 "기준선은 #111831 단색"이라고
 * 결론 낸 적이 있었는데, 그게 이 규칙을 안 거친 오독이었다). */
describe("사이드바 배경 (기준선 last-wins 규칙)", () => {
  const sidebarBg = lastDeclaration(baselineRules, ".sidebar", "background");
  const sidebarShadow = lastDeclaration(baselineRules, ".sidebar", "box-shadow");

  it("기준선 .sidebar 배경은 단색이 아니라 그라디언트다", () => {
    expect(sidebarBg).toMatch(/^linear-gradient\(/);
  });

  it("tokens.css --sidebar-bg 는 기준선이 실제로 그리는 .sidebar 배경과 같다(라이트·다크 공통)", () => {
    expect(norm(tokensResolved.light["--sidebar-bg"])).toBe(norm(sidebarBg));
    expect(norm(tokensResolved.dark["--sidebar-bg"])).toBe(norm(sidebarBg));
  });

  it("tokens.css --sidebar-shadow 는 기준선 .sidebar 의 box-shadow와 같다", () => {
    expect(norm(tokensResolved.light["--sidebar-shadow"])).toBe(norm(sidebarShadow));
    expect(norm(tokensResolved.dark["--sidebar-shadow"])).toBe(norm(sidebarShadow));
  });

  it("AppShell.jsx는 사이드바 배경을 리터럴로 다시 박아 두지 않고 tokens.css의 --sidebar-bg 를 참조한다", () => {
    const src = readFileSync(APP_SHELL_PATH, "utf8");
    expect(src).toContain("var(--sidebar-bg)");
    // 예전에 여기 있던 리터럴(#111936 그라디언트)이 되돌아오면, tokens.css를 고쳐도
    // AppShell.jsx가 다른 값을 그릴 수 있다 - 소스가 다시 둘로 갈라지는 걸 잡는다.
    expect(src).not.toMatch(/background:\s*"linear-gradient\(180deg,\s*#111936/);
  });
});

/* -------- 활성 메뉴 항목 — 기준선 .nav-item.is-active -------- *
 * 기준선 값은 var(--brand-accent)/var(--brand-purple)를 참조하므로, 기준선 자신의 원본
 * 스코프로 해석해야 한다(resolveScope). tokens.css 쪽은 이미 리터럴이라 그대로 비교한다. */
describe("사이드바 활성 항목 (기준선 last-wins 규칙)", () => {
  const rawBaselineLight = rawTokens(baselineRules).light;
  const probe = {
    ...rawBaselineLight,
    __navActiveBg: lastDeclaration(baselineRules, ".nav-item.is-active", "background"),
  };
  const resolvedNavActiveBg = resolveScope(probe).__navActiveBg;
  const navActiveFg = lastDeclaration(baselineRules, ".nav-item.is-active", "color");

  it("tokens.css --sidebar-active-bg 는 기준선 .nav-item.is-active 배경과 같다(테마 무관 고정색)", () => {
    expect(norm(tokensResolved.light["--sidebar-active-bg"])).toBe(norm(resolvedNavActiveBg));
    expect(norm(tokensResolved.dark["--sidebar-active-bg"])).toBe(norm(resolvedNavActiveBg));
  });

  it("tokens.css --sidebar-active-fg 는 기준선 .nav-item.is-active 글자색과 같다", () => {
    expect(norm(tokensResolved.light["--sidebar-active-fg"])).toBe(norm(navActiveFg));
  });
});

/* -------- 포커스 링 — 의도적으로 기준선 공식을 따르지 않는다 -------- *
 * 기준선의 :focus-visible { outline: 3px solid color-mix(in srgb, var(--primary) 70%, white) }
 * 를 그대로 계산하면 흰 배경 대비 2.76으로 3:1(WCAG 1.4.11 비텍스트 최소)에 못 미친다.
 * tokens.css의 --color-primary-soft는 그래서 이 공식을 쓰지 않고 실측 검증된 값(3.2)을
 * 유지한다 - 이 테스트는 "왜 다른지"를 기록해 다음 사람이 기준선과 다르다고 되돌리지
 * 않게 한다(theme-baseline.test.js의 "입력칸 배경" 테스트와 같은 패턴). */
it("포커스 링(--color-primary-soft)은 기준선 --primary-soft 공식과 다르다 (의도됨, 대비 확보)", () => {
  expect(norm(tokensResolved.light["--color-primary-soft"])).not.toBe(norm(baselineResolved.light["--primary-soft"]));
});
