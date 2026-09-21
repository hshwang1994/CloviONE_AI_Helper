import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

/* 작업 보드 백로그의 머리 — 티켓 표와 **같은** 머리 필터 · 정렬 (D-497).
 *
 * 사용자 지시: 백로그 그리드에는 열 머리 필터가 없다. 다른 티켓 그리드가 쓰는 머리 필터 · 정렬 UX 를 그대로 쓰고(새 패턴
 * 금지), 거를 수 있는 열 · 정렬할 수 있는 열 · 빈 값 표시를 다른 그리드와 맞춘다. 백로그는 끌어 순서를 바꾸는 목록이라
 * 표가 아니다(D-473) — 머리 칸만 표 머리와 같은 칸(`ui/GridHeaderCell.jsx`)이다. 이 파일이 지키는 것:
 *  1) 머리는 `role="table"` 「백로그 열」 안의 한 줄이고 일곱 칸이 티켓 표와 같은 어휘로 정렬 · 필터 표지를 단다.
 *  2) 머리 필터와 필터 바의 칸은 **같은 주소 상태**다 — 한쪽에서 걸면 다른 쪽이 그 값을 보이고, 칩도 하나다.
 *  3) 머리 정렬은 서버 정렬이다 — `sort` · `order` 를 싣고, 칸의 `aria-sort` 가 방향을 말한다.
 *  4) 정렬해서 보는 동안에는 끌기 · 「맨 위로/맨 아래로」를 쓰지 않고 한 줄 안내가 선다. 기본 순서로 되돌리는 길이 둘이다.
 *  5) 빈 칸은 표와 같이 「-」 · 「담당자 없음」이다.
 *  6) 「맨 위로」는 지금 보는 백로그의 조건을 목록 그대로(`position_*`) 싣는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "operator", id: "u-1" } }) }));

import { WorkBoard } from "./WorkBoard.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const TEAM = {
  selected: "d-a",
  options: [{ id: "d-a", name: "A팀", path: [{ id: "d-a", name: "A팀" }], manageable: true }],
  manageable: true,
};
const SPRINTS = [{
  id: "sp-a", name: "9-2", department_id: "d-a", starts_on: "2026-09-15", ends_on: "2026-09-22", state: "active", active: true,
}];
const PROJECTS = [{ id: "p-a", name: "A 프로젝트", dept_id: "d-a" }];
const ASSIGNEES = [{ user_id: "u-1", display_name: "김하나" }, { user_id: "u-2", display_name: "이두리" }];
const META = { priorities: ["긴급", "높음", "보통"], difficulties: ["상", "중", "하"], statuses: [] };

const ROWS = [
  {
    id: "t-1", page_id: "pg-1", key: "ABC-1", title: "담당자가 있는 일", status: "계획", priority: "높음", difficulty: "상",
    due: "2026-09-30", est_wd: 2, version: 4, sprint_id: null, project_uid: "p-a",
    assignees: [{ user_id: "u-1", display_name: "김하나" }], assignee_names: ["김하나"], assignee_tokens: 1,
  },
  {
    id: "t-2", page_id: "pg-2", key: "ABC-2", title: "비어 있는 일", status: "계획", priority: null, difficulty: null,
    due: null, est_wd: null, version: 1, sprint_id: null, project_uid: "p-a",
    assignees: [], assignee_names: [], assignee_tokens: 0,
  },
];

function stub(path, opts) {
  const url = String(path);
  if (url.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: PROJECTS });
  if (url.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: ASSIGNEES });
  if (url.startsWith("/api/tickets/meta")) return Promise.resolve(META);
  if (url.startsWith("/api/work/statuses")) return Promise.resolve({ statuses: [] });
  if (url.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: SPRINTS, team: TEAM });
  if (url.startsWith("/api/work/backlog")) return Promise.resolve({ items: ROWS, total: ROWS.length, next_cursor: null });
  if (url.includes("/move") && opts && opts.method === "POST") return Promise.resolve({ ticket: { ...ROWS[0], version: 5 } });
  if (url.startsWith("/api/work/board")) return Promise.resolve({ columns: [], unclassified: [], unclassified_total: 0, summary: { total: 0 } });
  return Promise.resolve({});
}

function Here() {
  const loc = useLocation();
  return <div data-testid="here">{`${loc.pathname}${loc.search}`}</div>;
}

function renderBacklog(extra = "") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/work-board?team=d-a&sprint=sp-a&tab=backlog${extra}`]}>
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
const paramsOf = (url) => new URLSearchParams(url.split("?")[1] || "");
const backlogCalls = () => apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith("/api/work/backlog?"));
const lastBacklog = () => paramsOf(backlogCalls().slice(-1)[0] || "");
const head = () => screen.getByRole("table", { name: "백로그 열" });
const headCell = (label) => within(head()).getAllByRole("columnheader").find((h) => h.getAttribute("title") === label);
const chipTexts = () => [...document.querySelectorAll("[data-filter-bar] [data-condition-chip]")].map((c) => c.textContent);
/* 끄는 줄은 dnd-kit 의 손잡이 역할(`button` · `aria-roledescription`)이고 이름은 「번호 제목」이다. */
const rowOf = (key, title) => screen.findByRole("button", { name: `${key} ${title}` });
const rowsShown = async () => rowOf("ABC-1", "담당자가 있는 일");

