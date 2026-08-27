import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import { Sparkline } from "./Sparkline.jsx";
import { resolveChartColor } from "./base.jsx";
import { lineSeriesOption } from "./LineSeries.jsx";
import { donutOption } from "./Donut.jsx";
import { barRowOption } from "./BarSeries.jsx";
import { CHART_DASH, CHART_SERIES, createClovirTheme } from "../theme.js";

/* qa-contract-change: LineSeries·Donut·BarSeries 를 ECharts 로 옮기며(§15.2) DOM의 circle[stroke-dasharray]·path[stroke] 를 직접 세던 단언을 걷었다 — 이제 그 색이 option.series[]에 실제로 들어가는지를 렌더 없이 순수 함수로 잰다. */
/* **렌더되는 색**을 잰다 — 정의된 토큰이 아니라 (REAUDIT §18.2 — ECharts 로 옮긴 뒤).
 *
 * LineSeries·Donut·BarSeries 는 이제 ECharts 가 그린다 — 그림을 렌더해서 픽셀을 재는
 * 시험은 안 만든다(계획 §18.2). 대신 **option 객체**를 겨눈다: 각 부품이 실제로 export 하는
 * 순수 함수(`lineSeriesOption`/`donutOption`/`barRowOption`)에 `resolveChartColor` 가
 * 돌려준 색을 그대로 먹여서, "테마가 고른 색이 옵션의 색 자리에 그대로 들어가는가"를
 * jsdom 렌더 없이 잰다. `resolveChartColor` 자신의 계약(Identity 는 Accent 를 안 따른다,
 * 팔레트 문자열 슬롯도 처리한다)은 `chart-color.test.js` 가 이미 지킨다 — 여기서 다시
 * 안 잰다.
 *
 * Sparkline 은 이번 회차에서 안 옮겼다(§15.2 «남기는 셋») — 그 부분만 그대로 DOM 을 잰다.
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

function toDashType(dash) {
  return dash ? dash.split(/\s+/).map(Number) : "solid";
}

describe("LineSeries — option 의 색·선 스타일 (렌더 없이, ECharts 로 옮긴 뒤)", () => {
  it.each(MODES)("%s — 두 시리즈가 chart[0]·chart[1] 로 들어간다", (mode) => {
    const theme = createClovirTheme(mode);
    const rows = [0, 1].map((idx) => ({
      color: resolveChartColor(theme, undefined, idx), dashType: toDashType(CHART_DASH[idx]),
      points: [5, 3, 0],
    }));
    const opt = lineSeriesOption({ rows, peak: 5, drawn: true });
    expect(opt.series.map((s) => s.lineStyle.color)).toEqual([CHART_SERIES[mode][0], CHART_SERIES[mode][1]]);
  });

  it("색만으로는 시리즈를 못 나르므로 2번 선은 실제로 파선 패턴이다", () => {
    const theme = createClovirTheme("light");
    const rows = [0, 1].map((idx) => ({
      color: resolveChartColor(theme, undefined, idx), dashType: toDashType(CHART_DASH[idx]),
      points: [5, 3, 0],
    }));
    const opt = lineSeriesOption({ rows, peak: 5, drawn: true });
    expect(opt.series[0].lineStyle.type).toBe("solid");
    expect(opt.series[1].lineStyle.type).toEqual(CHART_DASH[1].split(" ").map(Number));
  });

  it("사용자 Accent 를 바꿔도 시리즈 색은 그대로다 (Identity 는 Interaction 을 따르지 않는다)", () => {
    const a = resolveChartColor(createClovirTheme("light"), undefined, 0);
    const b = resolveChartColor(createClovirTheme("light", OTHER_ACCENT), undefined, 0);
    expect(b).toBe(a);
    expect(b).not.toBe(OTHER_ACCENT);
  });

  it("실제로 쓰이는 시리즈 색이 세 면에서 비텍스트 3:1 을 넘는다", () => {
    const theme = createClovirTheme("light");
    const faces = [theme.palette.background.plate, theme.palette.background.inset, theme.palette.background.canvas];
    for (const idx of [0, 1]) {
      const color = resolveChartColor(theme, undefined, idx);
      for (const face of faces) {
        expect(contrast(color, face), `${color} on ${face}`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it("시리즈가 5개를 넘으면 옵션에 6개(기타 포함)만 들어간다", () => {
    const theme = createClovirTheme("light");
    const rows = Array.from({ length: 6 }, (_, idx) => ({
      color: resolveChartColor(theme, undefined, idx), dashType: toDashType(CHART_DASH[idx]),
      points: [idx + 1, idx],
    }));
    const opt = lineSeriesOption({ rows, peak: 6, drawn: true });
    expect(opt.series.length).toBe(6);
  });
});

describe("Donut — option 의 조각 색", () => {
  it.each(MODES)("%s — 조각마다 다른 색이 itemStyle 에 들어간다", (mode) => {
    const theme = createClovirTheme(mode);
    const arcs = [0, 1, 2].map((idx) => ({ key: `s${idx}`, value: idx + 1, color: resolveChartColor(theme, undefined, idx) }));
    const opt = donutOption({ arcs, missing: 0, thickness: 5, size: "9rem", trackColor: "#track", drawn: true });
    const colors = opt.series[0].data.map((d) => d.itemStyle.color);
    expect(colors).toEqual([CHART_SERIES[mode][0], CHART_SERIES[mode][1], CHART_SERIES[mode][2]]);
    expect(new Set(colors).size).toBe(3);
  });

  it("모수와 조각 합의 차이(missing)는 트랙 색 조각으로 따로 들어간다", () => {
    const theme = createClovirTheme("light");
    const arcs = [{ key: "완료", value: 3, color: resolveChartColor(theme, undefined, 0) }];
    const opt = donutOption({ arcs, missing: 5, thickness: 5, size: "9rem", trackColor: "#track", drawn: true });
    expect(opt.series[0].data).toHaveLength(2);
    expect(opt.series[0].data[1]).toEqual({ name: "분류 없음", value: 5, itemStyle: { color: "#track" } });
  });

  it("drawn=false 면 모든 조각의 값이 0이다(useRevealOnce 지문 규약)", () => {
    const arcs = [{ key: "완료", value: 3, color: "#333" }];
    const opt = donutOption({ arcs, missing: 0, thickness: 5, size: "9rem", trackColor: "#track", drawn: false });
    expect(opt.series[0].data[0].value).toBe(0);
  });
});

describe("BarSeries — 막대 한 행의 option", () => {
  it.each(MODES)("%s — 기본색이 chart[0] 이다", (mode) => {
    const theme = createClovirTheme(mode);
    const fill = resolveChartColor(theme, undefined, 0);
    const opt = barRowOption({ pct: 50, fillColor: fill, trackColor: "#track", grown: true });
    expect(opt.series[0].data[0].itemStyle.color).toBe(CHART_SERIES[mode][0]);
  });

  it("grown=false 면 값이 0이다(useRevealOnce 지문 규약)", () => {
    const opt = barRowOption({ pct: 80, fillColor: "#333", trackColor: "#track", grown: false });
    expect(opt.series[0].data[0].value).toBe(0);
  });
});

describe("Sparkline 의 기본색도 chart[0] 이다 (이번 회차에서 안 옮겼다 — §15.2)", () => {
  it.each(MODES)("%s", (mode) => {
    const spark = withTheme(<Sparkline points={[1, 4, 2, 5]} />, mode);
    const line = spark.container.querySelector("path[stroke]");
    expect(line.getAttribute("stroke")).toBe(CHART_SERIES[mode][0]);
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
