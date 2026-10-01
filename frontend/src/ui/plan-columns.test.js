import { describe, expect, it } from "vitest";

import {
  VALUE_SAMPLE_ROWS, approxTextEm, columnSpec, columnTier, columnValueText, headerNeedRem, planColumns, stepUp, valuesNeedRem,
} from "./columnPlan.js";
import { COLUMN_TYPES } from "./columnTypes.js";

/* 표 열 폭 배분 (F3 · D-529). 예전에는 폭 없는 제목 열이 남는 폭 전부를 먹고 나머지 열은 바닥 rem 이 곧 폭이었다 — 1920 에서
 * 조직 구성원 이름 열이 500px 넘게 비고 이메일이 잘렸으며, 1366 에서는 열 바닥 합이 판보다 넓어 상태 · 역할 열이 판 밖으로
 * 나갔다. 아래 황금값은 계획 문서의 조직 구성원 표 계산표다(루트 16 · 2560 은 18). 정수 px 로 올리는 큰 나머지 순서 때문에
 * 칸 하나가 1px 다를 수 있어 ±1 로 보고, 합은 칸 폭과 정확히 같아야 한다. */

const ROLE_LABELS = ["일반 사용자", "운영자", "감사자", "관리자", "시스템 관리자"];
const MEMBERS = [
  { name: "UI QA", title: "팀장", email: "ui-qa@goodmit.co.kr", dept: "플랫폼개발팀", status: "활성", role: "시스템 관리자" },
  { name: "김지훈", title: "선임", email: "kim.jihoon@goodmit.co.kr", dept: "플랫폼개발팀", status: "활성", role: "운영자" },
];
const NAME = { key: "name", label: "이름", type: "name" };
const TITLE = { key: "title", label: "직책", type: "enum", tier: "secondary" };
const EMAIL = { key: "email", label: "이메일", type: "identifier" };
const DEPT = { key: "dept", label: "부서", type: "path" };
const STATUS = { key: "status", label: "상태", type: "status" };
const ROLE = { key: "role", label: "역할", type: "enum", values: ROLE_LABELS };
const ORG_COLS = [NAME, TITLE, EMAIL, DEPT, STATUS, ROLE];
const LEAF_COLS = [NAME, TITLE, EMAIL, STATUS, ROLE];

function expectWidths(plan, want, avail) {
  expect(plan.scroll).toBe(false);
  for (const [key, px] of Object.entries(want)) {
    if (px == null) {
      expect(plan.widths[key], `${key} 는 숨겨진다`).toBeUndefined();
      expect(plan.hidden.map((c) => c.key)).toContain(key);
    } else {
      expect(Math.abs(plan.widths[key] - px), `${key}: ${plan.widths[key]} ≈ ${px}`).toBeLessThanOrEqual(1);
    }
  }
  expect(Object.values(plan.widths).reduce((a, b) => a + b, 0)).toBe(avail);
}

describe("조직 구성원 표 — 계획의 계산표", () => {
  it("조직 @1366 = 724: 보조 열 직책만 숨기고 필수 넷이 모두 보인다", () => {
    const plan = planColumns(ORG_COLS, 724, { rows: MEMBERS });
    expectWidths(plan, { name: 154, title: null, email: 185, dept: 169, status: 96, role: 120 }, 724);
    expect(plan.hidden.map((c) => c.key)).toEqual(["title"]);
  });

  it("조직 @1600 = 910 · @1920 = 1230: 늘어나는 세 열이 같은 비중으로 받는다", () => {
    expectWidths(planColumns(ORG_COLS, 910, { rows: MEMBERS }),
      { name: 181, title: 104, email: 213, dept: 197, status: 96, role: 120 }, 910);
    expectWidths(planColumns(ORG_COLS, 1230, { rows: MEMBERS }),
      { name: 287, title: 104, email: 319, dept: 304, status: 96, role: 120 }, 1230);
  });

  it("조직 @2560 = 1783(루트 18): 늘어나는 열이 모두 상한이면 남는 폭을 모든 열이 지금 폭 비율로 나눈다", () => {
    expectWidths(planColumns(ORG_COLS, 1783, { rootPx: 18, rows: MEMBERS }),
      { name: 382, title: 138, email: 467, dept: 509, status: 127, role: 159 }, 1783);
  });

  it("말단 부서 @1366 · @1920: 부서 열은 그리지 않는다", () => {
    expectWidths(planColumns(LEAF_COLS, 724, { rows: MEMBERS }),
      { name: 186, title: 104, email: 218, status: 96, role: 120 }, 724);
    expectWidths(planColumns(LEAF_COLS, 1230, { rows: MEMBERS }),
      { name: 369, title: 133, email: 451, status: 123, role: 154 }, 1230);
  });

  it("역할 폭은 선택지 라벨 전부에서 정한다 — 화면에 없는 「시스템 관리자」도 잘리지 않는다", () => {
    const plan = planColumns(ORG_COLS, 1230, { rows: [MEMBERS[1]] });
    expect(plan.widths.role).toBeGreaterThanOrEqual(120);
  });
});

