import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import { DateField } from "./DateField.jsx";
import { createClovirTheme } from "./theme.js";

/* 날짜 칸 조작의 이름은 한국어다(r23 조작 요소 대장).
 *
 * 로캘을 안 주면 MUI 기본값 「Choose date」 · 「Year」 · 「Month」 · 「Day」가 그대로 접근 이름이 되어, 화면 낭독이 새 티켓 ·
 * 프로젝트 · 주간 리포트 수정 창의 날짜 칸을 영어로 읽었다. 눈에 보이는 글자가 아니라서 문구 대장(화면 글자)에는 잡히지 않았고,
 * 조작 요소 대장의 이름 칸에서 드러났다. 단추 이름은 명사구로 쓴다(D-587). */
function renderField(value) {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <DateField label="마감일" value={value} onChange={() => {}} />
    </ThemeProvider>,
  );
}

describe("DateField — 조작 이름", () => {
  it("달력 여는 단추는 「날짜 선택」이고, 값이 있으면 그 값을 함께 말한다", async () => {
    renderField("2026-10-20");
    const button = await screen.findByRole("button", { name: /^날짜 선택/ });
    expect(button).toHaveAccessibleName("날짜 선택(지금 2026년 10월 20일)");
    expect(screen.queryByRole("button", { name: /Choose date/ })).toBeNull();
  });

  it("값이 없으면 단추 이름은 「날짜 선택」 하나다", async () => {
    renderField("");
    expect(await screen.findByRole("button", { name: "날짜 선택" })).toBeInTheDocument();
  });

  it("연 · 월 · 일 구간의 이름이 한국어다", async () => {
    renderField("2026-10-20");
    await screen.findByRole("button", { name: /^날짜 선택/ });
    const names = screen.getAllByRole("spinbutton").map((el) => el.getAttribute("aria-label"));
    expect(names).toEqual(["연도", "월", "일"]);
  });
});
