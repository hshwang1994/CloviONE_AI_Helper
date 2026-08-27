import { describe, expect, it } from "vitest";

/* qa-contract-change: LineSeries 를 ECharts 로 다시 구현하며(§15.2) 손으로 계산하던 x좌표·path.d 파싱을 걷어냈다 — ECharts connectNulls:false 가 그 성질을 대신 지키므로 option 객체로 더 짧게 잰다. */
/* LineSeries 의 null 처리 (REAUDIT §15.2 · §18.2 — ECharts 로 옮긴 뒤).
 *
 * 예전 판은 x좌표를 손으로 계산해서 null 을 걸러낸 배열이 압축되지 않는지를 렌더된
 * SVG path 의 `d` 속성으로 쟀다. 지금은 ECharts 의 `line` 시리즈가 `connectNulls:false`
 * 기본값으로 이 성질을 직접 지킨다 — 원본 배열(길이·인덱스 그대로, null 포함)을
 * `series[].data` 에 넘기기만 하면 된다. 그래서 이제는 **그 배열 자체**를 잰다:
 * 렌더 없이, `lineSeriesOption` 이라는 순수 함수의 반환값만 본다.
 */
import { lineSeriesOption } from "./LineSeries.jsx";

describe("lineSeriesOption — null 값의 위치 보존", () => {
  it("가운데 null이 있어도 그 자리는 null로, 나머지 인덱스는 원래 자리에 그대로 남는다", () => {
    const opt = lineSeriesOption({
      rows: [{ color: "#333", dashType: "solid", points: [10, 20, 30, null, 40, 50] }],
      peak: 50,
      drawn: true,
    });
    expect(opt.series[0].data).toEqual([10, 20, 30, null, 40, 50]);
    // connectNulls 를 명시적으로 false 로 둔다 — 기본값에 기대지 않는다(라이브러리
    // 기본값이 바뀌면 이 성질이 조용히 사라질 수 있다).
    expect(opt.series[0].connectNulls).toBe(false);
  });

  it("null이 없을 때는 그대로 4칸이다", () => {
    const opt = lineSeriesOption({
      rows: [{ color: "#333", dashType: "solid", points: [0, 10, 20, 30] }],
      peak: 30,
      drawn: true,
    });
    expect(opt.series[0].data).toEqual([0, 10, 20, 30]);
  });

  it("drawn=false 면 모든 자리가 null이다(useRevealOnce 지문 규약 — 0부터 자라기 전 상태)", () => {
    const opt = lineSeriesOption({
      rows: [{ color: "#333", dashType: "solid", points: [10, 20, 30] }],
      peak: 30,
      drawn: false,
    });
    expect(opt.series[0].data).toEqual([null, null, null]);
  });

  it("x축 카테고리 수는 가장 긴 시리즈의 슬롯 수와 같다 — null도 슬롯을 차지한다", () => {
    const opt = lineSeriesOption({
      rows: [
        { color: "#111", dashType: "solid", points: [1, null, 3] },
        { color: "#222", dashType: "solid", points: [1, 2, 3, 4, 5] },
      ],
      peak: 5,
      drawn: true,
    });
    expect(opt.xAxis.data).toHaveLength(5);
  });
});
