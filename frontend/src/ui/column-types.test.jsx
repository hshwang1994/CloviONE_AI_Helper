import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

/* 표의 열이 «무엇인가»로 폭·정렬·자릿수를 정하는 계약 (C3 · R-91 · W6).
 *
 * 여기서 지키는 것은 셋이다:
 *   1) 개수형 열은 **가운데 + 자릿수 고정**이다. 우정렬에서 가운데로 옮겼고(지시 6·13)
 *      자릿수 고정은 그대로다 — 그것이 남은 세로 비교 수단이다.
 *   2) 식별자형 열도 가운데이고 `data-col-role="identifier"` 를 **실제로 내보낸다**.
 *      QA 가 그 표식으로 예외를 읽는데 그것을 붙이는 소스가 이 저장소에 없었다.
 *   3) **`resultScope` 없이는 어떤 열도 사라지지 않는다** (R-91). 서버가 페이지를 자르는
 *      목록에서 이번 페이지의 값이 우연히 같다고 열을 빼면, 페이지를 넘길 때마다 열이
 *      생겼다 사라진다.
 *
 * qa-contract-change: 핸드오프 D-3 · ACCEPTANCE E2 가 「머리글은 언제나 가운데」를 「제목 열만 왼쪽, 나머지 가운데 — 머리와 행이 같다」로 뒤집었다.
 * 제목 열 머리글 단언이 alignCenter 에서 alignLeft 로 옮겼고, 머리와 몸이 열마다 같은 축인지 단언을 더했다.
 * qa-contract-change: 열 폭 배분(D-529)이 「제목 열이 남는 폭을 다 먹고 나머지는 바닥 rem 이 곧 폭」을 「바닥 · 비중 · 상한과 머리글 ·
 * 값 길이로 나눈다」로 바꿨다. 타입 바닥 값(제목 16→14 · 식별자 12.5→11 · 상태 7.5→6 · 수치 8→7)의 단언을 옮기고, 머리글이 한 줄로
 * 서는지는 바닥 숫자 대신 머리글 필요 폭 계산으로 단언한다. 좁은 칸 숨김은 `planNarrowColumns` 대신 `planColumns` 로 단언한다.
 */

import { COLUMN_TYPES, assignLeftoverWidth, columnLayoutWidth, planColumnCollapse, resolveColumn, tableMinWidth, ALIGN_BY_TYPE } from "./columnTypes.js";
import { columnSpec, headerNeedRem, planColumns } from "./columnPlan.js";
import { DataTable, tableLayoutSx } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

function draw(ui) {
  return render(<ThemeModeProvider>{ui}</ThemeModeProvider>);
}

/* ── 표가 줄어들 수 있는 바닥 (2026-09-01) ────────────────────────────────────
 *
 * `table-layout: fixed` 는 열의 `min-width` 를 안 본다. 그래서 나머지 열의 고정 폭 합이
 * 칸보다 크면 남는 폭을 먹기로 한 `title` 이 **0** 을 받고, 제목 칸은 `maxWidth: 0` +
 * `overflow: hidden` 이라 글자가 통째로 사라진다. 머리글은 `overflow: visible` 이라
 * 옆 이름 위에 겹쳐 그려진다 — 「제목이 안 보이고 열 이름이 겹치는」 그 화면이다.
 *
 * 실측(팀 티켓 · light): 1280·1366·1536·1600 네 폭 모두에서 제목 열이 0px 였다. 창을
 * 줄여서가 아니라 그 표의 나머지 열이 이미 1272px 을 차지하기 때문이고, 그래서 1920
 * 화면에서 배율을 125% 로 올리기만 해도 같은 일이 났다.
 */
