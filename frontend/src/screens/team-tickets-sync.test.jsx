import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "../ui/kit.jsx";

/* 팀 티켓 동기화 배너(FN-03) — 고아였던 POST /api/tickets/sync 에 처음 생긴 화면 호출부.
 *
 *  1. 서버가 sync 블록을 안 주면(폴백 없는 경로) 배너를 안 그린다.
 *  2. can_sync:false 면 배너는 뜨되 버튼은 없다(팀 안내는 필요, 동작은 권한 없음).
 *  3. can_sync:true 면 버튼이 뜨고, 누르면 POST /api/tickets/sync 를 부르고 성공 토스트를 띄운다.
 *  4. 동기화 응답 status:"error" 면 실패 토스트를 띄운다(성공한 척 안 한다).
 *
 * 네트워크·타이머 없음: api는 mock. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "operator", id: "op-1" } }),
}));

import { TeamTickets } from "./TeamTickets.jsx";

const ROWS = [
  { id: "t-1", tid: 1, title: "서버 점검", status: "진행", assignee_names: ["동료"] },
];

function mockTeam(payload) {
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    if (p.startsWith("/api/tickets/sync")) return Promise.resolve(payload.syncResult || { sync: { status: "ok", ticket_count: 3, last_success_at: "2026-08-10T00:00:00Z" } });
    if (p.startsWith("/api/tickets/team")) {
      return Promise.resolve({
        configured: true, ok: true, items: ROWS, total: ROWS.length, page: 1, page_size: 20,
        sync: payload.sync, can_sync: payload.can_sync,
      });
    }
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
});

function renderTeamTickets() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/team-tickets"]}>
          <TeamTickets />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("팀 티켓 — 동기화 배너 (FN-03)", () => {
  it("서버가 sync 블록을 안 주면 배너를 그리지 않는다", async () => {
    mockTeam({ sync: null, can_sync: false });
    renderTeamTickets();
    await screen.findByText("서버 점검");
    expect(screen.queryByText(/마지막 동기화/)).toBeNull();
  });

  it("can_sync:false 면 안내는 뜨지만 버튼은 없다", async () => {
    mockTeam({ sync: { status: "ok", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" }, can_sync: false });
    renderTeamTickets();
    expect(await screen.findByText(/마지막 동기화/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "지금 동기화" })).toBeNull();
  });

  it("can_sync:true 면 버튼을 누르면 동기화를 요청하고 성공 토스트를 띄운다", async () => {
    const user = userEvent.setup();
    mockTeam({
      sync: { status: "ok", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" },
      can_sync: true,
      syncResult: { sync: { status: "ok", ticket_count: 9 } },
    });
    renderTeamTickets();
    const btn = await screen.findByRole("button", { name: "지금 동기화" });
    await user.click(btn);

    expect(await screen.findByText(/동기화했습니다. 티켓 9개/)).toBeInTheDocument();
    const calledSync = apiMock.mock.calls.some(([p, opts]) => String(p).startsWith("/api/tickets/sync") && opts && opts.method === "POST");
    expect(calledSync).toBe(true);
  });

  it("동기화 응답이 실패면 실패 토스트를 띄운다(성공한 척 안 한다)", async () => {
    const user = userEvent.setup();
    mockTeam({
      sync: { status: "ok", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" },
      can_sync: true,
      syncResult: { sync: { status: "error", error: "Notion 연결 실패" } },
    });
    renderTeamTickets();
    const btn = await screen.findByRole("button", { name: "지금 동기화" });
    await user.click(btn);

    expect(await screen.findByText(/동기화 실패: Notion 연결 실패/)).toBeInTheDocument();
  });
});
