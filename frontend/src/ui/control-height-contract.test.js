import { describe, expect, it } from "vitest";

import { CONTROL, CONTROL_HEIGHT_VAR, controlHeight, createClovirTheme, densityVars } from "./theme.js";

/* 컨트롤 높이는 둘이다 (D-526). 34 = 페이지 머리 · 도구 줄 · 필터 줄 · 폼 · 판 머리 · 발의 입력 · 선택 · 단추, 30 = 표 행 ·
 * 목록 행 · 선택 발 · 메시지 상자 · 체크리스트 행. 예전에는 입력만 36 이라 같은 줄의 34 단추와 2px, 30 단추와 6px
 * 어긋났다. 옛 이름(`button` · `buttonSm` · `input` · `iconButton` · `tableCellDense`)은 이 둘의 별칭으로만 남는다. */

const CONTROL_ALIASES = ["control", "controlDense", "button", "buttonSm", "input", "iconButton", "tableCellDense"];

describe("컨트롤 높이 계약", () => {
  it("컨트롤 높이 별칭은 전부 34 아니면 30 이다", () => {
    for (const key of CONTROL_ALIASES) {
      expect([34, 30], `CONTROL.${key} = ${CONTROL[key]}`).toContain(CONTROL[key]);
    }
    expect(CONTROL.control).toBe(34);
    expect(CONTROL.controlDense).toBe(30);
    expect(CONTROL.input, "입력은 단추와 같은 34 다 — 36 은 없다").toBe(CONTROL.control);
    expect(CONTROL.button).toBe(CONTROL.control);
    expect(CONTROL.buttonSm).toBe(CONTROL.controlDense);
  });

  it("입력 높이는 변수 하나에서 나오고, 밀집 그릇이 그 변수를 30 으로 바꾼다", () => {
    expect(controlHeight).toBe(`var(${CONTROL_HEIGHT_VAR}, 2.125rem)`);
    expect(densityVars("dense")).toEqual({ [CONTROL_HEIGHT_VAR]: "1.875rem" });
    expect(densityVars()).toEqual({});
    const t = createClovirTheme("light");
    expect(t.components.MuiOutlinedInput.styleOverrides.root.minHeight).toBe(controlHeight);
    expect(t.components.MuiAutocomplete.styleOverrides.inputRoot.height).toBe(controlHeight);
    expect(t.components.MuiPickersOutlinedInput.styleOverrides.root.minHeight).toBe(controlHeight);
  });

  it("입력의 위아래 안쪽 여백은 높이에서 계산된다 — 밀집 칸에서도 글이 가운데에 선다", () => {
    const t = createClovirTheme("light");
    const pad = t.components.MuiOutlinedInput.styleOverrides.input.paddingTop;
    expect(String(pad)).toContain(CONTROL_HEIGHT_VAR);
    expect(t.components.MuiOutlinedInput.styleOverrides.input.paddingBottom).toBe(pad);
  });
});
