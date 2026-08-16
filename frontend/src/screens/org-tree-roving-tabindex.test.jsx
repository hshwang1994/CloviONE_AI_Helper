/* 조직도 트리의 roving tabindex (whole-product 재감사, 2026-08-17).
 *
 * 모든 treeitem이 tabIndex=0이면 Tab이 트리 전체를 한 칸씩(접기 버튼 있는 노드는
 * 둘씩) 통과해야 해서, org-tree-arrow-keys.test.jsx가 고정한 화살표 키 이동이
 * 있으나 마나가 된다 — WAI-ARIA APG treeview 패턴은 트리 전체에서 Tab 정지점이
 * 하나(선택된 노드, 없으면 첫 루트)뿐이길 요구한다.
 */

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
}));

import { OrgTree } from "./OrgTree.jsx";

const ROWS = [
  { id: "a", depth: 0, kind: "department", name: "부서A" },
  { id: "a1", depth: 1, kind: "department", name: "부서A-1" },
  { id: "b", depth: 0, kind: "department", name: "부서B" },
];

function renderTree(selectedId) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockResolvedValue({ items: ROWS });
  return render(
    <QueryClientProvider client={qc}>
      <OrgTree selectedId={selectedId ?? null} onSelect={() => {}} />
    </QueryClientProvider>,
  );
}

describe("OrgTree — roving tabindex (트리 전체에서 Tab 정지점은 하나뿐)", () => {
  it("선택된 노드가 없으면 첫 루트 노드만 tabIndex=0, 나머지는 -1이다", async () => {
    renderTree(null);
    const a = await screen.findByRole("treeitem", { name: "부서A" });
    const a1 = screen.getByRole("treeitem", { name: "부서A-1" });
    const b = screen.getByRole("treeitem", { name: "부서B" });

    expect(a).toHaveAttribute("tabIndex", "0");
    expect(a1).toHaveAttribute("tabIndex", "-1");
    expect(b).toHaveAttribute("tabIndex", "-1");
  });

  it("노드가 선택되면 그 노드만 tabIndex=0이고 첫 루트를 포함한 나머지는 -1이다", async () => {
    renderTree("b");
    const a = await screen.findByRole("treeitem", { name: "부서A" });
    const b = screen.getByRole("treeitem", { name: "부서B" });

    expect(a).toHaveAttribute("tabIndex", "-1");
    expect(b).toHaveAttribute("tabIndex", "0");
  });

  it("접힌 자식 노드가 선택돼도(DOM에 없음) 부모/형제 노드 중 하나만 tabIndex=0이다", async () => {
    // a1은 a의 자식이라 a를 접으면 DOM에서 사라진다 — 이때도 tabIndex=0인 treeitem이
    // 정확히 하나여야 한다(사라진 selectedId를 아무도 못 받아 전부 -1이 되는 실패를 방지).
    renderTree("a1");
    const a = await screen.findByRole("treeitem", { name: "부서A" });
    const a1 = screen.getByRole("treeitem", { name: "부서A-1" });
    const b = screen.getByRole("treeitem", { name: "부서B" });

    expect(a).toHaveAttribute("tabIndex", "-1");
    expect(a1).toHaveAttribute("tabIndex", "0");
    expect(b).toHaveAttribute("tabIndex", "-1");
  });
});
