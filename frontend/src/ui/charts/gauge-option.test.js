import { describe, expect, it } from "vitest";

/* Gauge — ECharts 옵션 (§15.2 · §18.2).
 *
 * 그림을 렌더해서 픽셀을 재는 시험은 안 만든다 — `gaugeOption` 은 순수 함수라 jsdom 의
 * 실제 SVG 렌더 없이 값만 잰다.
 */
import { gaugeOption } from "./Gauge.jsx";

describe("gaugeOption", () => {
  it("완전한 원이다(시작 90도, 12시에서 시계 방향)", () => {
    const opt = gaugeOption({ pct: 62.5, thickness: 5, trackColor: "#eee", strokeColor: "#333", drawn: true });
    const series = opt.series[0];
    expect(series.startAngle).toBe(90);
    expect(series.endAngle).toBe(-270);
  });

  it("값은 0~100 스케일이고, drawn=false 이면 0에서 시작한다(useRevealOnce 와 같은 지문 규약)", () => {
    const notDrawn = gaugeOption({ pct: 80, thickness: 5, trackColor: "#eee", strokeColor: "#333", drawn: false });
    expect(notDrawn.series[0].data[0].value).toBe(0);

    const drawn = gaugeOption({ pct: 80, thickness: 5, trackColor: "#eee", strokeColor: "#333", drawn: true });
    expect(drawn.series[0].data[0].value).toBe(80);
    expect(drawn.series[0].min).toBe(0);
    expect(drawn.series[0].max).toBe(100);
  });

  it("트랙과 진행 색이 각각 축 색·진행 색으로 들어간다", () => {
    const opt = gaugeOption({ pct: 50, thickness: 6, trackColor: "#track", strokeColor: "#stroke", drawn: true });
    const series = opt.series[0];
    expect(series.axisLine.lineStyle.color).toEqual([[1, "#track"]]);
    expect(series.progress.itemStyle.color).toBe("#stroke");
    expect(series.axisLine.lineStyle.width).toBe(6);
    expect(series.progress.width).toBe(6);
  });

  it("ECharts 자신의 글자(디테일·눈금·제목)는 전부 끈다 — 글자는 바깥 HTML 이 낸다", () => {
    const opt = gaugeOption({ pct: 50, thickness: 5, trackColor: "#t", strokeColor: "#s", drawn: true });
    const series = opt.series[0];
    expect(series.detail.show).toBe(false);
    expect(series.title.show).toBe(false);
    expect(series.axisLabel.show).toBe(false);
    expect(series.pointer.show).toBe(false);
  });
});