describe("백로그 머리 — 티켓 표와 같은 머리 칸", () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockImplementation(stub); });

  it("🔴 머리는 한 줄 일곱 칸이고, 티켓 표와 같은 열이 정렬 · 필터 표지를 단다", async () => {
    renderBacklog();
    await rowsShown();
    const table = head();
    expect(within(table).getAllByRole("row")).toHaveLength(1);
    const cells = within(table).getAllByRole("columnheader");
    expect(cells.map((c) => c.getAttribute("title"))).toEqual(["티켓", "우선순위", "난이도", "예상", "마감", "담당자", "작업"]);
    // 정렬할 수 있는 열만 방향을 말한다 — 기본은 끌어 옮긴 순서라 어느 열도 정렬 중이 아니다.
    expect(cells.map((c) => c.getAttribute("aria-sort"))).toEqual(["none", "none", "none", "none", "none", null, null]);
    // 필터 표지 — 조건이 걸릴 수 있는 열에만 선다(티켓 표와 같은 열: 우선순위 · 난이도 · 예상 WD 범위 · 담당자).
    for (const label of ["우선순위", "난이도", "예상", "담당자"]) {
      expect(within(headCell(label)).getByRole("button", { name: `${label} 필터` })).toBeInTheDocument();
    }
    for (const label of ["티켓", "마감", "작업"]) {
      expect(within(headCell(label)).queryByRole("button", { name: `${label} 필터` })).toBeNull();
    }
    // 머리 가로 정렬은 열 어휘가 정한다 — 제목 열(티켓)만 왼쪽이다. 예전 머리는 티켓까지 전부 가운데였다.
    expect(getComputedStyle(cells[0]).justifyContent).toBe("flex-start");
    expect(getComputedStyle(cells[1]).justifyContent).toBe("center");
    // 몸통은 표의 행이 아니라 끄는 목록이다.
    const list = screen.getByRole("list", { name: "백로그 목록" });
    expect(table.contains(list)).toBe(false);
  });

  it("🔴 빈 칸은 표와 같이 「-」와 「담당자 없음」이다", async () => {
    renderBacklog();
    const empty = await rowOf("ABC-2", "비어 있는 일");
    const texts = [...empty.querySelectorAll("span, p")].map((el) => el.textContent);
    expect(texts.filter((t) => t === "-").length).toBeGreaterThanOrEqual(4); // 우선순위 · 난이도 · 예상 · 마감
    expect(within(empty).getByText("담당자 없음")).toBeInTheDocument();
    const full = await rowsShown();
    expect(within(full).getByText("2WD")).toBeInTheDocument();
    expect(within(full).getByText("김하나")).toBeInTheDocument();
  });

  it("🔴 머리 필터와 필터 바의 칸은 같은 주소 상태다 — 머리에서 걸면 바의 칸 · 칩 · 서버 질의가 같은 값이다", async () => {
    const user = userEvent.setup();
    renderBacklog();
    await rowsShown();
    const filterButton = within(headCell("우선순위")).getByRole("button", { name: "우선순위 필터" });
    expect(filterButton).toHaveAttribute("aria-pressed", "false");
    await user.click(filterButton);
    const paper = await waitFor(() => {
      const el = document.querySelector(".MuiPopover-paper");
      expect(el).not.toBeNull();
      return el;
    });
    await user.click(within(paper).getByRole("combobox", { name: "우선순위" }));
    await user.click(await screen.findByRole("option", { name: "높음" }));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(paramsOf(here()).getAll("priority")).toEqual(["높음"]));
    await waitFor(() => expect(lastBacklog().getAll("priority")).toEqual(["높음"]));
    expect(chipTexts()).toEqual(["우선순위: 높음"]);
    // 바의 칸도 같은 값을 말한다.
    const barCell = [...document.querySelectorAll("[data-filter-bar] [data-filter-kind=enum]")]
      .find((el) => el.querySelector("[data-prefix-label]").textContent === "우선순위");
    expect(barCell.querySelector("[data-row-value]").textContent).toBe("높음");
    await waitFor(() => expect(within(headCell("우선순위")).getByRole("button", { name: "우선순위 필터" })).toHaveAttribute("aria-pressed", "true"));
  });

  it("바에서 건 조건은 머리 필터가 걸린 것으로 보인다 — 담당자 · 예상 범위", async () => {
    renderBacklog("&assignee_user_id=u-2&est_wd_min=1");
    await rowsShown();
    expect(within(headCell("담당자")).getByRole("button", { name: "담당자 필터" })).toHaveAttribute("aria-pressed", "true");
    expect(within(headCell("예상")).getByRole("button", { name: "예상 필터" })).toHaveAttribute("aria-pressed", "true");
    expect(within(headCell("난이도")).getByRole("button", { name: "난이도 필터" })).toHaveAttribute("aria-pressed", "false");
    await waitFor(() => expect(chipTexts()).toEqual(["담당자: 이두리", "예상 WD: 1 ~ …"]));
    expect(lastBacklog().get("est_wd_min")).toBe("1");
    expect(lastBacklog().getAll("assignee_user_id")).toEqual(["u-2"]);
  });

  it("「내 티켓만」이 켜져 있으면 담당자 머리 필터도 서지 않는다 — 쓰지 않는 조건이다", async () => {
    renderBacklog("&mine=1");
    await rowsShown();
    expect(within(headCell("담당자")).queryByRole("button", { name: "담당자 필터" })).toBeNull();
    expect(within(headCell("우선순위")).getByRole("button", { name: "우선순위 필터" })).toBeInTheDocument();
  });
});

