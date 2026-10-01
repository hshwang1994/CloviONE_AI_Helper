import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { PeriodFilter } from "./PeriodFilter.jsx";
import { addDays, forgetPresets, kstToday, matchPreset, periodLabel, periodProblem, presetRange, rememberPreset } from "./period.js";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 「기간」 칸 (F4 · D-530). 예전에는 날짜 칸 둘(라벨 위 + 36)이 필터 줄에 섰고 칩도 둘이었다 — 하나만 지우면 반쪽 기간이 남았다.
 * 이 파일이 지키는 것: 프리셋 → 키 쌍(KST 달력일 경계), 키 쌍 → 이름, 서버 기본값의 이름, 칸 하나가 두 키를 함께 바꾸는 것. */

/* 2026-10-01 15:30 UTC = KST 2026-10-02 00:30 — 자정 근처라 UTC 날짜로 계산하면 하루가 밀리는 시각이다. */
const NOW = new Date("2026-10-01T15:30:00Z");

afterEach(() => forgetPresets());

describe("프리셋 → 키 쌍 — KST 달력일이다", () => {
  it("오늘은 KST 날짜다(UTC 로는 아직 10월 1일)", () => {
    expect(kstToday(NOW)).toBe("2026-10-02");
    expect(presetRange("today", { now: NOW })).toEqual({ from: "2026-10-02", to: "2026-10-02" });
  });

  it("최근 7일 · 30일은 오늘을 포함해 센다", () => {
    expect(presetRange("7d", { now: NOW })).toEqual({ from: "2026-09-26", to: "2026-10-02" });
    expect(presetRange("30d", { now: NOW })).toEqual({ from: "2026-09-03", to: "2026-10-02" });
  });

  it("이번 달은 1일부터 오늘까지, 지난달은 그 달 전체다 — 해가 넘어가도 맞다", () => {
    expect(presetRange("thisMonth", { now: NOW })).toEqual({ from: "2026-10-01", to: "2026-10-02" });
    expect(presetRange("lastMonth", { now: NOW })).toEqual({ from: "2026-09-01", to: "2026-09-30" });
    const january = new Date("2026-01-15T03:00:00Z");
    expect(presetRange("lastMonth", { now: january })).toEqual({ from: "2025-12-01", to: "2025-12-31" });
  });

  it("전체는 두 끝을 열어 둔다", () => {
    expect(presetRange("all", { now: NOW })).toEqual({ from: "", to: "" });
  });

  it("시각 프리셋은 KST 벽시계의 시작만 적고 끝을 열어 둔다", () => {
    expect(presetRange("1h", { mode: "datetime", now: NOW })).toEqual({ from: "2026-10-01T23:30", to: "" });
    expect(presetRange("24h", { mode: "datetime", now: NOW })).toEqual({ from: "2026-10-01T00:30", to: "" });
    expect(presetRange("7d", { mode: "datetime", now: NOW })).toEqual({ from: "2026-09-25T00:30", to: "" });
  });

  it("달력 더하기는 시간대를 타지 않는다", () => {
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDays("2024-03-01", -1)).toBe("2024-02-29");
  });
});

