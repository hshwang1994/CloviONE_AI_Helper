import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ThemeModeProvider } from "../ThemeModeProvider.jsx";
import { BarSeries } from "./BarSeries.jsx";

/* 막대는 **0 과 「모른다」를 못 가른다.**
 *
 * 길이가 0 인 막대는 「하나도 못 했다」로 읽힌다. 그런데 완료율이 `null` 인 달은 「할 것이
 * 없었다」다 — 배정이 0건이라 분모가 없다. 두 사실이 같은 그림을 갖는다면 글자가 갈라야
 * 한다. 그 자리가 `valueText` 다.
 *
 * 값을 아예 안 그리는 길(행을 빼는 것)은 더 나쁘다: 그 달이 화면에서 사라져 「6개월」이라고
 * 적어 둔 기간과 그려진 달 수가 어긋난다.
 */
function withTheme(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("BarSeries — 값 글자를 줄이 정할 수 있다", () => {
  it("valueText 를 준 줄은 그 글자를, 안 준 줄은 값과 단위를 말한다", () => {
    withTheme(
      <BarSeries
        max={100}
        unit="%"
        items={[
          { label: "26-06", value: 0, valueText: "-" },
          { label: "26-07", value: 50 },
        ]}
      />,
    );
    expect(screen.getByText("-")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    // 0% 라고 말하지 않는다 — 그것이 이 prop 이 생긴 이유다.
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("valueText 가 없으면 예전과 똑같다 — 안 쓰는 호출부는 한 글자도 안 바뀐다", () => {
    withTheme(<BarSeries unit="건" items={[{ label: "이번 주", value: 0 }]} />);
    expect(screen.getByText("0건")).toBeInTheDocument();
  });

  it("막대 길이는 여전히 값이 정한다 — 글자를 바꿔도 그림은 안 속인다", () => {
    const { container } = withTheme(
      <BarSeries max={100} unit="%" items={[{ label: "26-06", value: 0, valueText: "-" }]} />,
    );
    // 0 인 막대는 채워진 조각을 안 만든다(트랙만 남는다).
    const fills = container.querySelectorAll("rect[width]");
    for (const r of fills) expect(Number(r.getAttribute("width"))).toBe(100);
  });
});
