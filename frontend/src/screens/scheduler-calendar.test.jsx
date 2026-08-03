import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 스케줄러 캘린더 (PLAN Phase 6).
 *
 * 여기서 못박는 것:
 *   - 조회 구간을 **KST 달 경계**로 만든다. UTC 로 자르면 화면의 '8월'과 서버가 준 8월이
 *     9시간 어긋나 첫날/마지막날 실행이 통째로 빠진다.
 *   - 지난 실행과 앞으로의 예정을 **눈으로 구별**할 수 있다(색만이 아니라 표기로).
 *   - 서버가 "잘렸다"고 하면 그 사실을 숨기지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { SchedulerCalendar } from "./SchedulerCalendar.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const SCHEDULES = [{ id: "s-1", name: "매일 리포트", enabled: true, timezone: "Asia/Seoul" }];

function body(extra = {}) {
  return {
    items: [],
    start: "2026-08-01T00:00:00",
    end: "2026-08-31T00:00:00",
    truncated: false,
    schedules: SCHEDULES,
    ...extra,
  };
}

function renderCalendar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <SchedulerCalendar />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

let lastUrl = null;

beforeEach(() => {
  apiMock.mockReset();
  lastUrl = null;
  apiMock.mockImplementation((path) => { lastUrl = path; return Promise.resolve(body()); });
});

describe("실행 달력", () => {
  it("요일 머리글 7개와 6주치 칸을 그린다", async () => {
    renderCalendar();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(await screen.findByRole("grid")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader")).toHaveLength(7);
    // 6주 × 7일 = 42칸. 달을 넘길 때 높이가 튀지 않게 항상 42칸이다.
    expect(screen.getAllByRole("gridcell")).toHaveLength(42);
  });

  it("조회 구간을 start/end 로 넘기고 92일을 넘기지 않는다", async () => {
    renderCalendar();
    await waitFor(() => expect(lastUrl).toBeTruthy());
    const url = new URL("http://x" + lastUrl);
    const start = new Date(url.searchParams.get("start"));
    const end = new Date(url.searchParams.get("end"));
    expect(Number.isNaN(start.getTime())).toBe(false);
    expect(end.getTime()).toBeGreaterThan(start.getTime());
    const days = (end - start) / 86400000;
    expect(days).toBeLessThanOrEqual(92);
    // 달 경계는 KST 자정 = UTC 15:00 전날. 그래서 시각이 정각 15:00 이어야 한다.
    expect(start.getUTCHours()).toBe(15);
  });

  it("지난 실행과 앞으로의 예정을 구별해 그린다", async () => {
    const todayKst = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
    apiMock.mockImplementation((path) => {
      lastUrl = path;
      return Promise.resolve(body({
        items: [
          { kind: "run", schedule_id: "s-1", schedule_name: "매일 리포트",
            occurs_at: `${todayKst}T00:00:00`, status: "failed", run_id: "r-1", error_message: "n8n 500" },
          { kind: "planned", schedule_id: "s-1", schedule_name: "매일 리포트",
            occurs_at: `${todayKst}T02:00:00`, status: null, run_id: null, error_message: null },
        ],
      }));
    });
    renderCalendar();
    const dots = await screen.findAllByTitle(/매일 리포트/);
    expect(dots).toHaveLength(2);
    const titles = dots.map((d) => d.getAttribute("title"));
    expect(titles.some((t) => t.includes("예정"))).toBe(true);
    expect(titles.some((t) => t.includes("실패"))).toBe(true);
    // 색이 아니라 표기로도 구별된다(○ = 예정).
    expect(dots.some((d) => d.textContent.startsWith("○"))).toBe(true);
  });

  it("점을 누르면 상세가 열리고 오류 메시지를 보여 준다", async () => {
    const todayKst = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
    apiMock.mockImplementation(() => Promise.resolve(body({
      items: [{ kind: "run", schedule_id: "s-1", schedule_name: "매일 리포트",
        occurs_at: `${todayKst}T00:00:00`, status: "failed", run_id: "r-1", error_message: "n8n 500" }],
    })));
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("실행 기록");
    expect(dialog).toHaveTextContent("n8n 500");
  });

  it("서버가 잘렸다고 하면 그 사실을 숨기지 않는다", async () => {
    apiMock.mockImplementation(() => Promise.resolve(body({ truncated: true })));
    renderCalendar();
    expect(await screen.findByText(/전부 펼치지 못했습니다/)).toBeInTheDocument();
  });

  it("일정이 하나도 없으면 만들라고 안내한다", async () => {
    apiMock.mockImplementation(() => Promise.resolve(body({ schedules: [] })));
    renderCalendar();
    expect(await screen.findByText("등록된 실행 일정이 없습니다")).toBeInTheDocument();
    expect(screen.queryByRole("grid")).not.toBeInTheDocument();
  });
});
