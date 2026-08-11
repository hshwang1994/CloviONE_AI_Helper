/* KBD-01/02/03 — 키보드 포커스 링이 MUI 컴포넌트에서 사라졌던 문제의 회귀 방지.
 *
 * MUI ButtonBase 는 root 에 `outline: 0` 을 항상 깐다 - 마이그레이션 후 Button·IconButton·
 * ListItemButton·MenuItem·Tab 등이 키보드 탭으로 도착해도 표시가 없었다(감사: 정지점 45개 중
 * 38~45개가 outline:0 + boxShadow:none). 유일하던 표시(action.focusOpacity 12% 틴트,
 * palette.primary.soft)는 실측 대비 1.05(라이트)/1.45(다크)로 WCAG 1.4.11 3:1 미달이었다.
 *
 * 이 테스트는 `frontend/src/ui/theme.js:312` 의 MuiButtonBase 블록을 지우면(되돌리면) 실패해야
 * 한다 - 실제로 확인함(2026-08-11): 블록을 주석 처리하니 `focusVisibleOutline` 이 undefined 가
 * 되어 첫 assertion 에서 바로 깨졌다.
 */

import { describe, expect, it } from "vitest";

import { createClovirTheme } from "./theme.js";

describe("KBD-01/02/03: 키보드 포커스 링", () => {
  it.each(["light", "dark"])("%s 모드에서 ButtonBase 가 focus-visible 에서만 outline 을 받는다", (mode) => {
    const theme = createClovirTheme(mode);
    const buttonBaseRoot = theme.components.MuiButtonBase.styleOverrides.root;

    // 기본 root 자체에는 outline 이 없다 - MUI 의 outline:0 리셋을 건드리지 않고,
    // .Mui-focusVisible 에서만 얹는다(마우스 클릭에는 안 걸리고 키보드 탭에만 걸리는 클래스).
    expect(buttonBaseRoot.outline).toBeUndefined();

    const focusVisibleOutline = buttonBaseRoot["&.Mui-focusVisible"].outline;
    expect(focusVisibleOutline).toMatch(/^3px solid #[0-9A-Fa-f]{6}$/);

    // 대비 1.05/1.45(WCAG 미달)를 냈던 12% 배경 틴트(palette.primary.soft)를 재사용하면 안 된다.
    expect(focusVisibleOutline).not.toContain(theme.palette.primary.soft);
  });

  it.each(["light", "dark"])("%s 모드에서 링 색이 tokens.css 의 실측 검증값(--color-primary-soft)과 같다", (mode) => {
    const theme = createClovirTheme(mode);
    const expected = mode === "light" ? "#758AE1" : "#536CD6";
    const outline = theme.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline;

    expect(outline).toBe(`3px solid ${expected}`);
    expect(theme.components.MuiLink.styleOverrides.root["&:focus-visible"].outline).toBe(`3px solid ${expected}`);
    expect(theme.components.MuiOutlinedInput.styleOverrides.root["&.Mui-focused"].outline).toBe(`2px solid ${expected}`);
  });

  it("두 모드의 포커스 링 색이 서로 다르다(라이트/다크 각자 실측 대비를 맞춘 값)", () => {
    const light = createClovirTheme("light");
    const dark = createClovirTheme("dark");

    expect(light.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline).not.toBe(
      dark.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline,
    );
  });
});
