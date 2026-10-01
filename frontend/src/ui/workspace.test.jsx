import React from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ErrorState } from "./kit.jsx";
import { useScrollRoot } from "./scrollRoot.js";
import { WORKSPACE_TRACKS } from "./density.js";
import {
  PaneHead, Workspace, WorkspacePane, WorkspaceShellContext, WORKSPACE_FILL_QUERY, useWorkspaceShellState,
} from "./Workspace.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 관리 작업 공간 — 채움 모드 (F5 · D-531).
 *
 * 앱 틀은 창 하나가 굴러간다. 채움 모드는 고른 화면이 등록하고 창이 폭 1200 · 높이 600 이상일 때만 켜지고, 그때 판마다 몸만 굴러간다.
 * jsdom 에는 배치가 없다 — 여기서는 등록 · 해제, 모드 표식, 판 몸의 스크롤 상자 선언, 스크롤 창 문맥, 상태 자리를 잰다. 실제 높이 ·
 * 독립 굴림 · 고정 영역은 실브라우저 하네스(`scripts/ui_qa/workspace_e2e.py`)가 잰다. */

let mediaMatches = true;
const realMatchMedia = window.matchMedia;
beforeEach(() => {
  mediaMatches = true;
  window.matchMedia = (query) => ({
    matches: query === WORKSPACE_FILL_QUERY ? mediaMatches : false,
    media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  });
});
afterEach(() => { window.matchMedia = realMatchMedia; });

/* 앱 틀 흉내 — 등록 창구를 깔고 지금 채움인가를 표식으로 내건다. */
function Shell({ children }) {
  const ws = useWorkspaceShellState();
  return (
    <WorkspaceShellContext.Provider value={ws.api}>
      <div data-testid="shell" data-fill={ws.fill ? "on" : "off"}>{children}</div>
    </WorkspaceShellContext.Provider>
  );
}

function RootProbe({ name }) {
  return <span data-testid={name} data-root={String(useScrollRoot())} />;
}

function Screen() {
  return (
    <Workspace header={<h1>작업 공간</h1>}>
      <WorkspacePane label="트리" bodyLabel="부서 트리" flowMaxHeight="min(50vh, 28rem)"><RootProbe name="tree-root" /></WorkspacePane>
      <WorkspacePane label="구성원" head={<PaneHead title="플랫폼개발팀" />} body="table">
        <RootProbe name="table-root" />
        <ErrorState error={Object.assign(new Error("x"), { status: 500 })} onRetry={() => {}} />
      </WorkspacePane>
    </Workspace>
  );
}

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("등록 — 채움은 고른 화면이 있는 동안만", () => {
  it("작업 공간이 서면 앱 틀이 채움이 되고, 떠나면 돌아간다", () => {
    function App({ show }) {
      return <Shell>{show ? <Screen /> : <p>다른 화면</p>}</Shell>;
    }
    const { rerender } = ui(<App show />);
    expect(screen.getByTestId("shell")).toHaveAttribute("data-fill", "on");
    rerender(<ThemeModeProvider><App show={false} /></ThemeModeProvider>);
    expect(screen.getByTestId("shell")).toHaveAttribute("data-fill", "off");
  });

  it("창이 기준(폭 1200 · 높이 600)에 못 미치면 등록해도 흐름이다", () => {
    mediaMatches = false;
    const { container } = ui(<Shell><Screen /></Shell>);
    expect(screen.getByTestId("shell")).toHaveAttribute("data-fill", "off");
    expect(container.querySelector("[data-workspace]")).toHaveAttribute("data-workspace", "flow");
  });

  it("앱 틀이 없으면(시험 · 단독 임베드) 채움은 늘 꺼져 있다", () => {
    const { container } = ui(<Screen />);
    expect(container.querySelector("[data-workspace]")).toHaveAttribute("data-workspace", "flow");
  });

  it("기준은 폭 1200 이상 · 높이 600 이상이다", () => {
    expect(WORKSPACE_FILL_QUERY).toBe("(min-width:1200px) and (min-height:600px)");
    expect(WORKSPACE_TRACKS.tree).toEqual({ lg: "20rem minmax(0, 1fr)", xl: "22rem minmax(0, 1fr)" });
  });
});

describe("판 — 머리 · 도구 줄 · 발은 고정, 몸만 굴러간다", () => {
  it("채움이면 판 몸은 이름 있는 스크롤 영역이고 굴림이 판 밖으로 번지지 않는다", () => {
    const { container } = ui(<Shell><Screen /></Shell>);
    expect(container.querySelector("[data-workspace]")).toHaveAttribute("data-workspace", "fill");
    const body = screen.getByRole("region", { name: "부서 트리" });
    expect(body).toHaveAttribute("data-pane-body", "scroll");
    expect(body).toHaveAttribute("tabindex", "0");
    const st = getComputedStyle(body);
    expect(st.overflow).toBe("auto");
    expect(st.overscrollBehavior).toBe("contain");
    // 판 안의 감시점은 실제로 굴리는 조상을 찾는다 — 창 기준이면 판을 열자마자 끝까지 받는다.
    expect(screen.getByTestId("tree-root")).toHaveAttribute("data-root", "auto");
    expect(screen.getByTestId("table-root")).toHaveAttribute("data-root", "auto");
  });

  it("표 판의 몸은 스스로 굴리지 않는다 — 안의 `DataTable fill` 이 굴린다", () => {
    const { container } = ui(<Shell><Screen /></Shell>);
    const body = container.querySelector('[data-pane-body="table"]');
    expect(body).not.toHaveAttribute("tabindex");
    expect(getComputedStyle(body).overflow).toBe("hidden");
  });

  it("흐름이면 높이 상한을 받은 판만 자기 안에서 굴러가고, 나머지는 문서와 함께 흐른다", () => {
    mediaMatches = false;
    const { container } = ui(<Shell><Screen /></Shell>);
    const tree = screen.getByRole("region", { name: "부서 트리" });
    expect(getComputedStyle(tree).maxHeight).toBe("min(50vh, 28rem)");
    expect(screen.getByTestId("tree-root")).toHaveAttribute("data-root", "auto");
    expect(screen.getByTestId("table-root")).toHaveAttribute("data-root", "null");
    expect(container.querySelector('[data-pane-body="table"]')).not.toHaveAttribute("tabindex");
  });

  it("판 안의 오류는 그 판의 한 칸(region)이다", () => {
    const { container } = ui(<Shell><Screen /></Shell>);
    expect(container.querySelector("[data-error-layout]")).toHaveAttribute("data-error-layout", "region");
  });

  it("판 머리는 머리 줄 하나다 — 제목이 첫 줄 가운데선에 선다", () => {
    const { container } = ui(<Shell><Screen /></Shell>);
    const head = container.querySelector("[data-pane-head]");
    expect(head.querySelector(".k-head-row")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "플랫폼개발팀" })).toBeInTheDocument();
  });
});
