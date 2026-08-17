import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 회귀: 실행 일정 DataScreen(#/schedules)과 실행 달력(SchedulerCalendar.jsx,
 * #/scheduler-calendar)은 같은 스케줄/실행 자료를 두 가지 보기로 보여준다 —
 * data-screen/crossScreenKeys.js에 "schedules" 매핑이 없어서 어느 쪽에서 상태를 바꿔도
 * 다른 쪽 캐시는 그대로 낡아 있었다(CROSS_SCREEN_KEYS의 다른 항목들, 예: jobs -> dashboard와
 * 같은 부류의 결함). 양방향을 각각 확인한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
// 두 화면 모두 useAuth()를 쓴다(DataScreen의 역할 게이트, SchedulerCalendar의 OPS_ROLES 게이트) —
// cross-screen-invalidation.test.jsx와 같은 방식으로 고정 역할을 준다. 실제 로그인 왕복
// (/api/me, AuthProvider)은 이 회귀와 무관하다.
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
  AuthProvider: ({ children }) => children,
}));

import { DataScreen } from "./DataScreen.jsx";
import { SchedulerCalendar } from "./SchedulerCalendar.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { AuthProvider } from "../app/auth.jsx"; // 위 mock의 통과용(passthrough) 컴포넌트

describe("실행 일정 DataScreen -> 실행 달력 캐시", () => {
  const SCHEDULES_CONFIG = {
    key: "schedules",
    title: "실행 일정",
    endpoint: "/api/admin/schedules",
    columns: [{ key: "name", label: "이름" }],
    detailFields: [],
    actions: [
      { label: "지금 실행", when: (r) => r.enabled,
        path: (r) => "/api/admin/schedules/" + r.id + "/run-now" },
    ],
  };

  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue({ items: [{ id: "s-1", name: "매일 리포트", enabled: true }], page: 1, page_size: 20, total: 1 });
  });

  function renderScreen(qc) {
    return render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <MemoryRouter><DataScreen config={SCHEDULES_CONFIG} /></MemoryRouter>
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>,
    );
  }

  it("스케줄 화면의 '지금 실행'이 실행 달력 캐시(['scheduler-calendar'])까지 무효화한다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 달력이 이미 값을 들고 있는 상태를 만든다 — 그래야 '무효화됐다'가 뜻을 가진다.
    qc.setQueryData(["scheduler-calendar", 2026, 7, ""], { items: [] });
    expect(qc.getQueryState(["scheduler-calendar", 2026, 7, ""]).isInvalidated).toBe(false);

    renderScreen(qc);
    await screen.findByText("매일 리포트");
    apiMock.mockResolvedValueOnce({ ok: true });

    fireEvent.click(screen.getByText("매일 리포트"));
    fireEvent.click(await screen.findByRole("button", { name: "지금 실행" }));

    await waitFor(() => {
      expect(qc.getQueryState(["scheduler-calendar", 2026, 7, ""]).isInvalidated, "실행 달력").toBe(true);
    }, { timeout: 3000 });
  });
});

describe("실행 달력 -> 실행 일정 DataScreen 캐시", () => {
  const SCHEDULES = [{ id: "s-1", name: "매일 리포트", enabled: true, timezone: "Asia/Seoul" }];
  const todayKst = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());

  function body(extra = {}) {
    return {
      items: [{ kind: "run", schedule_id: "s-1", schedule_name: "매일 리포트",
        occurs_at: `${todayKst}T00:00:00`, status: "failed", run_id: "r-1", error_message: "n8n 500" }],
      start: "2026-08-01T00:00:00", end: "2026-08-31T00:00:00", truncated: false,
      schedules: SCHEDULES, ...extra,
    };
  }

  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path, opts) => {
      if (path.startsWith("/api/admin/schedules/runs/")) return Promise.resolve({ ok: true, run: { id: "r-1", status: "queued" } });
      return Promise.resolve(body());
    });
  });

  function renderCalendar(qc) {
    return render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <ThemeModeProvider>
            <ToastProvider>
              <ConfirmProvider>
                <MemoryRouter>
                  <SchedulerCalendar />
                </MemoryRouter>
              </ConfirmProvider>
            </ToastProvider>
          </ThemeModeProvider>
        </AuthProvider>
      </QueryClientProvider>,
    );
  }

  it("달력에서 실패한 실행을 재시도하면 실행 일정 DataScreen 캐시(['schedules'])까지 무효화한다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["schedules", "", 0, "{}"], { items: [] });
    expect(qc.getQueryState(["schedules", "", 0, "{}"]).isInvalidated).toBe(false);

    renderCalendar(qc);
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    await screen.findByRole("dialog");
    const retryBtn = await screen.findByRole("button", { name: "재시도" });
    await userEvent.click(retryBtn);
    const buttons = await screen.findAllByRole("button", { name: "재시도" });
    await userEvent.click(buttons[buttons.length - 1]);

    await waitFor(() => {
      expect(qc.getQueryState(["schedules", "", 0, "{}"]).isInvalidated, "실행 일정 화면").toBe(true);
    }, { timeout: 3000 });
  });
});
