import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ChoiceCards } from "./ChoiceCards.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 선택 카드 (계획 M1, D-548) — 저장되는 설정 값을 고르는 라디오 그룹.
 *
 * 지키는 것:
 *   1) `radiogroup` 안의 `radio` 이고, 고른 카드만 Tab 정지다.
 *   2) 화살표 키가 고른 값을 옮기고, 꺼진 선택지는 건너뛴다.
 *   3) 꺼진 선택지는 눌러도 바뀌지 않고, 설명이 `aria-describedby` 로 이어진다.
 */

const OPTIONS = [
  { value: "a", label: "첫째", description: "첫째 설명입니다." },
  { value: "b", label: "둘째", disabled: true, description: "둘째 설명입니다.", note: "지금은 고를 수 없습니다." },
  { value: "c", label: "셋째", description: "셋째 설명입니다." },
];

function Harness({ initial = "a" }) {
  const [value, setValue] = React.useState(initial);
  return (
    <ThemeModeProvider>
      <ChoiceCards name="t" ariaLabel="고르기" value={value} options={OPTIONS} onChange={setValue} />
    </ThemeModeProvider>
  );
}

describe("ChoiceCards", () => {
  it("라디오 그룹이고 고른 카드만 Tab 정지다", () => {
    render(<Harness />);
    expect(screen.getByRole("radiogroup", { name: "고르기" })).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.getAttribute("tabindex"))).toEqual(["0", "-1", "-1"]);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    expect(radios[0]).toHaveAccessibleDescription("첫째 설명입니다.");
  });

  it("화살표 키가 값을 옮기고 꺼진 선택지는 건너뛴다", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    screen.getAllByRole("radio")[0].focus();
    await user.keyboard("{ArrowRight}");
    const radios = screen.getAllByRole("radio");
    expect(radios[2]).toHaveAttribute("aria-checked", "true");
    expect(radios[2]).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getAllByRole("radio")[0]).toHaveAttribute("aria-checked", "true");
  });

  it("꺼진 선택지는 눌러도 바뀌지 않는다", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const off = screen.getAllByRole("radio")[1];
    expect(off).toHaveAttribute("aria-disabled", "true");
    await user.click(off);
    expect(screen.getAllByRole("radio")[0]).toHaveAttribute("aria-checked", "true");
  });
});
