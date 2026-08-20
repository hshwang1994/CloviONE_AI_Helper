import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import { BarSeries } from "./BarSeries.jsx";
import { Donut } from "./Donut.jsx";
import { LineSeries } from "./LineSeries.jsx";
import { Sparkline } from "./Sparkline.jsx";
import { CHART_DASH, CHART_SERIES, createClovirTheme } from "../theme.js";

/* **렌더되는 색**을 잰다 — 정의된 토큰이 아니라.
 *
 * `theme-contract.test.js` 는 `palette.chart` 가 세 면에서 3:1 을 넘는다고 단언하고 계속
 * 초록이었다. 그런데 그 값은 **아무도 쓰지 않았다**: `CHART_SERIES` 의 제품 소비처가 0곳이라
 * 화면에 실제로 나간 색은 `resolveChartColor` 의 옛 기본값 `primary.main`(사용자 Accent)이고,
 * dark 에서 그 색은 plate 대비 2.90:1 로 비텍스트 3:1 을 깼다. 즉 통과하는 검사가 제품과
 * 무관한 표본을 재고 있었다(F-W4-15 와 같은 형태 — "아무것도 안 재면서 통과").
 *
 * 그래서 이 파일은 토큰이 아니라 **DOM 에 실제로 찍힌 stroke/fill** 을 읽는다. 그리고
 * Accent 를 바꿔 가며 같은 값이 나오는지 확인한다 — Identity(제품 고정)와 Interaction
 * (사용자 선택)의 경계가 차트에서 지켜지는지가 이 파일의 질문이다(D-179).
 */

const MODES = ["light", "dark"];
const OTHER_ACCENT = "#327C98";   // ACCENT_PRESETS 의 청록 — 인디고와 확실히 다르다

function withTheme(node, mode = "light", accent) {
  return render(
    <ThemeProvider theme={createClovirTheme(mode, accent)}>{node}</ThemeProvider>,
  );
}

// srgb 상대 휘도 → 대비. theme-contract.test.js 와 같은 계산식이다.
function luminance(hex) {
  const h = String(hex).replace("#", "");
  const parts = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2];
}
function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const TWO_SERIES = [
  { label: "계획", points: [5, 3, 0] },
  { label: "잔여", points: [3, 2, 0] },
];