describe("필수 열은 어떤 폭에서도 숨지 않는다", () => {
  it("필수 바닥 합이 칸보다 크면 더 숨기지 않고 표가 바닥 합 폭으로 서서 가로로 굴러간다", () => {
    const plan = planColumns(ORG_COLS, 500, { rows: MEMBERS });
    expect(plan.scroll).toBe(true);
    expect(plan.hidden.map((c) => c.key)).toEqual(["title"]);
    expect(plan.shown.map((c) => c.key)).toEqual(["name", "email", "dept", "status", "role"]);
    expect(plan.tableWidth).toBe(144 + 176 + 160 + 96 + 120);
    expect(plan.widths).toEqual({ name: 144, email: 176, dept: 160, status: 96, role: 120 });
  });

  it("식별 열과 정렬 중인 열은 등급을 적어도 필수다", () => {
    expect(columnTier({ key: "t", type: "title", tier: "context" })).toBe("essential");
    expect(columnTier({ key: "x", type: "enum", tier: "secondary" }, "x")).toBe("essential");
    expect(columnTier({ key: "x", type: "enum", hideNarrow: true })).toBe("secondary");
    expect(columnTier({ key: "x", type: "enum" })).toBe("essential");
    expect(columnTier({ key: "x", type: "enum", tier: "context" })).toBe("context");
    // 옛 `keep` 은 필수의 별칭이다.
    expect(columnTier({ key: "x", type: "enum", hideNarrow: true, keep: true })).toBe("essential");
  });

  it("정렬 중인 보조 열은 숨기지 않고 다른 보조 열이 대신 빠진다", () => {
    const plan = planColumns(ORG_COLS, 724, { rows: MEMBERS, sortKey: "title" });
    expect(plan.hidden.map((c) => c.key)).not.toContain("title");
  });
});

describe("숨기는 순서 — 문맥 열 → 보조 열, 같은 등급은 priority 낮은 것 · 오른쪽 것부터", () => {
  const cols = [
    { key: "a", label: "이름", type: "name" },
    { key: "s1", label: "보조1", type: "enum", tier: "secondary" },
    { key: "c1", label: "문맥1", type: "enum", tier: "context" },
    { key: "s2", label: "보조2", type: "enum", tier: "secondary" },
    { key: "c2", label: "문맥2", type: "enum", tier: "context", priority: 5 },
  ];

  it("문맥 열부터 숨기고, 문맥 안에서는 priority 낮은 것이 먼저다", () => {
    // 바닥: 9rem(144) + 6.5rem × 4(416) = 560. 100 이 모자라면 c1(priority 0) 하나(104)면 된다.
    const one = planColumns(cols, 460, {});
    expect(one.hidden.map((c) => c.key)).toEqual(["c1"]);
    // 더 모자라면 문맥 둘 다 숨긴 뒤 보조의 오른쪽(s2)부터다. 알림은 표에 적힌 순서다.
    const two = planColumns(cols, 340, {});
    expect(two.hidden.map((c) => c.key)).toEqual(["c1", "s2", "c2"]);
    const all = planColumns(cols, 200, {});
    expect(all.hidden.map((c) => c.key)).toEqual(["s1", "c1", "s2", "c2"]);
    expect(all.shown.map((c) => c.key)).toEqual(["a"]);
  });
});

