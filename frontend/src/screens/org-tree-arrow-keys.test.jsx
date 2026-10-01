/* qa-contract-change: 조직도 트리가 작업 공간의 왼쪽 판 몸이 되며(O1 · D-533) 스스로 질의하지 않고 화면이 준 행(`rows`)을 그린다 — 렌더 표본을 질의 가짜에서 `rows` 로 옮겼다. 키 동작 단언은 그대로이고, 글자 입력 이동과 Enter 선택을 더했다.
 *
 * 조직도 트리의 화살표 키 이동 (whole-product 재감사, 2026-08-15).
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
import "@testing-library/jest-dom/vitest";

import { OrgTree } from "./OrgTree.jsx";

// depth 순 깊이 우선 평탄 목록(nestRows의 입력 계약) — 부서A 아래 부서A-1, 그 뒤 형제 부서B.
const ROWS = [
  { id: "a", depth: 0, kind: "department", name: "부서A" },
  { id: "a1", depth: 1, kind: "department", name: "부서A-1" },
  { id: "b", depth: 0, kind: "department", name: "부서B" },
];

function renderTree(onSelect = () => {}) {
  return render(<OrgTree rows={ROWS} selectedId={null} onSelect={onSelect} />);
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

  it("ArrowLeft 는 접고(이미 접혔으면 부모로), ArrowRight 는 펴고(이미 펴졌으면 첫 자식으로) 간다", async () => {
    const user = userEvent.setup();
    renderTree();
    const a = await screen.findByRole("treeitem", { name: "부서A" });
    expect(a).toHaveAttribute("aria-expanded", "true");

    screen.getByRole("treeitem", { name: "부서A-1" }).focus();
    await user.keyboard("{ArrowLeft}");
    // 자식에서 ← 는 부모로 간다(자식은 접을 것이 없다).
    expect(document.activeElement).toBe(a);
    await user.keyboard("{ArrowLeft}");
    expect(screen.queryByRole("treeitem", { name: "부서A-1" })).not.toBeInTheDocument();
    expect(a).toHaveAttribute("aria-expanded", "false");
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("treeitem", { name: "부서A-1" })).toBeInTheDocument();
    expect(document.activeElement).toBe(a);
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(screen.getByRole("treeitem", { name: "부서A-1" }));
  });

  it("Enter 와 Space 는 고른다 — 초점만 옮기는 화살표와 다르다", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderTree(onSelect);
    const b = await screen.findByRole("treeitem", { name: "부서B" });
    b.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ id: "b" }));
    screen.getByRole("treeitem", { name: "부서A" }).focus();
    await user.keyboard(" ");
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ id: "a" }));
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("글자를 치면 그 글자로 시작하는 다음 보이는 노드로 간다", async () => {
    const user = userEvent.setup();
    render(
      <OrgTree
        rows={[
          { id: "x", depth: 0, kind: "department", name: "기획팀" },
          { id: "y", depth: 0, kind: "department", name: "영업팀" },
          { id: "z", depth: 0, kind: "department", name: "개발팀" },
        ]}
        selectedId={null}
        onSelect={() => {}}
      />,
    );
    const first = await screen.findByRole("treeitem", { name: "기획팀" });
    first.focus();
    await user.keyboard("개");
    expect(document.activeElement).toBe(screen.getByRole("treeitem", { name: "개발팀" }));
  });
});
