import { describe, it, expect } from "vitest";
import {
  burndownSeries, scopeTrendSeries, shortDate, weekdayKo, datedLabel, healthBand, healthCuts,
  normalizeMeeting, pickOpenSprint, loadBand, wdBalanceItems,
} from "./sprint-charts.js";

/* 스프린트 그림들의 해석 규칙.
 *
 * 여기서 지키는 것: **숫자를 지어내지 않는다.** 그릴 게 없으면 null 이고(화면이 '데이터 없음'을
 * 그린다), 오늘 이후의 「남은 일」은 `null` 로 두어 선이 거기서 끊긴다 — 내일 얼마가 남을지는
 * 아무도 모르고, 그 자리를 채우면 그것은 그림이 아니라 창작이다.
 */

describe("burndownSeries", () => {
  // 서버(`app/work/meeting.py::_burndown`)가 주는 모양. 마지막 날은 아직 안 왔다.
  const points = [
    { date: "2026-08-03", ideal: 6, remaining: 6, scope: 6 },
    { date: "2026-08-04", ideal: 3, remaining: 4, scope: 6 },
    { date: "2026-08-05", ideal: 0, remaining: null, scope: 6 },
  ];

  it("이상선과 남은 일 선을 그대로 옮긴다", () => {
    const out = burndownSeries({ points });
    expect(out.series.map((s) => s.label)).toEqual(["이상", "남은 일"]);
    expect(out.series[0].points).toEqual([6, 3, 0]);
    expect(out.series[1].points).toEqual([6, 4, null]);
    expect(out.labels).toEqual(["8/3", "8/4", "8/5"]);
  });

  it("🔴 오늘 이후의 남은 일은 null 이다 — 미래를 그리지 않는다", () => {
    const out = burndownSeries({ points });
    expect(out.series[1].points[2]).toBeNull();
  });

  it("범위가 안 바뀌면 범위선을 그리지 않는다 — 이상선과 겹치는 장식이다", () => {
    expect(burndownSeries({ points }).series).toHaveLength(2);
  });

  it("범위가 불어나면 범위선이 붙고 요약이 그 사실을 말한다", () => {
    const grew = [
      { date: "2026-08-03", ideal: 6, remaining: 6, scope: 6 },
      { date: "2026-08-04", ideal: 3, remaining: 4, scope: 9 },
    ];
    const out = burndownSeries({ points: grew });
    expect(out.series.map((s) => s.label)).toContain("범위");
    expect(out.summary).toContain("범위가");
  });

  it("요약이 계획과의 차이를 글자로 말한다", () => {
    // 8/4 에 이상은 3, 남은 일은 4 — 1인일 뒤처져 있다.
    expect(burndownSeries({ points }).summary).toContain("1인일");
  });

  it("점이 부족하거나 전부 0이면 null — 빈 차트로 '0이다'와 '모른다'를 섞지 않는다", () => {
    expect(burndownSeries(null)).toBeNull();
    expect(burndownSeries({ points: [] })).toBeNull();
    expect(burndownSeries({ points: [{ date: "2026-08-03", ideal: 5, remaining: 5, scope: 5 }] })).toBeNull();
    expect(burndownSeries({ points: [
      { date: "2026-08-03", ideal: 0, remaining: 0, scope: 0 },
      { date: "2026-08-04", ideal: 0, remaining: 0, scope: 0 },
    ] })).toBeNull();
  });
});

