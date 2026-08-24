import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

/* 표의 열이 «무엇인가»로 폭·정렬·자릿수를 정하는 계약 (C3 · R-91 · W6).
 *
 * 여기서 지키는 것은 셋이다:
 *   1) 개수형 열은 **우정렬 + 자릿수 고정**이다 — `numeric_alignment` 8건의 뿌리.
 *   2) 식별자형 열은 좌정렬이고 `data-col-role="identifier"` 를 **실제로 내보낸다**.
 *      QA 가 그 표식으로 예외를 읽는데 그것을 붙이는 소스가 이 저장소에 없었다.
 *   3) **`resultScope` 없이는 어떤 열도 사라지지 않는다** (R-91). 서버가 페이지를 자르는
 *      목록에서 이번 페이지의 값이 우연히 같다고 열을 빼면, 페이지를 넘길 때마다 열이
 *      생겼다 사라진다.
 */

import { COLUMN_TYPES, planColumnCollapse, resolveColumn } from "./columnTypes.js";
import { DataTable } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

function draw(ui) {
  return render(<ThemeModeProvider>{ui}</ThemeModeProvider>);
}

describe("열 어휘 — 폭·정렬·자릿수는 의미에서 나온다", () => {
  it("개수·비율은 우정렬이고 자릿수를 고정한다", () => {
    for (const t of ["count", "number", "percent", "score"]) {
      expect(COLUMN_TYPES[t].align, t).toBe("right");
      expect(COLUMN_TYPES[t].numeric, t).toBe(true);
    }
  });

  it("식별자형 숫자는 **좌정렬**인데 자릿수는 고정한다", () => {
    // 티켓번호·포트·버전은 크기를 비교하지 않는다 — 우정렬이 오히려 틀렸다.
    expect(COLUMN_TYPES.identifier.align).toBe("left");
    expect(COLUMN_TYPES.identifier.numeric).toBe(true);
  });

  it("옛 `identifier: true` 플래그는 그대로 산다", () => {
    const got = resolveColumn({ key: "email", label: "이메일", identifier: true });
    expect(got.minWidth).toBe(COLUMN_TYPES.identifier.minWidth);
    expect(got.identifier).toBe(true);
  });

  it("`type` 을 안 준 열은 예전과 같은 값을 받는다 (회귀 0)", () => {
    const got = resolveColumn({ key: "x", label: "무엇" });
    expect(got.align).toBe("left");
    expect(got.numeric).toBe(false);
    expect(got.minWidth).toBe("4.5rem");
    expect(got.width).toBeUndefined();
  });

  it("호출부가 적은 값이 어휘표를 이긴다", () => {
    const got = resolveColumn({ key: "d", label: "날짜", type: "date", align: "right", minWidth: "20rem" });
    expect(got.align).toBe("right");
    expect(got.minWidth).toBe("20rem");
  });

  it("개수 열의 `td` 자신이 자릿수 고정을 든다", () => {
    // 안쪽 `<span>` 에만 걸면 QA 는 셀의 computed style 을 읽으므로 «없다» 고 본다.
    draw(<DataTable
      columns={[{ key: "n", label: "조회", type: "count" }]}
      rows={[{ n: 12 }, { n: 340 }, { n: 5 }]}
      rowKey={(r) => r.n}
    />);
    const cell = screen.getByText("340").closest("td");
    expect(cell.getAttribute("class")).toContain("MuiTableCell-alignRight");
    // 인라인 style 이 아니라 주입된 규칙으로 붙는다 — 브라우저가 실제로 계산하는 값을 본다
    // (QA 프로브도 `getComputedStyle(td)` 를 읽는다).
    expect(getComputedStyle(cell).fontVariantNumeric).toContain("tabular-nums");
  });

  it("식별자 열은 표식을 **실제로 내보낸다**", () => {
    draw(<DataTable
      columns={[{ key: "tid", label: "티켓", type: "identifier" }]}
      rows={[{ tid: "ABC-1" }]}
      rowKey={(r) => r.tid}
    />);
    expect(screen.getByText("티켓").closest("th").getAttribute("data-col-role")).toBe("identifier");
    expect(screen.getByText("ABC-1").closest("td").getAttribute("data-col-role")).toBe("identifier");
  });

  it("머리글과 본문이 **같은 함수**에서 정렬을 받는다", () => {
    // 한쪽만 설정하는 경로가 실제로 있었고, 그게 `header_cell_alignment_mismatch` 의 뿌리다.
    draw(<DataTable
      columns={[{ key: "n", label: "건수", type: "count" }]}
      rows={[{ n: 1 }]}
      rowKey={() => "r"}
    />);
    const th = screen.getByText("건수").closest("th");
    const td = screen.getByText("1").closest("td");
    expect(th.getAttribute("class")).toContain("alignRight");
    expect(td.getAttribute("class")).toContain("alignRight");
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