describe("표는 바닥 아래로 줄지 않는다 — 대신 가로로 민다", () => {
  const COLS = [
    { key: "tid", label: "티켓", type: "identifier", width: "10rem", minWidth: "10rem" },
    { key: "title", label: "제목", type: "title" },
    { key: "status", label: "상태", type: "status", width: "7.5rem" },
    { key: "due", label: "마감", type: "date", width: "8.5rem" },
  ];

  it("🔴 바닥은 제목 열의 바닥까지 **포함한** 합이다", () => {
    // 제목을 빼고 더하면 제목이 0 이 되는 그 폭이 바닥이 된다 — 고치기 전과 같아진다.
    expect(tableMinWidth(COLS)).toBe("calc(10rem + 14rem + 7.5rem + 8.5rem)");
  });

  it("바닥은 `type` 이 정한 폭에서 나온다 — 화면이 숫자를 다시 적지 않는다", () => {
    expect(tableMinWidth([{ key: "n", type: "count" }])).toBe(COLUMN_TYPES.count.minWidth);
    expect(tableMinWidth([{ key: "d", type: "datetime" }])).toBe(COLUMN_TYPES.datetime.minWidth);
  });

  it("폭을 아무도 안 적은 열도 바닥에 자기 몫을 낸다", () => {
    expect(tableMinWidth([{ key: "a" }, { key: "b" }])).toBe("calc(4.5rem + 4.5rem)");
  });

  it("퍼센트 폭은 바닥에 안 들어간다 — 표 폭에서 파생하는 값이라 순환이다", () => {
    expect(tableMinWidth([{ key: "a", width: "50%" }, { key: "b", type: "count" }]))
      .toBe(COLUMN_TYPES.count.minWidth);
  });

  it("열이 없으면 바닥도 없다", () => {
    expect(tableMinWidth([])).toBeUndefined();
    expect(tableMinWidth(null)).toBeUndefined();
  });

  it("🔴 표의 sx 가 그 바닥을 실제로 든다 — 값만 만들고 안 붙이면 아무 것도 안 고쳐진다", () => {
    const sx = tableLayoutSx(COLS);
    expect(sx.tableLayout).toBe("fixed");
    expect(sx.width).toBe("100%");
    expect(sx.minWidth).toBe(tableMinWidth(COLS));
  });

  it("🔴 그려진 표에 그 바닥이 붙어 있다", () => {
    const rows = [{ tid: "AAA-1", title: "화면에서 읽히는 제목", status: "진행", due: "2026-09-01" }];
    const { container } = draw(<DataTable columns={COLS} rows={rows} rowKey={(r) => r.tid} />);
    const table = container.querySelector("table");
    expect(table).toBeTruthy();
    expect(table.style.minWidth || getComputedStyle(table).minWidth)
      .toContain("14rem");
  });
});

/* ── 남는 폭의 주인 (D-501) ──────────────────────────────────────────────────
 *
 * 제목 열이 없는 표에서는 브라우저가 남는 폭을 **모든 열에 비례로** 나눴다. 기능 플래그의 「설명」은
 * 스무 글자 남짓에서 잘렸는데 「현재」 · 「기본값」 같은 짧은 값 열은 두 배로 늘어 빈칸만 넓었다. 설정의
 * 「항목명」은 거꾸로 제목 열이라 1,000px 을 먹고 옆 「설명」이 잘렸다. 남는 폭은 읽는 열의 것이다.
 */
