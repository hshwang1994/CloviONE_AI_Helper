import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

/* 판이 **어휘가 정한 자리**대로 서는가 (지시 5 · D-349).
 *
 * 이 파일이 지키는 것 셋이다. 「판에서 끈 이동은 `board_rank` 에 적힌다」는 넷째 규칙은
 * 서버 쪽에서 지킨다(`tests/unit/test_board_service.py`) — 끌기 자체를 jsdom 에서 흉내내면
 * 시험이 dnd-kit 의 포인터 계산을 검사하게 되고, 정작 두 목록이 안 섞이는가는 안 본다.
 *
 *  1) 열은 서버가 준 `placement` 로 고른다. 보류는 접혀 있고 취소는 숨는다 — 화면이
 *     상태 이름을 적어 열을 고르면 어휘가 바뀐 날 이 화면만 옛 목록으로 남는다.
 *  2) **신호는 카드를 옮기지 않는다.** 차단된 진행 중 티켓은 진행 중 열에 그대로 서고
 *     표식만 단다. 신호를 열로 만들면 「지금 무엇이 진행 중인가」에 답이 둘이 된다.
 *  3) 요약은 **자르기 전에 센 값**을 그린다. 열의 카드 수를 더해서 세면 잘린 열
 *     (`column_limit`)에서 조용히 틀린다.
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
    id: "t-1", page_id: "pg-1", key: "ABC-1", title: "차단된 일",
    status: "진행", priority: "높음", due: null, est_wd: 2,
    version: 3, assignees: [], assignee_names: [], assignee_tokens: 0,
    issue: false, blocked: false, blocked_reason: null, project: "포털 개편",
    ...over,
  };
}

/** 서버가 실제로 주는 판 한 장. 여섯 상태가 세 자리로 갈린다. */
const BOARD = {
  column_limit: 200,
  columns: [
    { key: "계획", label: "계획", category: "open", placement: "column", total: 1, cards: [card({ id: "t-0", key: "ABC-0", title: "할 일" })] },
    // 차단된 티켓은 **진행 중 열에** 있다.
    { key: "진행", label: "진행 중", category: "in_progress", placement: "column", total: 1, cards: [card({ blocked: true, blocked_reason: "외부 응답 대기" })] },
    { key: "검증", label: "검증", category: "in_progress", placement: "column", total: 0, cards: [] },
    { key: "완료", label: "완료", category: "done", placement: "column", total: 0, cards: [] },
    { key: "보류", label: "보류", category: "open", placement: "collapsed", total: 1, cards: [card({ id: "t-h", key: "ABC-9", title: "미룬 일" })] },
    { key: "취소", label: "취소", category: "canceled", placement: "hidden", total: 1, cards: [card({ id: "t-x", key: "ABC-8", title: "접은 일" })] },
  ],
  unclassified: [],
  unclassified_total: 0,
  summary: {
    // **자르기 전에 센 값**이다. 위 `cards` 를 더하면 4 지만 실제 판에는 40 건이 있다.
    total: 40,
    by_status: { "계획": 30, "진행": 6, "검증": 2, "완료": 1, "보류": 1, "취소": 0 },
    signals: { issue: 0, blocked: 1, overdue: 0 },
  },
};

/** 고를 것이 실제로 있어야 「고른 뒤 무엇이 주소에 실리는가」를 볼 수 있다. */
const PROJECTS = [{ id: "p-1", name: "포털 개편" }];
const SPRINTS = [
  {
    id: "sp-1", name: "8월 넷째 주", project_id: "p-1",
    starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active",
  },
];

const STATUSES = {
  statuses: [
    { key: "계획", label: "계획", terminal: false, board: "column" },
    { key: "진행", label: "진행 중", terminal: false, board: "column" },
    { key: "검증", label: "검증", terminal: false, board: "column" },
    { key: "완료", label: "완료", terminal: true, board: "column" },
    { key: "보류", label: "보류", terminal: false, board: "collapsed" },
    { key: "취소", label: "취소", terminal: true, board: "hidden" },
  ],
};

/** 「티켓 추가」가 어디로 데려갔는지 보려고 도착지가 주소를 그대로 적는다. */
function Landing() {
  const loc = useLocation();
  return <div data-landed={`${loc.pathname}${loc.search}`}>도착</div>;
}

function renderBoard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/work-board"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes>
                <Route path="/work-board" element={<WorkBoard />} />
                <Route path="/new-ticket" element={<Landing />} />
              </Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** 열은 `aria-label="<이름> (<건수>건)"` 인 section 이다(`DropColumn`). */
function lanes() {
  return screen.queryAllByRole("region").map((el) => el.getAttribute("aria-label"));
}

