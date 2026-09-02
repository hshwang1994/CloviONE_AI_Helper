import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ProjectWbs } from "./ProjectWbs.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* WBS 트리의 접기/펼치기.
 *
 * 계약 셋:
 *   1. **기본은 전부 펼침** — 처음 연 사람이 트리의 전체 모양을 먼저 본다(접힌 채로
 *      시작하면 「작업이 세 개뿐인 프로젝트」처럼 보인다).
 *   2. 접으면 하위가 DOM 에서 사라지고, 접힌 가지가 **몇 건을 숨겼는지** 말한다.
 *   3. 실제 button + aria-expanded 다 — 키보드·스크린리더가 같은 길을 쓴다.
 *      리프에는 토글이 없다(누를 수 없는 꺾쇠는 거짓말이다).
 */

function node(overrides) {
  return {
    key: overrides.key,
    title: overrides.title,
    depth: overrides.depth,
    children: overrides.children || [],
  };
}

const TREE = [
  node({
    key: "root", title: "루트 작업", depth: 0,
    children: [
      node({
        key: "child", title: "자식 작업", depth: 1,
        children: [node({ key: "grand", title: "손자 작업", depth: 2 })],
      }),
      node({ key: "solo", title: "홀로 작업", depth: 1 }),
    ],
  }),
];

const DATA = { roots: TREE, unplaced: [], progress: { percent: null, basis: null } };

function renderTree() {
  return render(
    <ThemeModeProvider>
      <ProjectWbs data={DATA} ticketsLinked />
    </ThemeModeProvider>,
  );
}

describe("WBS 접기/펼치기", () => {
  it("기본은 전부 펼침이다 — 손자까지 바로 보인다", () => {
    renderTree();
    expect(screen.getByText("손자 작업")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "하위 작업 접기: 루트 작업" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("접으면 하위가 사라지고 숨긴 건수를 말하며, 다시 펴면 돌아온다", async () => {
    renderTree();
    const toggle = screen.getByRole("button", { name: "하위 작업 접기: 루트 작업" });
    await userEvent.click(toggle);

    await waitFor(() => expect(screen.queryByText("자식 작업")).toBeNull());
    expect(screen.queryByText("손자 작업")).toBeNull();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // 루트 아래 자식 2 + 손자 1 = 3건이 숨었다.
    expect(screen.getByText("하위 3건")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "하위 작업 펼치기: 루트 작업" }));
    await waitFor(() => expect(screen.getByText("손자 작업")).toBeInTheDocument());
  });

  it("가지 하나를 접어도 형제 가지는 그대로다", async () => {
    renderTree();
    await userEvent.click(screen.getByRole("button", { name: "하위 작업 접기: 자식 작업" }));
    await waitFor(() => expect(screen.queryByText("손자 작업")).toBeNull());
    expect(screen.getByText("홀로 작업")).toBeInTheDocument();
    expect(screen.getByText("자식 작업")).toBeInTheDocument();
  });

  it("리프에는 토글이 없다 — 누를 수 없는 꺾쇠는 거짓말이다", () => {
    renderTree();
    expect(screen.queryByRole("button", { name: /하위 작업 (접기|펼치기): 홀로 작업/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /하위 작업 (접기|펼치기): 손자 작업/ })).toBeNull();
  });
});
