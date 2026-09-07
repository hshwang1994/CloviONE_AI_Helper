import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ThemeModeProvider } from "../ThemeModeProvider.jsx";
import { ColumnSeries } from "./ColumnSeries.jsx";

/* 세로 막대 — 시간축이 있는 값을 위한 그림.
 *
 * 가로 막대는 시간을 세로로 눕힌다. 읽는 사람은 시간을 위에서 아래로 따라가면서 크기는
 * 옆으로 재야 하고, 두 축이 직교하지 않는다. 이 부품이 재는 것 셋이다: 축 라벨과 막대가
 * 같은 격자를 쓰는가, 0 과 「모른다」를 가르는가, 기준을 준 값이 절대값으로 서는가.
 */
function withTheme(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

const MONTHS = [
  { key: "2026-06", label: "26-06", value: 0, valueText: "-", hint: "2026-06" },
  { key: "2026-07", label: "26-07", value: 50 },
  { key: "2026-08", label: "26-08", value: 100 },
];

describe("ColumnSeries", () => {
  it("달마다 값 글자와 x축 라벨이 함께 선다", () => {
    withTheme(<ColumnSeries items={MONTHS} max={100} unit="%" />);
    for (const label of ["26-06", "26-07", "26-08"]) {
      expect(screen.getByText(label), label).toBeInTheDocument();
    }
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  /* 🔴 길이 0 인 막대는 「하나도 못 했다」로 읽힌다. 값이 없는 칸은 **막대를 안 만든다** —
     글자가 그 둘을 가른다. */
  it("값이 없는 칸은 막대를 안 그리고 «-» 로 적는다", () => {
    const { container } = withTheme(<ColumnSeries items={MONTHS} max={100} unit="%" />);
    expect(screen.getByText("-")).toBeInTheDocument();
    expect(screen.queryByText("0%")).toBeNull();
    // 막대는 값이 있는 둘만 그려진다 — 값 없는 칸에는 0px 막대도 없다.
    expect(container.querySelectorAll("[data-column-bar]")).toHaveLength(2);
  });

  it("y축 라벨은 기준을 그대로 말한다 — 꼭대기·가운데·0", () => {
    withTheme(<ColumnSeries items={MONTHS} max={100} unit="%" />);
    for (const t of ["100", "50", "0"]) {
      expect(screen.getAllByText(t).length, t).toBeGreaterThan(0);
    }
  });

  it("기준을 안 주면 가장 큰 값이 꼭대기다", () => {
    withTheme(<ColumnSeries items={[{ label: "가", value: 4 }, { label: "나", value: 2 }]} unit="건" />);
    expect(screen.getByText("4건")).toBeInTheDocument();
    // 축 꼭대기가 4다(기준을 안 줬으니 관측된 최대).
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);
  });

  it("x축 라벨은 한 줄이고 넘치면 말줄임이다 — 줄이 늘면 막대 바닥선이 어긋난다", () => {
    const { container } = withTheme(
      <ColumnSeries items={[{ label: "아주 긴 달 이름입니다", value: 1 }]} unit="건" />,
    );
    const label = screen.getByText("아주 긴 달 이름입니다");
    expect(getComputedStyle(label).whiteSpace).toBe("nowrap");
    expect(getComputedStyle(label).textOverflow).toBe("ellipsis");
    expect(container).toBeTruthy();
  });

  /* 한 칸에 막대가 둘일 수 있다. 값 글자는 **그중 한 막대**의 값이고 자기 막대 바로 위에
     선다 — 칸 가운데는 두 막대 사이의 빈 자리라, 그 위의 숫자가 어느 막대의 값인지 눈이
     못 정한다. */
  describe("한 칸에 막대 둘", () => {
    const GROUPED = [
      { key: "a", label: "26-07", bars: [{ key: "assigned", value: 4 }, { key: "done", value: 2 }] },
      { key: "b", label: "26-08", bars: [{ key: "assigned", value: 6 }, { key: "done", value: 6 }] },
    ];

    it("막대는 칸마다 둘이고 값 글자는 하나다", () => {
      const { container } = withTheme(<ColumnSeries items={GROUPED} unit="건" />);
      expect(container.querySelectorAll("[data-column-bar]")).toHaveLength(4);
      // 기본은 마지막 막대(완료)의 값이다 — 배정 4 는 글자로 안 나온다.
      expect(screen.getByText("2건")).toBeInTheDocument();
      expect(screen.queryByText("4건")).toBeNull();
    });

    it("labelBar 로 어느 막대의 값을 적을지 정한다", () => {
      withTheme(<ColumnSeries items={GROUPED} unit="건" labelBar={0} />);
      expect(screen.getByText("4건")).toBeInTheDocument();
      expect(screen.queryByText("2건")).toBeNull();
    });

    it("기준을 안 주면 두 막대를 통틀어 가장 큰 값이 꼭대기다", () => {
      withTheme(<ColumnSeries items={GROUPED} unit="건" />);
      // 배정 6 이 최대라 y축 꼭대기가 6 이다.
      expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    });
  });

  it("항목이 없으면 빈 상자를 남기지 않는다", () => {
    withTheme(<ColumnSeries items={[]} emptyLabel="집계할 달이 없습니다" />);
    expect(screen.getByText("집계할 달이 없습니다")).toBeInTheDocument();
  });
});
