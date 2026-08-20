import { describe, it, expect } from "vitest";
import { burndownSeries, shortDate, wdBalanceItems } from "./sprint-charts.js";

/* 스프린트 두 그림의 해석 규칙.
 *
 * 여기서 지키는 것: **숫자를 지어내지 않는다.** 그릴 게 없으면 null 이고(화면이 '데이터 없음'을
 * 그린다), 선 이름은 데이터가 실제로 말할 수 있는 것만 말한다('이상/실제'가 아니라 '계획/미완료').
 */

describe("burndownSeries", () => {
  const points = [
    { date: "2026-08-03", planned: 5, open: 3 },
    { date: "2026-08-04", planned: 3, open: 2 },
    { date: "2026-08-05", planned: 0, open: 0 },
  ];

  it("서버가 준 두 계열을 그대로 옮긴다", () => {
    const out = burndownSeries({ points });
    expect(out.series.map((s) => s.label)).toEqual(["계획(마감일 기준)", "아직 미완료"]);
    expect(out.series[0].points).toEqual([5, 3, 0]);
    expect(out.series[1].points).toEqual([3, 2, 0]);
    expect(out.labels).toEqual(["8/3", "8/4", "8/5"]);
  });

  it("선 이름이 '이상/실제'가 아니다 — 완료 시각 이력이 없으므로 그렇게 부르면 거짓이다", () => {
    const labels = burndownSeries({ points }).series.map((s) => s.label).join(" ");
    expect(labels).not.toMatch(/이상|실제/);
  });

  it("요약 한 줄이 두 숫자를 글자로도 말한다", () => {
    expect(burndownSeries({ points }).summary).toContain("5인일");
    expect(burndownSeries({ points }).summary).toContain("3인일");
  });

  it("점이 부족하거나 전부 0이면 null — 빈 차트로 '0이다'와 '모른다'를 섞지 않는다", () => {
    expect(burndownSeries(null)).toBeNull();
    expect(burndownSeries({ points: [] })).toBeNull();
    expect(burndownSeries({ points: [{ date: "2026-08-03", planned: 5, open: 5 }] })).toBeNull();
    expect(burndownSeries({ points: [
      { date: "2026-08-03", planned: 0, open: 0 },
      { date: "2026-08-04", planned: 0, open: 0 },
    ] })).toBeNull();
  });
});

describe("wdBalanceItems", () => {
  const devs = [
    { name: "많이맡은이", est_all: 6, est_done: 2, assigned: 5 },
    { name: "보통이", est_all: 2, est_done: 2, assigned: 2 },
    { name: "쉬는이", est_all: 0, est_done: 0, assigned: 0 },
  ];

  it("업무량 많은 순으로 정렬하고 담당 건수를 함께 말한다", () => {
    const out = wdBalanceItems(devs);
    expect(out.items.map((i) => i.label)).toEqual(["많이맡은이", "보통이"]);
    expect(out.items[0].note).toContain("담당 5건");
  });

  it("배정 없는 사람은 막대에서 빼고 숫자로만 말한다 — 0짜리 막대가 편중을 묻는다", () => {
    const out = wdBalanceItems(devs);
    expect(out.items.some((i) => i.label === "쉬는이")).toBe(false);
    expect(out.summary).toContain("배정이 없는 사람 1명");
  });

  /* W5: 기대값이 `"primary"` 에서 **색 없음**으로 바뀌었다. 단언은 그대로 살아 있고
     오히려 강해진다 — 예전에는 «과부하가 아닌 사람은 primary 다» 였는데, `primary` 는
     사용자 Accent 라 청록을 고른 사용자의 화면에서 이 막대가 청록이 됐다. 이제 이 함수는
     **색을 정하지 않고**(그래서 부품이 Brand 고정 시리즈 색을 준다) 과부하만 톤으로 짚는다.
     "사용자 Accent 를 지목하지 않는다" 를 함께 단언해 되돌아가면 여기서 걸리게 한다. */
  it("평균의 1.5배를 넘는 사람만 색으로 짚고, 나머지는 색을 정하지 않는다", () => {
    const out = wdBalanceItems(devs);   // 평균 4 → 6은 1.5배 이하(=6)라 표시 안 함
    expect(out.items[0].color).toBeUndefined();
    const skewed = wdBalanceItems([
      { name: "몰린이", est_all: 10, est_done: 0, assigned: 8 },
      { name: "가벼운이", est_all: 1, est_done: 0, assigned: 1 },
    ]);
    expect(skewed.items[0].color).toBe("warn");   // 평균 5.5 → 10 > 8.25
    expect(skewed.items[1].color).toBeUndefined();
    // 사용자 Accent 는 어떤 항목의 색으로도 다시 등장하지 않는다.
    expect(skewed.items.map((i) => i.color)).not.toContain("primary");
    expect(out.items.map((i) => i.color)).not.toContain("primary");
  });

  /* 번다운 두 선도 같은 이유로 색을 정하지 않는다 — 시리즈 슬롯(색 + 선 스타일)은 부품이
     준다. 예전 값은 `primary`(사용자 Accent)와 `warning`(상태색)이었고, 그 갈색은 바로 옆
     담당자 막대에서 «과부하»를 뜻했다. 한 화면에서 같은 색이 두 가지를 뜻하면 색은
     아무것도 뜻하지 않는다. */
  it("번다운 두 선은 색을 정하지 않는다 — Accent 도 상태색도 시리즈가 아니다", () => {
    const series = burndownSeries({ points: [
      { date: "2026-08-03", planned: 5, open: 3 },
      { date: "2026-08-04", planned: 3, open: 2 },
    ] }).series;
    expect(series.map((s) => s.color)).toEqual([undefined, undefined]);
    expect(series.map((s) => s.color)).not.toContain("primary");
    expect(series.map((s) => s.color)).not.toContain("warning");
  });

  it("아무도 배정이 없으면 null", () => {
    expect(wdBalanceItems([{ name: "혼자", est_all: 0, est_done: 0, assigned: 0 }])).toBeNull();
    expect(wdBalanceItems([])).toBeNull();
    expect(wdBalanceItems(null)).toBeNull();
  });
});

describe("shortDate", () => {
  it("ISO 날짜를 축 눈금용 짧은 형태로", () => {
    expect(shortDate("2026-08-03")).toBe("8/3");
    expect(shortDate("2026-12-25")).toBe("12/25");
  });
  it("모르는 모양은 그대로 둔다(임의로 지어내지 않는다)", () => {
    expect(shortDate("nope")).toBe("nope");
    expect(shortDate(null)).toBe("");
  });
});
