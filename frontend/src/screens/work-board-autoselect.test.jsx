import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/* 회차 자동 선택 — 판 질의는 선택이 정리된 뒤 **정확히 한 번** 나간다(§8.3).
 *
 * 🔴 예전의 두 결함:
 *  1) 진입 즉시 회차 없는 판 질의(전 회차 최대 비용)를 쏘고, 자동 선택이 끝나면 같은
 *     판을 두 번째로 읽었다 — 진입 한 번에 판 요청이 항상 둘이었다(429 기여).
 *  2) 열린 회차가 없으면 `pickOpenSprint` 가 「가장 미래의 회차」(starts_on 내림차순의
 *     첫 줄 — 대개 아직 안 열었거나 이미 닫힌 회차)로 물러나 첫 화면이 빈 판이 됐다.
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

function sprint(over) {
  return {
    id: "sp-1", name: "이번 회차", project_id: "",
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
    if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints });
    if (path.startsWith("/api/work/board")) return Promise.resolve(BOARD);
    if (path.startsWith("/api/work/backlog")) return Promise.resolve({ items: [], total: 0 });
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

async function settle() {
  // 판 질의가 실제로 나갈 때까지(이 픽스처의 판은 비어 있어 열 대신 빈 상태가 선다).
  await waitFor(() => expect(boardCalls().length).toBeGreaterThan(0));
  // 자동 선택 → 재질의의 여지가 있는 두 번째 렌더 사이클까지 흘려보낸다.
  await new Promise((r) => setTimeout(r, 80));
}

describe("회차 자동 선택과 판 질의 수", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("🔴 열린 회차가 있으면 그 회차를 실은 판 질의가 정확히 한 번 나간다", async () => {
    stubApi([sprint()]);
    renderBoard();
    await settle();
    const calls = boardCalls();
    expect(calls).toHaveLength(1);
    expect(new URLSearchParams(calls[0].split("?")[1]).get("sprint_id")).toBe("sp-1");
  });

  it("🔴 열린 회차가 없으면(전부 예정·종료) 자동 선택하지 않는다 — 질의도 한 번뿐", async () => {
    stubApi([
      sprint({ id: "sp-9", name: "다음 회차", state: "planned", active: false }),
      sprint({ id: "sp-0", name: "지난 회차", state: "closed", active: false }),
    ]);
    renderBoard();
    await settle();
    const calls = boardCalls();
    expect(calls).toHaveLength(1);
    expect(new URLSearchParams(calls[0].split("?")[1]).get("sprint_id")).toBeNull();
    // 화면이 이유를 말한다 — 빈 판을 조용히 보여 주지 않는다.
    expect(screen.getByText("진행 중인 회차가 없습니다.")).toBeTruthy();
  });

  it("주소에 회차를 실어 들어오면 그 회차로 곧장 읽고, 비운 선택을 되살리지 않는다", async () => {
    stubApi([sprint(), sprint({ id: "sp-2", name: "다른 회차", state: "planned", active: false })]);
    renderBoard("/work-board?sprint=sp-2");
    await settle();
    let calls = boardCalls();
    expect(calls).toHaveLength(1);
    expect(new URLSearchParams(calls[0].split("?")[1]).get("sprint_id")).toBe("sp-2");

    // 사용자가 회차를 「전체」로 비운다 — 자동 선택이 sp-1 을 다시 덮으면 안 된다.
    await userEvent.click(screen.getByRole("combobox", { name: /스프린트/ }));
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