describe("남는 폭의 분배", () => {
  it("한 열이 남는 폭을 혼자 먹지 않는다 — 늘어나는 열 둘이 비중대로 나누고 상한에서 멈춘다", () => {
    const cols = [
      { key: "t", label: "제목", type: "title" },
      { key: "d", label: "설명", type: "text" },
      { key: "n", label: "건수", type: "count" },
    ];
    const plan = planColumns(cols, 1300, {});
    // 바닥 224 + 192 + 96 = 512, 남는 788 을 3:3 으로 — 제목이 상한(576)에서 멈추면 나머지는 설명이 받는다.
    expect(plan.widths.t).toBe(576);
    expect(plan.widths.d).toBe(1300 - 576 - 96);
    expect(plan.widths.n).toBe(96);
    // 둘 다 상한이면 남는 폭은 세 열이 지금 폭 비율로 나눈다 — 건수 열도 조금 받는다.
    const wide = planColumns(cols, 1600, {});
    expect(wide.widths.t).toBeGreaterThan(576);
    expect(wide.widths.d).toBeGreaterThan(768);
    expect(wide.widths.n).toBeGreaterThan(96);
    expect(wide.widths.t + wide.widths.d + wide.widths.n).toBe(1600);
  });

  it("남는 폭을 비율로 나눌 때 선택 · 동작 칸은 받지 않는다", () => {
    const cols = [
      { key: "sel", label: "", type: "select" },
      { key: "n", label: "이름", type: "name" },
      { key: "c", label: "건수", type: "count" },
      { key: "act", label: "", type: "actions", actionCount: 2 },
    ];
    const plan = planColumns(cols, 2000, {});
    expect(plan.widths.sel).toBe(40);
    // 동작 칸 = 30 × 2 + 8 + 32 = 100 → 0.5rem 단위로 올려 104.
    expect(plan.widths.act).toBe(104);
    expect(plan.widths.n + plan.widths.c).toBe(2000 - 40 - 104);
    expect(plan.widths.n).toBeGreaterThan(288);
  });

  it("칸 폭을 못 쟀으면 배분하지 않는다 — 첫 그림은 옛 배치다", () => {
    const plan = planColumns(ORG_COLS, 0, {});
    expect(plan.widths).toBeNull();
    expect(plan.shown).toHaveLength(ORG_COLS.length);
  });

  it("호출부가 적은 폭은 고정 폭으로 지킨다", () => {
    const plan = planColumns([{ key: "m", label: "달", type: "title", width: "6.5rem" }, { key: "c", label: "건수", type: "count" }], 1000, {});
    expect(plan.widths.m).toBeGreaterThanOrEqual(104);
    expect(plan.widths.m + plan.widths.c).toBe(1000);
  });
});