describe("작업 보드의 열", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: PROJECTS });
      if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
      if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
      if (path.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
      if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: SPRINTS });
      if (path.startsWith("/api/work/board")) return Promise.resolve(BOARD);
      if (path.startsWith("/api/work/backlog")) return Promise.resolve({ items: [], total: 0 });
      return Promise.resolve({});
    });
  });

  it("기본 판은 실행 열 넷만 세운다 — 보류는 접히고 취소는 숨는다", async () => {
    renderBoard();
    await waitFor(() => expect(lanes().length).toBeGreaterThan(0));
    const titles = lanes().map((l) => l.replace(/ \(.*$/, ""));
    expect(titles).toEqual(["계획", "진행 중", "검증", "완료"]);
    expect(screen.queryByText("미룬 일")).toBeNull();
    expect(screen.queryByText("접은 일")).toBeNull();
  });

  it("「보류 펴기」를 누르면 보류 열이 선다. 없애는 것이 아니라 접는 것이다", async () => {
    renderBoard();
    await waitFor(() => expect(lanes().length).toBe(4));
    await userEvent.click(screen.getByRole("button", { name: "보류 펴기" }));
    await waitFor(() => expect(screen.getByText("미룬 일")).toBeTruthy());
    expect(lanes().map((l) => l.replace(/ \(.*$/, ""))).toContain("보류");
    // 취소는 여전히 숨는다 — 스위치가 따로다.
    expect(screen.queryByText("접은 일")).toBeNull();
  });

  it("🔴 차단된 티켓은 「차단」 열로 옮겨 가지 않는다 — 진행 중에 있고 표식만 단다", async () => {
    renderBoard();
    await waitFor(() => expect(screen.getByText("차단된 일")).toBeTruthy());
    expect(lanes().map((l) => l.replace(/ \(.*$/, ""))).not.toContain("차단됨");
    // 카드가 진행 중 열 **안에** 있다.
    const lane = screen.getByRole("region", { name: /^진행 중/ });
    expect(lane.textContent).toContain("차단된 일");
    // 그리고 그 카드에 신호 표식이 붙는다.
    expect(lane.querySelector('[data-signal="blocked"]')).toBeTruthy();
  });

  it("🔴 요약은 잘리기 전에 센 값이다 — 열의 카드 수를 더한 값이 아니다", async () => {
    renderBoard();
    await waitFor(() => expect(screen.getByRole("group", { name: "상태별 티켓 수" })).toBeTruthy());
    const strip = screen.getByRole("group", { name: "상태별 티켓 수" });
    // 판에 그려진 카드는 넷뿐이지만 요약은 40 이다.
    expect(strip.textContent).toContain("40");
    expect(strip.textContent).toContain("30");
  });

  it("신호 줄은 켜진 것이 있을 때만 선다", async () => {
    // 「차단 0 · 지연 0 · 이슈 0」 은 매일 같은 자리를 쓰면서 아무 것도 말하지 않는다.
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/work/board")) {
        return Promise.resolve({
          ...BOARD,
          summary: { ...BOARD.summary, signals: { issue: 0, blocked: 0, overdue: 0 } },
        });
      }
      if (path.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
      if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: PROJECTS });
      if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
      if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
      if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: SPRINTS });
      return Promise.resolve({ items: [], total: 0 });
    });
    renderBoard();
    // 상태 줄은 뜬다 — 그것이 「아직 안 읽었다」와 「신호가 없다」를 가른다.
    await waitFor(() => expect(screen.getByRole("group", { name: "상태별 티켓 수" })).toBeTruthy());
    expect(screen.queryByRole("group", { name: "신호별 티켓 수" })).toBeNull();
  });

  it("🔴 판에서 만든 티켓은 지금 보고 있는 회차로 간다 — 만드는 자리가 기본값을 정한다", async () => {
    renderBoard();
    await waitFor(() => expect(screen.getByRole("button", { name: "티켓 추가" })).toBeTruthy());
    // 프로젝트와 회차를 고른 상태를 만든다. 조합 상자라 목록에서 고른다.
    await userEvent.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await userEvent.click(await screen.findByRole("option", { name: "포털 개편" }));
    await userEvent.click(screen.getByRole("combobox", { name: /스프린트/ }));
    await userEvent.click(await screen.findByRole("option", { name: "8월 넷째 주" }));

    await userEvent.click(screen.getByRole("button", { name: "티켓 추가" }));
    const landed = await screen.findByText("도착");
    const to = landed.getAttribute("data-landed");
    expect(to).toContain("/new-ticket");
    expect(to).toContain("project=p-1");
    // 이 한 칸이 없으면 만든 사람이 곧바로 「스프린트에 담기」를 한 번 더 눌러야 하고,
    // 그 한 번을 빠뜨린 티켓은 회의에서 아무도 못 본다.
    expect(to).toContain("sprint=sp-1");
  });

  it("칸 아래 「이 칸에 추가」는 그 칸의 상태를 싣는다", async () => {
    renderBoard();
    const adders = await screen.findAllByRole("link", { name: "이 칸에 추가" });
    expect(adders.length).toBeGreaterThan(0);
    expect(adders[0].getAttribute("href")).toContain("status=");
  });
});