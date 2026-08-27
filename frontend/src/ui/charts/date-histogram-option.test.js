import { describe, expect, it } from "vitest";

/* DateHistogram — ECharts 옵션 (§15.2 · §18.2).
 *
 * 그림을 렌더해서 픽셀을 재는 시험은 안 만든다 — `dateHistogramOption` 은 순수 함수라
 * jsdom 의 실제 SVG 렌더 없이 값만 잰다.
 *
 * REAUDIT C10 — 서버는 항상 고정 폭(90일)을 낸다. 자료가 그 창의 한 구석에만 몰려 있으면
 * dataZoom 의 초기 창이 그 구간을 앞뒤 며칠 여유로 감싸 연다 — "막대 두 개 + 텅 빈 축"으로
 * 처음부터 열리지 않는다.
 */
import { dateHistogramOption } from "./DateHistogram.jsx";

function days(counts) {
  return counts.map((count, i) => ({ date: `2026-08-${String(i + 1).padStart(2, "0")}`, count }));
}

describe("dateHistogramOption", () => {
  it("🔴 자료가 창 앞쪽에 몰려 있으면 초기 dataZoom 이 그 구간(±3일)만 연다", () => {
    // 90일 중 앞 이틀에만 자료가 있고 나머지는 0건 — 처음 그림이 "막대 2개 + 빈 축"이던 자리.
    const counts = [5, 3, ...Array(87).fill(0)];
    const opt = dateHistogramOption({ days: days(counts), fillColor: "#f", trackColor: "#t", drawn: true });
    const zoom = opt.dataZoom[0];
    expect(zoom.startValue).toBe(0);
    expect(zoom.endValue).toBe(4); // populated index 1 + PAD(3)
  });

  it("자료가 창 전체에 고르게 퍼져 있으면 처음과 끝을 그대로 연다 — 오늘과 같은 그림이다", () => {
    const counts = Array(90).fill(1);
    const opt = dateHistogramOption({ days: days(counts), fillColor: "#f", trackColor: "#t", drawn: true });
    const zoom = opt.dataZoom[0];
    expect(zoom.startValue).toBe(0);
    expect(zoom.endValue).toBe(89);
  });

  it("여유(±3일)가 배열 경계를 넘지 않는다", () => {
    // 맨 끝 날에만 자료가 있다 — endValue + PAD 가 배열 길이를 넘으면 안 된다.
    const counts = [...Array(9).fill(0), 4];
    const opt = dateHistogramOption({ days: days(counts), fillColor: "#f", trackColor: "#t", drawn: true });
    const zoom = opt.dataZoom[0];
    expect(zoom.startValue).toBe(6); // populated index 9 - PAD(3)
    expect(zoom.endValue).toBe(9); // 배열 길이(10)를 넘지 않는다
  });

  it("0건인 날뿐이면(빈 프로젝트) 전체를 그대로 연다", () => {
    const opt = dateHistogramOption({ days: days(Array(10).fill(0)), fillColor: "#f", trackColor: "#t", drawn: true });
    const zoom = opt.dataZoom[0];
    expect(zoom.startValue).toBe(0);
    expect(zoom.endValue).toBe(9);
  });

  it("휠·드래그로 창 밖도 계속 볼 수 있다 — type은 'inside'다(페이지가 아니라 그림 안에서 탐색)", () => {
    const opt = dateHistogramOption({ days: days([1, 0, 0]), fillColor: "#f", trackColor: "#t", drawn: true });
    expect(opt.dataZoom[0].type).toBe("inside");
    expect(opt.dataZoom[0].zoomOnMouseWheel).toBe(true);
  });
});