describe("차트 시리즈 색은 Brand 고정 팔레트에서 온다 (렌더 결과 기준)", () => {
  it.each(MODES)("%s — LineSeries 의 두 선이 chart[0]·chart[1] 로 그려진다", (mode) => {
    const { container } = withTheme(<LineSeries series={TWO_SERIES} />, mode);
    const strokes = Array.from(container.querySelectorAll("path[stroke]")).map((p) => p.getAttribute("stroke"));
    expect(strokes).toEqual([CHART_SERIES[mode][0], CHART_SERIES[mode][1]]);
  });

  it("색만으로는 시리즈를 못 나르므로 2번 선은 실제로 파선으로 그려진다", () => {
    const { container } = withTheme(<LineSeries series={TWO_SERIES} />);
    const paths = Array.from(container.querySelectorAll("path[stroke]"));
    expect(paths[0].getAttribute("stroke-dasharray")).toBeNull();
    expect(paths[1].getAttribute("stroke-dasharray")).toBe(CHART_DASH[1]);
  });

  it("사용자 Accent 를 바꿔도 시리즈 색은 그대로다 (Identity 는 Interaction 을 따르지 않는다)", () => {
    const a = withTheme(<LineSeries series={TWO_SERIES} />, "light");
    const strokesA = Array.from(a.container.querySelectorAll("path[stroke]")).map((p) => p.getAttribute("stroke"));
    const b = withTheme(<LineSeries series={TWO_SERIES} />, "light", OTHER_ACCENT);
    const strokesB = Array.from(b.container.querySelectorAll("path[stroke]")).map((p) => p.getAttribute("stroke"));
    expect(strokesB).toEqual(strokesA);
    // 그리고 그 색은 Accent 자체가 아니다 — 예전 기본값이 정확히 Accent 였다.
    expect(strokesB).not.toContain(OTHER_ACCENT);
  });

  it.each(MODES)("%s — Donut 의 조각들이 서로 다른 색으로 그려진다", (mode) => {
    const { container } = withTheme(
      <Donut segments={[{ label: "계획", value: 4 }, { label: "진행", value: 2 }, { label: "완료", value: 1 }]} />,
      mode,
    );
    // 첫 <circle> 은 트랙이다 — 조각은 그 뒤부터.
    const arcs = Array.from(container.querySelectorAll("circle[stroke-dasharray]")).map((c) => c.getAttribute("stroke"));
    expect(arcs).toEqual([CHART_SERIES[mode][0], CHART_SERIES[mode][1], CHART_SERIES[mode][2]]);
    expect(new Set(arcs).size).toBe(3);
  });

  it("Donut 의 모수는 입력이다 — 안 주면 조각 합, 주면 그 값이고 차이를 글자로 말한다", () => {
    const segs = [{ label: "완료", value: 3 }, { label: "남음", value: 2 }];
    const derived = withTheme(<Donut segments={segs} unit="건" />);
    expect(derived.container.textContent).toContain("5건");
    expect(derived.container.textContent).not.toContain("분류 없음");

    const explicit = withTheme(<Donut segments={segs} total={8} unit="건" />);
    expect(explicit.container.textContent).toContain("8건");
    expect(explicit.container.textContent).toContain("분류 없음");
    expect(explicit.container.textContent).toContain("3건");   // 8 - 5
  });

  it.each(MODES)("%s — BarSeries 와 Sparkline 의 기본색도 chart[0] 이다", (mode) => {
    const bar = withTheme(<BarSeries items={[{ label: "가", value: 3 }, { label: "나", value: 1 }]} />, mode);
    const fills = Array.from(bar.container.querySelectorAll("rect"))
      .map((r) => r.getAttribute("fill"))
      .filter((f) => f === CHART_SERIES[mode][0]);
    expect(fills.length).toBeGreaterThan(0);

    const spark = withTheme(<Sparkline points={[1, 4, 2, 5]} />, mode);
    const line = spark.container.querySelector("path[stroke]");
    expect(line.getAttribute("stroke")).toBe(CHART_SERIES[mode][0]);
  });

  it.each(MODES)("%s — 실제로 그려지는 시리즈 색이 세 면에서 비텍스트 3:1 을 넘는다", (mode) => {
    const theme = createClovirTheme(mode);
    const { container } = withTheme(<LineSeries series={TWO_SERIES} />, mode);
    const strokes = Array.from(container.querySelectorAll("path[stroke]")).map((p) => p.getAttribute("stroke"));
    const faces = [theme.palette.background.plate, theme.palette.background.inset, theme.palette.background.canvas];
    for (const s of strokes) {
      for (const face of faces) {
        expect(contrast(s, face), `${s} on ${face}`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it("시리즈가 5개를 넘으면 나머지를 '기타' 하나로 접는다 — 6번째부터는 구분되지 않는다", () => {
    const many = Array.from({ length: 8 }, (_, i) => ({ label: `S${i}`, points: [i + 1, i] }));
    const { container } = withTheme(<LineSeries series={many} />);
    const strokes = container.querySelectorAll("path[stroke]");
    expect(strokes.length).toBe(6);
    expect(container.textContent).toContain("기타");
  });
});

describe("Sparkline 의 바닥은 0 이다 (면적이 값에 비례한다)", () => {
  it("값이 전부 양수면 면 채움이 viewBox 바닥이 아니라 0 선에서 닫힌다", () => {
    const { container } = withTheme(<Sparkline points={[2, 4, 3]} />);
    const area = container.querySelector("path[fill-opacity]");
    // 예전 판은 항상 `L100 32 L0 32 Z`(viewBox 바닥)로 닫았다. 이제 0 선은 y=29(H-PAD)다.
    expect(area.getAttribute("d")).not.toMatch(/L100 32 L0 32 Z/);
    expect(area.getAttribute("d")).toMatch(/L100 29\.00 L0 29\.00 Z/);
  });
});
