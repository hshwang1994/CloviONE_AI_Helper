/* 조직도 트리의 검색 · 펼침 · 접기 (O1 · D-533, 6절 1 · 3).
 *
 * 못박는 것:
 *   ① 처음에는 조직(깊이 0)만 펴져 있다 — 전부 펼친 채 시작하지 않는다.
 *   ② 검색은 접힌 부모를 강제로 펴서 맞은 노드를 보이고, 맞은 글자를 굵게 한다. 검색을 지우면 검색 전 펼침으로 돌아간다.
 *   ③ 「모두 접기 · 펼치기」 신호가 트리 전체에 닿는다.
 *   ④ 줄의 수는 이름이 아니라 설명이다(「구성원 N명」). 미사용 · 상위 관계 오류는 점 + 낱말이고 배지가 아니다.
 *   ⑤ 맞는 것이 없으면 조건 0건 상태와 「필터 지우기」가 선다.
 */
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { OrgTree } from "../OrgTree.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const ROWS = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, active: true, subtree_user_count: 9 },
  { id: "dep-sales", kind: "department", name: "영업팀", depth: 1, active: true, subtree_user_count: 6 },
  { id: "dep-kr", kind: "department", name: "국내영업", depth: 2, active: false, subtree_user_count: 2 },
  { id: "dep-dev", kind: "department", name: "개발팀", depth: 1, active: true, subtree_user_count: 3, cycle: true },
];

function renderTree(props = {}) {
  const all = { rows: ROWS, selectedId: null, onSelect: () => {}, ...props };
  const view = render(<ThemeModeProvider><OrgTree {...all} /></ThemeModeProvider>);
  const rerender = (next) => view.rerender(<ThemeModeProvider><OrgTree {...all} {...next} /></ThemeModeProvider>);
  return { ...view, rerender };
}
const item = (name) => screen.queryByRole("treeitem", { name });

describe("처음 펼침", () => {
  it("조직만 펴져 있고 부서 가지는 접혀 있다", async () => {
    renderTree();
    expect(await screen.findByRole("treeitem", { name: "클로비원" })).toHaveAttribute("aria-expanded", "true");
    expect(item("영업팀")).toHaveAttribute("aria-expanded", "false");
    expect(item("국내영업")).toBeNull();
  });

  it("고른 노드가 접힌 가지 안이면 그 조상이 펴진다", async () => {
    renderTree({ selectedId: "dep-kr" });
    expect(await screen.findByRole("treeitem", { name: "국내영업" })).toHaveAttribute("aria-selected", "true");
    expect(item("영업팀")).toHaveAttribute("aria-expanded", "true");
  });
});

describe("검색", () => {
  it("접힌 부모를 강제로 펴서 맞은 노드를 보이고, 맞은 글자를 굵게 한다", async () => {
    renderTree({ query: "국내" });
    const kr = await screen.findByRole("treeitem", { name: "국내영업" });
    expect(item("영업팀")).toHaveAttribute("aria-expanded", "true");
    expect(within(kr).getByText("국내").tagName).toBe("MARK");
    // 맞지 않는 가지는 사라진다.
    expect(item("개발팀")).toBeNull();
  });

  it("검색을 지우면 검색 전 펼침으로 돌아간다", async () => {
    const { rerender } = renderTree({ query: "국내" });
    await screen.findByRole("treeitem", { name: "국내영업" });
    rerender({ query: "" });
    expect(item("국내영업")).toBeNull();
    expect(item("영업팀")).toHaveAttribute("aria-expanded", "false");
    expect(item("개발팀")).toBeInTheDocument();
  });

  it("맞는 것이 없으면 조건 0건 상태이고 「필터 지우기」가 조건을 푼다", async () => {
    const onClearSearch = vi.fn();
    renderTree({ query: "없는부서", onClearSearch });
    expect(await screen.findByText("조건에 맞는 조직이나 부서가 없습니다.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "필터 지우기" }));
    expect(onClearSearch).toHaveBeenCalled();
  });
});

describe("모두 접기 · 펼치기", () => {
  it("신호가 오면 트리 전체를 접거나 편다", async () => {
    const { rerender } = renderTree();
    await screen.findByRole("treeitem", { name: "클로비원" });
    rerender({ collapseSignal: { kind: "expand", at: 1 } });
    expect(item("국내영업")).toBeInTheDocument();
    rerender({ collapseSignal: { kind: "collapse", at: 2 } });
    expect(item("영업팀")).toBeNull();
    expect(item("클로비원")).toHaveAttribute("aria-expanded", "false");
  });
});

describe("줄의 모양", () => {
  it("수는 설명으로 붙는다 — 이름은 노드 이름 그대로다", async () => {
    renderTree();
    const org = await screen.findByRole("treeitem", { name: "클로비원" });
    expect(org).toHaveAccessibleName("클로비원");
    expect(org).toHaveAccessibleDescription("구성원 9명");
  });

  it("상위 관계 오류는 점 + 낱말이고 설명에 함께 실린다 — 줄 안에 배지가 없다", async () => {
    const { container } = renderTree();
    const dev = await screen.findByRole("treeitem", { name: "개발팀" });
    expect(dev).toHaveAccessibleDescription("구성원 3명 상위 관계 오류");
    expect(container.querySelector('[role="tree"] .k-badge')).toBeNull();
  });

  it("계층은 aria-level · aria-setsize · aria-posinset 이 말한다", async () => {
    renderTree({ collapseSignal: { kind: "expand", at: 1 } });
    const kr = await screen.findByRole("treeitem", { name: "국내영업" });
    expect(kr).toHaveAttribute("aria-level", "3");
    expect(item("영업팀")).toHaveAttribute("aria-level", "2");
    expect(item("영업팀")).toHaveAttribute("aria-setsize", "2");
    expect(item("개발팀")).toHaveAttribute("aria-posinset", "2");
  });

  it("줄을 누르면 고르고, 펼침 칸을 누르면 고르지 않고 편다", async () => {
    const onSelect = vi.fn();
    renderTree({ onSelect });
    const sales = await screen.findByRole("treeitem", { name: "영업팀" });
    await userEvent.click(sales.querySelector('[aria-hidden="true"]'));
    expect(onSelect).not.toHaveBeenCalled();
    expect(sales).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(within(sales).getByText("영업팀"));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "dep-sales" }));
  });
});
