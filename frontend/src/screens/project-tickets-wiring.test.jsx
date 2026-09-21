import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

/* 프로젝트의 티켓 탭 — 팀 티켓과 **같은 배선** (D-497 과 같은 회차).
 *
 * 이 탭은 팀 티켓 목록 부품(`ticketColumns` · `GroupedTickets`)을 그대로 쓰면서 정렬 · 머리 필터 배선만 빠져 있었다 —
 * 열은 정렬 표지 · 필터 표지를 선언하는데 눌리지 않았고, 필터 바는 「완료, 취소 포함」 한 칸짜리 줄이었다. 서버
 * (`GET /api/tickets/team` 의 `TicketListQuery`)는 정렬 · 여러 값 조건 · 범위를 이미 받는다. 지키는 것:
 *  1) 필터 바가 팀 티켓과 같은 줄이다 — 검색 → 조건 칸 → 오른쪽 끝 「완료, 취소 포함」. 프로젝트는 조건이 아니라 문맥이다.
 *  2) 머리 정렬 · 머리 필터가 서버 질의와 주소로 간다. 머리 필터로 건 조건도 칩을 가진다.
 *  3) 담당자 후보는 이 프로젝트에 닿는 사람이다.
 *  4) 티켓을 열었다 돌아오면 걸어 둔 조건 그대로다 — `from` 이 지금 주소(탭 + 조건)를 싣는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "operator", id: "u-1" } }) }));

import { ProjectTickets } from "./ProjectTickets.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const TICKETS = [{
  id: "pg-1", key: "ABC-1", title: "첫 티켓", status: "계획", priority: "높음", difficulty: "상", due: "2026-09-30",
  est_wd: 2, act_wd: null, created_at: "2026-09-01T00:00:00Z", project: "포털 개편", project_uid: "p-1",
  assignee_names: ["김하나"], assignee_people: [], assignee_user_ids: ["u-1"],
}];

function stub(path) {
  const url = String(path);
  if (url.startsWith("/api/tickets/team")) {
    return Promise.resolve({ configured: true, ok: true, items: TICKETS, tickets: TICKETS, total: 1, page: 1, page_size: 50 });
  }
  if (url.startsWith("/api/tickets/meta")) {
    return Promise.resolve({ configured: true, ok: true, statuses: ["계획", "진행"], priorities: ["높음", "보통"], difficulties: ["상", "하"] });
  }
  if (url.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [{ user_id: "u-1", display_name: "김하나" }] });
  if (url.startsWith("/api/work/statuses")) return Promise.resolve({ statuses: [{ key: "계획", label: "계획" }, { key: "진행", label: "진행 중" }] });
  return Promise.resolve({});
}

function Here() {
  const loc = useLocation();
  return <div data-testid="here">{`${loc.pathname}${loc.search}`}</div>;
}

function Landing() {
  const loc = useLocation();
  return <div data-testid="landed" data-from={(loc.state && loc.state.from) || ""}>도착</div>;
}

function renderTab(entry = "/projects/p-1?tab=tickets") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Here />
              <Routes>
                <Route path="/projects/:id" element={<ProjectTickets project={{ id: "p-1", name: "포털 개편" }} />} />
                <Route path="/tickets/:id" element={<Landing />} />
              </Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const paramsOf = (url) => new URLSearchParams(url.split("?")[1] || "");
const listCalls = () => apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith("/api/tickets/team"));
const lastList = () => paramsOf(listCalls().slice(-1)[0] || "");
const here = () => screen.getByTestId("here").textContent;

describe("프로젝트 티켓 탭 — 팀 티켓과 같은 배선", () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockImplementation(stub); });

  it("🔴 필터 바가 팀 티켓과 같은 줄이다 — 프로젝트는 조건이 아니라 이 탭의 문맥이다", async () => {
    renderTab();
    await screen.findByText("첫 티켓");
    const bar = document.querySelector("[data-filter-bar]");
    expect(bar).not.toBeNull();
    expect(within(bar).getByRole("searchbox", { name: "검색어" })).toBeInTheDocument();
    expect([...bar.querySelectorAll("[data-filter-row] [data-prefix-label]")].map((el) => el.textContent))
      .toEqual(["담당자", "대분류", "상태", "우선순위", "난이도", "기한"]);
    // 「완료, 취소 포함」은 보기 방식이라 줄의 오른쪽 끝 묶음이다.
    expect(within(bar).getByRole("button", { name: "완료, 취소 포함" })).toHaveAttribute("aria-pressed", "false");
    // 서버에는 언제나 이 프로젝트와 범위를 싣는다 — 기본 정렬이면 정렬은 싣지 않는다.
    expect(lastList().get("project_id")).toBe("p-1");
    expect(lastList().get("active")).toBe("true");
    expect(lastList().get("sort")).toBeNull();
    // 담당자 후보는 이 프로젝트에 닿는 사람이다 — 조직 전체 명부를 따로 묻지 않는다.
    const assigneeCalls = apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith("/api/tickets/assignees"));
    expect(assigneeCalls).toEqual(["/api/tickets/assignees?project_id=p-1"]);
  });

  it("🔴 머리 정렬이 서버 질의와 주소로 간다 — 탭은 그대로다", async () => {
    const user = userEvent.setup();
    renderTab();
    await screen.findByText("첫 티켓");
    await user.click(screen.getByRole("button", { name: "마감" }));
    await waitFor(() => expect(lastList().get("sort")).toBe("due_date"));
    expect(lastList().get("order")).toBe("asc");
    expect(paramsOf(here()).get("tab")).toBe("tickets");
    expect(paramsOf(here()).get("sort")).toBe("due_date");
    expect(screen.getByRole("columnheader", { name: /마감/ })).toHaveAttribute("aria-sort", "ascending");
  });

  it("🔴 머리 필터로 건 조건이 서버로 가고 조건 줄에 칩으로 선다", async () => {
    const user = userEvent.setup();
    renderTab();
    await screen.findByText("첫 티켓");
    await user.click(screen.getByRole("button", { name: "상태 필터" }));
    const paper = await waitFor(() => {
      const el = document.querySelector(".MuiPopover-paper");
      expect(el).not.toBeNull();
      return el;
    });
    await user.click(within(paper).getByRole("combobox", { name: "상태" }));
    await user.click(await screen.findByRole("option", { name: "계획" }));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(lastList().getAll("status")).toEqual(["계획"]));
    expect(paramsOf(here()).getAll("status")).toEqual(["계획"]);
    const chips = [...document.querySelectorAll("[data-filter-bar] [data-condition-chip]")].map((c) => c.textContent);
    expect(chips).toEqual(["상태: 계획"]);
  });

  it("「완료, 취소 포함」을 켜면 범위가 넓어지고, 「필터 지우기」는 범위를 건드리지 않는다", async () => {
    const user = userEvent.setup();
    renderTab("/projects/p-1?tab=tickets&q=로그");
    await screen.findByText("첫 티켓");
    await user.click(screen.getByRole("button", { name: "완료, 취소 포함" }));
    await waitFor(() => expect(lastList().get("active")).toBe("false"));
    const line = document.querySelector("[data-filter-bar] [data-condition-line]");
    await user.click(within(line).getByRole("button", { name: "필터 지우기" }));
    await waitFor(() => expect(paramsOf(here()).get("q")).toBeNull());
    expect(paramsOf(here()).get("active")).toBe("0");
    expect(lastList().get("active")).toBe("false");
  });

  it("🔴 티켓을 열었다 돌아오면 조건 그대로다 — from 이 탭과 조건을 싣는다", async () => {
    const user = userEvent.setup();
    renderTab("/projects/p-1?tab=tickets&q=로그&priority=높음");
    await user.click(await screen.findByRole("button", { name: "첫 티켓" }));
    const landed = await screen.findByTestId("landed");
    const from = landed.getAttribute("data-from");
    expect(from.startsWith("/projects/p-1?")).toBe(true);
    const back = paramsOf(from);
    expect(back.get("tab")).toBe("tickets");
    expect(back.get("q")).toBe("로그");
    expect(back.getAll("priority")).toEqual(["높음"]);
  });
});
