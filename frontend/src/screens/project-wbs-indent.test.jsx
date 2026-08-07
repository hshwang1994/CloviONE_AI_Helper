import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ProjectWbs } from "./ProjectWbs.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* WBS 트리의 들여쓰기 폭 계약.
 *
 * ProjectWbs.jsx 의 `INDENT_REM = 1.25` 는 "들여쓰기 한 칸 = 1.25rem" 이라는 뜻인데,
 * `pl: steps * INDENT_REM` 처럼 **숫자**로 sx 에 넘기면 MUI 가 그 숫자를
 * theme.spacing() 에 태운다(frontend/src/ui/theme.js: spacing = factor => `${0.5 * factor}rem`).
 * 그러면 깊이 2칸이 2.5rem 이 아니라 1.25rem 으로, 딱 절반만 들여써진다 - 부모/자식
 * 계층이 화면에서 잘 안 갈린다.
 *
 * MyTickets.jsx 의 NT_FIELD_GAP_REM 이 같은 함정을 `${NT_FIELD_GAP_REM}rem` 문자열로
 * 피한 것과 같은 방식으로, 여기서도 문자열을 넘겨 spacing() 배율을 건너뛰어야 한다.
 */

function node(overrides) {
  return {
    key: overrides.key,
    title: overrides.title,
    depth: overrides.depth,
    children: overrides.children || [],
  };
}

// 루트(0) → 자식(1) → 손자(2), 3단 계층.
const TREE = [
  node({
    key: "root",
    title: "루트 작업",
    depth: 0,
    children: [
      node({
        key: "child",
        title: "자식 작업",
        depth: 1,
        children: [node({ key: "grand", title: "손자 작업", depth: 2 })],
      }),
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

// 행 제목의 부모가 곧 pl(들여쓰기)이 실려 있는 flex 행 컨테이너다.
function rowOf(title) {
  return screen.getByText(title).parentElement;
}

describe("WBS 트리의 깊이별 들여쓰기", () => {
  it("깊이 0은 들여쓰지 않는다", () => {
    renderTree();
    expect(getComputedStyle(rowOf("루트 작업")).paddingLeft).toBe("0rem");
  });

  it("깊이 1은 한 칸(1.25rem) 들여쓴다", () => {
    renderTree();
    expect(getComputedStyle(rowOf("자식 작업")).paddingLeft).toBe("1.25rem");
  });

  it("깊이 2는 두 칸(2.5rem) 들여쓴다 — theme.spacing() 배율에 걸려 1.25rem(절반)이 되면 안 된다", () => {
    renderTree();
    expect(getComputedStyle(rowOf("손자 작업")).paddingLeft).toBe("2.5rem");
  });
});
