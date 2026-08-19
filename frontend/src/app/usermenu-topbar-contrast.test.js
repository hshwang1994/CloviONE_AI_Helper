import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { ACCENT_PRESETS, createClovirTheme } from "../ui/theme.js";

/* 상단바 사용자 영역의 대비 — **실제 chrome 색**으로 잰다.
 *
 * ## 이 파일이 무엇을 대체했는가
 *
 * `usermenu-topbar-gradient-contrast.test.js` 는 상단바가 보라 그라데이션이라는 전제로
 * "78% 지점 최악의 광원" 위 흰 글자 대비를 계산했다(WF7-K01). D-141 로 chrome 이 캔버스
 * 계열 **단색**이 되면서 그 전제가 사라졌고, 그 시험은 존재하지 않는 배경에 대해 계속
 * 초록불을 내고 있었다 — 그 사이 `UserMenu.jsx` 는 어두운 배경용 리터럴
 * (`rgba(0,0,0,.15)` 알약, `rgba(255,255,255,.22)` 아바타)을 그대로 들고 있어서, 밝은
 * 상단바에 검은 알약이 얹히고 아바타 이니셜은 흰 원 안 흰 글자가 됐다. **초록불이 결함을
 * 가린 자리**다.
 *
 * 그래서 여기서는 두 가지를 본다.
 *   1. 값이 **테마에서 온다** — 리터럴을 다시 박으면 실패한다(그게 원래 결함이었다).
 *   2. 그 조합의 대비가 강조색 프리셋 전부 × 두 모드에서 AA 를 넘는다.
 */

const AA_NORMAL_TEXT = 4.5;

function channel(c8) {
  const c = c8 / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
function rgb(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!m) throw new Error(`hex 가 아니다: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function luminance(hex) {
  const [r, g, b] = rgb(hex).map(channel);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

const SRC = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "UserMenu.jsx"),
  "utf-8",
);
const BUTTON_BLOCK = (() => {
  const start = SRC.indexOf("<Button");
  return SRC.slice(start, start + 2200);
})();

describe("사용자 영역은 chrome 색을 리터럴로 다시 박지 않는다", () => {
  it("어두운 배경 전제의 옛 리터럴을 스타일로 쓰지 않는다", () => {
    /* 이 값들이 **선언으로** 남아 있는 것이 원래 결함이었다 — 상단바가 밝아졌는데 값만
       안 따라왔다. 주석 안의 언급(왜 바꿨는지 설명)은 잡지 않는다: 그 설명이 사라지면
       다음 사람이 같은 리터럴을 "원래 그랬으니" 하고 되돌린다. */
    expect(BUTTON_BLOCK).not.toMatch(/(bgcolor|color|background)\s*:\s*"rgba\(/);
  });

  it("호버·아바타가 테마 토큰을 쓴다 — 상단바 색이 바뀌면 같이 따라온다", () => {
    expect(BUTTON_BLOCK).toMatch(/bgcolor:\s*"sidebar\.hover"/);
    expect(BUTTON_BLOCK).toMatch(/bgcolor:\s*"background\.plate"/);
    expect(BUTTON_BLOCK).toMatch(/color:\s*"text\.secondary"/);
  });

  /* D-179 로 Shell 이 인디고가 되면서 계정 이름의 잉크도 chrome 잉크여야 한다.
     예전에는 `text.primary`(본문 잉크)였고, 그때는 상단바가 캔버스 계열이라 우연히 맞았다 —
     **값이 배경을 따라오지 않는다**는 같은 종류의 결함이 한 번 더 일어난 것이다. 그래서
     이제 **소스가 쓰는 토큰 이름을 시험이 읽어** 그 토큰으로 대비를 잰다. 배선과 측정이
     한 줄로 묶여, 다음에 배경이 또 바뀌면 대비 시험이 같이 빨개진다. */
  it("계정 이름이 chrome 잉크 토큰을 쓴다 (본문 잉크가 아니다)", () => {
    expect(BUTTON_BLOCK).toMatch(/color:\s*"sidebar\.text"/);
    expect(BUTTON_BLOCK).not.toMatch(/color:\s*"text\.primary"/);
  });
});

describe("사용자 영역 대비 — 강조색 프리셋 전부 × 두 모드", () => {
  const cases = [];
  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) cases.push([mode, accent]);
  }

  it.each(cases)("%s / accent=%s — 계정 이름이 상단바 위에서 AA", (mode, accent) => {
    const p = createClovirTheme(mode, accent).palette;
    const ratio = contrast(p.sidebar.text, p.sidebar.bg);
    expect(ratio, `이름 ${p.sidebar.text} on chrome ${p.sidebar.bg} = ${ratio.toFixed(2)}`)
      .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it.each(cases)("%s / accent=%s — 아바타 이니셜이 아바타 면 위에서 AA", (mode, accent) => {
    const p = createClovirTheme(mode, accent).palette;
    const ratio = contrast(p.text.secondary, p.background.plate);
    expect(ratio, `이니셜 ${p.text.secondary} on ${p.background.plate} = ${ratio.toFixed(2)}`)
      .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  /* 아바타 **원 자체**의 대비는 재지 않는다. `aria-hidden` 인 장식 원이고 상태를 알리는
     컨트롤이 아니다(WCAG 1.4.11 의 대상이 아니다) — 읽어야 하는 것은 그 안의 이니셜이고
     위 시험이 그것을 잰다. 원을 chrome 에서 떼어 놓는 하이라인은 시각적 마감이라 값만
     토큰(`sidebar.line`)에서 오게 하고(위 배선 시험), 비율을 못박지 않는다. */
});
