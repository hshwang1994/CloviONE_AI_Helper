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

  it("평균의 1.5배를 넘는 사람만 색으로 짚는다", () => {
    const out = wdBalanceItems(devs);   // 평균 4 → 6은 1.5배 이하(=6)라 표시 안 함
    expect(out.items[0].color).toBe("primary");
    const skewed = wdBalanceItems([
      { name: "몰린이", est_all: 10, est_done: 0, assigned: 8 },
      { name: "가벼운이", est_all: 1, est_done: 0, assigned: 1 },
    ]);
    expect(skewed.items[0].color).toBe("warn");   // 평균 5.5 → 10 > 8.25
    expect(skewed.items[1].color).toBe("primary");
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
