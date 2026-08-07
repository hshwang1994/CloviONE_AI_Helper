import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 프로젝트 주간 리포트의 AI 요약 생성(§L 소비처) — 백엔드 배선(job/handler/router)은
 * tests/integration/test_project_weekly_llm_summary.py 가 본다. 여기서는 화면이
 *
 *  1. AI 요약이 꺼져 있으면(llm_notice 있음) 버튼을 아예 안 보여준다(있는 척 안 한다).
 *  2. 버튼을 누르면 트리거 API를 부르고 "요청했다"고만 말한다(완료를 지어내지 않는다).
 *  3. 저장본이 AI 요약(source:"llm")이면 그 문장을 보여주고, 규칙 요약이면 규칙 문장을 보여준다.
 *
 * 만 확인한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "admin", id: "u-1" } }),
}));

import { ProjectWeekly } from "./ProjectWeekly.jsx";
import { ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function baseData(patch) {
  return {
    window: { start: "2026-08-03", end_exclusive: "2026-08-10", prev_week: "2026-07-27", next_week: "2026-08-10" },
    basis: { tickets_linked: true, sample_tickets: 3, sample_milestones: 1 },
    milestones: {},
    done: { count: 0, items: [] },
    in_progress: { count: 0, items: [] },
    delayed: { count: 0, items: [] },
    issues: { count: 0, items: [] },
    next_week: { count: 0, items: [] },
    summary_md: "규칙이 계산한 이번 주 요약입니다.",
    source: "rule",
    llm_summary: null,
    llm_notice: null,
    saved: null,
    ...patch,
  };
}

function query(data) {
  return { isPending: false, isError: false, data, error: null, refetch: () => {} };
}

function renderWeekly(data) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <MemoryRouter>
            <ProjectWeekly projectId="p-1" week="" onWeek={() => {}} query={query(data)} />
          </MemoryRouter>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ ok: true });
});

describe("AI 요약 생성 버튼", () => {
  it("AI 요약이 꺼져 있으면(llm_notice) 버튼이 안 보인다", () => {
    renderWeekly(baseData({ llm_notice: "AI 요약이 꺼져 있어 규칙으로 만든 요약을 보여줍니다." }));
    expect(screen.queryByRole("button", { name: "AI 요약 생성" })).not.toBeInTheDocument();
  });

  it("🔴 AI 요약이 켜져 있으면 버튼이 있고, 누르면 트리거 API를 부르고 '요청했다'고만 말한다", async () => {
    renderWeekly(baseData());
    const btn = await screen.findByRole("button", { name: "AI 요약 생성" });
    await userEvent.click(btn);
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      "/api/projects/p-1/weekly-report/llm-summary",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(await screen.findByText(/요청했습니다/)).toBeInTheDocument();
    // 완료됐다고 말하지 않는다 - 이 화면은 비동기 결과를 기다리지 않는다.
    expect(screen.queryByText(/완료되었습니다/)).not.toBeInTheDocument();
  });

  it("저장본이 AI 요약이면 그 문장을 보여준다(지금 계산한 규칙 문장이 아니라)", () => {
    renderWeekly(baseData({
      saved: { week_of: "2026-08-03", summary_md: "AI가 다듬은 문장입니다.", source: "llm", generated_at: "2026-08-03T10:00:00" },
    }));
    expect(screen.getByText("AI가 다듬은 문장입니다.")).toBeInTheDocument();
    expect(screen.queryByText("규칙이 계산한 이번 주 요약입니다.")).not.toBeInTheDocument();
    expect(screen.getByText(/AI 가 쓴 요약입니다/)).toBeInTheDocument();
  });

  it("저장본이 규칙 요약이면(또는 없으면) 지금 계산한 규칙 문장을 보여준다", () => {
    renderWeekly(baseData({
      saved: { week_of: "2026-08-03", summary_md: "지난번 저장된 규칙 문장.", source: "rule", generated_at: "2026-08-03T10:00:00" },
    }));
    expect(screen.getByText("규칙이 계산한 이번 주 요약입니다.")).toBeInTheDocument();
    expect(screen.getByText(/규칙으로 만든 요약입니다/)).toBeInTheDocument();
  });
});
