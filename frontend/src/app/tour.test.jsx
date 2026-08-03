import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 첫 로그인 둘러보기 — **건너뛴 사람에게 다시 뜨지 않는다**를 화면 층에서 고정한다.
 *
 * 판정은 서버(GET /api/me/preferences 의 tour.show)가 한다. 브라우저 저장소에 두면
 * 다른 PC·시크릿 창에서 다시 뜬다 — "껐는데 또 나온다"는 화면을 못 믿게 만드는 가장 빠른 길이다.
 * 그래서 여기서는 (1) show=true 면 뜨고 (2) 건너뛰면 서버에 skip 을 보내고 즉시 닫히며
 * (3) show=false 면 아예 안 뜨고 (4) 홈이 아니면 안 뜬다 를 각각 확인한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("./auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1", display_name: "나" } }),
}));

import { Tour, TOUR_STEPS } from "./Tour.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function prefs(show) {
  return {
    avatar: { url: null, updated_at: null },
    notifications: { muted_types: [], catalog: [], unmutable: [] },
    dnd: { enabled: false, until: null, quiet_hours_enabled: false, quiet_start: "22:00", quiet_end: "08:00", quiet_now: false, reason: null, max_minutes: 1440 },
    tour: { version: 1, seen_version: show ? 0 : 1, show, skipped: false, completed_at: null },
  };
}

function renderTour(path = "/me") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Tour />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("첫 로그인 둘러보기", () => {
  it("서버가 show=true 라고 하면 홈에서 뜬다", async () => {
    apiMock.mockResolvedValue(prefs(true));
    renderTour();
    expect(await screen.findByText(TOUR_STEPS[0].title)).toBeInTheDocument();
  });

  it("서버가 show=false 라고 하면 뜨지 않는다 — 이미 봤거나 건너뛴 사람이다", async () => {
    apiMock.mockResolvedValue(prefs(false));
    renderTour();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByText(TOUR_STEPS[0].title)).toBeNull();
  });

  it("홈이 아니면 자동으로 열지 않는다 — 하려던 일을 모달로 끊지 않는다", async () => {
    apiMock.mockResolvedValue(prefs(true));
    renderTour("/my-tickets");
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByText(TOUR_STEPS[0].title)).toBeNull();
  });

  it("건너뛰면 즉시 닫히고 서버에 skip 을 보낸다", async () => {
    apiMock.mockImplementation((path, options) => {
      if (path === "/api/me/tour") return Promise.resolve(prefs(false));
      return Promise.resolve(prefs(true));
    });
    renderTour();
    expect(await screen.findByText(TOUR_STEPS[0].title)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "건너뛰기" }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith("/api/me/tour", {
        method: "POST", body: { action: "skip" },
      })
    );
    // 서버 응답을 기다리지 않고 화면에서 먼저 사라진다 — 기다리면 '닫기가 안 눌린다'로 보인다.
    await waitFor(() => expect(screen.queryByText(TOUR_STEPS[0].title)).toBeNull());
  });

  it("마지막 단계까지 가면 complete 로 기록한다", async () => {
    apiMock.mockImplementation((path) => Promise.resolve(prefs(path !== "/api/me/tour")));
    renderTour();
    expect(await screen.findByText(TOUR_STEPS[0].title)).toBeInTheDocument();

    for (let i = 0; i < TOUR_STEPS.length - 1; i += 1) {
      await userEvent.click(screen.getByRole("button", { name: "다음" }));
    }
    await userEvent.click(screen.getByRole("button", { name: "시작하기" }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith("/api/me/tour", {
        method: "POST", body: { action: "complete" },
      })
    );
  });

  it("설정 조회가 실패해도 조용히 안 뜬다 — 오류 모달로 첫 화면을 덮지 않는다", async () => {
    apiMock.mockRejectedValue(Object.assign(new Error("서버 오류"), { status: 500 }));
    renderTour();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByText(TOUR_STEPS[0].title)).toBeNull();
  });
});