describe("백로그 머리 정렬", () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockImplementation(stub); });

  it("🔴 머리를 누르면 서버 정렬을 싣고, 다시 누르면 방향이 바뀐다 — aria-sort 가 방향을 말한다", async () => {
    const user = userEvent.setup();
    renderBacklog();
    await rowsShown();
    // 기본은 끌어 옮긴 순서다 — 정렬을 싣지 않는다.
    expect(lastBacklog().get("sort")).toBeNull();
    await user.click(within(headCell("마감")).getByRole("button", { name: "마감" }));
    await waitFor(() => expect(lastBacklog().get("sort")).toBe("due_date"));
    expect(lastBacklog().get("order")).toBe("asc");
    expect(paramsOf(here()).get("sort")).toBe("due_date");
    await waitFor(() => expect(headCell("마감")).toHaveAttribute("aria-sort", "ascending"));
    expect(headCell("우선순위")).toHaveAttribute("aria-sort", "none");

    await user.click(within(headCell("마감")).getByRole("button", { name: "마감" }));
    await waitFor(() => expect(lastBacklog().get("order")).toBe("desc"));
    await waitFor(() => expect(headCell("마감")).toHaveAttribute("aria-sort", "descending"));

    // 다른 열은 그 열의 기본 방향으로 시작한다(티켓 표와 같은 규칙 — 예상 WD 는 큰 것부터).
    await user.click(within(headCell("예상")).getByRole("button", { name: "예상" }));
    await waitFor(() => expect(lastBacklog().get("sort")).toBe("est_wd"));
    expect(lastBacklog().get("order")).toBe("desc");
    await waitFor(() => expect(headCell("마감")).toHaveAttribute("aria-sort", "none"));
  });

  it("🔴 정렬해서 보는 동안에는 끌 수 없다 — 한 줄 안내, 「맨 위로/맨 아래로」 없음, 목록 끌기 꺼짐", async () => {
    const user = userEvent.setup();
    renderBacklog("&sort=priority");
    const row = await rowsShown();
    expect(await screen.findByText("정렬해서 보는 동안에는 끌어서 순서를 바꿀 수 없습니다.")).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-disabled", "true");
    await user.click(within(row).getByRole("button", { name: "ABC-1 백로그 작업" }));
    const items = (await screen.findAllByRole("menuitem")).map((m) => m.textContent);
    expect(items).toEqual(["빠른 수정"]);
    // 조건 줄에 정렬 칩이 선다 — 무엇으로 정렬했는지가 목록 위에 보인다.
    expect(chipTexts()).toEqual(["정렬: 우선순위 ↑"]);
  });

  it("기본 순서(끌어 옮긴 순서)에서는 끌 수 있고 「맨 위로/맨 아래로」가 있다", async () => {
    const user = userEvent.setup();
    renderBacklog();
    const row = await rowsShown();
    expect(row).toHaveAttribute("aria-disabled", "false");
    expect(screen.queryByText("정렬해서 보는 동안에는 끌어서 순서를 바꿀 수 없습니다.")).toBeNull();
    await user.click(within(row).getByRole("button", { name: "ABC-1 백로그 작업" }));
    const items = (await screen.findAllByRole("menuitem")).map((m) => m.textContent);
    expect(items).toEqual(["빠른 수정", "맨 위로", "맨 아래로"]);
    expect(chipTexts()).toEqual([]);
  });

  it("🔴 「기본 순서로 보기」가 끌어 옮긴 순서로 되돌린다 — 정렬을 걷고 끌기가 돌아온다", async () => {
    const user = userEvent.setup();
    renderBacklog("&sort=due_date&order=desc");
    await rowsShown();
    await waitFor(() => expect(lastBacklog().get("sort")).toBe("due_date"));
    await user.click(await screen.findByRole("button", { name: "기본 순서로 보기" }));
    await waitFor(() => expect(here()).toBe("/work-board?team=d-a&sprint=sp-a&tab=backlog"));
    await waitFor(() => expect(lastBacklog().get("sort")).toBeNull());
    expect(lastBacklog().get("order")).toBeNull();
    const row = await rowsShown();
    await waitFor(() => expect(row).toHaveAttribute("aria-disabled", "false"));
    expect(screen.queryByText("정렬해서 보는 동안에는 끌어서 순서를 바꿀 수 없습니다.")).toBeNull();
  });

  it("정렬 칩을 지워도 기본 순서로 돌아간다", async () => {
    const user = userEvent.setup();
    renderBacklog("&sort=due_date&order=desc");
    await rowsShown();
    await waitFor(() => expect(chipTexts()).toEqual(["정렬: 마감 ↓"]));
    const chip = document.querySelector("[data-filter-bar] [data-condition-chip]");
    await user.click(chip.querySelector(".MuiChip-deleteIcon"));
    await waitFor(() => expect(paramsOf(here()).get("sort")).toBeNull());
    expect(chipTexts()).toEqual([]);
  });

  it("허용표 밖의 정렬 값은 기본 순서로 읽는다 — 서버가 거절할 값을 싣지 않는다", async () => {
    renderBacklog("&sort=created_at&order=desc");
    const row = await rowsShown();
    expect(lastBacklog().get("sort")).toBeNull();
    expect(lastBacklog().get("order")).toBeNull();
    expect(row).toHaveAttribute("aria-disabled", "false");
  });
});

