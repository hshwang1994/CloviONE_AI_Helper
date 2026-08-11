import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, it, expect } from "vitest";

import { createClovirTheme, ACCENT_PRESETS } from "./theme.js";

/* CTR-01/CTR-02/CTR-04: MuiLink(테마 기본 색)와 ConsoleSwitch(AppShell.jsx)의 활성 탭
 * 글자색이 배경과 WCAG AA(4.5:1) 대비를 만족하는지 확인한다.
 *
 * 팔레트 값(theme.palette.primary.dark 등)을 테스트 안에서 독립적으로 다시 계산하면 안
 * 된다 — 그 값 자체는 배선(MuiLink가 실제로 그 값을 쓰는지)과 무관하게 항상 존재하므로,
 * 배선이 빠진 회귀(원래 버그: MuiLink가 color를 안 줘서 MUI 기본값 primary.main으로
 * 렌더된 것)를 절대 못 잡는다(1차 시도에서 실제로 이 실수를 했다 — stash로 되돌려도
 * 통과해서 직접 확인함). 그래서 theme.components.MuiLink.styleOverrides.root.color처럼
 * **실제로 적용되는 설정값**을 읽는다. ConsoleSwitch(AppShell.jsx)는 sx prop 리터럴이라
 * 테마 객체에 없다 — jsdom이 emotion 동적 클래스의 computed style을 안정적으로 못 주므로
 * (body-editor-toolbar-contrast.test.jsx의 같은 이유) 소스 텍스트를 직접 읽는다
 * (test_deploy_wiring.py와 같은 기법의 프런트 버전). */
function srgbToLinear(c) {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`not a hex color: ${hex}`);
  const int = parseInt(m[1], 16);
  const r = srgbToLinear((int >> 16) & 255);
  const g = srgbToLinear((int >> 8) & 255);
  const b = srgbToLinear(int & 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(hexA, hexB) {
  const la = relativeLuminance(hexA);
  const lb = relativeLuminance(hexB);
  const lighter = Math.max(la, lb);
  const darker = Math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}

const AA_NORMAL_TEXT = 4.5;

describe("CTR-01/CTR-04 — MuiLink이 실제로 primary.dark(대비 보강 변수)를 쓰고, 그 값이 AA를 만족한다", () => {
  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent}`, () => {
        const theme = createClovirTheme(mode, accent);
        // 배선 확인: MuiLink styleOverrides가 실제로 primary.dark를 참조하는가(원래 버그는
        // color 자체가 없어 MUI가 자기 기본값 primary.main으로 렌더한 것이었다).
        const wiredColor = theme.components?.MuiLink?.styleOverrides?.root?.color;
        expect(wiredColor, "MuiLink styleOverrides.root.color가 설정돼 있지 않다").toBe(
          theme.palette.primary.dark,
        );

        const surfaces = [
          theme.palette.background.paper,
          theme.palette.background.surface2,
          theme.palette.background.default,
        ];
        for (const surface of surfaces) {
          const ratio = contrastRatio(wiredColor, surface);
          expect(
            ratio,
            `mode=${mode} accent=${accent} linkColor=${wiredColor} surface=${surface} ratio=${ratio.toFixed(2)}`,
          ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        }
      });
    }
  }
});

describe("CTR-02 — ConsoleSwitch 활성 탭이 실제로 primary.main을 쓰고, 그 값이 흰 배경과 AA를 만족한다", () => {
  const appShellSrc = readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "AppShell.jsx"),
    "utf-8",
  );

  it("ConsoleSwitch의 활성 탭 color가 primary.main이다(다크 표면용으로 밝힌 primary.dark가 아니다)", () => {
    // bgcolor가 항상 리터럴 common.white인 바로 그 줄에서 color를 읽는다 — 다른 곳의
    // primary.dark 참조(예: MuiLink)까지 잘못 걸리지 않도록 좁힌다.
    const block = appShellSrc.slice(
      appShellSrc.indexOf("function ConsoleSwitch"),
      appShellSrc.indexOf("function ConsoleSwitch") + 2000,
    );
    const colorLine = /color:\s*seg\.on\s*\?\s*"([^"]+)"/.exec(block);
    expect(colorLine, "ConsoleSwitch에서 seg.on 삼항 color 선언을 못 찾았다").not.toBeNull();
    expect(colorLine[1]).toBe("primary.main");
  });

  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent} — primary.main vs 흰 배경(common.white)`, () => {
        const theme = createClovirTheme(mode, accent);
        const ratio = contrastRatio(theme.palette.primary.main, "#FFFFFF");
        expect(
          ratio,
          `mode=${mode} accent=${accent} color=${theme.palette.primary.main} ratio=${ratio.toFixed(2)}`,
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });
    }
  }
});
