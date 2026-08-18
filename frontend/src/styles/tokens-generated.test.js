/* tokens.css 는 손으로 쓰지 않는다 — theme.js 에서 생성한다.
 *
 * ## 이 파일이 무엇을 대체했는가
 *
 * 예전 `tokens-baseline.test.js` 는 폐기한 목업(지시 64)을 파싱해
 * tokens.css 값과 대조했다. 목업은 지시 64로 폐기했고, 더 중요한 것은 그 구조가 **드리프트를
 * 못 막았다**는 점이다: SPA 쪽 tokens.css 는 시험이 있었지만 Jinja 쪽 사본
 * (`app/static/css/tokens.css`)에는 시험이 없어서 조용히 낡았다(흰 사이드바, 56px 상단바,
 * surface 계층 없음 — 로그인 화면만 다른 제품처럼 보이던 이유).
 *
 * 이제 두 파일 다 `scripts/generate_design_tokens.mjs` 가 만든다. 이 시험이 지키는 것은:
 *   1. 생성물이 정본(theme.js)과 실제로 같은 값인가
 *   2. 두 벌이 서로 갈라지지 않았는가
 *   3. 화면 코드가 chrome 색을 리터럴로 다시 박아 두지 않았는가
 *   4. 폐기한 목업을 아직 참조하지 않는가
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { createClovirTheme, RADIUS } from "../ui/theme.js";

/* vitest 는 frontend/ 에서 돈다. */
const REPO = join(process.cwd(), "..");
const SPA_CSS = join(process.cwd(), "src", "styles", "tokens.css");
const JINJA_CSS = join(REPO, "app", "static", "css", "tokens.css");
const APPSHELL = join(process.cwd(), "src", "app", "AppShell.jsx");

const read = (p) => readFileSync(p, "utf8");

/** `:root { ... }` 또는 `[data-theme="dark"] { ... }` 블록에서 변수를 뽑는다. */
function varsIn(css, selector) {
  const start = css.indexOf(selector + " {");
  if (start < 0) return {};
  const end = css.indexOf("\n}", start);
  const body = css.slice(start, end);
  const out = {};
  for (const m of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    out[m[1]] = m[2].trim();
  }
  return out;
}

describe("생성물이라는 사실이 파일에 적혀 있다", () => {
  it.each([
    ["SPA", SPA_CSS],
    ["Jinja", JINJA_CSS],
  ])("%s tokens.css 가 생성 파일임을 밝히고 정본을 가리킨다", (_label, path) => {
    const css = read(path);
    expect(css).toMatch(/생성 파일이다/);
    expect(css).toMatch(/frontend\/src\/ui\/theme\.js/);
    expect(css).toMatch(/generate_design_tokens\.mjs/);
  });
});

describe("생성물이 정본과 같은 값이다", () => {
  const cases = [
    ["light", ":root"],
    ["dark", '[data-theme="dark"]'],
  ];

  it.each(cases)("%s — 면·글자·실선이 theme.js 와 일치한다", (mode, selector) => {
    const v = varsIn(read(SPA_CSS), selector);
    const p = createClovirTheme(mode).palette;
    expect(v["--color-bg"]).toBe(p.background.canvas);
    expect(v["--color-card"]).toBe(p.background.plate);
    expect(v["--color-surface-2"]).toBe(p.background.inset);
    expect(v["--color-surface-3"]).toBe(p.background.sunken);
    expect(v["--color-text"]).toBe(p.text.primary);
    expect(v["--color-muted"]).toBe(p.text.secondary);
    expect(v["--color-border"]).toBe(p.divider);
  });

  it.each(cases)("%s — 상태색이 theme.js 와 일치한다", (mode, selector) => {
    const v = varsIn(read(SPA_CSS), selector);
    const p = createClovirTheme(mode).palette;
    expect(v["--color-success"]).toBe(p.success.main);
    expect(v["--color-warning"]).toBe(p.warning.main);
    expect(v["--color-error"]).toBe(p.error.main);
    expect(v["--color-info"]).toBe(p.info.main);
  });

  it("모서리 토큰이 RADIUS 와 일치한다", () => {
    const v = varsIn(read(SPA_CSS), ":root");
    expect(v["--radius-sm"]).toBe(`${RADIUS.sm}px`);
    expect(v["--radius-md"]).toBe(`${RADIUS.md}px`);
    expect(v["--radius-lg"]).toBe(`${RADIUS.lg}px`);
    expect(v["--radius-pill"]).toBe(`${RADIUS.full}px`);
  });

  it("판에는 그림자가 없다 — 옛 별칭도 전부 none 으로 접혔다", () => {
    const v = varsIn(read(SPA_CSS), ":root");
    for (const k of ["--shadow-sm", "--shadow-card", "--shadow-subtle", "--shadow-hero"]) {
      expect(v[k], k).toBe("none");
    }
    // 떠 있는 것은 여전히 그림자를 갖는다.
    expect(v["--shadow-dropdown"]).not.toBe("none");
    expect(v["--shadow-modal"]).not.toBe("none");
  });
});

