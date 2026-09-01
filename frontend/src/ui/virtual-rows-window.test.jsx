import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

/* 표의 스크롤 창이 어디인가 — 두 모드의 계약.
 *
 * 이 앱의 셸은 문서를 굴린다(`AppShell` 은 `main` 에 overflow 를 안 준다). 그래서 목록의
 * 기본은 윈도이고, 안쪽 상자는 스스로 높이를 가진 자리만 쓴다. 이 구분이 무너지면 두 가지가
 * 조용히 깨진다: ① 스크롤바가 둘이 되고 ② `lib/listReturn.js` 의 스크롤 복원이 아무것도
 * 못 되돌린다(그 파일은 `window.scrollY` 만 안다). */

import { DataTable } from "./kit.jsx";
import { createClovirTheme } from "./theme.js";

const COLUMNS = [
  { key: "title", label: "제목", type: "title" },
  { key: "state", label: "상태", type: "status" },
];
const ROWS = Array.from({ length: 120 }, (_, i) => ({ title: `행 ${i}`, state: "계획" }));

function renderTable(props) {
  const r = render(
    <ThemeProvider theme={createClovirTheme()}>
      <DataTable columns={COLUMNS} rows={ROWS} rowKey={(x) => x.title} {...props} />
    </ThemeProvider>,
  );
  const container = r.container.querySelector(".MuiTableContainer-root");
  return { ...r, container, table: r.container.querySelector("table") };
}

describe("DataTable 의 가상화 모드", () => {
  it("기본은 윈도다 — 이 상자는 스크롤 창이 안 된다", () => {
    const { container } = renderTable({ virtualize: {} });
    const style = window.getComputedStyle(container);
    expect(style.overflowY).toBe("visible");
    expect(style.overflowX).toBe("visible");
    expect(style.maxHeight).toBe("");
  });

  it("height 를 주면 안쪽 상자다 — 작업 보드 레인처럼 스스로 높이를 가진 자리", () => {
    const { container } = renderTable({ virtualize: { height: "20rem" } });
    const style = window.getComputedStyle(container);
    expect(style.maxHeight).toBe("20rem");
    expect(style.overflowY).toBe("auto");
  });

  it("mode:\"box\" 로도 안쪽 상자를 고를 수 있다 — 되돌릴 길을 남긴다", () => {
    const { container } = renderTable({ virtualize: { mode: "box" } });
    expect(window.getComputedStyle(container).maxHeight).toBe("32rem");
  });

  it("가상화를 안 쓰면 한 픽셀도 안 바뀐다", () => {
    const { container } = renderTable({});
    expect(window.getComputedStyle(container).maxHeight).toBe("");
  });
});

describe("QA 프로브가 읽는 두 숫자는 서로 다른 질문이다", () => {
  it("data-virtual-total 은 지금까지 받은 행 수다", () => {
    const { table } = renderTable({ virtualize: {} });
    expect(table.getAttribute("data-virtual-total")).toBe("120");
  });

  it("data-list-total 은 전체 건수다 — 한 속성에 두 뜻을 싣지 않는다", () => {
    const { table } = renderTable({ virtualize: {}, total: 1148 });
    expect(table.getAttribute("data-list-total")).toBe("1148");
    expect(table.getAttribute("data-virtual-total")).toBe("120");
  });

  it("전체 건수를 모르면 그 속성을 안 낸다", () => {
    const { table } = renderTable({ virtualize: {} });
    expect(table.getAttribute("data-list-total")).toBeNull();
  });
});

describe("고정 열 이름과 가상화가 이제 함께 선다", () => {
  it("둘을 같이 켜도 상자가 스크롤 창이 되지 않는다 — 예전엔 상호배타였다", () => {
    const { container, table } = renderTable({ virtualize: {}, stickyHeader: true });
    expect(window.getComputedStyle(container).overflowY).toBe("visible");
    expect(table.getAttribute("data-virtual-total")).toBe("120");
  });

  it("윈도 모드에서도 행을 실제로 그린다 — 창을 못 읽으면 한 줄도 안 나온다", () => {
    const { container } = renderTable({ virtualize: {} });
    const bodyRows = container.querySelectorAll("tbody tr:not([aria-hidden='true'])");
    expect(bodyRows.length).toBeGreaterThan(0);
    /* 그리고 전부는 아니다 — 그것이 가상화의 목적이다. */
    expect(bodyRows.length).toBeLessThan(ROWS.length);
  });
});