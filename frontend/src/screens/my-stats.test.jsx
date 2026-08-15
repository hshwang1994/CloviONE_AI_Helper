import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 내 업무량 · 완료 통계 화면 — 서버가 준 숫자를 **그대로** 말하는가.
 *
 * 화면에서 다시 집계하지 않는 것이 이 화면의 설계다(홈과 숫자가 어긋나면 둘 다 못 믿는다).
 * 그래서 여기서 확인하는 것은 계산이 아니라 '전달'과 '빈/장애 상태의 구분'이다:
 *   1) 티켓이 0건인 것과 소스가 죽은 것은 **다른 화면**이다.
 *   2) 연결이 없어서 못 세는 것도 0건이 아니다 — 이유를 말해야 사용자가 뭘 할지 안다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1" } }),
}));

import { MyStats } from "./MyStats.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function stats(over = {}) {
  return {
    ok: true,
    source: { configured: true, ok: true, mapped: true },
    today: "2026-08-03",
    totals: {
      all: 6, active: 4, done: 1, cancelled: 1, overdue: 1, due_today: 1,
      due_soon: 0, blocked: 1, no_due: 1, completion_rate: 0.2,
    },
    workload: {
      est_wd_active: 6.5, est_wd_overdue: 2, act_wd_done: 2, est_wd_done: 1.5,
      by_status: [{ name: "진행", count: 3, est_wd: 3 }, { name: "완료", count: 1, est_wd: 1.5 }],
      by_priority: [{ name: "높음", count: 2, est_wd: 2 }],
      by_week: [
        { start: "2026-08-03", end_exclusive: "2026-08-10", label: "이번 주", count: 1, est_wd: 1 },
        { start: "2026-08-10", end_exclusive: "2026-08-17", label: "다음 주", count: 1, est_wd: 3 },
        { start: "2026-08-17", end_exclusive: "2026-08-24", label: "2주 뒤", count: 0, est_wd: 0 },
        { start: "2026-08-24", end_exclusive: "2026-08-31", label: "3주 뒤", count: 0, est_wd: 0 },
      ],
      by_week_extra: {
        overdue: { count: 1, est_wd: 2 },
        later: { count: 0, est_wd: 0 },
        no_due: { count: 1, est_wd: 0.5 },
      },
    },
    months: [
      { month: "2026-06", assigned: 0, done: 0, cancelled: 0, open: 0, overdue: 0, est_wd: 0, act_wd: 0, completion_rate: null },
      { month: "2026-07", assigned: 3, done: 1, cancelled: 1, open: 1, overdue: 1, est_wd: 4.5, act_wd: 2, completion_rate: 0.5 },
      { month: "2026-08", assigned: 3, done: 0, cancelled: 0, open: 3, overdue: 0, est_wd: 4, act_wd: 0, completion_rate: 0 },
    ],
    sync: { status: "ok", last_run_at: null, last_success_at: "2026-08-03T00:57:00", ticket_count: 8, truncated: false, error: null },
    ...over,
  };
}