describe("백로그 「맨 위로」의 위치 조건", () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockImplementation(stub); });

  const moveBody = () => {
    const call = apiMock.mock.calls.find(([p, o]) => String(p).includes("/move") && o && o.method === "POST");
    return call ? call[1].body : null;
  };

  it("🔴 지금 보는 백로그의 조건을 목록 그대로 싣는다 — 여러 값 축은 목록, 범위는 수", async () => {
    const user = userEvent.setup();
    renderBacklog("&project_id=p-a&priority=%EB%86%92%EC%9D%8C&priority=%EA%B8%B4%EA%B8%89&assignee_user_id=u-1&est_wd_min=1&est_wd_max=3&signal=overdue&q=x");
    const row = await rowsShown();
    await user.click(within(row).getByRole("button", { name: "ABC-1 백로그 작업" }));
    await user.click(await screen.findByRole("menuitem", { name: "맨 위로" }));
    await waitFor(() => expect(moveBody()).not.toBeNull());
    expect(moveBody()).toEqual({
      reorder: true,
      base_version: 4,
      to_position: "top",
      position_project_id: ["p-a"],
      position_q: "x",
      position_assignee_user_id: ["u-1"],
      position_mine: false,
      position_priority: ["높음", "긴급"],
      position_difficulty: null,
      position_est_wd_min: 1,
      position_est_wd_max: 3,
      position_department_id: "d-a",
      position_signal: "overdue",
    });
  });

  it("「내 티켓만」이 켜져 있으면 담당자 조건 대신 mine 을 싣는다", async () => {
    const user = userEvent.setup();
    renderBacklog("&assignee_user_id=u-2&mine=1");
    const row = await rowsShown();
    await user.click(within(row).getByRole("button", { name: "ABC-1 백로그 작업" }));
    await user.click(await screen.findByRole("menuitem", { name: "맨 아래로" }));
    await waitFor(() => expect(moveBody()).not.toBeNull());
    expect(moveBody().to_position).toBe("bottom");
    expect(moveBody().position_mine).toBe(true);
    expect(moveBody().position_assignee_user_id).toBeNull();
  });
});

