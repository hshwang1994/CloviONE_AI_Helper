import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 실행 달력의 ARIA grid 계층 (접근성 감사 3).
 *
 * role="grid" 는 role 계층이 강제다: grid > row > (columnheader | gridcell).
 * 행이 없으면 스크린리더의 표 탐색이 아예 동작하지 않아 **날짜 이동이 안 된다** -
 * 격자를 그려 놓고 격자로 못 읽는 상태였다.
 *
 * 하나만 넣고 끝내지 않기 위해, 여기서는 셀·머리글이 **각각 행에 속하는지**까지 본다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { SchedulerCalendar } from "./SchedulerCalendar.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { AuthProvider } from "../app/auth.jsx";

const SCHEDULES = [{ id: "s-1", name: "매일 리포트", enabled: true, timezone: "Asia/Seoul" }];
// SchedulerCalendar가 재시도 버튼의 역할 게이트에 useAuth()를 쓰므로(M9), AuthProvider가
// 마운트되며 부르는 `/api/me`도 이 목이 함께 감당한다.
const ME = { user: { id: "u-1", role: "operator" }, csrf_token: "t", features: {}, branding: {} };

function renderCalendar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path === "/api/me") return Promise.resolve(ME);
    return Promise.resolve({
      items: [], start: "2026-08-01T00:00:00", end: "2026-08-31T00:00:00",
      truncated: false, schedules: SCHEDULES,
    });
  });
});

describe("실행 달력의 격자 구조", () => {
  it("머리글 한 줄과 여섯 주가 각각 row 다", async () => {
    renderCalendar();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    const grid = await screen.findByRole("grid");
    expect(grid).toBeInTheDocument();
    // 머리글 1 + 6주 = 7행. 달을 넘겨도 높이가 튀지 않게 항상 6주를 그린다.
    expect(screen.getAllByRole("row")).toHaveLength(7);
  });

  it("모든 gridcell 이 row 안에 있다", async () => {
    renderCalendar();
    const grid = await screen.findByRole("grid");
    const cells = screen.getAllByRole("gridcell");
    expect(cells).toHaveLength(42);
    cells.forEach((cell) => {
      const row = cell.closest('[role="row"]');
      expect(row).not.toBeNull();
      expect(row.closest('[role="grid"]')).toBe(grid);
    });
  });

  it("모든 columnheader 가 같은 한 row 안에 있다", async () => {
    renderCalendar();
    await screen.findByRole("grid");
    const heads = screen.getAllByRole("columnheader");
    expect(heads).toHaveLength(7);
    const rows = heads.map((h) => h.closest('[role="row"]'));
    rows.forEach((row) => expect(row).not.toBeNull());
    expect(new Set(rows).size).toBe(1);
  });

  it("행 상자는 레이아웃을 먹지 않는다(display: contents)", async () => {
    // 의미(row)를 넣느라 배치가 바뀌면 안 된다 — 평범한 블록으로 두면 일곱 칸이 바깥 격자의
    // 열이 아니라 행 안에서 다시 배치돼 달력이 세로 일곱 줄로 무너진다.
    renderCalendar();
    await screen.findByRole("grid");
    screen.getAllByRole("row").forEach((row) => {
      expect(window.getComputedStyle(row).display).toBe("contents");
    });
  });

  it("한 주는 일곱 칸이다", async () => {
    renderCalendar();
    await screen.findByRole("grid");
    const weekRows = screen.getAllByRole("row").filter((r) => r.querySelector('[role="gridcell"]'));
    expect(weekRows).toHaveLength(6);
    weekRows.forEach((r) => expect(r.querySelectorAll('[role="gridcell"]')).toHaveLength(7));
  });
});