describe("남는 폭은 읽는 열이 갖는다 (D-501)", () => {
  const colWidths = (container) => [...container.querySelectorAll("colgroup col")].map((c) => c.style.width);

  it("`grow` 열은 폭을 받지 않고 남는 폭을 먹는다 — 바닥은 자기 minWidth 다", () => {
    const prose = { key: "d", label: "설명", type: "text", grow: true };
    expect(columnLayoutWidth(prose)).toBeUndefined();
    // 폭을 안 받아도 표 바닥에는 자기 몫(12rem)을 낸다 — 안 내면 좁은 칸에서 설명이 0 이 된다.
    expect(tableMinWidth([{ key: "n", type: "count" }, prose])).toBe("calc(6rem + 12rem)");
  });

  it("제목 열은 폭을 안 적으면 남는 폭을 먹고, 적으면 그 폭을 지킨다", () => {
    expect(columnLayoutWidth({ key: "t", label: "제목", type: "title" })).toBeUndefined();
    expect(columnLayoutWidth({ key: "t", label: "항목명", type: "title", width: "14rem" })).toBe("14rem");
  });

  it("남는 폭을 먹는 열이 없으면 **마지막 산문 열**이 먹는다", () => {
    const cols = [
      { key: "name", label: "플래그", type: "identifier" },
      { key: "why", label: "사유", type: "text" },
      { key: "value", label: "현재", type: "enum" },
      { key: "desc", label: "설명", type: "text" },
    ];
    const got = assignLeftoverWidth(cols);
    expect(got.map((c) => !!c.grow)).toEqual([false, false, false, true]);
    // 원본 열 정의는 건드리지 않는다 — registry 의 선언이 다음 렌더에 오염되지 않는다.
    expect(cols[3].grow).toBeUndefined();
  });

  it("반례 — 제목 열이 폭을 먹으면 산문 열은 자라지 않는다(같은 배열을 그대로 돌려준다)", () => {
    const cols = [{ key: "t", label: "제목", type: "title" }, { key: "d", label: "설명", type: "text" }];
    expect(assignLeftoverWidth(cols)).toBe(cols);
  });

  it("반례 — 폭을 적은 산문 열과 산문이 아닌 열은 고르지 않는다", () => {
    const pinned = [{ key: "a", label: "상태", type: "status" }, { key: "d", label: "설명", type: "text", width: "20rem" }];
    expect(assignLeftoverWidth(pinned)).toBe(pinned);
    const noProse = [{ key: "a", label: "상태", type: "status" }, { key: "n", label: "건수", type: "count" }];
    expect(assignLeftoverWidth(noProse)).toBe(noProse);
  });

  it("좁은 칸에서 산문 열이 빠지면 그 폭은 남은 산문 열의 것이다", () => {
    const cols = [
      { key: "a", label: "오류", type: "text" },
      { key: "b", label: "메모", type: "text", hideNarrow: true },
    ];
    const plan = planColumns(cols, 250, { rootPx: 16 });
    expect(plan.hidden.map((c) => c.key)).toEqual(["b"]);
    expect(plan.shown.map((c) => c.key)).toEqual(["a"]);
    // 남은 산문 열이 칸 전체를 받는다(바닥 192 + 남는 58).
    expect(plan.widths).toEqual({ a: 250 });
  });

  it("🔴 그려진 표에서 산문 열의 `<col>` 만 폭이 비고 나머지는 자기 바닥 폭을 든다", () => {
    const { container } = draw(<DataTable
      columns={[
        { key: "name", label: "플래그", type: "identifier" },
        { key: "value", label: "현재", type: "enum" },
        { key: "desc", label: "설명", type: "text" },
      ]}
      rows={[{ name: "board_enabled", value: "활성", desc: "자유게시판 모듈입니다." }]}
      rowKey={(r) => r.name}
    />);
    // 첫 그림(칸 폭을 아직 못 잼)은 옛 바닥 배치다 — 식별자 바닥은 11rem(D-529).
    expect(colWidths(container)).toEqual(["11rem", "6.5rem", ""]);
    // 머리 칸도 같은 폭을 말한다 — `<col>` 과 머리 칸이 갈리면 브라우저마다 다른 폭이 선다.
    expect(getComputedStyle(screen.getByText("현재").closest("th")).width).toBe("6.5rem");
    expect(getComputedStyle(screen.getByText("설명").closest("th")).width).not.toBe("12rem");
  });

  it("🔴 폭을 적은 제목 열은 그 폭으로 그려지고 산문 열이 남는 폭을 먹는다(설정 「항목명」)", () => {
    const { container } = draw(<DataTable
      columns={[
        { key: "label", label: "항목명", type: "title", width: "15rem", minWidth: "10rem" },
        { key: "value", label: "현재 값", type: "text" },
        { key: "desc", label: "설명", type: "text" },
      ]}
      rows={[{ label: "대화 보존 기간(일)", value: "90일", desc: "초과 시 백그라운드 작업이 정리합니다." }]}
      rowKey={(r) => r.label}
    />);
    expect(colWidths(container)).toEqual(["15rem", "12rem", ""]);
  });
});