describe("백로그 「회차에 담기」 — 같은 담기는 한 번만 나간다 (P4)", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("같은 틱에 두 번 눌러도 이동 요청은 한 번이고, 담는 동안 단추가 꺼진다", async () => {
    /* 담기는 카드의 base_version 을 싣는다. 예전에는 단추가 안 꺼져 둘째 요청이 첫째가 올린 판을 모른 채 나가
       409(「다른 사람이 먼저 이 티켓을 옮겼습니다」)로 끝났다. 응답을 붙잡아 그 창을 연다. */
    const moves = [];
    apiMock.mockImplementation((path, opts) => {
      if (String(path).includes("/move") && opts && opts.method === "POST") {
        moves.push(opts.body);
        return new Promise(() => {});
      }
      return stub(path, opts);
    });
    renderBacklog();
    const row = await rowsShown();
    const add = within(row).getByRole("button", { name: "회차에 담기" });
    act(() => {
      fireEvent.click(add);
      fireEvent.click(add);
    });
    await waitFor(() => expect(moves).toHaveLength(1));
    await act(async () => {});
    expect(moves).toEqual([{ sprint_id: "sp-a", set_sprint: true, base_version: 4 }]);
    expect(within(row).getByRole("button", { name: "회차에 담기" })).toBeDisabled();
  });
});
