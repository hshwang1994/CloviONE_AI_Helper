import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "../ui/kit.jsx";

/* 팀 티켓 동기화(FN-03) — 고아였던 POST /api/tickets/sync 의 화면 호출부.
 *
 * 2026-08 재설계(지시 1 · 29): 정상 동작을 매번 알리는 상시 배너를 없앴다. 안내는 **조치가
 * 필요할 때만** 나오고(실패 / 한 번도 성공 못 함), 평상시 수동 동기화는 화면 머리의 넘침
 * 메뉴에 있다. 기능·권한·API 는 그대로다 — 자리만 바뀐다.
 *
 *  1. 미러가 정상이면 아무 안내도 안 그린다(예전엔 "마지막 동기화: …"가 상시로 떴다).
 *  2. 실패했으면 무엇을 보고 있는지 알린다. 권한이 없으면 안내만 뜨고 복구 버튼은 없다.
 *  3. can_sync:true 면 머리 넘침 메뉴로 POST /api/tickets/sync 를 부르고 성공 토스트를 띄운다.
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

describe("팀 티켓 — 동기화 (FN-03)", () => {
  it("서버가 sync 블록을 안 주면 안내를 그리지 않는다", async () => {
    mockTeam({ sync: null, can_sync: false });
    renderTeamTickets();
    await screen.findByText("서버 점검");
    expect(screen.queryByText(/동기화/)).toBeNull();
  });

  it("미러가 정상이면 아무 안내도 안 그린다 (지시 1)", async () => {
    mockTeam({ sync: { status: "ok", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" }, can_sync: false });
    renderTeamTickets();
    await screen.findByText("서버 점검");
    // 예전에는 여기에 "마지막 동기화: 2026. 8. 9. …, 티켓 5개"가 상시로 떴다.
    expect(screen.queryByText(/마지막 동기화/)).toBeNull();
    expect(screen.queryByText(/마지막 정상 데이터/)).toBeNull();
  });

  it("실패했는데 권한이 없으면 안내만 뜨고 복구 버튼은 없다", async () => {
    mockTeam({ sync: { status: "error", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" }, can_sync: false });
    renderTeamTickets();
    expect(await screen.findByText(/마지막 정상 데이터를 보고 있습니다/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "지금 동기화" })).toBeNull();
  });

  it("한 번도 동기화되지 않았으면 '0건'과 구분해 말한다 (UB-26)", async () => {
    mockTeam({ sync: { status: "ok", ticket_count: 0, last_success_at: null }, can_sync: false });
    renderTeamTickets();
    expect(await screen.findByText(/아직 한 번도 동기화되지 않았습니다/)).toBeInTheDocument();
  });

  it("can_sync:true 면 머리 넘침 메뉴에서 동기화를 요청하고 성공 토스트를 띄운다", async () => {
    const user = userEvent.setup();
    mockTeam({
      sync: { status: "ok", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" },
      can_sync: true,
      syncResult: { sync: { status: "ok", ticket_count: 9 } },
    });
    renderTeamTickets();
    await user.click(await screen.findByRole("button", { name: "팀 티켓 더 보기" }));
    await user.click(await screen.findByRole("menuitem", { name: "지금 동기화" }));

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
    await user.click(await screen.findByRole("button", { name: "팀 티켓 더 보기" }));
    await user.click(await screen.findByRole("menuitem", { name: "지금 동기화" }));

    expect(await screen.findByText(/동기화 실패: Notion 연결 실패/)).toBeInTheDocument();
  });
});
