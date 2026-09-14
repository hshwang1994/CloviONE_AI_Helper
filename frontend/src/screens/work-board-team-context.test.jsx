import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

/* 작업 보드의 **팀 문맥** (D-482).
 *
 * 문맥은 팀 → 회차 → 프로젝트 순서다. 이 파일이 지키는 것:
 *  1) 팀 후보가 둘 이상이고 기본 팀이 없으면 화면이 고르라고 말한다 — 「전체 팀」 판은 없다.
 *  2) 팀을 바꾸면 회차·프로젝트가 비워지고 그 팀의 회차 목록을 새로 읽는다.
 *  3) 프로젝트를 바꿔도 팀·회차·회차 목록은 그대로다 — 프로젝트는 필터다.
 *  4) 「필터 초기화」는 팀·회차·탭을 건드리지 않는다.
 *  5) 편성 단추는 팀의 관리 범위(`manageable`)를 따른다 — 역할만으로는 안 선다.
 *  6) 「스프린트 회의」·「티켓 추가」 링크가 팀 문맥을 싣는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "operator", id: "u-1" } }) }));

import { WorkBoard } from "./WorkBoard.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const STATUSES = { statuses: [{ key: "계획", label: "계획", terminal: false, board: "column" }] };
const BOARD = {
  columns: [{ key: "계획", label: "계획", category: "open", placement: "column", total: 0, cards: [] }],
  unclassified: [], unclassified_total: 0,
  summary: { total: 0, by_status: {}, signals: { issue: 0, blocked: 0, overdue: 0 } },
};
const OPTIONS = [
  { id: "d-a", name: "A팀", path: [{ id: "d-a", name: "A팀" }], manageable: true },
  { id: "d-b", name: "B팀", path: [{ id: "d-b", name: "B팀" }], manageable: false },
];
const SPRINTS_A = [{ id: "sp-a", name: "9-2", department_id: "d-a", starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active", active: true }];
const SPRINTS_B = [{ id: "sp-b", name: "9-2", department_id: "d-b", starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active", active: true }];
const PROJECTS = [
  { id: "p-a", name: "A 프로젝트", dept_id: "d-a" },
  { id: "p-b", name: "B 프로젝트", dept_id: "d-b" },
];

function stub({ defaultTeam = null } = {}) {
  return (path) => {
    const url = String(path);
    if (url.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: PROJECTS });
    if (url.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (url.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
    if (url.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
    if (url.startsWith("/api/work/sprints")) {
      const team = new URLSearchParams(url.split("?")[1] || "").get("department_id") || defaultTeam;
      const row = OPTIONS.find((o) => o.id === team) || null;
      return Promise.resolve({
        sprints: team === "d-a" ? SPRINTS_A : team === "d-b" ? SPRINTS_B : [],
        team: { selected: team, options: OPTIONS, manageable: !!(row && row.manageable) },
      });
    }
    if (url.startsWith("/api/work/board")) return Promise.resolve(BOARD);
    if (url.startsWith("/api/work/backlog")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({});
  };
}

function Here() {
  const loc = useLocation();
  return <div data-testid="here">{`${loc.pathname}${loc.search}`}</div>;
}

function renderBoard(entry = "/work-board") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Here />
              <Routes>
                <Route path="/work-board" element={<WorkBoard />} />
              </Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const calls = (prefix) => apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith(prefix));

describe("작업 보드의 팀 문맥", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("🔴 기본 팀이 없으면 고르라고 말하고, 고르면 그 팀의 회차와 판을 읽는다", async () => {
    apiMock.mockImplementation(stub());
    renderBoard();
    await screen.findByText("팀을 골라 주세요.");
    expect(calls("/api/work/board?")).toHaveLength(0);
    await userEvent.click(screen.getByRole("combobox", { name: /^팀/ }));
    await userEvent.click(await screen.findByRole("option", { name: "A팀" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("team=d-a"));
    await waitFor(() => expect(calls("/api/work/sprints?department_id=d-a").length).toBeGreaterThan(0));
    await waitFor(() => expect(calls("/api/work/board?").length).toBe(1));
    const params = new URLSearchParams(calls("/api/work/board?")[0].split("?")[1]);
    expect(params.get("department_id")).toBe("d-a");
    expect(params.get("sprint_id")).toBe("sp-a");
  });

  it("🔴 팀을 바꾸면 회차와 프로젝트가 비워지고 그 팀의 열린 회차가 다시 선다", async () => {
    apiMock.mockImplementation(stub({ defaultTeam: "d-a" }));
    renderBoard("/work-board?team=d-a&sprint=sp-a&project=p-a");
    await waitFor(() => expect(calls("/api/work/board?").length).toBe(1));
    await userEvent.click(await screen.findByRole("combobox", { name: /^팀/ }));
    await userEvent.click(await screen.findByRole("option", { name: "B팀" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("team=d-b"));
    expect(screen.getByTestId("here").textContent).not.toContain("project=p-a");
    // B 팀의 열린 회차가 자동으로 선다 — A 팀의 회차 id 가 남지 않는다.
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("sprint=sp-b"));
    expect(screen.getByTestId("here").textContent).not.toContain("sp-a");
  });

  it("🔴 프로젝트를 바꿔도 팀·회차는 그대로고 회차 목록을 다시 읽지 않는다", async () => {
    apiMock.mockImplementation(stub({ defaultTeam: "d-a" }));
    renderBoard("/work-board?team=d-a&sprint=sp-a");
    await waitFor(() => expect(calls("/api/work/board?").length).toBe(1));
    const sprintsBefore = calls("/api/work/sprints").length;
    await userEvent.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    // 후보는 이 팀의 프로젝트뿐이다.
    expect(screen.queryByRole("option", { name: "B 프로젝트" })).toBeNull();
    await userEvent.click(await screen.findByRole("option", { name: "A 프로젝트" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("project=p-a"));
    expect(screen.getByTestId("here").textContent).toContain("team=d-a");
    expect(screen.getByTestId("here").textContent).toContain("sprint=sp-a");
    expect(calls("/api/work/sprints").length).toBe(sprintsBefore);
  });

  it("「필터 초기화」는 팀·회차를 건드리지 않는다", async () => {
    apiMock.mockImplementation(stub({ defaultTeam: "d-a" }));
    renderBoard("/work-board?team=d-a&sprint=sp-a&project=p-a&q=x&mine=1");
    await waitFor(() => expect(calls("/api/work/board?").length).toBe(1));
    await userEvent.click(screen.getByRole("button", { name: "필터 초기화" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toBe("/work-board?team=d-a&sprint=sp-a"));
  });

  it("🔴 편성 단추는 팀의 관리 범위를 따른다 — B 팀(관리 밖)에서는 서지 않는다", async () => {
    apiMock.mockImplementation(stub({ defaultTeam: "d-a" }));
    renderBoard("/work-board?team=d-a&sprint=sp-a");
    await waitFor(() => expect(screen.getByRole("button", { name: "회차 추가" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "회차 닫기" })).toBeTruthy();
    const link = screen.getByRole("link", { name: "스프린트 회의" });
    expect(link.getAttribute("href")).toContain("team=d-a");
    expect(link.getAttribute("href")).toContain("sprint=sp-a");
    expect(screen.getByRole("link", { name: "티켓 추가" }).getAttribute("href")).toContain("team=d-a");

    await userEvent.click(screen.getByRole("combobox", { name: /^팀/ }));
    await userEvent.click(await screen.findByRole("option", { name: "B팀" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("sprint=sp-b"));
    await waitFor(() => expect(screen.queryByRole("button", { name: "회차 추가" })).toBeNull());
    expect(screen.queryByRole("button", { name: "회차 닫기" })).toBeNull();
    // 「티켓 추가」는 회차를 싣지 않는다 — 담을 권한이 없다.
    expect(screen.getByRole("link", { name: "티켓 추가" }).getAttribute("href")).not.toContain("sprint=");
  });
});