describe("scopeTrendSeries", () => {
  const trend = [
    { date: "2026-08-03", added: 0, removed: 0 },
    { date: "2026-08-04", added: 2, removed: 0 },
    { date: "2026-08-05", added: 3, removed: 1 },
  ];

  it("일자별 누적 두 선을 낸다", () => {
    const out = scopeTrendSeries({ trend });
    expect(out.series.map((s) => s.label)).toEqual(["들어옴", "빠짐"]);
    expect(out.series[0].points).toEqual([0, 2, 3]);
    expect(out.series[1].points).toEqual([0, 0, 1]);
  });

  it("드나든 것이 없으면 null — 바닥에 붙은 선 둘은 그림이 아니다", () => {
    expect(scopeTrendSeries(null)).toBeNull();
    expect(scopeTrendSeries({ trend: [] })).toBeNull();
    expect(scopeTrendSeries({ trend: [
      { date: "2026-08-03", added: 0, removed: 0 },
      { date: "2026-08-04", added: 0, removed: 0 },
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
  it("번다운 선들은 색을 정하지 않는다 — Accent 도 상태색도 시리즈가 아니다", () => {
    const series = burndownSeries({ points: [
      { date: "2026-08-03", ideal: 5, remaining: 5, scope: 5 },
      { date: "2026-08-04", ideal: 3, remaining: 2, scope: 5 },
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

describe("weekdayKo · datedLabel", () => {
  it("달력일 기준으로 요일을 붙인다 — 월요일 주가 아니다", () => {
    expect(weekdayKo("2026-08-24")).toBe("월");
    expect(weekdayKo("2026-08-27")).toBe("목");
    expect(datedLabel("2026-08-24")).toBe("8/24 월");
  });
});

describe("healthBand · healthCuts", () => {
  it("점수를 양호·주의·위험으로만 나눈다 — 식을 다시 계산하지 않는다", () => {
    expect(healthBand(75).label).toBe("양호");
    expect(healthBand(62.5).label).toBe("주의");
    expect(healthBand(40).kind).toBe("danger");
    expect(healthBand(null)).toBeNull();
  });
  it("깎인 이유를 지연·차단 건수로 말한다", () => {
    expect(healthCuts({ overdue: 1, blocked: 1 })).toBe("지연 1건, 차단 1건이 깎습니다.");
    expect(healthCuts({ overdue: 0, blocked: 0 })).toContain("깎인 점수가 없습니다");
  });
});

describe("pickOpenSprint", () => {
  it("오늘에 걸린 회차(active)를 상태 폴백보다 앞세운다", () => {
    const rows = [
      { id: "old", state: "active" },
      { id: "now", state: "active", active: true },
    ];
    expect(pickOpenSprint(rows).id).toBe("now");
    expect(pickOpenSprint([{ id: "a", state: "closed" }, { id: "b", state: "active" }]).id).toBe("b");
  });

  it("🔴 열린 회차가 없으면 고르지 않는다 — 첫 줄 폴백 없음 (qa-contract-change)", () => {
    // 목록은 starts_on 내림차순이라 첫 줄은 「가장 미래의 회차」다 — 그 폴백이 보드·회의를
    // 진입하자마자 안 연(또는 닫힌) 회차의 빈 판으로 데려갔다.
    expect(pickOpenSprint([{ id: "p", state: "planned" }, { id: "c", state: "closed" }])).toBeNull();
    expect(pickOpenSprint([])).toBeNull();
    expect(pickOpenSprint(null)).toBeNull();
  });
});

describe("loadBand", () => {
  it("중앙값의 1.5배를 높음으로 본다", () => {
    expect(loadBand(9, 4).kind).toBe("danger");
    expect(loadBand(1, 4).kind).toBe("ok");
    expect(loadBand(4, 4).label).toBe("보통");
  });
});

describe("normalizeMeeting", () => {
  it("부분 응답의 빈 갈래를 채운다 — 화면의 무방어 접근이 안 죽는다", () => {
    const out = normalizeMeeting({ sprint: { id: "s" }, today: "2026-08-27" });
    expect(out.discuss).toEqual({});
    expect(out.neighbours).toEqual({ prev: null, next: null });
    expect(out.summary.total).toBe(0);
    expect(out.summary.remaining_wd).toBe(0);
    expect(out.scope).toEqual({ tracked: false, added: 0, removed: 0, trend: [] });
    expect(out.candidates).toEqual([]);
    expect(out.decisions).toEqual([]);
    expect(out.health).toBeNull();
    expect(out.burndown).toEqual({ points: [] });
  });

  it("회차가 없으면 그릴 것이 없다 — null", () => {
    expect(normalizeMeeting(null)).toBeNull();
    expect(normalizeMeeting({ today: "2026-08-27" })).toBeNull();
    expect(normalizeMeeting({ sprint: { id: "s" } })).toBeNull();
  });

  it("온전한 응답은 값이 그대로 지나간다", () => {
    const raw = {
      sprint: { id: "s" }, today: "2026-08-27", phase: "during",
      summary: { total: 4, done: 1 }, health: { score: 62.5 },
      neighbours: { prev: { id: "p" }, next: null },
      discuss: { overdue: { items: [], total: 0, truncated: false } },
      scope: { tracked: true, added: 2, removed: 1, trend: [] },
      candidates: [{ id: "c" }], decisions: [{ id: "d" }],
    };
    const out = normalizeMeeting(raw);
    expect(out.summary.total).toBe(4);
    expect(out.summary.in_progress).toBe(0);
    expect(out.health.score).toBe(62.5);
    expect(out.scope.added).toBe(2);
    expect(out.neighbours.prev.id).toBe("p");
  });
});
