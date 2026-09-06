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
 */

import { COLUMN_TYPES, planColumnCollapse, resolveColumn, tableMinWidth } from "./columnTypes.js";
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
    expect(tableMinWidth(COLS)).toBe("calc(10rem + 16rem + 7.5rem + 8.5rem)");
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
      .toContain("16rem");
  });
});

describe("열 어휘 — 폭·정렬·자릿수는 의미에서 나온다", () => {
  it("개수·비율은 가운데이고 자릿수를 고정한다", () => {
    for (const t of ["count", "number", "percent", "score"]) {
      expect(COLUMN_TYPES[t].align, t).toBe("center");
      expect(COLUMN_TYPES[t].numeric, t).toBe(true);
    }
  });

  it("왼쪽은 제목 하나뿐이다 (2026-09-06 지시)", () => {
    /* 제목은 표당 하나이고(`SINGLETON_TYPES`) 남는 폭을 전부 가져 값이 실제로 칸을
       채운다 — 가운데에 두면 행마다 시작점이 크게 흔들린다. 그래서 이 열만 왼쪽이다. */
    expect(COLUMN_TYPES.title.align).toBe("left");

    // 반례 — 예전에 함께 왼쪽이던 둘은 이제 가운데다. 한쪽만 재면 「전부 왼쪽」도 통과한다.
    for (const t of ["name", "text"]) {
      expect(COLUMN_TYPES[t].align, t).toBe("center");
    }

    // 그리고 어휘 전체에서 왼쪽인 것이 정확히 하나다 — 새 타입이 조용히 왼쪽으로 들어오면
    // 표에 축이 둘 생긴다(머리글은 언제나 가운데다).
    const left = Object.keys(COLUMN_TYPES).filter((t) => COLUMN_TYPES[t].align === "left");
    expect(left).toEqual(["title"]);
  });

  it("보는 열은 가운데에 선다 — 티켓 ID·상태·짧은 닫힌 집합·날짜·행 동작", () => {
    for (const t of ["identifier", "status", "enum", "date", "datetime", "actions"]) {
      expect(COLUMN_TYPES[t].align, t).toBe("center");
    }
    // 식별자형 숫자도 자릿수는 고정한다 — 값이 칸 안에서 흔들리지 않게.
    expect(COLUMN_TYPES.identifier.numeric).toBe(true);
  });

  it("옛 `identifier: true` 플래그는 그대로 산다", () => {
    const got = resolveColumn({ key: "email", label: "이메일", identifier: true });
    expect(got.minWidth).toBe(COLUMN_TYPES.identifier.minWidth);
    expect(got.identifier).toBe(true);
  });

  it("`type` 을 안 준 열도 가운데다 — 타입이 없다고 축이 달라지지 않는다", () => {
    /* 타입을 안 준 열만 왼쪽이면 같은 표 안에서 이유 없이 그 열 하나만 삐져 나온다.
       값이 산문이라 왼쪽이 필요하면 정렬이 아니라 타입을 준다(`type: "text"`). */
    const got = resolveColumn({ key: "x", label: "무엇" });
    expect(got.align).toBe("center");
    expect(got.numeric).toBe(false);
    expect(got.minWidth).toBe("4.5rem");
    expect(got.width).toBeUndefined();
  });

  it("반례 — 호출부가 왼쪽을 적으면 그것이 이긴다", () => {
    // 어휘를 가운데로 모았다고 화면이 자기 사정을 못 적게 되는 것은 아니다.
    expect(resolveColumn({ key: "x", label: "무엇", align: "left" }).align).toBe("left");
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
    expect(cell.getAttribute("class")).toContain("MuiTableCell-alignCenter");
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

  it("머리글 이름은 열의 정렬과 상관없이 **언제나 가운데**다", () => {
    /* 몸통이 왼쪽인 열에서도 머리글은 가운데다(지시 6). 예전에는 호출부가 몸통의 정렬을
       머리글에 그대로 넘겨서, 왼쪽에 붙은 이름 옆에 오른쪽에 붙은 이름이 섰다. */
    draw(<DataTable
      columns={[
        { key: "t", label: "제목", type: "title" },
        { key: "n", label: "건수", type: "count" },
      ]}
      rows={[{ t: "가", n: 1 }]}
      rowKey={() => "r"}
    />);
    expect(screen.getByText("제목").closest("th").getAttribute("class")).toContain("alignCenter");
    expect(screen.getByText("건수").closest("th").getAttribute("class")).toContain("alignCenter");
    // 몸통은 의미대로 갈린다.
    expect(screen.getByText("가").closest("td").getAttribute("class")).toContain("alignLeft");
    expect(screen.getByText("1").closest("td").getAttribute("class")).toContain("alignCenter");
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

  it("수치 열은 「예상 WD」 머리글이 한 줄로 설 바닥 폭을 갖는다", () => {
    expect(COLUMN_TYPES.number.minWidth).toBe("8rem");
  });

  it("상태·닫힌 집합·개수·시각 열도 머리글+정렬이 한 줄로 설 바닥 폭을 갖는다", () => {
    expect(COLUMN_TYPES.status.minWidth).toBe("7.5rem");
    expect(COLUMN_TYPES.enum.minWidth).toBe("6.5rem");
    expect(COLUMN_TYPES.count.minWidth).toBe("6rem");
    expect(COLUMN_TYPES.datetime.minWidth).toBe("11rem");
    expect(COLUMN_TYPES.actions.minWidth).toBe("6.5rem");
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
