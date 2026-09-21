import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";

/* 「진입 때 한 번」 회차 자동 선택은 **주소가 비면 다시 무장한다** — 작업 보드 · 스프린트 회의 (D-498 의 안전띠).
 *
 * 같은 메뉴를 다시 누르면 주소가 질의 없는 `/work-board` · `/sprint` 로 바뀐다. 셸은 이제 그것을 새 진입으로 보고 화면을
 * 다시 마운트하지만(`app/navEntry.jsx`), 화면이 그것에 기대면 안 된다 — 주소가 비는 길은 뒤로가기 · 목록의 기억 · 손으로
 * 고친 주소에도 있다. 예전에는 화면이 산 채로 주소만 비면 팀 자동 선택은 다시 돌았는데 회차 자동 선택은 「이 팀은 이미
 * 했다」로 멈춰, 회차가 빠진 판이 섰다(`?team=…` — 한 번 누른 끝 상태와 다르다). 여기서는 화면을 **다시 마운트하지 않은
 * 채** 주소만 비우고, 두 번째 끝 상태가 첫 끝 상태와 같은지 잰다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "operator", id: "u-1" } }) }));

import { WorkBoard } from "./WorkBoard.jsx";
import { Sprint } from "./Sprint.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const TEAM = {
  selected: "d-a",
  options: [{ id: "d-a", name: "A팀", path: [{ id: "d-a", name: "A팀" }], manageable: true }],
  manageable: true,
};
const SPRINTS = [
  { id: "sp-old", name: "9-1", department_id: "d-a", starts_on: "2026-09-01", ends_on: "2026-09-12", state: "closed", active: false },
  { id: "sp-open", name: "9-2", department_id: "d-a", starts_on: "2026-09-15", ends_on: "2026-09-22", state: "active", active: true },
];

function stub(path) {
  const url = String(path);
  if (url.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
  if (url.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
  if (url.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
  if (url.startsWith("/api/work/statuses")) return Promise.resolve({ statuses: [] });
  // 회의 본문은 이 시험의 관심이 아니다 — 끝나지 않는 응답으로 두면 화면은 불러오는 모양에 머문다.
  if (url.includes("/meeting")) return new Promise(() => {});
  if (url.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: SPRINTS, team: TEAM });
  if (url.startsWith("/api/work/board")) {
    return Promise.resolve({ columns: [], unclassified: [], unclassified_total: 0, summary: { total: 0, by_status: {}, signals: {} } });
  }
  if (url.startsWith("/api/work/backlog")) return Promise.resolve({ items: [], total: 0 });
  return Promise.resolve({});
}

function Here() {
  const loc = useLocation();
  return <div data-testid="here">{`${loc.pathname}${loc.search}`}</div>;
}

/* 같은 메뉴를 다시 누른 것과 같은 이동 — 질의 없는 주소로 간다. 화면은 같은 `Route` 라 다시 마운트되지 않는다. */
function SameMenu({ to }) {
  const nav = useNavigate();
  return <button type="button" onClick={() => nav(to)}>같은 메뉴</button>;
}

function renderAt(path, element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Here />
              <SameMenu to={path} />
              <Routes>
                <Route path={path} element={element} />
              </Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const here = () => screen.getByTestId("here").textContent;

describe("주소가 비면 회차 자동 선택을 다시 무장한다", () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockImplementation(stub); });

  it("🔴 작업 보드 — 두 번 들어온 끝 상태가 한 번 들어온 끝 상태와 같다(열린 회차의 판)", async () => {
    renderAt("/work-board", <WorkBoard />);
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a&sprint=sp-open"));
    const once = here();

    await userEvent.click(screen.getByRole("button", { name: "같은 메뉴" }));
    await waitFor(() => expect(here()).toBe(once));
    await new Promise((r) => setTimeout(r, 50));
    expect(here()).toBe(once);
    // 마지막 판 질의가 그 회차를 싣는다 — 회차 없는 판(`scope=execution` 만)으로 끝나지 않는다.
    const boards = apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith("/api/work/board?"));
    const last = new URLSearchParams(boards[boards.length - 1].split("?")[1]);
    expect(last.get("sprint_id")).toBe("sp-open");
    expect(last.get("department_id")).toBe("d-a");
  });

  it("🔴 스프린트 회의 — 두 번 들어온 끝 상태가 한 번 들어온 끝 상태와 같다(열린 회차의 회의)", async () => {
    renderAt("/sprint", <Sprint />);
    await waitFor(() => expect(here()).toBe("/sprint?team=d-a&sprint=sp-open"));
    const once = here();

    await userEvent.click(screen.getByRole("button", { name: "같은 메뉴" }));
    await waitFor(() => expect(here()).toBe(once));
    await new Promise((r) => setTimeout(r, 50));
    expect(here()).toBe(once);
  });

  it("같은 팀에서 사용자가 손으로 비운 회차는 되살리지 않는다 — 주소가 빈 것이 아니라 선택을 바꾼 것이다", async () => {
    renderAt("/work-board", <WorkBoard />);
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a&sprint=sp-open"));
    await userEvent.click(screen.getByRole("combobox", { name: /^회차/ }));
    await userEvent.click(await screen.findByRole("option", { name: "전체" }));
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a"));
    await new Promise((r) => setTimeout(r, 50));
    expect(here()).toBe("/work-board?team=d-a");
  });
});
