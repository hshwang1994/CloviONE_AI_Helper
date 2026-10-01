/* qa-contract-change: 조직도 트리가 작업 공간의 왼쪽 판 몸이 되며(O1 · D-533) 화면이 준 행(`rows`)을 그린다. 예전 셋째 시험은 「접힌 자식이 골라진」 경우를 이름으로만 말하고 실제로는 펼친 채 단언했다 — 이제 접기 · 검색 · 「사용 중만」으로 고른 노드를 **실제로** 숨기고 Tab 정지가 가장 가까운 보이는 조상(없으면 첫 줄)으로 옮겨 가는지 본다.
 *
 * 조직도 트리 — roving tabindex (트리 전체에서 Tab 정지점은 하나뿐).
 *
 * 고른 노드가 접힘 · 검색 · 거르기로 숨으면 예전 트리는 tabIndex=0 인 줄이 하나도 없어 Tab 으로 트리에 들어갈 수 없었다(6절 1).
 * 펼침 칸(▸ · ▾)은 마우스 전용이라 Tab 이 멈추지 않는다 — 키보드는 → · ← 로 편다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { OrgTree } from "./OrgTree.jsx";

const ROWS = [
  { id: "a", depth: 0, kind: "department", name: "부서A", active: true },
  { id: "a1", depth: 1, kind: "department", name: "부서A-1", active: false },
  { id: "b", depth: 0, kind: "department", name: "부서B", active: true },
];

const stops = () => screen.getAllByRole("treeitem").filter((el) => el.getAttribute("tabindex") === "0");

describe("OrgTree — roving tabindex (트리 전체에서 Tab 정지점은 하나뿐)", () => {
  it("선택된 노드가 없으면 첫 루트 노드만 tabIndex=0, 나머지는 -1이다", async () => {
    render(<OrgTree rows={ROWS} selectedId={null} onSelect={() => {}} />);
    const a = await screen.findByRole("treeitem", { name: "부서A" });
    expect(a).toHaveAttribute("tabIndex", "0");
    expect(screen.getByRole("treeitem", { name: "부서A-1" })).toHaveAttribute("tabIndex", "-1");
    expect(screen.getByRole("treeitem", { name: "부서B" })).toHaveAttribute("tabIndex", "-1");
  });

  it("노드가 선택되면 그 노드만 tabIndex=0이다", async () => {
    render(<OrgTree rows={ROWS} selectedId="b" onSelect={() => {}} />);
    expect(await screen.findByRole("treeitem", { name: "부서A" })).toHaveAttribute("tabIndex", "-1");
    expect(screen.getByRole("treeitem", { name: "부서B" })).toHaveAttribute("tabIndex", "0");
    expect(stops()).toHaveLength(1);
  });

  it("고른 자식을 접어 숨기면 Tab 정지가 그 부모로 옮겨 간다 — 정지점이 사라지지 않는다", async () => {
    const user = userEvent.setup();
    render(<OrgTree rows={ROWS} selectedId="a1" onSelect={() => {}} />);
    const a1 = await screen.findByRole("treeitem", { name: "부서A-1" });
    expect(a1).toHaveAttribute("tabIndex", "0");
    screen.getByRole("treeitem", { name: "부서A" }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.queryByRole("treeitem", { name: "부서A-1" })).toBeNull();
    expect(stops().map((el) => el.getAttribute("aria-label"))).toEqual(["부서A"]);
  });

  it("검색이 고른 노드와 그 조상을 모두 걸러 내면 첫 줄이 정지점이다", async () => {
    render(<OrgTree rows={ROWS} selectedId="a1" query="부서B" onSelect={() => {}} />);
    await screen.findByRole("treeitem", { name: "부서B" });
    expect(screen.queryByRole("treeitem", { name: "부서A" })).toBeNull();
    expect(stops().map((el) => el.getAttribute("aria-label"))).toEqual(["부서B"]);
  });

  it("「사용 중만」이 고른 미사용 말단을 숨기면 보이는 조상이 정지점이다", async () => {
    render(<OrgTree rows={ROWS} selectedId="a1" activeOnly onSelect={() => {}} />);
    await screen.findByRole("treeitem", { name: "부서A" });
    expect(screen.queryByRole("treeitem", { name: "부서A-1" })).toBeNull();
    expect(stops().map((el) => el.getAttribute("aria-label"))).toEqual(["부서A"]);
  });

  it("펼침 칸은 Tab 정지점이 아니다 — 트리 안에 초점을 받는 단추가 없다", async () => {
    const { container } = render(<OrgTree rows={ROWS} selectedId={null} onSelect={() => {}} />);
    await screen.findByRole("treeitem", { name: "부서A" });
    expect(container.querySelectorAll('[role="tree"] button')).toHaveLength(0);
    const focusable = container.querySelectorAll('[role="tree"] [tabindex="0"]');
    expect(focusable).toHaveLength(1);
  });
});