describe("키 쌍 → 이름", () => {
  it("오늘 계산한 프리셋과 같으면 그 이름이다", () => {
    expect(periodLabel(presetRange("7d", { now: NOW }), { now: NOW })).toBe("최근 7일");
    expect(matchPreset(presetRange("lastMonth", { now: NOW }), { now: NOW })).toBe("lastMonth");
  });

  it("어제 고른 「최근 7일」은 오늘의 「최근 7일」이 아니다 — 날짜를 말한다", () => {
    const yesterday = new Date(NOW.getTime() - 24 * 3600 * 1000);
    const old = presetRange("7d", { now: yesterday });
    expect(periodLabel(old, { now: NOW })).toBe("9월 25일 ~ 10월 1일");
  });

  it("한쪽만 있으면 부터 · 까지, 다른 해면 해를 붙인다", () => {
    expect(periodLabel({ from: "2026-09-02", to: "" }, { now: NOW })).toBe("9월 2일부터");
    expect(periodLabel({ from: "", to: "2026-09-30" }, { now: NOW })).toBe("9월 30일까지");
    expect(periodLabel({ from: "2025-12-30", to: "2026-01-02" }, { now: NOW })).toBe("2025년 12월 30일 ~ 1월 2일");
  });

  it("빈 값은 서버 기본값의 이름이다 — 보통 「전체」, AI 사용 통계는 「최근 30일」", () => {
    expect(periodLabel({ from: "", to: "" }, { now: NOW })).toBe("전체");
    expect(periodLabel({ from: "", to: "" }, { now: NOW, emptyPreset: "30d" })).toBe("최근 30일");
    expect(periodLabel({ from: "", to: "" }, { now: NOW, emptyLabel: "최근 24시간" })).toBe("최근 24시간");
    // 서버 기본값과 같은 기간을 손으로 적어도 같은 이름이다.
    expect(periodLabel(presetRange("30d", { now: NOW }), { now: NOW, emptyPreset: "30d", presets: ["today", "7d", "30d"] })).toBe("최근 30일");
  });

  it("시각 쌍은 방금 고른 프리셋만 그 이름이고, 다시 열면 실제 시각을 말한다", () => {
    const r = presetRange("1h", { mode: "datetime", now: NOW });
    expect(periodLabel(r, { mode: "datetime", now: NOW })).toBe("10월 1일 23:30부터");
    rememberPreset(r, "1h", "datetime");
    expect(periodLabel(r, { mode: "datetime", now: NOW })).toBe("최근 1시간");
    forgetPresets();
    expect(periodLabel(r, { mode: "datetime", now: NOW })).toBe("10월 1일 23:30부터");
  });

  it("시작이 끝보다 늦으면 문장으로 막는다", () => {
    expect(periodProblem({ from: "2026-10-02", to: "2026-10-01" })).toBe("시작이 끝보다 늦습니다.");
    expect(periodProblem({ from: "2026-10-01", to: "2026-10-01" })).toBe("");
    expect(periodProblem({ from: "2026-10-01", to: "" })).toBe("");
  });
});

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("PeriodFilter — 칸 하나, 키 둘", () => {
  it("칸은 34 줄 칸 해부다 — 칸 안 이름 「기간」과 값", () => {
    const { container } = ui(<PeriodFilter from="" to="" onChange={() => {}} now={NOW} emptyPreset="30d" presets={["today", "7d", "30d"]} />);
    const cell = container.querySelector('[data-filter-kind="period"]');
    expect(cell).not.toBeNull();
    expect(cell.querySelector("[data-prefix-label]")).toHaveTextContent("기간");
    expect(cell.querySelector("[data-row-value]")).toHaveTextContent("최근 30일");
    // 대화상자를 여는 콤보 상자로 알린다 — 메뉴(listbox)가 아니다.
    expect(within(cell).getByRole("combobox")).toHaveAttribute("aria-haspopup", "dialog");
  });

  it("프리셋을 고르면 두 키를 함께 바꾸고, 서버 기본값 프리셋이면 두 키를 비운다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    ui(<PeriodFilter from="" to="" onChange={onChange} now={NOW} emptyPreset="30d" presets={["today", "7d", "30d"]} />);
    await user.click(screen.getByRole("combobox", { name: "기간" }));
    const dialog = await screen.findByRole("dialog", { name: "기간 고르기" });
    // 지금 값(빈 값 = 최근 30일)이 표시된다.
    expect(within(dialog).getByRole("menuitemradio", { name: "최근 30일" })).toHaveAttribute("aria-checked", "true");
    await user.click(within(dialog).getByRole("menuitemradio", { name: "최근 7일" }));
    expect(onChange).toHaveBeenLastCalledWith({ from: "2026-09-26", to: "2026-10-02" });

    await user.click(screen.getByRole("combobox", { name: "기간" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("menuitemradio", { name: "최근 30일" }));
    expect(onChange).toHaveBeenLastCalledWith({ from: "", to: "" });
  });

  it("직접 고른 기간이 거꾸로면 「적용」이 막히고 까닭을 말한다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    ui(<PeriodFilter mode="datetime" from="2026-10-01T10:00" to="2026-10-01T09:00" onChange={onChange} now={NOW} />);
    await user.click(screen.getByRole("combobox", { name: "기간" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("시작이 끝보다 늦습니다.");
    expect(within(dialog).getByRole("button", { name: "적용" })).toBeDisabled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("시각 쌍의 직접 선택은 두 시각을 함께 적용한다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    ui(<PeriodFilter mode="datetime" from="" to="" onChange={onChange} now={NOW} />);
    await user.click(screen.getByRole("combobox", { name: "기간" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByRole("menuitemradio").map((el) => el.textContent)).toEqual(["최근 1시간", "최근 24시간", "최근 7일", "전체"]);
    const start = within(dialog).getByLabelText("시작 시각");
    await user.type(start, "2026-10-01T09:00");
    await user.click(within(dialog).getByRole("button", { name: "적용" }));
    expect(onChange).toHaveBeenLastCalledWith({ from: "2026-10-01T09:00", to: "" });
  });
});
