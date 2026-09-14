import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/* qa-contract-change: 회차가 팀의 것이 되어(D-482) 자동 선택 앞에 **팀 자동 선택**이 한 단계 더 생겼다 — 서버가 준 기본 팀이 주소에 먼저 실리고, 그 뒤 그 팀의 열린 회차가 선다. 「판 질의는 정확히 한 번」 계약은 그대로이고, 회차 선택기 이름이 「회차」로 바뀌었다. 단언 수는 늘었다.
 *
 * 회차 자동 선택 — 판 질의는 선택이 정리된 뒤 **정확히 한 번** 나간다(§8.3).
 *
 * 🔴 예전의 두 결함:
 *  1) 진입 즉시 회차 없는 판 질의(전 회차 최대 비용)를 쏘고, 자동 선택이 끝나면 같은
 *     판을 두 번째로 읽었다 — 진입 한 번에 판 요청이 항상 둘이었다(429 기여).
 *  2) 열린 회차가 없으면 「가장 미래의 회차」로 물러나 첫 화면이 빈 판이 됐다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { WorkBoard } from "./WorkBoard.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const STATUSES = {
  statuses: [
    { key: "계획", label: "계획", terminal: false, board: "column" },
    { key: "진행", label: "진행 중", terminal: false, board: "column" },
  ],
};

const BOARD = {
  column_limit: 50,
  columns: [
    { key: "계획", label: "계획", category: "open", placement: "column", total: 0, cards: [] },
    { key: "진행", label: "진행 중", category: "in_progress", placement: "column", total: 0, cards: [] },
  ],
  unclassified: [],
  unclassified_total: 0,
  summary: { total: 0, by_status: {}, signals: { issue: 0, blocked: 0, overdue: 0 } },
};

const TEAM = {
  selected: "d-a",
  options: [{ id: "d-a", name: "A팀", path: [{ id: "d-a", name: "A팀" }], manageable: true }],
  manageable: true,
};

function sprint(over) {
  return {
    id: "sp-1", name: "이번 회차", department_id: "d-a",
    starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active", active: true,
    ...over,
  };
}

function stubApi(sprints) {
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
    if (path.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
    if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints, team: TEAM });
    if (path.startsWith("/api/work/board")) return Promise.resolve(BOARD);
    if (path.startsWith("/api/work/backlog")) return Promise.resolve({ items: [], total: 0, team: TEAM });
    return Promise.resolve({});
  });
}

function renderBoard(entry = "/work-board") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
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

function boardCalls() {
  return apiMock.mock.calls
    .map(([path]) => String(path))
    .filter((p) => p.startsWith("/api/work/board?"));
}

describe("회차 자동 선택과 판 질의 수", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("🔴 열린 회차가 있으면 그 회차를 실은 판 질의가 정확히 한 번 나간다 — 팀도 함께", async () => {
    stubApi([sprint()]);
    renderBoard();
    await waitFor(() => expect(boardCalls().length).toBe(1));
    const params = new URLSearchParams(boardCalls()[0].split("?")[1]);
    expect(params.get("sprint_id")).toBe("sp-1");
    // 서버가 준 기본 팀이 판 질의에 실린다 — 팀 없는 질의(전 팀 최대 비용)는 없다.
    expect(params.get("department_id")).toBe("d-a");
    // 잠시 뒤에도 둘째 질의가 없다.
    await new Promise((r) => setTimeout(r, 50));
    expect(boardCalls().length).toBe(1);
  });

  it("🔴 열린 회차가 없으면(전부 예정·종료) 자동 선택하지 않는다 — 질의도 한 번뿐", async () => {
    stubApi([
      sprint({ id: "sp-9", name: "다음 회차", state: "planned", active: false }),
      sprint({ id: "sp-0", name: "지난 회차", state: "closed", active: false }),
    ]);
    renderBoard();
    await waitFor(() => expect(boardCalls().length).toBe(1));
    expect(new URLSearchParams(boardCalls()[0].split("?")[1]).get("sprint_id")).toBeNull();
    await new Promise((r) => setTimeout(r, 50));
    expect(boardCalls().length).toBe(1);
    expect(screen.getByText("진행 중인 회차가 없습니다.")).toBeTruthy();
  });

  it("주소에 회차를 실어 들어오면 그 회차로 곧장 읽고, 비운 선택을 되살리지 않는다", async () => {
    stubApi([sprint(), sprint({ id: "sp-2", name: "다른 회차", state: "planned", active: false })]);
    renderBoard("/work-board?team=d-a&sprint=sp-2");
    await waitFor(() => expect(boardCalls().length).toBe(1));
    expect(new URLSearchParams(boardCalls()[0].split("?")[1]).get("sprint_id")).toBe("sp-2");

    // 사용자가 회차를 「전체」로 비운다 — 자동 선택이 sp-1 을 다시 덮으면 안 된다.
    await userEvent.click(screen.getByRole("combobox", { name: /^회차/ }));
    await userEvent.click(await screen.findByRole("option", { name: "전체" }));
    await waitFor(() => {
      const later = boardCalls();
      expect(new URLSearchParams(later[later.length - 1].split("?")[1]).get("sprint_id")).toBeNull();
    });
    await new Promise((r) => setTimeout(r, 50));
    const final = boardCalls();
    expect(
      final.filter((p) => new URLSearchParams(p.split("?")[1]).get("sprint_id") === "sp-1")
    ).toHaveLength(0);
  });
});
