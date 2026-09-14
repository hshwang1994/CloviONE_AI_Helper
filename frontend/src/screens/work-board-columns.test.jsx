import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";

/* qa-contract-change: 작업 보드 상단의 상태·신호 요약 카드가 사라졌다(D-484 — 판이 집계 카드보다 먼저 선다). 「타일을 누르면 열로 데려간다」·「요약은 자르기 전 값」 단정은 그 카드와 함께 걷고, 대신 새 계약 셋을 단정한다: 카드를 누르면 상세가 아니라 **미리보기**가 열리고(D-483), 「티켓 상세 보기」만 상세로 가며 뒤로가기 한 번에 미리보기 없는 판으로 돌아온다, 회차 선택기 이름은 「회차」다(D-482), 「티켓 추가」 링크가 팀 문맥을 싣는다. 단언 수는 늘었다.
 *
 * 판이 **어휘가 정한 자리**대로 서는가 (지시 5 · D-349).
 *
 *  1) 열은 서버가 준 `placement` 로 고른다. 보류는 접혀 있고 취소는 숨는다.
 *  2) **신호는 카드를 옮기지 않는다.** 차단된 진행 중 티켓은 진행 중 열에 그대로 서고
 *     표식만 단다.
 *  3) 카드를 누르면 **미리보기**다. 팀·회차·필터가 주소에 그대로 남고, 상세로 가는 것은
 *     「티켓 상세 보기」뿐이다.
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
    project_uid: "p-1", sprint_id: "sp-1",
    ...over,
  };
}

/** 서버가 실제로 주는 판 한 장. 여섯 상태가 세 자리로 갈린다. */
const BOARD = {
  column_limit: 200,
  columns: [
    { key: "계획", label: "계획", category: "open", placement: "column", total: 1, cards: [card({ id: "t-0", page_id: "pg-0", key: "ABC-0", title: "할 일" })] },
    // 차단된 티켓은 **진행 중 열에** 있다.
    { key: "진행", label: "진행 중", category: "in_progress", placement: "column", total: 1, cards: [card({ blocked: true, blocked_reason: "외부 응답 대기" })] },
    { key: "검증", label: "검증", category: "in_progress", placement: "column", total: 0, cards: [] },
    { key: "완료", label: "완료", category: "done", placement: "column", total: 0, cards: [] },
    { key: "보류", label: "보류", category: "open", placement: "collapsed", total: 1, cards: [card({ id: "t-h", page_id: "pg-h", key: "ABC-9", title: "미룬 일" })] },
    { key: "취소", label: "취소", category: "canceled", placement: "hidden", total: 1, cards: [card({ id: "t-x", page_id: "pg-x", key: "ABC-8", title: "접은 일" })] },
  ],
  unclassified: [],
  unclassified_total: 0,
  summary: {
    total: 40,
    by_status: { "계획": 30, "진행": 6, "검증": 2, "완료": 1, "보류": 1, "취소": 0 },
    signals: { issue: 0, blocked: 1, overdue: 0 },
  },
  team: { selected: "d-a", options: [], manageable: true },
};

const TEAM = {
  selected: "d-a",
  options: [{ id: "d-a", name: "A팀", path: [{ id: "d-a", name: "A팀" }], manageable: true }],
  manageable: true,
};
/** 프로젝트에는 팀이 있다 — 회차 문맥의 후보는 그 팀의 것만이다(D-482). */
const PROJECTS = [{ id: "p-1", name: "포털 개편", dept_id: "d-a" }];
const SPRINTS = [
  {
    id: "sp-1", name: "8월 넷째 주", department_id: "d-a",
    starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active", active: true,
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

const TICKET = {
  configured: true, ok: true, can_edit: true,
  ticket: {
    id: "pg-1", key: "ABC-1", title: "차단된 일", status: "진행", priority: "높음",
    project: "포털 개편", project_uid: "p-1", due: "2026-08-28", est_wd: 2, sprint_id: "sp-1",
    assignee_people: [], blocked: true, blocked_reason: "외부 응답 대기",
  },
  body_markdown: "외부 API 응답을 기다리고 있습니다.",
};

/** 「티켓 추가」·「티켓 상세 보기」가 어디로 데려갔는지 보려고 도착지가 주소를 그대로 적는다. */
function Landing() {
  const loc = useLocation();
  const nav = useNavigate();
  return (
    <div>
      <div data-landed={`${loc.pathname}${loc.search}`} data-from={(loc.state && loc.state.from) || ""}>
        도착
      </div>
      {/* 브라우저 뒤로가기의 자리 — MemoryRouter 는 window.history 를 안 쓴다. */}
      <button type="button" onClick={() => nav(-1)}>뒤로</button>
    </div>
  );
}

/** 지금 주소를 밖에서 읽는 창. */
function Here() {
  const loc = useLocation();
  return <div data-testid="here">{`${loc.pathname}${loc.search}`}</div>;
}

function renderBoard(entry = "/work-board?team=d-a&sprint=sp-1") {
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
                <Route path="/new-ticket" element={<Landing />} />
                <Route path="/tickets/:id" element={<Landing />} />
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

function stub(path) {
  if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: PROJECTS });
  if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
  if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ priorities: [], difficulties: [] });
  if (path.startsWith("/api/tickets/pg-")) return Promise.resolve(TICKET);
  if (path.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
  if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: SPRINTS, team: TEAM });
  if (path.startsWith("/api/work/board")) return Promise.resolve(BOARD);
  if (path.startsWith("/api/work/backlog")) return Promise.resolve({ items: [], total: 0, team: TEAM });
  return Promise.resolve({});
}

