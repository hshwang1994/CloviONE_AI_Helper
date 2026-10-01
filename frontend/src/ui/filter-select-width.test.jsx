import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { FILTER_SELECT_SIZES, FilterSelect, SELECT_WIDTH_RANGE_REM, selectWidthRem } from "./filters.jsx";
import { FilterBar, SEARCH_SLOT_STEPS } from "./FilterBar.jsx";
import { SearchBox } from "./filters.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 닫힌 집합 칸의 폭은 **선택지**가 정한다 (F4 · D-530).
 *
 * 예전 칸은 `flex: 0 0 auto` 라 지금 고른 값의 길이가 폭을 정했다 — 값을 바꾸는 순간 칸이 늘어 옆 칸을 밀었고, 상한(13rem)에 닿은
 * 「문제 종류」 값은 여섯 글자에서 잘렸다. 폭은 가장 긴 선택지로 한 번 정하고 [8, 16]rem 으로 묶는다. jsdom 에는 캔버스가 없어 글 폭은
 * 어림(한글 1em · 그 밖 0.58em)이다 — 이 시험은 그 어림으로 계산이 맞는지를 본다. */

const LONG = [
  { value: "a", label: "담당자를 포털 계정으로 연결하지 못한 티켓 3건" },
  { value: "b", label: "닫힌 계정 2건" },
];

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("selectWidthRem — 선택지로 잰 폭", () => {
  it("짧은 선택지는 바닥(8rem)에 선다", () => {
    expect(selectWidthRem({ label: "상태", options: [{ value: "a", label: "활성" }] })).toBe(8);
  });

  it("가장 긴 선택지가 폭을 정하고 0.5rem 단위로 올린다", () => {
    // 14 + 6 + 32 + 2 = 54px = 3.375rem, 「결과」 2em × 0.9375, 「정책으로 막힘」 6.25em × 0.9375
    const rem = selectWidthRem({ label: "결과", options: [{ value: "x", label: "정책으로 막힘" }] });
    expect(rem).toBe(Math.ceil((3.375 + 2 * 0.9375 + 6.25 * 0.9375) / 0.5) * 0.5);
    expect(rem % 0.5).toBe(0);
  });

  it("「전체」 낱말도 선택지로 센다 — 빈 값도 칸에 선다", () => {
    const withAll = selectWidthRem({ label: "상태", options: [{ value: "a", label: "가" }], allLabel: "보관 제외 전체 상태들" });
    const noAll = selectWidthRem({ label: "상태", options: [{ value: "a", label: "가" }], allLabel: "보관 제외 전체 상태들", noAllOption: true });
    expect(withAll).toBeGreaterThan(noAll);
  });

  it("아주 긴 선택지는 상한(16rem)에 멈춘다 — 넘치면 칸 안에서 말줄임이다", () => {
    expect(selectWidthRem({ label: "문제 종류", options: LONG })).toBe(SELECT_WIDTH_RANGE_REM[1]);
  });

  it("크기를 말하면 그 표가 이긴다 — S 8 · M 10 · L 13 · XL 16", () => {
    expect(FILTER_SELECT_SIZES).toEqual({ S: 8, M: 10, L: 13, XL: 16 });
    for (const [size, rem] of Object.entries(FILTER_SELECT_SIZES)) {
      expect(selectWidthRem({ label: "문제 종류", options: LONG, size })).toBe(rem);
    }
  });
});

describe("FilterSelect 줄 칸 — 값을 바꿔도 폭이 흔들리지 않는다", () => {
  function Harness({ options, label = "결과" }) {
    const [value, setValue] = React.useState("");
    return (
      <FilterBar>
        <FilterSelect label={label} value={value} onChange={setValue} options={options} />
      </FilterBar>
    );
  }

  it("칸 폭은 선택지로 정한 rem 이고 값을 고른 뒤에도 같다", async () => {
    const user = userEvent.setup();
    const options = [{ value: "ok", label: "성공" }, { value: "blocked_policy", label: "정책으로 막힘" }];
    const { container } = ui(<Harness options={options} />);
    const cell = container.querySelector('[data-filter-kind="enum"]');
    const before = getComputedStyle(cell).width;
    expect(before).toBe(`${selectWidthRem({ label: "결과", options })}rem`);
    await user.click(screen.getByRole("combobox", { name: "결과" }));
    await user.click(await screen.findByRole("option", { name: "정책으로 막힘" }));
    expect(getComputedStyle(cell).width).toBe(before);
    // 긴 값은 칸 안에서 말줄임이고 전체 값은 `title` 이 든다.
    expect(cell.querySelector("[data-row-value]")).toHaveAttribute("title", "결과 정책으로 막힘");
  });

  it("호출부가 폭을 말하면 그것이 이긴다", () => {
    const { container } = ui(
      <FilterBar>
        <FilterSelect label="상태" value="" onChange={() => {}} options={[{ value: "a", label: "가" }]} sx={{ width: "12rem" }} />
      </FilterBar>,
    );
    expect(getComputedStyle(container.querySelector('[data-filter-kind="enum"]')).width).toBe("12rem");
  });
});

describe("검색 칸은 남는 폭을 먹지 않는다", () => {
  it("계단은 면 폭 64rem 이상 20rem · 44 ~ 64rem 16rem 이고 그 아래는 제 줄 전체다", () => {
    expect(SEARCH_SLOT_STEPS).toEqual([[64, "20rem"], [44, "16rem"]]);
  });

  it("필터 면 안의 검색 칸은 자라지 않는 고정 폭 칸이다", () => {
    ui(
      <FilterBar search={<SearchBox value="" onSearch={() => {}} ariaLabel="검색" />}>
        <FilterSelect label="상태" value="" onChange={() => {}} options={[{ value: "a", label: "가" }]} />
      </FilterBar>,
    );
    /* jsdom 의 계산 스타일은 특이도를 보지 않고 나중에 실린 규칙(검색 칸 자신의 `flex: 1 1 20rem`)을 쓴다 — 그래서 줄이 실은 규칙
       글을 직접 본다. 브라우저에서는 줄의 규칙(클래스 + 속성 선택자)이 이긴다. */
    const css = [...document.querySelectorAll("style")].map((s) => s.textContent).join(" ");
    const block = (css.match(/>\s*\[data-filter-kind=search\]\s*\{[^}]*\}/) || [""])[0];
    // flex-grow 0 — 검색이 줄을 먹고 조건 칸을 바닥 폭으로 누르지 않는다. 폭은 계단 변수가 말한다(상한 20rem).
    expect(block).toMatch(/flex-grow:\s*0/);
    expect(block).toMatch(/flex-shrink:\s*0/);
    expect(block).toMatch(/flex-basis:\s*var\(--search-slot,\s*20rem\)/);
  });
});
