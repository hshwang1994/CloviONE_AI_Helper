import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";

import { GridHeaderCell } from "./GridHeaderCell.jsx";
import { TableHeaderCell } from "./TableHeaderCell.jsx";
import { createClovirTheme } from "./theme.js";

/* 격자 머리 칸(`ui/GridHeaderCell.jsx`, D-497) — 표가 아닌 격자(끌어 옮기는 백로그)의 머리가 **표 머리와 같은 칸**을 쓴다.
 *
 * 새 조작 모양이 아니다. 그래서 여기서 지키는 것은 「표 머리와 같은가」다:
 *  1) 칸 안쪽(이름 · 정렬 단추 · 표지 · 필터 단추)이 `TableHeaderCell` 과 글자 하나까지 같은 마크업이다.
 *  2) 칸의 역할은 `columnheader` 이고, 정렬할 수 있는 열만 `aria-sort` 를 단다(없음 → 오름 → 내림).
 *  3) 정렬 단추 · 필터 창이 같은 콜백을 같은 인자로 부른다.
 *  4) 가로 정렬은 열 어휘가 정한다 — 제목 열만 왼쪽이다. */

function withTheme(node) {
  return render(<ThemeProvider theme={createClovirTheme()}>{node}</ThemeProvider>);
}

const DUE = { key: "due", label: "마감", type: "date", sortable: true };
const PRIORITY = { key: "priority", label: "우선순위", type: "status", sortable: true, filter: { kind: "enum", field: "priority" } };
const TICKET = { key: "tid", label: "티켓", type: "title", sortable: true };
const ASSIGNEE = { key: "assignee", label: "담당자", type: "name", filter: { kind: "entity", field: "assignee_user_id" } };
const ACTIONS = { key: "_actions", label: "작업", type: "actions" };

