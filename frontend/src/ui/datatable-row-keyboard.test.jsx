/* PA-RC-0023: 표 행은 키보드만으로 상세에 닿아야 한다.
 *
 * 「상세」 버튼 열은 이제 없다 — 행 클릭과 완전히 같은 일을 해서 잉크만 쓰고 정보를 더하지
 * 않았다(원래는 그 열이 유일한 키보드 진입점이었다, 행 자체엔 tabIndex가 없어 Tab으로
 * 건너뛸 수 없었다). 이 시험이 고정하는 것: 열을 지우기 **전에** 행 자체가 먼저 키보드로
 * 도달 가능해졌다는 사실 — 순서를 반대로 했다면 그 사이(버튼은 없는데 행은 아직 못 받는)
 * 키보드 사용자가 상세에 닿을 방법이 없는 창이 생겼을 것이다.
 *
 * role="button"을 행에 주지 않는 이유: 행 안에 실제 버튼(재시도·취소 등 registry 액션)이
 * 함께 있는 표가 있다 — role=button 위에 포커스 가능한 자손을 두는 것은 WAI-ARIA 금지다
 * (kit.jsx의 StatusTile이 이미 같은 이유로 카드 안에 중첩 버튼을 안 둔다). tabIndex +
 * aria-label + Enter/Space 처리만으로 키보드 도달을 준다.
 */
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataTable } from "./kit.jsx";

const ROWS = [{ id: "r1", name: "첫 행" }, { id: "r2", name: "둘째 행" }];
const COLS = [{ key: "name", label: "이름" }];

describe("표 행의 키보드 도달", () => {
  it("onRow가 있으면 행이 포커스 가능하고 이름표(aria-label)를 갖는다", () => {
    render(<DataTable columns={COLS} rows={ROWS} rowKey={(r) => r.id} onRow={() => {}} />);
    const row = screen.getByRole("row", { name: "상세 보기: 첫 행" });
    expect(row).toHaveAttribute("tabindex", "0");
  });

  it("onRow가 없으면 행이 포커스 대상이 아니다", () => {
    render(<DataTable columns={COLS} rows={ROWS} rowKey={(r) => r.id} />);
    const row = screen.getAllByRole("row")[1]; // [0]은 헤더 행
    expect(row).not.toHaveAttribute("tabindex");
  });

  it("행에 포커스를 두고 Enter를 누르면 onRow(row)를 부른다", async () => {
    const user = userEvent.setup();
    const onRow = vi.fn();
    render(<DataTable columns={COLS} rows={ROWS} rowKey={(r) => r.id} onRow={onRow} />);
    const row = screen.getByRole("row", { name: "상세 보기: 첫 행" });
    row.focus();
    await user.keyboard("{Enter}");
    expect(onRow).toHaveBeenCalledWith(ROWS[0]);
  });

  it("행에 포커스를 두고 Space를 누르면 onRow(row)를 부른다", async () => {
    const user = userEvent.setup();
    const onRow = vi.fn();
    render(<DataTable columns={COLS} rows={ROWS} rowKey={(r) => r.id} onRow={onRow} />);
    const row = screen.getByRole("row", { name: "상세 보기: 둘째 행" });
    row.focus();
    await user.keyboard(" ");
    expect(onRow).toHaveBeenCalledWith(ROWS[1]);
  });

  it("셀 안의 실제 버튼(재시도 같은 registry 행 액션) 위의 Enter는 행 핸들러를 이중 발화하지 않는다", async () => {
    const user = userEvent.setup();
    const onRow = vi.fn();
    const cellAction = vi.fn();
    const colsWithAction = [
      ...COLS,
      { key: "retry", label: "동작", render: (row) => (
        <button onClick={(e) => { e.stopPropagation(); cellAction(row); }}>재시도</button>
      ) },
    ];
    render(<DataTable columns={colsWithAction} rows={ROWS} rowKey={(r) => r.id} onRow={onRow} />);
    const retryButton = screen.getAllByRole("button", { name: "재시도" })[0];
    retryButton.focus();
    await user.keyboard("{Enter}");
    // 버튼 자신의 onClick만 한 번 불려야 한다 — 행의 onKeyDown이 같은 Enter를 또 잡아
    // onRow까지 함께 부르면 안 된다(재시도를 눌렀는데 상세도 같이 열리는 이중 동작).
    expect(cellAction).toHaveBeenCalledTimes(1);
    expect(onRow).not.toHaveBeenCalled();
  });
});
