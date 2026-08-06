/* 표의 '상세' 버튼은 **중립색**이다 (K-B1).
 *
 * 이 저장소에서 가장 많이 반복되는 버튼이다 — 관리자 28화면 × 표의 모든 행. 예전에는
 * `MuiButton variant="outlined"` 를 그대로 써서 MUI 기본 색(primary)이 붙었고, 같은 화면의
 * 다른 버튼(kit `default` = `color:"inherit"`)과 혼자만 달랐다. 한 화면에 수십 개가 깔리므로
 * 이 하나가 화면 전체의 색 인상을 정한다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DataTable, Button } from "./kit.jsx";

const ROWS = [{ id: "r1", name: "첫 행" }, { id: "r2", name: "둘째 행" }];
const COLS = [{ key: "name", label: "이름" }];

describe("표의 상세 버튼", () => {
  it("kit 기본 버튼과 같은 색 클래스를 쓴다 — 혼자 파랗지 않다", () => {
    const { container } = render(
      <>
        <DataTable columns={COLS} rows={ROWS} rowKey={(r) => r.id} onRow={() => {}} />
        <Button>기준 버튼</Button>
      </>,
    );
    const detail = screen.getAllByRole("button", { name: /상세 보기/ })[0];
    const reference = screen.getByRole("button", { name: "기준 버튼" });

    // MUI 는 색을 클래스로 낸다(`MuiButton-outlinedInherit` vs `MuiButton-outlinedPrimary`).
    const colorClass = (el) =>
      [...el.classList].find((c) => /^MuiButton-(outlined|contained|text)[A-Z]/.test(c));
    expect(colorClass(detail)).toBe(colorClass(reference));
    expect(colorClass(detail)).not.toMatch(/Primary$/);
    expect(container).toBeTruthy();
  });

  it("행마다 그 행이 무엇인지 읽어 주는 이름을 갖는다", () => {
    render(<DataTable columns={COLS} rows={ROWS} rowKey={(r) => r.id} onRow={() => {}} />);
    expect(screen.getByRole("button", { name: "상세 보기: 첫 행" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "상세 보기: 둘째 행" })).toBeTruthy();
  });
});
