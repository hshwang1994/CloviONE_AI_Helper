import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/* SEM-02(PA-F-031): BulkActions는 PageHeader의 h1과 같은 줄에 붙었다 사라지는 임시
 * 컨트롤 묶음이라 h2로 구획하기 어색하다 - role="toolbar"+aria-label로 스크린리더가
 * "일괄 작업"으로 식별/건너뛸 수 있게 한다. MyTickets.jsx·TeamDocs.jsx·Trash.jsx 3화면이
 * 공유하는 컴포넌트라 여기 한 번 고치면 셋 다 해결된다.
 */

import { BulkActions } from "./bulkSelect.jsx";

describe("BulkActions 툴바 역할 (SEM-02)", () => {
  it("선택이 있으면 role=toolbar와 라벨을 함께 그린다", () => {
    render(<BulkActions count={3} onClear={() => {}}><button>삭제</button></BulkActions>);
    const toolbar = screen.getByRole("toolbar", { name: "일괄 작업" });
    expect(toolbar).toBeInTheDocument();
    expect(toolbar).toHaveTextContent("3개 선택");
  });

  it("선택이 없으면 여전히 아무것도 그리지 않는다(기존 동작 보존)", () => {
    render(<BulkActions count={0} onClear={() => {}}><button>삭제</button></BulkActions>);
    expect(screen.queryByRole("toolbar")).toBeNull();
  });
});
