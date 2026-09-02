import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/* 열의 「더 보기」 — **첫 쪽과 같은 조건**이 다음 쪽에도 실린다(§8.5).
 *
 * 🔴 이 파일이 태어난 이유: 예전 `loadMoreColumn` 은 선언된 적 없는 변수를 참조해
 * **누르는 즉시 ReferenceError** 였고(열 50건 초과는 다음 쪽을 영영 못 받았다), 설령
 * 고쳐도 검색·부서·우선순위·난이도·신호를 안 실어 서버 계약(`app/work/router.py` —
 * 「조건이 어긋나면 이 쪽에서 다른 카드가 새거나 겹친다」)을 어겼다. 그 두 결함 다
 * 이 화면의 어떤 시험도 「더 보기」를 눌러 본 적이 없어서 살아남았다.
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

function card(over) {
  return {
    id: "t-1", page_id: "pg-1", key: "ABC-1", title: "첫 쪽의 일",
    status: "계획", priority: "높음", due: null, est_wd: 2,
    version: 3, assignees: [], assignee_names: [], assignee_tokens: 0,
    issue: false, blocked: false, blocked_reason: null, project: "포털 개편",
    ...over,
  };
}

const STATUSES = {
  statuses: [
    { key: "계획", label: "계획", terminal: false, board: "column" },
    { key: "진행", label: "진행 중", terminal: false, board: "column" },
  ],
};

/** 계획 열 하나가 2건 중 1건만 실려 와 「더 보기」가 선다. */
const BOARD = {
  column_limit: 50,
  columns: [
    {
      key: "계획", label: "계획", category: "open", placement: "column",
      total: 2, cards: [card()], next_cursor: "cur-1",
    },
    { key: "진행", label: "진행 중", category: "in_progress", placement: "column", total: 0, cards: [] },
  ],
  unclassified: [],
  unclassified_total: 0,
  summary: { total: 2, by_status: { "계획": 2, "진행": 0 }, signals: { issue: 0, blocked: 0, overdue: 0 } },
};

const SPRINTS = [
  {
    id: "sp-1", name: "8월 넷째 주", project_id: "",
    starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active",
  },
];

function stubApi({ board = BOARD, sprints = SPRINTS, column } = {}) {
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
    if (path.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
    if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints });
    if (path.startsWith("/api/work/board/columns/")) {
      return Promise.resolve(column || { cards: [], next_cursor: null });
    }
    if (path.startsWith("/api/work/board")) return Promise.resolve(board);
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

function columnCalls() {
  return apiMock.mock.calls
    .map(([path]) => String(path))
    .filter((p) => p.startsWith("/api/work/board/columns/"));
}

describe("열의 「더 보기」", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("🔴 첫 쪽과 같은 조건을 전부 싣는다 — 검색·부서·우선순위·난이도·신호 포함", async () => {
    stubApi({ column: { cards: [card({ id: "t-2", key: "ABC-2", title: "다음 쪽의 일" })], next_cursor: null } });
    // 조건을 걸어 둔 채 진입한다 — 회차도 주소에 있어 자동 선택이 끼어들지 않는다.
    renderBoard(
      "/work-board?sprint=sp-1&q=%EC%9D%B8%EC%A6%9D&dept=d-1&priority=%EB%86%92%EC%9D%8C&difficulty=%EC%83%81&signal=blocked"
    );
    await userEvent.click(await screen.findByRole("button", { name: "더 보기" }));
    await waitFor(() => expect(columnCalls().length).toBe(1));

    const url = columnCalls()[0];
    expect(url).toContain(`/api/work/board/columns/${encodeURIComponent("계획")}?`);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("q")).toBe("인증");
    expect(params.get("department_id")).toBe("d-1");
    expect(params.get("priority")).toBe("높음");
    expect(params.get("difficulty")).toBe("상");
    expect(params.get("signal")).toBe("blocked");
    expect(params.get("sprint_id")).toBe("sp-1");
    expect(params.get("scope")).toBe("execution");
    expect(params.get("cursor")).toBe("cur-1");
    // 서버가 받지 않는 옛 이름이 다시 스며들면 안 된다.
    expect(params.get("blocked_only")).toBeNull();

    // 받은 다음 쪽이 실제로 열에 붙는다 — 오류 토스트가 아니라.
    await screen.findByText("다음 쪽의 일");
    expect(screen.queryByText(/더 받아오지 못했습니다/)).toBeNull();
  });

  it("첫 쪽과 겹치는 카드는 한 번만 그린다 — 재조회 뒤의 확장분 중복", async () => {
    // 다음 쪽이 첫 쪽의 t-1 을 그대로 다시 싣는다(이동·재조회 직후에 실제로 생기는 모양).
    stubApi({
      column: {
        cards: [card(), card({ id: "t-2", key: "ABC-2", title: "다음 쪽의 일" })],
        next_cursor: null,
      },
    });
    renderBoard("/work-board?sprint=sp-1");
    await userEvent.click(await screen.findByRole("button", { name: "더 보기" }));
    await screen.findByText("다음 쪽의 일");
    expect(screen.getAllByText("첫 쪽의 일")).toHaveLength(1);
  });
});

describe("빈 판의 「완료와 취소 보기」", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("🔴 누르면 죽지 않고 scope=all 로 다시 읽는다", async () => {
    const empty = {
      ...BOARD,
      columns: BOARD.columns.map((c) => ({ ...c, total: 0, cards: [], next_cursor: null })),
      summary: { total: 0, by_status: {}, signals: { issue: 0, blocked: 0, overdue: 0 } },
    };
    // 회차 없음 — 빈 상태의 도움말·행동 버튼이 서는 조건이다.
    stubApi({ board: empty, sprints: [] });
    renderBoard();
    await userEvent.click(
      await screen.findByRole("button", { name: "완료와 취소 보기" })
    );
    // 예전에는 이 클릭이 선언 안 된 setter 를 불러 ErrorBoundary 로 떨어졌다.
    await waitFor(() => {
      const boardCalls = apiMock.mock.calls
        .map(([path]) => String(path))
        .filter((p) => p.startsWith("/api/work/board?"));
      expect(boardCalls.some((p) => new URLSearchParams(p.split("?")[1]).get("scope") === "all")).toBe(true);
    });
  });
});