describe("작업 보드의 열", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(stub);
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
    const lane = screen.getByRole("region", { name: /^진행 중/ });
    expect(lane.textContent).toContain("차단된 일");
    expect(lane.querySelector('[data-signal="blocked"]')).toBeTruthy();
  });

  it("🔴 판 위에 요약 카드가 없다 — 판이 먼저 선다(D-484)", async () => {
    renderBoard();
    await waitFor(() => expect(lanes().length).toBe(4));
    expect(screen.queryByRole("group", { name: "상태별 티켓 수" })).toBeNull();
    expect(screen.queryByRole("group", { name: "신호별 티켓 수" })).toBeNull();
    // 「상세 필터」 접이도 없다 — 조건은 항상 보인다.
    expect(screen.queryByRole("button", { name: /상세 필터/ })).toBeNull();
    expect(screen.getByRole("button", { name: "필터 초기화" })).toBeTruthy();
  });

  it("🔴 카드를 누르면 상세가 아니라 미리보기가 열린다 — 팀·회차는 주소에 그대로다(D-483)", async () => {
    renderBoard();
    await userEvent.click(await screen.findByText("차단된 일"));
    // 주소에 미리보기가 실리고(뒤로가기 한 번이 미리보기를 닫는다), 문맥은 그대로다.
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("peek=pg-1"));
    expect(screen.getByTestId("here").textContent).toContain("team=d-a");
    expect(screen.getByTestId("here").textContent).toContain("sprint=sp-1");
    // 상세로 가지 않았다.
    expect(screen.queryByText("도착")).toBeNull();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/외부 API 응답을 기다리고/)).toBeTruthy();
    expect(apiMock.mock.calls.some(([p]) => p === "/api/tickets/pg-1")).toBe(true);
  });

  it("🔴 「티켓 상세 보기」만 상세로 가고, 되돌아오면 미리보기 없는 판이다", async () => {
    renderBoard();
    await userEvent.click(await screen.findByText("차단된 일"));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "티켓 상세 보기" }));
    const landed = await screen.findByText("도착");
    expect(landed.getAttribute("data-landed")).toBe("/tickets/pg-1");
    // 상세의 「목록」이 돌아올 자리를 실어 보낸다.
    expect(landed.getAttribute("data-from")).toBe("/work-board");
    // 미리보기 항목은 상세로 **갈아 끼워졌다** — 뒤로가기 한 번에 미리보기 없는 판이다.
    await userEvent.click(screen.getByRole("button", { name: "뒤로" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toBe("/work-board?team=d-a&sprint=sp-1"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("🔴 판에서 만든 티켓은 지금 보고 있는 팀과 회차로 간다 — 만드는 자리가 기본값을 정한다", async () => {
    renderBoard();
    await waitFor(() => expect(screen.getByRole("link", { name: "티켓 추가" })).toBeTruthy());
    // 회차 선택기의 이름은 「회차」다 — 「스프린트」는 화면 이름에만 남는다(D-482).
    expect(screen.getByRole("combobox", { name: /^회차/ })).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: /스프린트/ })).toBeNull();
    await userEvent.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await userEvent.click(await screen.findByRole("option", { name: "포털 개편" }));

    await userEvent.click(screen.getByRole("link", { name: "티켓 추가" }));
    const landed = await screen.findByText("도착");
    const to = landed.getAttribute("data-landed");
    expect(to).toContain("/new-ticket");
    expect(to).toContain("team=d-a");
    expect(to).toContain("project=p-1");
    expect(to).toContain("sprint=sp-1");
  });

  it("칸 아래 「이 칸에 추가」는 그 칸의 상태와 팀을 싣는다", async () => {
    renderBoard();
    const adders = await screen.findAllByRole("link", { name: "이 칸에 추가" });
    expect(adders.length).toBeGreaterThan(0);
    expect(adders[0].getAttribute("href")).toContain("status=");
    expect(adders[0].getAttribute("href")).toContain("team=d-a");
  });

  it("편성할 수 있는 열린 회차의 카드에는 「현재 회차에서 빼기」가 있다 — 「제거」가 아니다", async () => {
    renderBoard();
    await screen.findByText("차단된 일");
    await userEvent.click(screen.getByRole("button", { name: "ABC-1 카드 작업" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "현재 회차에서 빼기" }));
    await waitFor(() => {
      const call = apiMock.mock.calls.find(([p, o]) => String(p).includes("/move") && o && o.method === "POST");
      expect(call).toBeTruthy();
      expect(call[1].body).toEqual({ sprint_id: null, set_sprint: true, base_version: 3 });
    });
    // 메뉴를 누른 것이 카드의 미리보기를 열지 않는다.
    expect(screen.getByTestId("here").textContent).not.toContain("peek=");
  });
});
