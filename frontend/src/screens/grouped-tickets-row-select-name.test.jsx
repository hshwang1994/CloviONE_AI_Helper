/* GroupedTickets(내 티켓·미할당 화면의 표)의 선택 체크박스 접근 이름.
 *
 * `ui/row-select-name.test.jsx` 가 DataTable에 대해 이미 못박은 계약과 **같은 계약**이다:
 * 체크박스의 접근 이름에는 그 행을 구별하는 값(제목)이 들어가야 스크린리더로 "선택 삭제"
 * 흐름을 쓸 수 있다. DataTable은 렌더러에 `ctx = { rowName }` 를 두 번째 인자로 넘겨 이를
 * 만족한다(kit.jsx::cellValue) — 그런데 GroupedTickets(MyTickets.jsx)의 `groupedCell(c, t)`
 * 는 `c.render(t)` 처럼 인자를 하나만 넘긴다. `selectionColumn` 의 render는 `(row, ctx) => …`
 * 로 ctx를 받아 `selectLabel(ctx && ctx.rowName)` 을 쓰므로, ctx가 항상 undefined면 모든 행이
 * 다시 "이 항목 선택" 으로 낭독된다 — DataTable에서 고쳤던 바로 그 문제가 내 티켓·미할당
 * 화면(GroupedTickets 사용처)에서는 그대로 남아 있었는지 확인한다. */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { GroupedTickets, ticketColumns } from "./MyTickets.jsx";
import { selectionColumn, useRowSelection } from "../ui/bulkSelect.jsx";

const ROWS = [
  { id: "t-1", tid: 4101, title: "로그인 실패 조사", project: "인프라" },
  { id: "t-2", tid: 4102, title: "배포 스크립트 정리", project: "인프라" },
];

function Harness() {
  const selection = useRowSelection();
  const columns = [selectionColumn(selection, ROWS.map((r) => r.id)), ...ticketColumns({})];
  return <GroupedTickets rows={ROWS} columns={columns} />;
}

describe("GroupedTickets 행 체크박스 이름", () => {
  it("열 정의의 rowName(제목)이 체크박스 접근 이름에 들어간다", () => {
    render(<Harness />);
    expect(screen.getByRole("checkbox", { name: "로그인 실패 조사 선택" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "배포 스크립트 정리 선택" })).toBeInTheDocument();
  });

  it("같은 이름('이 항목 선택')이 행마다 반복되지 않는다", () => {
    render(<Harness />);
    expect(screen.queryAllByRole("checkbox", { name: "이 항목 선택" })).toHaveLength(0);
  });
});