describe("두 벌이 갈라지지 않는다 (Jinja 사본이 조용히 낡던 자리)", () => {
  it.each([
    ["light", ":root"],
    ["dark", '[data-theme="dark"]'],
  ])("%s — Jinja 사본의 공통 변수가 SPA 와 글자 단위로 같다", (_mode, selector) => {
    const spa = varsIn(read(SPA_CSS), selector);
    const jinja = varsIn(read(JINJA_CSS), selector);
    const shared = Object.keys(jinja);
    expect(shared.length).toBeGreaterThan(40);
    for (const k of shared) {
      expect(jinja[k], `${selector} ${k}`).toBe(spa[k]);
    }
  });

  it("Jinja 사본은 시스템 다크 선호도 함께 따른다(로그인 화면에는 토글이 없다)", () => {
    expect(read(JINJA_CSS)).toMatch(/@media \(prefers-color-scheme: dark\)/);
  });

  it("네이티브 컨트롤이 테마를 따른다(color-scheme)", () => {
    for (const path of [SPA_CSS, JINJA_CSS]) {
      const css = read(path);
      expect(css).toMatch(/color-scheme:\s*light/);
      expect(css).toMatch(/color-scheme:\s*dark/);
    }
  });
});

describe("화면 코드가 chrome 색을 리터럴로 다시 박지 않는다", () => {
  const shell = read(APPSHELL);

  it("사이드바 배경을 hex 리터럴로 적지 않는다", () => {
    // 예전에 `bgcolor: "#1B2447"` 이 Drawer paper 에 직접 박혀 있었고, 그것이 실제로
    // 그려지는 값이라 토큰을 고쳐도 화면이 안 바뀌었다.
    expect(shell).not.toMatch(/#1B2447/i);
    expect(shell).toMatch(/bgcolor:\s*"sidebar\.bg"/);
  });

  it("사이드바 글자·호버를 rgba 리터럴로 적지 않는다", () => {
    expect(shell).not.toMatch(/rgba\(237,\s*240,\s*255/);
    expect(shell).not.toMatch(/rgba\(255,\s*255,\s*255,\s*\.\d+\)/);
  });

  it("상단바가 그라디언트가 아니다 (chrome 은 발광하지 않는다)", () => {
    expect(shell).not.toMatch(/radial-gradient/);
    expect(shell).not.toMatch(/linear-gradient\(112deg/);
  });

  it("선택 표현이 앞머리 레일이다 (큰 알약 배경이 아니다)", () => {
    expect(shell).toMatch(/sidebar\.activeRail/);
  });
});

describe("폐기한 목업을 아직 참조하지 않는다 (지시 64)", () => {
  it.each([
    ["SPA tokens.css", SPA_CSS],
    ["Jinja tokens.css", JINJA_CSS],
    ["AppShell.jsx", APPSHELL],
  ])("%s 에 목업 경로가 없다", (_label, path) => {
    const text = read(path);
    // 경로 문자열을 정규식 특수문자 없이 그대로 찾는다.
    expect(text.includes("preview-standalone")).toBe(false);
    expect(text.includes("design/baseline")).toBe(false);
  });
});
