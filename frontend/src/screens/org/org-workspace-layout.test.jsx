import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 관리 작업 공간의 배치 (O1 · F5 · D-531 · D-533).
 *
 * jsdom 에는 배치가 없다 — 여기서는 화면이 채움 모드를 **원하고**, 창이 기준을 넘으면 앱 틀이 채움이 되며, 판마다 몸이 스크롤
 * 상자로 선언되는지를 본다. 실제 높이 · 독립 굴림 · 고정 영역은 실브라우저 하네스(`scripts/ui_qa/workspace_e2e.py` 의 조직 경우)가 잰다.
 *
 *   채움(폭 1200 · 높이 600 이상)  앱 틀 채움 · 왼쪽 판 몸 = 「조직도 목록」 스크롤 영역 · 오른쪽 판 몸 = 표가 직접 굴리는 상자
 *   흐름(그보다 작은 창)            앱 틀 흐름 · 왼쪽 판 몸만 높이 상한이 있는 스크롤 영역 · 오른쪽 표는 문서와 함께 흐른다
 *   화면을 떠나면                   등록이 풀려 앱 틀이 흐름으로 돌아간다
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1", management: { kind: "global" } } }),
}));

import { OrgWorkspace } from "./OrgWorkspace.jsx";
import { WORKSPACE_FILL_QUERY, WorkspaceShellContext, useWorkspaceShellState } from "../../ui/Workspace.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, active: true, child_count: 1, subtree_user_count: 2, created_at: AT },
  { id: "dep-1", kind: "department", name: "영업팀", depth: 1, org_id: "org-1", active: true, child_count: 0, subtree_user_count: 2, created_at: AT },
];
const ORGS = [{ id: "org-1", name: "클로비원", slug: "clovirone", status: "active", department_count: 1, created_at: AT }];

let fillMatches = true;
const realMatchMedia = window.matchMedia;
beforeEach(() => {
  fillMatches = true;
  apiMock.mockReset();
  apiMock.mockImplementation((url) => {
    const u = String(url);
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    if (u.startsWith("/api/admin/users")) {
      return Promise.resolve({ items: [{ id: "u-1", display_name: "김영업", email: "a@example.com", role: "user", active: true }], total: 1 });
    }
    return Promise.resolve({ items: [] });
  });
  window.matchMedia = (query) => ({
    matches: query === WORKSPACE_FILL_QUERY ? fillMatches : false,
    media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  });
});
afterEach(() => { window.matchMedia = realMatchMedia; });

function Shell({ children }) {
  const ws = useWorkspaceShellState();
  return (
    <WorkspaceShellContext.Provider value={ws.api}>
      <div data-testid="shell" data-fill={ws.fill ? "on" : "off"}>{children}</div>
    </WorkspaceShellContext.Provider>
  );
}

function renderAt(path, { show = true } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (visible) => (
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[path]}>
          <Shell>
            <Routes>
              <Route path="/organizations" element={visible ? <OrgWorkspace /> : <p>다른 화면</p>} />
            </Routes>
          </Shell>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
  const view = render(tree(show));
  return { ...view, swap: (visible) => view.rerender(tree(visible)) };
}

describe("채움 모드", () => {
  it("창이 기준을 넘으면 앱 틀이 채움이 되고, 두 판의 몸이 각자 스크롤 상자다", async () => {
    const { container } = renderAt("/organizations");
    expect(await screen.findByRole("treeitem", { name: "클로비원" })).toBeInTheDocument();
    expect(screen.getByTestId("shell")).toHaveAttribute("data-fill", "on");
    expect(container.querySelector("[data-workspace]")).toHaveAttribute("data-workspace", "fill");

    const treeBody = screen.getByRole("region", { name: "조직도 목록" });
    expect(treeBody).toHaveAttribute("tabindex", "0");
    expect(treeBody).toHaveAttribute("data-pane-body", "scroll");
    expect(within(treeBody).getByRole("tree", { name: "조직도" })).toBeInTheDocument();

    // 오른쪽은 표가 직접 굴린다 — 판 몸은 상자가 아니라 표 상자를 담는 세로 묶음이다.
    const right = screen.getByTestId("org-console-panel");
    expect(await within(right).findByText("김영업")).toBeInTheDocument();
    expect(right.querySelector('[data-pane-body="table"]')).not.toBeNull();
    expect(right.querySelector('[data-table-box="fill"]')).not.toBeNull();
    // 고정 영역 — 판 머리 · 도구 줄은 몸 밖에 선다.
    const pane = right.querySelector("[data-workspace-pane]");
    expect(pane.querySelector("[data-pane-head]")).not.toBeNull();
    expect(pane.querySelector("[data-pane-toolbar]")).not.toBeNull();
    expect(pane.querySelector('[data-pane-body="table"] [data-pane-head]')).toBeNull();
  });

  it("화면을 떠나면 앱 틀이 흐름으로 돌아간다", async () => {
    const { swap } = renderAt("/organizations");
    await screen.findByRole("treeitem", { name: "클로비원" });
    expect(screen.getByTestId("shell")).toHaveAttribute("data-fill", "on");
    swap(false);
    expect(screen.getByTestId("shell")).toHaveAttribute("data-fill", "off");
  });
});

describe("흐름 모드", () => {
  it("창이 기준보다 작으면 앱 틀은 흐름이고, 왼쪽 판 몸만 높이 상한이 있는 스크롤 영역이다", async () => {
    fillMatches = false;
    const { container } = renderAt("/organizations");
    await screen.findByRole("treeitem", { name: "클로비원" });
    expect(screen.getByTestId("shell")).toHaveAttribute("data-fill", "off");
    expect(container.querySelector("[data-workspace]")).toHaveAttribute("data-workspace", "flow");
    expect(screen.getByRole("region", { name: "조직도 목록" })).toHaveAttribute("tabindex", "0");
    const right = screen.getByTestId("org-console-panel");
    expect(await within(right).findByText("김영업")).toBeInTheDocument();
    expect(right.querySelector('[data-pane-body="table"]')).not.toHaveAttribute("role");
    // 흐름에서는 표 상자가 스크롤 창이 아니다 — 높이 제한 없는 상자 안의 감시점은 늘 보여 끝까지 받는다.
    expect(right.querySelector('[data-table-box="fill"]')).toBeNull();
  });
});
