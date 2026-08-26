import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/* 기간별 달성 비율 묶음이 지키는 것 셋.
 *
 *   1. **모든 줄이 같은 구조다.** 예전 `BarSeries` 배치는 부연이 어떤 줄에만 한 줄을 더
 *      만들어 행 높이가 들쭉날쭉했다(실측 1920: 넉 주 중 둘만).
 *   2. **분모가 없는 줄을 0% 로 그리지 않는다.** 마감이 0건인 주는 「아무것도 못 했다」가
 *      아니라 「할 것이 없었다」다.
 *   3. **막대가 기준을 넘지 않는다.** 비율이라 100% 가 상한이다.
 */

import { ProgressRows } from "./ProgressRows.jsx";
import { resetRevealMemory } from "../motion.js";

const ROWS = [
  { key: "a", label: "8월 3일 주간", value: 0, total: 0 },
  { key: "b", label: "8월 10일 주간", value: 3, total: 12 },
  { key: "c", label: "8월 17일 주간", value: 2, total: 2 },
];

function widths() {
  // 채운 막대는 트랙 뒤에 오는 두 번째 rect 다. 트랙만 있는 줄에는 채운 막대가 없다.
  return [...document.querySelectorAll("svg")].map((svg) => {
    const fills = svg.querySelectorAll("rect");
    return fills.length > 1 ? Number(fills[1].getAttribute("width")) : null;
  });
}

beforeEach(() => {
  resetRevealMemory();
  // 연출 없이 최종 상태로 그리게 한다 — 이 시험이 재는 것은 폭이지 전환이 아니다.
  vi.stubGlobal("matchMedia", (q) => ({
    matches: q.includes("prefers-reduced-motion"), media: q,
    addEventListener() {}, removeEventListener() {},
  }));
});

describe("ProgressRows", () => {
  it("모든 줄이 기간과 사실 한 줄을 갖는다", () => {
    render(<ProgressRows items={ROWS} formatRow={(r) => `마감 ${r.total}건 중 ${r.value}건 완료`} />);
    expect(screen.getByText("8월 3일 주간")).toBeInTheDocument();
    expect(screen.getByText("마감 12건 중 3건 완료")).toBeInTheDocument();
    expect(screen.getByText("마감 2건 중 2건 완료")).toBeInTheDocument();
  });

  it("🔴 분모가 0 인 줄은 0% 가 아니라 「마감 없음」이고 채운 막대가 없다", () => {
    render(<ProgressRows items={ROWS} emptyRowLabel="마감 없음" />);
    expect(screen.getByText("마감 없음")).toBeInTheDocument();
    expect(widths()[0]).toBeNull();
  });

  it("막대는 value/total 비율이고 100 을 넘지 않는다", () => {
    render(<ProgressRows items={ROWS} revealKey="t:1" />);
    const w = widths();
    expect(w[1]).toBe(25);   // 3 / 12
    expect(w[2]).toBe(100);  // 2 / 2
  });

  it("값이 숫자가 아닌 줄은 버린다 — 없는 값을 0 으로 그리지 않는다", () => {
    render(<ProgressRows items={[{ label: "빈 주", value: null, total: 4 }, ...ROWS]} />);
    expect(screen.queryByText("빈 주")).toBeNull();
  });

  it("줄이 하나도 없으면 그림을 접고 한 줄로 말한다", () => {
    render(<ProgressRows items={[]} emptyLabel="표본이 없습니다" />);
    expect(screen.getByText("표본이 없습니다")).toBeInTheDocument();
    expect(document.querySelector("svg")).toBeNull();
  });
});
