import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { DataTable } from "./kit.jsx";
import { selectionColumn, useRowSelection } from "./bulkSelect.jsx";

/* 좁은 화면에서 표는 **카드 목록**이 된다. 그때 열 `label` 은 필드 이름이 되는데,
 * 선택 열의 `label` 은 이름이 아니라 「전체 선택」 체크박스다.
 *
 * 실측이 잡은 상태(W5, `/my-tickets`·`/unassigned`·`/team-docs-trash` 390px):
 *   · 카드 20개짜리 목록에 **전체 선택 체크박스가 20개** 생긴다. 그중 아무거나 누르면
 *     그 카드가 아니라 목록 전체가 선택된다 — 어느 카드에서 눌렀는지는 아무 뜻이 없다.
 *   · 그 체크박스는 캡션 줄상자 안에 있고 행 체크박스는 값 칸에 있어 중심선이 3.5px
 *     어긋난다(`control_baseline_mismatch`). 어긋남은 증상이고 원인은 위 한 줄이다.
 *
 * 계약은 둘이다. **이름 자리에는 낱말**(`cardLabel`)이 오고, **목록 전체의 조작기는
 * 목록 위에 한 번**(`cardHeader`) 온다 — 표에서 머리행이 하나이듯이.
 */

const ROWS = [
  { id: "t-1", title: "로그인 실패 조사" },
  { id: "t-2", title: "배포 스크립트 정리" },
  { id: "t-3", title: "야간 배치 지연" },
];
const COLS = [{ key: "title", label: "제목", rowName: true }];

function Harness() {
  const selection = useRowSelection();
  const columns = [selectionColumn(selection, ROWS.map((r) => r.id)), ...COLS];
  return <DataTable columns={columns} rows={ROWS} rowKey={(r) => r.id} />;
}

// 카드 뷰로 접히는 폭을 흉내낸다. `useMediaQuery` 가 보는 것은 matchMedia 하나다.
function setNarrow(narrow) {
  window.matchMedia = vi.fn().mockImplementation((q) => ({
    matches: narrow,
    media: q,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }));
}

const originalMatchMedia = window.matchMedia;
afterEach(() => { window.matchMedia = originalMatchMedia; });

describe("카드 뷰의 선택 열 — 전체 선택은 목록당 하나다", () => {
  beforeEach(() => setNarrow(true));

  it("🔴 「전체 선택」이 카드 수만큼 복제되지 않는다 — 목록 전체에 하나뿐이다", () => {
    render(<Harness />);
    // 카드는 셋인데 전체 선택은 하나여야 한다.
    expect(screen.getAllByRole("checkbox", { name: /선택$/ }).length).toBeGreaterThanOrEqual(4);
    expect(screen.getAllByRole("checkbox", { name: "전체 선택" })).toHaveLength(1);
  });

  it("🔴 카드의 이름 자리는 조작기가 아니라 낱말이다", () => {
    render(<Harness />);
    // 각 카드에는 그 행을 고르는 체크박스가 하나씩, 그리고 이름 자리에 「선택」이라는 글자.
    expect(screen.getAllByText("선택")).toHaveLength(ROWS.length);
    for (const row of ROWS) {
      expect(screen.getByRole("checkbox", { name: `${row.title} 선택` })).toBeInTheDocument();
    }
  });

  it("전체 선택을 누르면 보이는 행 전부가 선택된다(카드에서도 뜻이 그대로다)", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("checkbox", { name: "전체 선택" }));
    for (const row of ROWS) {
      expect(screen.getByRole("checkbox", { name: `${row.title} 선택` })).toBeChecked();
    }
  });
});

describe("넓은 화면의 표는 그대로다 — 머리행이 전체 선택을 든다", () => {
  beforeEach(() => setNarrow(false));

  it("표 머리행에 전체 선택이 하나 있고, 이름 자리를 따로 만들지 않는다", () => {
    render(<Harness />);
    const head = screen.getAllByRole("rowgroup")[0];
    expect(within(head).getByRole("checkbox", { name: "전체 선택" })).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox", { name: "전체 선택" })).toHaveLength(1);
    // 카드 전용 이름(`cardLabel`)은 표에서는 안 그려진다.
    expect(screen.queryByText("선택")).toBeNull();
  });
});