function renderStats() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/my-stats"]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <MyStats />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("내 업무량 · 완료 통계", () => {
  it("서버가 준 숫자를 카드에 그대로 낸다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    expect(await screen.findByText("남은 일")).toBeInTheDocument();
    expect(screen.getByText("완료율(취소 제외)")).toBeInTheDocument();
    // 20% = 서버가 준 0.2. 화면이 다시 계산하지 않는다.
    expect(screen.getByText("20%")).toBeInTheDocument();
  });

  it("SEM-02: 단독 라우트라 PageHeader가 h1이고, 5개 구역 제목이 그 바로 아래 h2다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    await screen.findByText("남은 일");

    expect(screen.getByRole("heading", { level: 1, name: "내 업무량, 완료 통계" })).toBeInTheDocument();
    const level2Names = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    for (const title of ["달별 완료 추이", "앞으로의 부하(주별)", "상태 구성", "남은 일의 우선순위", "공수(WD)"]) {
      expect(level2Names).toContain(title);
    }
    expect(level2Names).toHaveLength(5);
  });

  it("배정이 0건인 달의 완료율은 '-' 다 — 0% 가 아니다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    await screen.findByText("달별 완료 추이");
    const row = screen.getByText("2026-06").closest("tr");
    expect(row).not.toBeNull();
    expect(row.textContent).toContain("-");
    // 같은 표에서 0% 인 달(2026-08)은 실제로 0% 로 나온다 — 둘이 구분된다.
    expect(screen.getByText("2026-08").closest("tr").textContent).toContain("0%");
  });

  it("티켓이 0건이면 '없다'고 말하고 갈 곳을 준다", async () => {
    apiMock.mockResolvedValue(stats({
      totals: { all: 0, active: 0, done: 0, cancelled: 0, overdue: 0, due_today: 0, due_soon: 0, blocked: 0, no_due: 0, completion_rate: null },
    }));
    renderStats();
    expect(await screen.findByText("아직 집계할 티켓이 없습니다")).toBeInTheDocument();
    expect(screen.getByText("내 티켓으로")).toBeInTheDocument();
  });

  it("연결이 없으면 0건이 아니라 '연결이 없다'고 말한다", async () => {
    apiMock.mockResolvedValue(stats({ source: { configured: true, ok: true, mapped: false } }));
    renderStats();
    expect(await screen.findByText(/Notion 사용자와 연결되어 있지 않아/)).toBeInTheDocument();
  });

  /* WF1 R4 — 위 시험은 totals를 안 바꿔 항상 6건이라, 연결이 없는 계정이 실제로도
   * 거의 항상 함께 겪는 "담당 티켓 0건" 조합을 재현하지 않았다(그래서 이 결함을
   * 가리고 있었다). 그 조합에서는 배너("계정 연결을 요청하세요")와 빈 상태("담당
   * 티켓이 하나도 없어서" + "내 티켓으로")가 서로 다른 원인을 말했고, CTA가 데려가는
   * /my-tickets도 같은 이유(연결 안 됨)로 똑같이 비어 있는 막다른 길이었다. */
  it("연결이 없고 0건이면, 빈 상태가 배너와 같은 원인을 말하고 막다른 CTA를 안 준다", async () => {
    apiMock.mockResolvedValue(stats({
      source: { configured: true, ok: true, mapped: false },
      totals: { all: 0, active: 0, done: 0, cancelled: 0, overdue: 0, due_today: 0, due_soon: 0, blocked: 0, no_due: 0, completion_rate: null },
    }));
    renderStats();
    expect(await screen.findByText(/Notion 사용자와 연결되어 있지 않아/)).toBeInTheDocument();
    expect(await screen.findByText("아직 집계할 티켓이 없습니다")).toBeInTheDocument();
    // 옛 문구("담당인 티켓이 하나도 없어서")와 그 CTA("내 티켓으로")는 이 조합에서 안 보인다 —
    // 배너가 이미 말한 원인(연결 안 됨)을 빈 상태가 반복하거나, 못 고치는 CTA를 주지 않는다.
    expect(screen.queryByText(/담당인 티켓이 하나도 없어서/)).not.toBeInTheDocument();
    expect(screen.queryByText("내 티켓으로")).not.toBeInTheDocument();
  });

  it("소스가 미설정이면 그 사실을 말한다", async () => {
    apiMock.mockResolvedValue(stats({
      source: { configured: false, ok: false, mapped: true, message: "Notion 연동이 설정되지 않았습니다." },
    }));
    renderStats();
    expect(await screen.findByText("Notion 연동이 설정되지 않았습니다.")).toBeInTheDocument();
  });

  it("조회 자체가 실패하면 다시 시도할 길을 준다", async () => {
    apiMock.mockRejectedValue(Object.assign(new Error("서버 오류"), { status: 500 }));
    renderStats();
    expect(await screen.findByText("불러오지 못했습니다")).toBeInTheDocument();
  });

  it("기간을 바꾸면 그 값으로 다시 조회한다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    await screen.findByText("남은 일");
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/me/stats?months=6&weeks=4"));
  });

  it("미러 동기화 상태는 raw 영문(idle/running/ok/error, app/tickets/models.py) 대신 한국어로 보여준다", async () => {
    apiMock.mockResolvedValue(stats({
      sync: { status: "error", last_run_at: null, last_success_at: "2026-08-03T00:57:00", ticket_count: 8, truncated: false, error: "boom" },
    }));
    renderStats();
    await screen.findByText("남은 일");
    expect(screen.queryByText(/티켓 미러 상태:\s*error/)).not.toBeInTheDocument();
    expect(screen.getByText(/티켓 미러 상태:\s*오류/)).toBeInTheDocument();
  });
});
