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
import { dateHistogramOption, zoomedIn } from "./DateHistogram.jsx";

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

/* 🔴 날짜 눈금 — 2026-09-01 이전에는 이 그림 밖 HTML `flex` 줄이 그렸고, 그 줄이 두 가지로
 * 틀렸다: 90 칸을 등분해 「6/14」를 「6/1」로 **잘랐고**, 그림이 실제로 보여 주는 구간
 * (dataZoom 이 연 창)과 무관하게 언제나 90 일 전체를 말했다. 축을 그림에 넘기면 둘 다
 * 구조적으로 없어진다 — 축은 지금 보이는 카테고리를 알고, 자리가 모자라면 뺀다. */
describe("dateHistogramOption — 날짜 눈금", () => {
  const opt = () => dateHistogramOption({
    days: days([1, 0, 2, 0, 3]), fillColor: "#f", trackColor: "#t", drawn: true,
    axisColor: "#666", axisLineColor: "#ddd", fontSize: 12,
  });

  it("x축을 그린다 — 눈금이 그림 안에 있어야 확대·이동을 따라간다", () => {
    const x = opt().xAxis;
    expect(x.show).toBe(true);
    expect(x.axisLabel.show).toBe(true);
  });

  it("자리가 모자라면 **자르지 않고 뺀다** — 잘린 「6/1」은 6월 1일이라는 거짓말이다", () => {
    expect(opt().xAxis.axisLabel.hideOverlap).toBe(true);
  });

  it("눈금 글자는 'M/D' 다 — 축에 연도를 반복해 적지 않는다", () => {
    expect(opt().xAxis.axisLabel.formatter("2026-06-14")).toBe("6/14");
  });

  it("눈금 글꼴은 호출부가 넘긴 px 다 — SVG 는 rem 을 안 받으므로 4K 레버를 여기서 푼다", () => {
    expect(opt().xAxis.axisLabel.fontSize).toBe(12);
  });

  it("눈금이 판 안쪽에 자리를 얻는다(containLabel) — 끄면 상자 밖으로 나가 잘린다", () => {
    expect(opt().grid.containLabel).toBe(true);
  });

  it("가장 높은 막대 위에 여백이 있다 — 0 이면 최댓값 막대가 판 위에 붙어 잘린 것처럼 보인다", () => {
    expect(opt().grid.top).toBeGreaterThanOrEqual(8);
  });
});

/* r23 #39 — 그림은 자료가 있는 구간을 먼저 열고 문장은 창 전체(최근 90일)를 말한다. 막대는 칸이 넓어도 40px 까지다. */
describe("창 · 구간 · 막대 폭", () => {
  it("처음 여는 구간이 창보다 좁을 때만 zoomedIn 이 참이다", () => {
    expect(zoomedIn(days([5, 3, ...Array(87).fill(0)]))).toBe(true);
    expect(zoomedIn(days(Array(90).fill(1)))).toBe(false);
    expect(zoomedIn([])).toBe(false);
  });

  it("자료가 하루에 몰려도 막대는 40px 까지만 선다", () => {
    const opt = dateHistogramOption({ days: days([0, 0, 8, 0]), fillColor: "#f", trackColor: "#t", drawn: true });
    expect(opt.series[0].barMaxWidth).toBe(40);
  });
});
