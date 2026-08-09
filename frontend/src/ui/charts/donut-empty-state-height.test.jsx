import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Donut } from "./Donut.jsx";
import { ThemeModeProvider } from "../ThemeModeProvider.jsx";

/* Donut 빈 상태의 높이 회귀.
 *
 * Donut은 데이터가 있을 때 size(기본 9rem)로 도넛 박스의 폭·높이를 정하는데, rows가 비어
 * ChartEmpty로 빠지는 경로는 size를 넘기지 않아 ChartEmpty 자체 기본값(4rem)으로 떨어졌다 —
 * 로딩→빈 상태 전환에서 카드가 9rem에서 4rem으로 훅 줄어드는 문제였다. LineSeries/Sparkline은
 * 이미 자신의 height prop을 그대로 ChartEmpty에 넘겨 이 문제가 없다(charts/base.jsx의
 * ChartEmpty 주석 참조) — Donut도 같은 방식으로, 새 prop을 만들지 않고 기존 size를 넘긴다.
 */
function emptyBox(label = "데이터 없음") {
  return screen.getByText(label).parentElement;
}

function renderDonut(props) {
  return render(
    <ThemeModeProvider>
      <Donut segments={[]} {...props} />
    </ThemeModeProvider>,
  );
}

describe("Donut 빈 상태의 높이", () => {
  it("size 기본값(9rem)을 빈 상태에도 그대로 써서 4rem으로 줄지 않는다", () => {
    renderDonut({});
    expect(getComputedStyle(emptyBox()).minHeight).toBe("9rem");
  });

  it("size를 바꾸면 빈 상태 높이도 같이 바뀐다", () => {
    renderDonut({ size: "14rem" });
    expect(getComputedStyle(emptyBox()).minHeight).toBe("14rem");
  });
});