describe("머리글과 값 길이", () => {
  it("글 폭 어림은 한글 1em · 빈칸 0.25em · 그 밖 0.58em 이다", () => {
    expect(approxTextEm("시스템 관리자")).toBeCloseTo(6.25, 5);
    expect(approxTextEm("ab1")).toBeCloseTo(1.74, 5);
  });

  it("머리글 필요 폭은 이름 + 칸 여백 32 + 정렬 · 필터 표지마다 22 를 0.5rem 단위로 올린 값이다", () => {
    // 「우선순위」 4글자 × 12 = 48 + 32 + 22 × 2 = 124 → 7.75rem → 8rem.
    expect(headerNeedRem("우선순위", 2)).toBe(8);
    expect(headerNeedRem("", 2)).toBe(0);
    expect(stepUp(6.01)).toBe(6.5);
  });

  it("상태 열의 폭은 바닥 · 머리글 · 가장 긴 상태 낱말 가운데 가장 긴 것이다", () => {
    const spec = columnSpec({ key: "s", label: "우선순위", type: "status" }, { glyphs: 2 });
    expect(spec.kind).toBe("fixed");
    expect(spec.min).toBe(8);
    const long = columnSpec({ key: "s", label: "상태", type: "status" }, { rows: [{ s: "수신측이 거부함" }] });
    // 「수신측이 거부함」 한글 7 + 빈칸 1 = 7.25em × 14 = 101.5 + 32 = 133.5 → 8.5rem.
    expect(long.min).toBe(8.5);
    expect(valuesNeedRem(["가"])).toBe(3);
  });

  it("값 길이는 열의 화면 낱말로 잰다 — value(row) · hint(row) · 글 값 순서", () => {
    expect(columnValueText({ key: "r", value: (row) => (row.r === "system_admin" ? "시스템 관리자" : row.r) }, { r: "system_admin" }))
      .toBe("시스템 관리자");
    expect(columnValueText({ key: "r", hint: () => "운영자" }, { r: "operator" })).toBe("운영자");
    expect(columnValueText({ key: "n" }, { n: 3 })).toBe("3");
    expect(columnValueText({ key: "o" }, { o: { a: 1 } })).toBeNull();
  });

  it("id 는 화면 글이 아니다 — 그리는 함수가 있는 열은 서버가 준 화면 낱말(*_label · *_name · *_title)만 잰다", () => {
    const uuid = "62134ac8-831e-4071-bb07-d7c3144d85eb";
    // 부서 열은 부서 id 를 들고 이름을 그린다 — id 길이로 재면 바닥이 20rem 을 넘어 1366 프로젝트 표가 가로로 굴렀다(P5 캡처).
    expect(columnValueText({ key: "dept_id", render: () => "플랫폼개발팀" }, { dept_id: uuid })).toBeNull();
    expect(columnValueText({ key: "id" }, { id: uuid })).toBeNull();
    expect(columnValueText({ key: "kind", render: () => "초대" }, { kind: "invite" })).toBeNull();
    expect(columnValueText({ key: "status_label", render: () => null }, { status_label: "수신측이 거부함" })).toBe("수신측이 거부함");
    expect(columnValueText({ key: "dept_id", render: () => null, value: () => "플랫폼개발팀" }, { dept_id: uuid })).toBe("플랫폼개발팀");
    const rows = [{ dept_id: uuid }];
    expect(columnSpec({ key: "dept_id", label: "부서", min: "7rem", render: () => "플랫폼개발팀" }, { rows }).min).toBe(7);
  });

  it("받은 행은 앞 VALUE_SAMPLE_ROWS 행만 잰다 — 무한 받기 목록이 길어져도 계산이 커지지 않는다", () => {
    const rows = Array.from({ length: VALUE_SAMPLE_ROWS + 10 }, (_, i) => ({ s: i === VALUE_SAMPLE_ROWS + 5 ? "아주 긴 상태 낱말이 끝에 있다" : "짧음" }));
    expect(columnSpec({ key: "s", label: "상태", type: "status" }, { rows }).min).toBe(6);
  });
});

describe("열 타입 표 — 바닥 · 비중 · 상한", () => {
  it("늘어나는 글 다섯은 바닥 · 비중 · 상한을 갖는다", () => {
    const grow = Object.fromEntries(["title", "text", "name", "identifier", "path"].map((k) => [k,
      [COLUMN_TYPES[k].minWidth, COLUMN_TYPES[k].weight, COLUMN_TYPES[k].maxWidth]]));
    expect(grow).toEqual({
      title: ["14rem", 3, "36rem"], text: ["12rem", 3, "48rem"], name: ["9rem", 2, "18rem"],
      identifier: ["11rem", 2, "22rem"], path: ["10rem", 2, "24rem"],
    });
  });

  it("내용 길이 열은 바탕만 갖고, 고정 열은 정해진 폭이다", () => {
    expect(["status", "enum", "code"].map((k) => [COLUMN_TYPES[k].minWidth, !!COLUMN_TYPES[k].content]))
      .toEqual([["6rem", true], ["6.5rem", true], ["6.5rem", true]]);
    expect(["count", "number", "percent", "score", "date", "datetime", "select"].map((k) => COLUMN_TYPES[k].minWidth))
      .toEqual(["6rem", "7rem", "6rem", "6rem", "8.5rem", "11rem", "2.5rem"]);
  });
});