describe("격자 머리 칸", () => {
  it("🔴 칸 안쪽은 표 머리 칸과 같은 마크업이다 — 같은 부품(`HeaderCellContent`)을 쓴다", () => {
    const props = {
      column: PRIORITY, sort: { key: "priority", dir: "desc" }, onSort: () => {},
      filterValue: ["높음"], onFilter: () => {}, filterOptions: [{ value: "높음", label: "높음" }],
    };
    const grid = withTheme(<div role="row"><GridHeaderCell {...props} /></div>);
    const gridInner = grid.container.querySelector("[role=columnheader]").innerHTML;
    grid.unmount();
    const table = withTheme(<table><thead><tr><TableHeaderCell {...props} /></tr></thead></table>);
    // MUI 표 칸은 `TableHead` 문맥 밖이면 `td` 로 선다 — 칸 요소가 아니라 그 **안쪽**을 견준다.
    const tableInner = table.container.querySelector("thead tr > *").innerHTML;
    expect(gridInner.length).toBeGreaterThan(0);
    // emotion 클래스 이름까지 같다 — 같은 sx 를 가진 같은 요소들이다.
    expect(gridInner).toBe(tableInner);
  });

  it("🔴 역할은 columnheader 이고, 정렬할 수 있는 열만 방향을 말한다", () => {
    const { rerender } = withTheme(
      <div role="row">
        <GridHeaderCell column={DUE} sort={{ key: "rank", dir: "asc" }} onSort={() => {}} />
        <GridHeaderCell column={ASSIGNEE} sort={{ key: "rank", dir: "asc" }} onSort={() => {}} onFilter={() => {}} filterValue={[]} />
        <GridHeaderCell column={ACTIONS} sort={{ key: "rank", dir: "asc" }} onSort={() => {}} />
      </div>,
    );
    const heads = screen.getAllByRole("columnheader");
    expect(heads.map((h) => h.getAttribute("aria-sort"))).toEqual(["none", null, null]);
    expect(heads.map((h) => h.getAttribute("title"))).toEqual(["마감", "담당자", "작업"]);
    const theme = createClovirTheme();
    rerender(
      <ThemeProvider theme={theme}>
        <div role="row"><GridHeaderCell column={DUE} sort={{ key: "due", dir: "asc" }} onSort={() => {}} /></div>
      </ThemeProvider>,
    );
    expect(screen.getByRole("columnheader")).toHaveAttribute("aria-sort", "ascending");
    rerender(
      <ThemeProvider theme={theme}>
        <div role="row"><GridHeaderCell column={DUE} sort={{ key: "due", dir: "desc" }} onSort={() => {}} /></div>
      </ThemeProvider>,
    );
    expect(screen.getByRole("columnheader")).toHaveAttribute("aria-sort", "descending");
    // 방향 표지는 칸 안 글리프다(뜻은 aria-sort 가 말한다).
    expect(screen.getByRole("columnheader").querySelector("[data-head-glyph=sort]")).not.toBeNull();
  });

  it("정렬 단추는 열 키로, 필터 창은 조건 필드와 값으로 부른다", async () => {
    const onSort = vi.fn();
    const onFilter = vi.fn();
    withTheme(
      <div role="row">
        <GridHeaderCell
          column={PRIORITY} sort={{ key: "rank", dir: "asc" }} onSort={onSort}
          filterValue={[]} onFilter={onFilter}
          filterOptions={[{ value: "높음", label: "높음" }, { value: "낮음", label: "낮음" }]}
        />
      </div>,
    );
    await userEvent.click(screen.getByRole("button", { name: "우선순위" }));
    expect(onSort).toHaveBeenCalledWith("priority");
    const filterButton = screen.getByRole("button", { name: "우선순위 필터" });
    expect(filterButton).toHaveAttribute("aria-pressed", "false");
    expect(filterButton.querySelector("[data-head-glyph=filter]")).not.toBeNull();
    await userEvent.click(filterButton);
    const popover = await screen.findByRole("presentation");
    // 열 필터 창의 「이 조건 지우기」는 빈 목록으로 부른다 — 조건 필드 이름은 열 선언의 `filter.field` 다.
    await userEvent.click(within(popover).getByRole("button", { name: "이 조건 지우기" }));
    expect(onFilter).toHaveBeenCalledWith("priority", []);
  });

  it("걸린 조건이 있으면 필터 단추가 눌린 상태다 — 표 머리와 같은 판정", () => {
    withTheme(
      <div role="row">
        <GridHeaderCell column={ASSIGNEE} filterValue={["u-1"]} onFilter={() => {}} entityOptions={[{ value: "u-1", label: "김하나" }]} />
      </div>,
    );
    expect(screen.getByRole("button", { name: "담당자 필터" })).toHaveAttribute("aria-pressed", "true");
    // 정렬할 수 없는 열이라 정렬 단추가 없고 이름만 선다.
    expect(screen.queryByRole("button", { name: "담당자" })).toBeNull();
    expect(screen.getByRole("columnheader")).not.toHaveAttribute("aria-sort");
  });

  it("🔴 가로 정렬은 열 어휘가 정한다 — 제목 열만 왼쪽이고 나머지는 가운데다", () => {
    withTheme(
      <div role="row">
        <GridHeaderCell column={TICKET} sort={{ key: "rank", dir: "asc" }} onSort={() => {}} />
        <GridHeaderCell column={DUE} sort={{ key: "rank", dir: "asc" }} onSort={() => {}} />
      </div>,
    );
    const [ticket, due] = screen.getAllByRole("columnheader");
    expect(getComputedStyle(ticket).justifyContent).toBe("flex-start");
    expect(getComputedStyle(due).justifyContent).toBe("center");
    // 안쪽 줄도 같은 축이다 — 표 머리의 제목 열과 같은 규칙.
    expect(getComputedStyle(ticket.firstElementChild).justifyContent).toBe("flex-start");
    expect(getComputedStyle(due.firstElementChild).justifyContent).toBe("center");
    // 격자 칸은 트랙보다 넓어지지 않는다.
    expect(getComputedStyle(due).minWidth).toBe("0");
  });
});
