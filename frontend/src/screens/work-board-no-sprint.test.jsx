import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 회차 없는 판도 선다 — 같은 메뉴를 두 번 누른 뒤의 그 상태다.
 *
 * 🔴 이 파일이 생긴 이유(2026-09-21): 사용자가 작업 보드 메뉴를 빠르게 두 번 누르면 「500」 화면을 봤다. 서버는
 * 한 번도 5xx 를 내지 않았다. 재현 하네스(`scripts/ui_qa/reactivate_e2e.py`)가 Chromium · Firefox 둘 다에서 같은
 * 예외를 잡았다 — `TypeError: Cannot read properties of null (reading 'draggable')`. 재클릭이 질의 없는 주소로
 * 가서 팀만 다시 골라지고 회차가 빠진 판(`?team=…`)이 섰고, 그 판에 카드가 있으면 `DragBoard` 에 `disabled={null}`
 * 이 넘어가 dnd-kit 이 렌더 중에 죽었다. 오류 경계가 화면을 대신 그렸고 그 그림이 「500」 팻말이었다.
 *
 * 재진입 규칙(`app/navEntry.jsx`)이 회차 자동 선택을 되살리지만, 회차 없는 판은 그것과 별개로 정당한 상태다 —
 * 회차가 하나도 없는 팀이 그렇다. 그래서 그 상태 자체를 여기서 세운다.
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

const CARD = {
  id: "t-1", page_id: "pg-1", key: "ABC-1", title: "회차 밖에서 진행 중인 일",
  status: "진행", priority: "높음", due: null, est_wd: 2,
  version: 3, assignees: [], assignee_names: [], assignee_tokens: 0,
  issue: false, blocked: false, blocked_reason: null, project: "포털 개편",
};

const BOARD = {
  column_limit: 50,
  columns: [
    { key: "진행", label: "진행 중", category: "in_progress", placement: "column", total: 1, cards: [CARD], next_cursor: null },
  ],
  unclassified: [],
  unclassified_total: 0,
  summary: { total: 1, by_status: { "진행": 1 }, signals: { issue: 0, blocked: 0, overdue: 0 } },
};

const TEAM = {
  selected: "d-1",
  options: [{ id: "d-1", name: "A팀", path: [{ id: "d-1", name: "A팀" }], manageable: true }],
  manageable: true,
};

/* 이 화면의 오류 경계와 같은 자리 — 렌더 예외를 받아 적는다. */
class Catch extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error) { this.props.onError(error); }
  render() { return this.state.error ? <div>오류 경계</div> : this.props.children; }
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
    if (path.startsWith("/api/work/statuses")) {
      return Promise.resolve({ statuses: [{ key: "진행", label: "진행 중", terminal: false, board: "column" }] });
    }
    // 회차가 하나도 없는 팀 — 자동 선택이 고를 회차가 없어 판은 회차 없이 선다.
    if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: [], team: TEAM });
    if (path.startsWith("/api/work/board")) return Promise.resolve(BOARD);
    if (path.startsWith("/api/work/backlog")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({});
  });
});

describe("회차 없는 판", () => {
  it("🔴 카드가 있어도 화면이 죽지 않고 카드를 그린다", async () => {
    const errors = [];
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/work-board?team=d-1"]}>
        <QueryClientProvider client={qc}>
          <ThemeModeProvider>
            <ToastProvider>
              <ConfirmProvider>
                <Catch onError={(e) => errors.push(e)}>
                  <Routes>
                    <Route path="/work-board" element={<WorkBoard />} />
                  </Routes>
                </Catch>
              </ConfirmProvider>
            </ToastProvider>
          </ThemeModeProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText("회차 밖에서 진행 중인 일")).toBeInTheDocument();
    expect(screen.queryByText("오류 경계")).toBeNull();
    expect(errors.map((e) => String(e && e.message))).toEqual([]);
    spy.mockRestore();
  });
});
