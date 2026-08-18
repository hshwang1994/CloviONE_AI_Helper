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
    /* 두께가 3px 에서 2px 이 됐다(D-141). 얇아진 것이 아니라 **링 자체가 세졌다**:
       예전 링(#758AE1)은 흰 판 대비 3.2 로 3:1 을 겨우 넘어서 두께로 벌충하고 있었다.
       지금 링은 판 대비 7.59 다(theme-contract.test.js 가 세 면 모두에서 3:1 을 강제한다).
       WCAG 2.2 의 최소 둘레 두께 2px 도 충족한다. */
    expect(focusVisibleOutline).toMatch(/^2px solid #[0-9A-Fa-f]{6}$/);
    expect(buttonBaseRoot["&.Mui-focusVisible"].outlineOffset).toBeGreaterThan(0);

    // 대비 1.05/1.45(WCAG 미달)를 냈던 12% 배경 틴트(palette.primary.soft)를 재사용하면 안 된다.
    expect(focusVisibleOutline).not.toContain(theme.palette.primary.soft);
  });

  it.each(["light", "dark"])("%s 모드에서 버튼·링크·입력이 **같은** 포커스 링 색을 쓴다", (mode) => {
    /* 값을 리터럴로 박지 않는다. 예전에는 tokens.css 의 실측값을 두 곳에 손으로 적어 두고
       서로 같은지 봤는데, 지금 tokens.css 는 theme.js 에서 생성되므로(단일 정본) 검사할
       것은 "세 컴포넌트가 팔레트의 그 한 값을 쓰는가"다. 그 값의 대비는
       theme-contract.test.js 가 세 면 모두에서 별도로 강제한다. */
    const theme = createClovirTheme(mode);
    const ring = theme.palette.focusRing;
    expect(ring).toMatch(/^#[0-9A-Fa-f]{6}$/);

    expect(theme.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline).toBe(`2px solid ${ring}`);
    expect(theme.components.MuiLink.styleOverrides.root["&:focus-visible"].outline).toBe(`2px solid ${ring}`);
    expect(theme.components.MuiOutlinedInput.styleOverrides.root["&.Mui-focused"].outline).toBe(`2px solid ${ring}`);
  });

  it("두 모드의 포커스 링 색이 서로 다르다(라이트/다크 각자 실측 대비를 맞춘 값)", () => {
    const light = createClovirTheme("light");
    const dark = createClovirTheme("dark");

    expect(light.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline).not.toBe(
      dark.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline,
    );
  });
});
