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
    /* D-179 에서 링 값이 **변수를 통해** 온다. 이유는 이 제품에 대비가 정반대인 두 면이
       있기 때문이다 — 밝은 Canvas 와 인디고 Shell. Canvas 용 링을 Shell 위에 그리면 light
       에서 1.38~1.83:1 로 사실상 보이지 않는다(실측). 변수는 **상속**이라 Shell 컨테이너가
       값을 한 번 바꾸면 그 안 전체가 따라오고, 선택자 특이도 싸움이 없다.
       fallback 은 여전히 팔레트의 실제 hex 여야 한다 — 변수가 없는 문맥에서도 링이 그려진다. */
    expect(focusVisibleOutline).toMatch(/^2px solid var\(--clovir-focus-ring, #[0-9A-Fa-f]{6}\)$/);
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

    const want = `2px solid var(--clovir-focus-ring, ${ring})`;
    expect(theme.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline).toBe(want);
    expect(theme.components.MuiLink.styleOverrides.root["&:focus-visible"].outline).toBe(want);
    expect(theme.components.MuiOutlinedInput.styleOverrides.root["&.Mui-focused"].outline).toBe(want);

    /* 변수의 기본값은 `:root` 에서 나온다. 이 줄이 없으면 MUI 컴포넌트가 아닌 요소
       (예: `component="a"` 로 그린 '본문 바로가기')가 UA 기본 외곽선으로 떨어진다 —
       실측에서 실제로 `#101010` 이었다. */
    const base = theme.components.MuiCssBaseline.styleOverrides;
    expect(base[":root"]["--clovir-focus-ring"]).toBe(ring);
    expect(base[":focus-visible"].outline).toBe(want);
  });

  /* Shell 위의 링은 Canvas 용 링이면 안 된다 — 이 숫자가 그 이유다. 팔레트가 바뀌어
     Canvas 링이 Shell 에서도 3:1 을 넘게 되면 이 시험이 먼저 빨개지고, 그때 변수 분기를
     유지할지 다시 판단하면 된다(조용히 낡지 않는다). */
  it("Canvas 용 링은 Shell 위에서 비텍스트 3:1 에 미달하고, Shell 용 링은 통과한다", () => {
    const lum = (hex) => {
      const ch = [1, 3, 5]
        .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
        .map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
      return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
    };
    const contrast = (a, b) => {
      const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };
    const p = createClovirTheme("light").palette;
    const stops = [p.chrome.shell, ...(p.chrome.shellImage.match(/#[0-9A-Fa-f]{6}/g) || [])];
    for (const stop of stops) {
      expect(contrast(p.focusRing, stop), `canvas ring on ${stop}`).toBeLessThan(3);
      expect(contrast(p.chrome.focusRing, stop), `chrome ring on ${stop}`).toBeGreaterThanOrEqual(3);
    }
  });

  it("두 모드의 포커스 링 색이 서로 다르다(라이트/다크 각자 실측 대비를 맞춘 값)", () => {
    const light = createClovirTheme("light");
    const dark = createClovirTheme("dark");

    expect(light.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline).not.toBe(
      dark.components.MuiButtonBase.styleOverrides.root["&.Mui-focusVisible"].outline,
    );
  });
});