describe("열 어휘 — 폭·정렬·자릿수는 의미에서 나온다", () => {
  it("비교하는 수(개수 · 수치 · 비율 · 점수)는 오른쪽이고 자릿수를 고정한다 (D-506)", () => {
    for (const t of ["count", "number", "percent", "score"]) {
      expect(COLUMN_TYPES[t].align, t).toBe("right");
      expect(COLUMN_TYPES[t].numeric, t).toBe(true);
    }
  });

  it("읽는 글(제목 · 이름 · 긴 토큰 · 설명 · 경로)은 왼쪽이다 (D-506)", () => {
    for (const t of ["title", "name", "identifier", "text", "path"]) {
      expect(COLUMN_TYPES[t].align, t).toBe("left");
    }
  });

  it("보는 값(상태 · 닫힌 집합 · 날짜 · 짧은 코드 · 행 동작 · 선택)은 가운데다", () => {
    for (const t of ["status", "enum", "date", "datetime", "code", "actions", "select"]) {
      expect(COLUMN_TYPES[t].align, t).toBe("center");
    }
    // 짧은 코드(티켓 번호 · 버전)는 자릿수를 고정한다 — 값이 칸 안에서 흔들리지 않게.
    expect(COLUMN_TYPES.code.numeric).toBe(true);
  });

  it("모든 타입이 세 축 중 하나를 갖는다 — 새 타입이 축 없이 들어오지 못한다", () => {
    for (const [t, a] of Object.entries(ALIGN_BY_TYPE)) {
      expect(["left", "center", "right"], t).toContain(a);
    }
  });

  it("옛 `identifier: true` 플래그는 그대로 산다", () => {
    const got = resolveColumn({ key: "email", label: "이메일", identifier: true });
    expect(got.minWidth).toBe(COLUMN_TYPES.identifier.minWidth);
    expect(got.identifier).toBe(true);
    expect(got.align).toBe("left");
  });

  it("`type` 을 안 준 열은 가운데다 — 값이 글이면 타입을 준다", () => {
    const got = resolveColumn({ key: "x", label: "무엇" });
    expect(got.align).toBe("center");
    expect(got.numeric).toBe(false);
    expect(got.minWidth).toBe("4.5rem");
    expect(got.width).toBeUndefined();
  });

  it("🔴 화면이 적은 `align` 은 무시된다 — 정렬은 언제나 타입이 정한다", () => {
    // 화면마다 정렬을 고르면 같은 뜻의 열이 화면마다 다른 축에 선다(D-506).
    expect(resolveColumn({ key: "x", label: "무엇", align: "left" }).align).toBe("center");
    const got = resolveColumn({ key: "d", label: "날짜", type: "date", align: "right", minWidth: "20rem" });
    expect(got.align).toBe("center");
    // 폭은 여전히 호출부가 이긴다.
    expect(got.minWidth).toBe("20rem");
  });

  it("개수 열의 `td` 자신이 오른쪽 정렬과 자릿수 고정을 든다", () => {
    // 안쪽 `<span>` 에만 걸면 QA 는 셀의 computed style 을 읽으므로 «없다» 고 본다.
    draw(<DataTable
      columns={[{ key: "n", label: "조회", type: "count" }]}
      rows={[{ n: 12 }, { n: 340 }, { n: 5 }]}
      rowKey={(r) => r.n}
    />);
    const cell = screen.getByText("340").closest("td");
    expect(cell.getAttribute("class")).toContain("MuiTableCell-alignRight");
    expect(getComputedStyle(cell).fontVariantNumeric).toContain("tabular-nums");
  });

  it("식별자 열은 표식을 **실제로 내보낸다**", () => {
    draw(<DataTable
      columns={[{ key: "tid", label: "티켓", type: "code" }]}
      rows={[{ tid: "ABC-1" }]}
      rowKey={(r) => r.tid}
    />);
    expect(screen.getByText("티켓").closest("th").getAttribute("data-col-role")).toBe("identifier");
    expect(screen.getByText("ABC-1").closest("td").getAttribute("data-col-role")).toBe("identifier");
  });

  it("머리글은 **자기 열의 몸통과 같은 축**이다 — 왼쪽 · 가운데 · 오른쪽 셋 다 (핸드오프 E2 · D-506)", () => {
    draw(<DataTable
      columns={[
        { key: "t", label: "제목", type: "title" },
        { key: "s", label: "상태", type: "status" },
        { key: "n", label: "건수", type: "count" },
      ]}
      rows={[{ t: "가", s: "완료", n: 1 }]}
      rowKey={() => "r"}
    />);
    expect(screen.getByText("제목").closest("th").getAttribute("class")).toContain("alignLeft");
    expect(screen.getByText("상태").closest("th").getAttribute("class")).toContain("alignCenter");
    expect(screen.getByText("건수").closest("th").getAttribute("class")).toContain("alignRight");
    expect(screen.getByText("가").closest("td").getAttribute("class")).toContain("alignLeft");
    expect(screen.getByText("완료").closest("td").getAttribute("class")).toContain("alignCenter");
    expect(screen.getByText("1").closest("td").getAttribute("class")).toContain("alignRight");
    const axis = (el) => (/alignLeft/.test(el.className) ? "l" : /alignRight/.test(el.className) ? "r" : "c");
    const heads = [...document.querySelectorAll("thead th")].map(axis);
    const cells = [...document.querySelectorAll("tbody tr:first-child td")].map(axis);
    expect(heads).toEqual(cells);
    // 오른쪽 열의 머리 덩어리(이름 + 조작기)도 오른쪽 끝에 선다.
    expect(getComputedStyle(screen.getByText("건수").closest("th").firstElementChild).justifyContent).toBe("flex-end");
  });

  it("정렬·필터 조작기는 이름과 한 덩어리로 칸 가운데에 선다", () => {
    /* 예전 `1fr auto 1fr` 격자는 이름의 중심을 지키려다 좁은 열에서 옆 칸과 겹쳤다.
       지금은 이름+화살표+필터가 한 flex 줄이고, 그 줄 전체가 가운데다. */
    draw(<DataTable
      columns={[
        { key: "a", label: "가나", type: "enum" },
        { key: "b", label: "다라", type: "enum", sortable: true, filter: { kind: "enum", field: "b" } },
      ]}
      rows={[{ a: "x", b: "y" }]}
      rowKey={() => "r"}
      sort={{ key: "b", dir: "asc" }}
      onSort={() => {}}
      onFilter={() => {}}
    />);
    const plain = screen.getByText("가나").closest("th").firstElementChild;
    const busy = screen.getByText("다라").closest("th").firstElementChild;
    for (const row of [plain, busy]) {
      expect(getComputedStyle(row).display).toBe("flex");
      expect(getComputedStyle(row).justifyContent).toBe("center");
      expect(getComputedStyle(row).gridTemplateColumns).not.toBe("1fr auto 1fr");
    }
  });

  it("수치 열은 「예상 WD」 머리글이 정렬 표지와 함께 한 줄로 서는 폭을 받는다", () => {
    expect(COLUMN_TYPES.number.minWidth).toBe("7rem");
    const spec = columnSpec({ key: "wd", label: "예상 WD", type: "number" }, { glyphs: 1 });
    expect(spec.min).toBeGreaterThanOrEqual(headerNeedRem("예상 WD", 1));
    expect(spec.min).toBe(7);
  });

  it("상태 · 닫힌 집합 · 개수 · 시각 열은 머리글 + 정렬 · 필터 표지가 한 줄로 서는 폭을 받는다", () => {
    expect(COLUMN_TYPES.status.minWidth).toBe("6rem");
    expect(COLUMN_TYPES.enum.minWidth).toBe("6.5rem");
    expect(COLUMN_TYPES.count.minWidth).toBe("6rem");
    expect(COLUMN_TYPES.datetime.minWidth).toBe("11rem");
    expect(COLUMN_TYPES.actions.minWidth).toBe("6.5rem");
    // 바닥보다 머리글이 길면 머리글 폭이 이긴다 — 「우선순위」 + 정렬 + 필터는 8rem 이다.
    expect(columnSpec({ key: "p", label: "우선순위", type: "status" }, { glyphs: 2 }).min).toBe(8);
    expect(columnSpec({ key: "n", label: "조회", type: "count" }, { glyphs: 1 }).min).toBe(6);
    expect(columnSpec({ key: "at", label: "마지막 로그인 시각", type: "datetime" }, { glyphs: 1 }).min)
      .toBeGreaterThanOrEqual(headerNeedRem("마지막 로그인 시각", 1));
  });
});

