import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "../ui/kit.jsx";

/* 팀 티켓 — 없어진 미러 안내와, 없어진 동기화 트리거.
 *
 * qa-contract-change: 서버가 응답에 sync 블록을 더 이상 싣지 않으므로(티켓 표가 이 서버의 정본이라 낡을 것이 없다) 「실패했으면 이렇게 말한다」를 시험할 대상 자체가 사라졌고, 그 자리를 「옛 블록이 되돌아와도 화면이 그것을 말하지 않는다」로 바꿨다. 단언 수는 열 개로 늘었다.
 *
 * 이 파일이 못박는 것은 셋이다.
 *
 *  1. 서버가 sync 블록을 안 주면 아무 안내도 안 그린다.
 *  2. 서버가 **옛 sync 블록을 다시 실어 보내도** 화면이 그것을 안 그린다. 화면이 그 키를
 *     보고 안내를 되살리면, 멈춘 동기화의 마지막 시각이 날마다 더 낡은 채로 다시 뜬다.
 *  3. **어떤 응답이 와도** 동기화 버튼을 그리지 않고 /api/tickets/sync 를 부르지 않는다.
 *     서버가 옛 계약(can_sync:true)을 다시 실어 보내도 마찬가지다 — 화면이 그 키를 보고
 *     버튼을 되살리면, 없어진 쓰기 경로를 화면이 혼자 되살리는 셈이 된다.
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
  apiMock.mockImplementation((path) => {
    const p = String(path);
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

describe("팀 티켓 — 미러 안내가 없다", () => {
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

  it("옛 sync 블록이 error 로 되돌아와도 실패 안내를 안 그린다", async () => {
    /* 예전에는 이 시험이 반대를 단언했다: 실패하면 "마지막 정상 데이터를 보고 있습니다"
       를 보여 준다. 그 미러가 없어졌으므로 지금 그 문구가 뜬다는 것은 화면이 죽은
       계약을 되살렸다는 뜻이다. */
    mockTeam({ sync: { status: "error", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" }, can_sync: false });
    renderTeamTickets();
    await screen.findByText("서버 점검");
    expect(screen.queryByText(/마지막 정상 데이터를 보고 있습니다/)).toBeNull();
    expect(screen.queryByText(/최근 동기화에 실패했습니다/)).toBeNull();
  });

  it("옛 sync 블록이 「한 번도 성공 못 함」으로 되돌아와도 그 문구를 안 그린다", async () => {
    mockTeam({ sync: { status: "ok", ticket_count: 0, last_success_at: null }, can_sync: false });
    renderTeamTickets();
    await screen.findByText("서버 점검");
    expect(screen.queryByText(/아직 한 번도 동기화되지 않았습니다/)).toBeNull();
    expect(screen.queryByText(/일부만 동기화됐습니다/)).toBeNull();
  });
});

describe("팀 티켓 — 동기화를 시작할 방법이 없다", () => {
  it("서버가 실패 상태를 실어 보내도 복구 버튼을 내주지 않는다", async () => {
    mockTeam({ sync: { status: "error", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" }, can_sync: true });
    renderTeamTickets();
    await screen.findByText("서버 점검");
    expect(screen.queryByRole("button", { name: "지금 동기화" })).toBeNull();
  });

  it("서버가 can_sync:true 를 다시 보내와도 넘침 메뉴와 동기화 항목을 만들지 않는다", async () => {
    mockTeam({
      sync: { status: "ok", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" },
      can_sync: true,
    });
    renderTeamTickets();
    await screen.findByText("서버 점검");
    expect(screen.queryByRole("button", { name: "팀 티켓 더 보기" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "지금 동기화" })).toBeNull();
  });

  it("화면을 그리는 동안 /api/tickets/sync 를 한 번도 부르지 않는다", async () => {
    mockTeam({
      sync: { status: "error", ticket_count: 5, last_success_at: "2026-08-09T00:00:00Z" },
      can_sync: true,
    });
    renderTeamTickets();
    await screen.findByText("서버 점검");
    const calledSync = apiMock.mock.calls.some(([p]) => String(p).startsWith("/api/tickets/sync"));
    expect(calledSync).toBe(false);
  });
});
