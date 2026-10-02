import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import Box from "@mui/material/Box";

import { FACTS_ROW_SX, TechDetail } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 짧은 상태 면의 사실 줄(P17V) — 「기술 정보」가 단계 · 속성 띠 끝에 접힌 채 붙고, 펼치면 제 줄로 내려간다.
 * 「기술 정보」에 줄 하나를 따로 주던 때는 메일 · AI 연결 상태 면이 그만큼 길어져 첫 폼 칸이 1366 첫 화면 기준(420px) 아래로 밀렸다. */

function draw(trailing) {
  return render(
    <ThemeModeProvider>
      <Box sx={FACTS_ROW_SX} data-testid="row">
        <span>DNS 조회 정상</span>
        <TechDetail trailing={trailing}>상태 코드 ok</TechDetail>
      </Box>
    </ThemeModeProvider>,
  );
}

describe("사실 줄 끝의 「기술 정보」", () => {
  it("접힌 채 줄의 마지막 칸으로 오른쪽 끝에 서고, 펼치면 줄 전체 폭을 받는다", () => {
    const { container, getByTestId } = draw(true);
    const row = getByTestId("row");
    expect(getComputedStyle(row).display).toBe("flex");
    expect(getComputedStyle(row).flexWrap).toBe("wrap");
    const details = container.querySelector("details.k-techdetail");
    expect(details.hasAttribute("data-trailing")).toBe(true);
    expect(getComputedStyle(details).flexGrow).toBe("0");
    expect(getComputedStyle(details).marginInlineStart || getComputedStyle(details).marginLeft).toBe("auto");
    details.setAttribute("open", "");
    expect(getComputedStyle(details).flexBasis).toBe("100%");
  });

  it("반례 — `trailing` 이 없으면 예전처럼 제 줄의 접기다(줄 칸 규칙을 받지 않는다)", () => {
    const { container } = draw(false);
    const details = container.querySelector("details.k-techdetail");
    expect(details.hasAttribute("data-trailing")).toBe(false);
    details.setAttribute("open", "");
    expect(getComputedStyle(details).flexBasis).not.toBe("100%");
  });
});