describe("열 제거는 질의 계약을 아는 호출부만 시킬 수 있다 (R-91)", () => {
  const cols = [
    { key: "title", label: "제목", type: "title" },
    { key: "status", label: "상태", type: "enum" },
  ];
  const rows = [
    { title: "가", status: "진행" },
    { title: "나", status: "진행" },
    { title: "다", status: "진행" },
  ];

  it("🔴 `resultScope` 가 없으면 아무 열도 안 없앤다", () => {
    const got = planColumnCollapse(cols, rows, undefined);
    expect(got.removed).toEqual([]);
    expect(got.caption).toBe("");
  });

  it("🔴 서버 페이징 + 우연히 같은 값 → 열은 남는다", () => {
    const got = planColumnCollapse(cols, rows, { serverPaged: true, activeFilters: [], fixedColumns: [] });
    expect(got.removed).toEqual([]);
    expect(got.shrink).toEqual(["status"]);   // 빼지 않고 **줄인다**
  });

  it("사용자가 그 축을 직접 걸었으면 뺀다 — 조건을 풀면 돌아온다", () => {
    const got = planColumnCollapse(cols, rows, { serverPaged: true, activeFilters: ["status"] });
    expect(got.removed.map((r) => r.key)).toEqual(["status"]);
    expect(got.caption).toContain("진행");
  });

  it("질의 계약이 그 값을 고정하면 뺀다", () => {
    const got = planColumnCollapse(cols, rows, { serverPaged: true, fixedColumns: ["status"] });
    expect(got.removed.map((r) => r.key)).toEqual(["status"]);
  });

  it("🔴 행을 식별하는 열은 조건이 걸려도 안 뺀다", () => {
    const same = [{ title: "같음", status: "a" }, { title: "같음", status: "b" }];
    const got = planColumnCollapse(cols, same, { fixedColumns: ["title"] });
    expect(got.removed).toEqual([]);
  });

  it("전 행이 비었는데 서버 페이징이면 줄이기만 한다", () => {
    const blank = [{ title: "가", note: "" }, { title: "나", note: null }];
    const c2 = [...cols, { key: "note", label: "메모", type: "text" }];
    const paged = planColumnCollapse(c2, blank, { serverPaged: true });
    expect(paged.removed).toEqual([]);
    expect(paged.shrink).toContain("note");
    // 서버가 전체를 주는 화면에서는 「없다」가 사실이라 뺄 수 있다.
    const whole = planColumnCollapse(c2, blank, { serverPaged: false });
    expect(whole.removed.map((r) => r.key)).toContain("note");
  });

  it("뺀 열은 표가 **한 번 말한다**", () => {
    draw(<DataTable
      columns={cols}
      rows={rows}
      rowKey={(r) => r.title}
      resultScope={{ serverPaged: true, activeFilters: ["status"] }}
    />);
    expect(screen.queryByText("상태")).toBeNull();
    // 조사도 열 이름에서 파생한다 — 「상태은」이 아니라 「상태는」이다.
    expect(screen.getByText(/상태는 이 목록에서 전부 '진행'/)).toBeTruthy();
  });
});
