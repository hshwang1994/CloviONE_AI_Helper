/* 조직도 트리의 화살표 키 이동 (whole-product 재감사, 2026-08-15).
 *
 * `role="tree"`를 선언했으면 WAI-ARIA treeview 패턴상 위/아래/Home/End로 "보이는"
 * treeitem 사이를 옮길 수 있어야 한다 — 예전엔 좌/우(펴기/접기)와 Enter/Space(선택)만
 * 있고 위/아래가 없어서, 키보드 사용자는 화살표 대신 Tab으로 모든 노드를 하나씩(접기
 * 버튼까지 포함해 둘씩) 거쳐야 했다.
 */

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
}));

import { OrgTree } from "./OrgTree.jsx";

// depth 순 깊이 우선 평탄 목록(nestRows의 입력 계약) — 부서A 아래 부서A-1, 그 뒤 형제 부서B.
const ROWS = [
  { id: "a", depth: 0, kind: "department", name: "부서A" },
  { id: "a1", depth: 1, kind: "department", name: "부서A-1" },
  { id: "b", depth: 0, kind: "department", name: "부서B" },
];

function renderTree() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockResolvedValue({ items: ROWS });
  return render(
    <QueryClientProvider client={qc}>
      <OrgTree selectedId={null} onSelect={() => {}} />
    </QueryClientProvider>,
  );
}

describe("OrgTree — 화살표 키로 보이는 노드 사이를 이동한다", () => {
  it("ArrowDown/ArrowUp이 문서 순서(부모 다음 자식, 그다음 형제)로 포커스를 옮긴다", async () => {
    const user = userEvent.setup();
    renderTree();
    const a = await screen.findByRole("treeitem", { name: "부서A" });
    const a1 = screen.getByRole("treeitem", { name: "부서A-1" });
    const b = screen.getByRole("treeitem", { name: "부서B" });

    a.focus();
    expect(document.activeElement).toBe(a);

    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(a1);

    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(b);

    // 마지막 노드에서 더 내려가도 벗어나지 않는다(범위 밖 인덱스는 조용히 무시).
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(b);

    await user.keyboard("{ArrowUp}");
    expect(document.activeElement).toBe(a1);
  });

  it("Home/End가 각각 첫/마지막 보이는 노드로 곧장 이동한다", async () => {
    const user = userEvent.setup();
    renderTree();
    const a = await screen.findByRole("treeitem", { name: "부서A" });
    const a1 = screen.getByRole("treeitem", { name: "부서A-1" });
    const b = screen.getByRole("treeitem", { name: "부서B" });

    a1.focus();
    await user.keyboard("{End}");
    expect(document.activeElement).toBe(b);

    await user.keyboard("{Home}");
    expect(document.activeElement).toBe(a);
  });

  it("ArrowRight/ArrowLeft(펴기/접기)는 그대로 동작한다(회귀 방지)", async () => {
    const user = userEvent.setup();
    renderTree();
    const a = await screen.findByRole("treeitem", { name: "부서A" });
    expect(screen.getByRole("treeitem", { name: "부서A-1" })).toBeInTheDocument();

    a.focus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.queryByRole("treeitem", { name: "부서A-1" })).not.toBeInTheDocument();

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("treeitem", { name: "부서A-1" })).toBeInTheDocument();
  });
});
