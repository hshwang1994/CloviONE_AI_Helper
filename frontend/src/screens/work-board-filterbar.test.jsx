import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

/* 작업 보드 상단 — 문맥 · 보기 줄과 데이터 필터 한 줄 (D-497).
 *
 * 사용자 지시: 위가 두 줄로 흩어져 다른 티켓 목록과 달랐다. 「검색 → 주요 필터」를 일반 데스크톱 폭에서 한 줄로 세우고,
 * 「내 티켓만」은 데이터 필터가 아니라 보기 옵션이니 「보류 펴기」 · 「완료와 취소 보기」와 함께(보류의 왼쪽) 두고, 데이터
 * 필터와 보기 옵션을 눈으로 가르라고 했다. 이 파일이 지키는 것:
 *  1) 데이터 조건은 티켓 목록과 같은 필터 바 **한 줄**이다 — 검색 → 프로젝트(wide) → 담당자 → 우선순위 → 난이도 → 신호.
 *     팀 · 회차 · 보기 전환 · 보기 옵션은 그 줄이 아니라 문맥 줄에 선다.
 *  2) 보기 옵션 묶음의 차례와 구성 — 「내 티켓만」이 맨 앞이고, 백로그 탭에서 보류 · 완료와 취소가 빠져도 제자리다.
 *  3) 「필터 지우기」는 데이터 조건만 걷는다 — 팀 · 회차 · 탭 · 보류 · 완료와 취소 · 내 티켓만은 그대로다.
 *  4) 옛 주소 키(`project` · `assignee`)는 한 번 읽어 새 키로 고쳐 쓴다 — 판 질의는 새 키로 한 번만 나간다.
 *  5) 「내 티켓만」 — 담당자 칸은 이유와 함께 꺼지고 칩이 서지 않으며, 그 상태로 비면 「내 티켓이 없습니다」다.
 *  6) 칸에서 여러 값을 고르면 서버 질의에 키를 되풀이해 싣는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "operator", id: "u-1" } }) }));

import { WorkBoard, rewriteLegacyBoardSearch } from "./WorkBoard.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const OPTIONS = [
  { id: "d-a", name: "A팀", path: [{ id: "d-a", name: "A팀" }], manageable: true },
  { id: "d-b", name: "B팀", path: [{ id: "d-b", name: "B팀" }], manageable: true },
];
const SPRINTS = [{
  id: "sp-a", name: "9-2", department_id: "d-a", starts_on: "2026-09-15", ends_on: "2026-09-22", state: "active", active: true,
}];
const PROJECTS = [
  { id: "p-a", name: "A 프로젝트", dept_id: "d-a" },
  { id: "p-b", name: "B 프로젝트", dept_id: "d-b" },
];
const ASSIGNEES = [{ user_id: "u-1", display_name: "김하나" }, { user_id: "u-2", display_name: "이두리" }];
const META = { priorities: ["긴급", "높음", "보통"], difficulties: ["상", "중", "하"], statuses: [] };
const STATUSES = { statuses: [{ key: "계획", label: "계획", terminal: false, board: "column" }] };

function card(over) {
  return {
    id: "t-1", page_id: "pg-1", key: "ABC-1", title: "첫 일", status: "계획", priority: "높음", due: null, est_wd: 2,
    version: 1, assignees: [], assignee_names: [], assignee_tokens: 0, issue: false, blocked: false,
    project: "A 프로젝트", project_uid: "p-a", sprint_id: "sp-a",
    ...over,
  };
}
function boardOf(cards) {
  return {
    columns: [{ key: "계획", label: "계획", category: "open", placement: "column", total: cards.length, cards }],
    unclassified: [], unclassified_total: 0,
    summary: { total: cards.length, by_status: { "계획": cards.length }, signals: { issue: 0, blocked: 0, overdue: 0 } },
  };
}

function stub({ board = boardOf([card()]), backlog = [card({ id: "t-9", key: "ABC-9", title: "다음 일", sprint_id: null })] } = {}) {
  return (path) => {
    const url = String(path);
    if (url.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: PROJECTS });
    if (url.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: ASSIGNEES });
    if (url.startsWith("/api/tickets/meta")) return Promise.resolve(META);
    if (url.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
    if (url.startsWith("/api/work/sprints")) {
      return Promise.resolve({ sprints: SPRINTS, team: { selected: "d-a", options: OPTIONS, manageable: true } });
    }
    if (url.startsWith("/api/work/board")) return Promise.resolve(board);
    if (url.startsWith("/api/work/backlog")) return Promise.resolve({ items: backlog, total: backlog.length, next_cursor: null });
    return Promise.resolve({});
  };
}

function Here() {
  const loc = useLocation();
  return <div data-testid="here">{`${loc.pathname}${loc.search}`}</div>;
}

function renderBoard(entry) {
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

const here = () => screen.getByTestId("here").textContent;
const calls = (prefix) => apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith(prefix));
const paramsOf = (url) => new URLSearchParams(url.split("?")[1] || "");
const lastBoard = () => paramsOf(calls("/api/work/board?").slice(-1)[0] || "");
const conditionLine = () => document.querySelector("[data-filter-bar] [data-condition-line]");
const chipTexts = () => [...(conditionLine() || document.createElement("div")).querySelectorAll("[data-condition-chip]")].map((c) => c.textContent);

describe("작업 보드 — 데이터 필터는 한 줄이고 보기 옵션은 따로 선다", () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockImplementation(stub()); });

  it("🔴 데이터 조건은 필터 바 한 줄이다 — 검색 → 프로젝트(wide) → 담당자 → 우선순위 → 난이도 → 신호", async () => {
    renderBoard("/work-board?team=d-a&sprint=sp-a");
    await waitFor(() => expect(calls("/api/work/board?")).toHaveLength(1));
    const bar = document.querySelector("[data-filter-bar]");
    const rows = bar.querySelectorAll("[data-filter-row]");
    expect(rows).toHaveLength(1);
    const cells = [...rows[0].children];
    expect(cells.map((el) => el.getAttribute("data-filter-kind"))).toEqual(["search", "entity", "entity", "enum", "enum", "enum"]);
    expect(cells.slice(1).map((el) => el.querySelector("[data-prefix-label]").textContent))
      .toEqual(["프로젝트", "담당자", "우선순위", "난이도", "신호"]);
    // 프로젝트는 값이 긴 축이라 wide 칸이고, 담당자는 사람이라 기본 칸이다.
    expect(cells[1].getAttribute("data-filter-size")).toBe("wide");
    expect(cells[2].getAttribute("data-filter-size")).toBeNull();
    expect(within(bar).getByRole("searchbox", { name: "검색어" })).toHaveAttribute("placeholder", "티켓 제목, 이름 검색");

    // 팀 · 회차 · 보기 전환 · 보기 옵션은 필터 바가 아니라 문맥 줄에 선다. 팀 칸은 회차 목록 응답이 후보를 들고 와야 선다
    // (주소에 회차가 있으면 판 질의는 그보다 먼저 나간다).
    await screen.findByRole("combobox", { name: "팀" });
    const context = document.querySelector("[data-context-bar]");
    expect(context).not.toBeNull();
    expect(context.compareDocumentPosition(bar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    for (const name of ["팀", "회차"]) {
      const box = screen.getByRole("combobox", { name });
      expect(context.contains(box)).toBe(true);
      expect(bar.contains(box)).toBe(false);
    }
    expect(context.contains(screen.getByRole("tablist", { name: "보기 선택" }))).toBe(true);
    expect(within(bar).queryByRole("button", { name: "내 티켓만" })).toBeNull();
    expect(within(bar).queryByRole("button", { name: "보류 펴기" })).toBeNull();
    // 팀 · 회차 칸도 값이 긴 축이라 wide 칸이다.
    expect([...context.querySelectorAll("[data-filter-kind=entity]")].map((el) => el.getAttribute("data-filter-size")))
      .toEqual(["wide", "wide"]);
  });

  it("🔴 보기 옵션 묶음 — 「내 티켓만」이 맨 앞이고, 백로그 탭에서 뒤의 둘이 빠져도 제자리다", async () => {
    renderBoard("/work-board?team=d-a&sprint=sp-a");
    const group = await screen.findByRole("group", { name: "보기 옵션" });
    expect(document.querySelector("[data-context-bar]").contains(group)).toBe(true);
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(["내 티켓만", "보류 펴기", "완료와 취소 보기"]);
    const mineBefore = within(group).getByRole("button", { name: "내 티켓만" });

    await userEvent.click(screen.getByRole("tab", { name: "백로그" }));
    await waitFor(() => expect(here()).toContain("tab=backlog"));
    const groupAfter = screen.getByRole("group", { name: "보기 옵션" });
    expect(within(groupAfter).getAllByRole("button").map((b) => b.textContent)).toEqual(["내 티켓만"]);
    // 같은 단추가 같은 자리에 남는다 — 탭을 바꿔도 새로 그려져 다른 자리로 튀지 않는다.
    expect(within(groupAfter).getByRole("button", { name: "내 티켓만" })).toBe(mineBefore);
    expect(groupAfter).toBe(group);
    // 백로그 탭의 회차 칸은 「담을 회차」다(거르는 축이 아니라 담는 대상이다).
    expect(screen.getByRole("combobox", { name: "담을 회차" })).toBeInTheDocument();
  });

  it("🔴 「내 티켓만」은 보기 옵션이다 — 켜도 조건 칩이 서지 않고 조건 수에 안 든다", async () => {
    renderBoard("/work-board?team=d-a&sprint=sp-a&q=로그");
    await waitFor(() => expect(chipTexts()).toEqual(["검색: 로그"]));
    const mine = screen.getByRole("button", { name: "내 티켓만" });
    expect(mine).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(mine);
    await waitFor(() => expect(here()).toContain("mine=1"));
    expect(screen.getByRole("button", { name: "내 티켓만" })).toHaveAttribute("aria-pressed", "true");
    expect(chipTexts()).toEqual(["검색: 로그"]);
    expect(conditionLine().querySelector("[data-condition-count]").textContent).toMatch(/^조건 1개에 맞는 /);
    await waitFor(() => expect(lastBoard().get("mine")).toBe("true"));
  });

  it("🔴 「필터 지우기」는 데이터 조건만 걷는다 — 팀 · 회차 · 보류 · 완료와 취소 · 내 티켓만은 그대로다", async () => {
    apiMock.mockImplementation(stub({ board: boardOf([]) }));
    renderBoard("/work-board?team=d-a&sprint=sp-a&hold=1&all=1&mine=1&q=로그&project_id=p-a&priority=높음&signal=blocked&est_wd_min=1");
    await waitFor(() => expect(conditionLine()).not.toBeNull());
    await waitFor(() => expect(chipTexts()).toEqual(["우선순위: 높음", "신호: 차단됨", "프로젝트: A 프로젝트", "검색: 로그", "예상 WD: 1 ~ …"]));
    expect(conditionLine().querySelector("[data-condition-count]").textContent).toBe("조건 5개에 맞는 결과가 0건입니다.");
    // 조건 때문에 빈 판이라 빈 상태도 같은 지우기를 준다.
    expect(await screen.findByText("조건에 맞는 티켓이 없습니다.")).toBeInTheDocument();

    await userEvent.click(within(conditionLine()).getByRole("button", { name: "필터 지우기" }));
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a&sprint=sp-a&hold=1&all=1&mine=1"));
    expect(conditionLine()).toBeNull();
    await waitFor(() => {
      const p = lastBoard();
      expect(p.get("q")).toBeNull();
      expect(p.getAll("project_id")).toEqual([]);
      expect(p.get("est_wd_min")).toBeNull();
      // 보기 옵션은 그대로 실린다.
      expect(p.get("mine")).toBe("true");
      expect(p.get("scope")).toBe("all");
      expect(p.get("sprint_id")).toBe("sp-a");
    });
  });

  it("백로그 탭의 「필터 지우기」는 조건 줄에 선 정렬 칩도 걷는다 — 탭은 그대로다", async () => {
    renderBoard("/work-board?team=d-a&sprint=sp-a&tab=backlog&sort=due_date&q=x");
    await waitFor(() => expect(chipTexts()).toEqual(["검색: x", "정렬: 마감 ↑"]));
    await userEvent.click(within(conditionLine()).getByRole("button", { name: "필터 지우기" }));
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a&sprint=sp-a&tab=backlog"));
  });

  it("칸에서 여러 값을 고르면 주소와 판 질의에 키를 되풀이해 싣는다 — 신호는 값 하나다", async () => {
    const user = userEvent.setup();
    renderBoard("/work-board?team=d-a&sprint=sp-a");
    await waitFor(() => expect(calls("/api/work/board?")).toHaveLength(1));
    await user.click(screen.getByRole("combobox", { name: "우선순위" }));
    await user.click(await screen.findByRole("option", { name: "높음" }));
    await user.click(await screen.findByRole("option", { name: "긴급" }));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(paramsOf(here()).getAll("priority")).toEqual(["높음", "긴급"]));
    await waitFor(() => expect(lastBoard().getAll("priority")).toEqual(["높음", "긴급"]));

    await user.click(screen.getByRole("combobox", { name: "신호" }));
    await user.click(await screen.findByRole("option", { name: "차단됨" }));
    await waitFor(() => expect(lastBoard().get("signal")).toBe("blocked"));
    expect(paramsOf(here()).getAll("signal")).toEqual(["blocked"]);
    expect(chipTexts()).toEqual(["우선순위: 높음", "우선순위: 긴급", "신호: 차단됨"]);
  });
});

describe("옛 주소 키", () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockImplementation(stub()); });

  it("옛 키를 새 키로 고쳐 쓴다 — 다른 키의 값은 그대로이고, 새 키가 이미 있으면 새 키가 이긴다", () => {
    expect(rewriteLegacyBoardSearch("team=d-a&project=p-a&sprint=sp-a&assignee=u-1"))
      .toBe("team=d-a&sprint=sp-a&project_id=p-a&assignee_user_id=u-1");
    expect(rewriteLegacyBoardSearch("project=p-old&project_id=p-new")).toBe("project_id=p-new");
    // 빈 옛 키도 걷는다 — 남겨 두면 매번 고쳐 쓰려 든다.
    expect(rewriteLegacyBoardSearch("team=d-a&project=")).toBe("team=d-a");
    // 고칠 것이 없으면 null 이다(주소를 건드리지 않는다).
    expect(rewriteLegacyBoardSearch("team=d-a&project_id=p-a&sprint=sp-a")).toBeNull();
    expect(rewriteLegacyBoardSearch("")).toBeNull();
  });

  it("🔴 옛 주소로 들어오면 새 키로 고쳐 쓰고, 판 질의는 그 조건으로 한 번만 나간다", async () => {
    renderBoard("/work-board?team=d-a&sprint=sp-a&project=p-a&assignee=u-2");
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a&sprint=sp-a&project_id=p-a&assignee_user_id=u-2"));
    await waitFor(() => expect(calls("/api/work/board?")).toHaveLength(1));
    const p = lastBoard();
    expect(p.getAll("project_id")).toEqual(["p-a"]);
    expect(p.getAll("assignee_user_id")).toEqual(["u-2"]);
    expect(p.get("project")).toBeNull();
    await new Promise((r) => setTimeout(r, 50));
    expect(calls("/api/work/board?")).toHaveLength(1);
    // 조건 칩이 새 키의 값을 이름으로 말한다.
    await waitFor(() => expect(chipTexts()).toEqual(["프로젝트: A 프로젝트", "담당자: 이두리"]));
  });
});

describe("「내 티켓만」과 담당자 조건", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("🔴 켜져 있으면 담당자 칸은 이유와 함께 꺼지고 칩이 서지 않는다 — 값은 주소에 남아 끄면 돌아온다", async () => {
    apiMock.mockImplementation(stub());
    renderBoard("/work-board?team=d-a&sprint=sp-a&assignee_user_id=u-2&mine=1");
    const box = await screen.findByRole("combobox", { name: "담당자" });
    expect(box).toBeDisabled();
    const reason = "「내 티켓만」이 켜져 있는 동안에는 담당자 조건을 쓰지 않습니다.";
    expect(box.closest("[data-filter-off]")).toHaveAttribute("title", reason);
    const described = box.getAttribute("aria-describedby");
    expect(described).toBeTruthy();
    expect(document.getElementById(described).textContent).toBe(reason);
    expect(conditionLine()).toBeNull();
    await waitFor(() => expect(lastBoard().get("mine")).toBe("true"));
    expect(lastBoard().getAll("assignee_user_id")).toEqual([]);

    await userEvent.click(screen.getByRole("button", { name: "내 티켓만" }));
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a&sprint=sp-a&assignee_user_id=u-2"));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "담당자" })).not.toBeDisabled());
    await waitFor(() => expect(chipTexts()).toEqual(["담당자: 이두리"]));
    await waitFor(() => expect(lastBoard().getAll("assignee_user_id")).toEqual(["u-2"]));
    expect(lastBoard().get("mine")).toBeNull();
  });

  it("🔴 켜진 채 비면 「내 티켓이 없습니다」 — 「내 티켓만 끄기」가 그 자리에서 되돌린다", async () => {
    apiMock.mockImplementation(stub({ board: boardOf([]) }));
    renderBoard("/work-board?team=d-a&sprint=sp-a&mine=1");
    expect(await screen.findByText("내 티켓이 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("「내 티켓만」을 끄면 이 팀의 티켓을 모두 볼 수 있습니다.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "내 티켓만 끄기" }));
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a&sprint=sp-a"));
    expect(screen.queryByText("내 티켓이 없습니다.")).toBeNull();
  });

  it("조건도 걸려 있으면 조건 때문에 빈 목록이 먼저다 — 「필터 지우기」를 준다", async () => {
    apiMock.mockImplementation(stub({ board: boardOf([]) }));
    renderBoard("/work-board?team=d-a&sprint=sp-a&mine=1&q=없는말");
    expect(await screen.findByText("조건에 맞는 티켓이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText("내 티켓이 없습니다.")).toBeNull();
  });

  it("백로그도 같은 말을 한다 — 켜진 채 비면 「내 티켓이 없습니다」", async () => {
    apiMock.mockImplementation(stub({ backlog: [] }));
    renderBoard("/work-board?team=d-a&sprint=sp-a&tab=backlog&mine=1");
    expect(await screen.findByText("내 티켓이 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내 티켓만 끄기" })).toBeInTheDocument();
  });
});
