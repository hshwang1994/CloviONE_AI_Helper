import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/* 열의 「더 보기」 — **첫 쪽과 같은 조건**이 다음 쪽에도 실린다(§8.5).
 *
 * qa-contract-change: 판의 조건이 티켓 목록과 같은 여러 값 상태가 됐다(D-497) — 프로젝트 · 담당자 주소 키가 `project_id` · `assignee_user_id` 이고 프로젝트 · 담당자 · 우선순위 · 난이도는 키를 되풀이해 싣는다. 예상 WD 범위(`est_wd_min` · `est_wd_max`)도 판 · 열이 같이 받는다. 「더 보기」 단정은 한 값 `get` 에 더해 되풀이한 값 전부(`getAll`)와 판 질의와 열 질의의 조건이 글자까지 같은지를 잰다. 「내 티켓만」이 켜지면 담당자 조건 대신 `mine` 이 실리는 것도 새로 잰다.
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
    id: "sp-1", name: "8월 넷째 주", department_id: "d-1",
    starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active",
  },
];
// 회차는 팀의 것이다(D-482) — 회차 목록 응답이 팀 봉투를 함께 싣는다.
const TEAM = {
  selected: "d-1",
  options: [{ id: "d-1", name: "A팀", path: [{ id: "d-1", name: "A팀" }], manageable: true }],
  manageable: true,
};

function stubApi({ board = BOARD, sprints = SPRINTS, column } = {}) {
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
    if (path.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
    if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints, team: TEAM });
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

  it("🔴 첫 쪽과 같은 조건을 전부 싣는다 — 검색·팀·우선순위·난이도·신호 포함", async () => {
    stubApi({ column: { cards: [card({ id: "t-2", key: "ABC-2", title: "다음 쪽의 일" })], next_cursor: null } });
    // 조건을 걸어 둔 채 진입한다 — 팀·회차도 주소에 있어 자동 선택이 끼어들지 않는다.
    renderBoard(
      "/work-board?team=d-1&sprint=sp-1&q=%EC%9D%B8%EC%A6%9D&priority=%EB%86%92%EC%9D%8C&difficulty=%EC%83%81&signal=blocked"
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

  it("🔴 여러 값 조건은 키를 되풀이해 싣고, 판과 다음 쪽이 같은 조건이다 — 프로젝트 · 담당자 · 우선순위 · 난이도 · 예상 범위", async () => {
    stubApi({ column: { cards: [], next_cursor: null } });
    renderBoard(
      "/work-board?team=d-1&sprint=sp-1"
      + "&project_id=p-1&project_id=p-2&assignee_user_id=u-1&assignee_user_id=u-2"
      + "&priority=%EB%86%92%EC%9D%8C&priority=%EA%B8%B4%EA%B8%89&difficulty=%EC%83%81&difficulty=%ED%95%98"
      + "&est_wd_min=1&est_wd_max=3"
    );
    await userEvent.click(await screen.findByRole("button", { name: "더 보기" }));
    await waitFor(() => expect(columnCalls().length).toBe(1));
    const boardCalls = apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith("/api/work/board?"));
    expect(boardCalls).toHaveLength(1);
    const first = new URLSearchParams(boardCalls[0].split("?")[1]);
    const next = new URLSearchParams(columnCalls()[0].split("?")[1]);
    for (const params of [first, next]) {
      expect(params.getAll("project_id")).toEqual(["p-1", "p-2"]);
      expect(params.getAll("assignee_user_id")).toEqual(["u-1", "u-2"]);
      expect(params.getAll("priority")).toEqual(["높음", "긴급"]);
      expect(params.getAll("difficulty")).toEqual(["상", "하"]);
      expect(params.get("est_wd_min")).toBe("1");
      expect(params.get("est_wd_max")).toBe("3");
      expect(params.get("department_id")).toBe("d-1");
      // 옛 한 값 키와 판이 받지 않는 정렬은 싣지 않는다.
      expect(params.get("project")).toBeNull();
      expect(params.get("assignee")).toBeNull();
      expect(params.get("sort")).toBeNull();
      expect(params.get("mine")).toBeNull();
    }
    // 조건 부분은 글자까지 같다 — 다른 것은 쪽 · 범위 값뿐이다.
    const conditions = (params) => {
      const copy = new URLSearchParams(params);
      for (const key of ["cursor", "limit", "column_page_size"]) copy.delete(key);
      return copy.toString();
    };
    expect(conditions(next)).toBe(conditions(first));
  });

  it("🔴 「내 티켓만」이 켜지면 담당자 조건은 싣지 않고 mine 을 싣는다 — 판과 다음 쪽이 같다", async () => {
    stubApi({ column: { cards: [], next_cursor: null } });
    renderBoard("/work-board?team=d-1&sprint=sp-1&assignee_user_id=u-1&mine=1");
    await userEvent.click(await screen.findByRole("button", { name: "더 보기" }));
    await waitFor(() => expect(columnCalls().length).toBe(1));
    const next = new URLSearchParams(columnCalls()[0].split("?")[1]);
    expect(next.get("mine")).toBe("true");
    expect(next.getAll("assignee_user_id")).toEqual([]);
    const boardCall = apiMock.mock.calls.map(([p]) => String(p)).find((p) => p.startsWith("/api/work/board?"));
    const first = new URLSearchParams(boardCall.split("?")[1]);
    expect(first.get("mine")).toBe("true");
    expect(first.getAll("assignee_user_id")).toEqual([]);
  });

  it("첫 쪽과 겹치는 카드는 한 번만 그린다 — 재조회 뒤의 확장분 중복", async () => {
    // 다음 쪽이 첫 쪽의 t-1 을 그대로 다시 싣는다(이동·재조회 직후에 실제로 생기는 모양).
    stubApi({
      column: {
        cards: [card(), card({ id: "t-2", key: "ABC-2", title: "다음 쪽의 일" })],
        next_cursor: null,
      },
    });
    renderBoard("/work-board?team=d-1&sprint=sp-1");
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
