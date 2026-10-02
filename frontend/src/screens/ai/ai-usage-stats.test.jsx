import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI 사용 통계 — 실제 사용량 분석 (계획 A6, D-543).
 *
 * 지키는 것:
 *   1) 지표는 한 줄이다(카드가 아니다) — AI 요청 · 성공률 · 실패 · 정책 차단 · 입력 토큰 · 출력 토큰 · 평균 응답.
 *   2) 보기 기준은 조건이 아니다 — 바꾸면 표의 첫 열 이름이 바뀌고, 조건 칩 · 「필터 지우기」에 들지 않는다.
 *   3) 기간은 세그먼티드이고, 서버가 쓴 기간을 문장으로 보인다(빈 칸인데 30일을 쓰는 일이 없다). 「직접 선택」은 날짜 둘을 고른 뒤에 묻는다.
 *   4) 검색은 서버로 간다(`q`). 행을 누르면 같은 기간 · 조건의 호출 기록으로 간다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { AiUsageStats, recordsHref } from "./AiUsageStats.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const STATS = {
  items: [
    { key: "assistant.chat", label: "AI 도우미", calls: 1284, ok: 1240, errors: 31, blocked_policy: 3, blocked_quota: 10,
      success_rate: 98, input_tokens: 2_100_000, output_tokens: 640_000, avg_latency_ms: 3200, last_at: "2026-10-01T05:05:00" },
  ],
  total: 1,
  totals: { calls: 1284, ok: 1240, errors: 31, blocked_policy: 3, blocked_quota: 10, success_rate: 98,
    input_tokens: 2_100_000, output_tokens: 640_000, avg_latency_ms: 3200, last_at: "2026-10-01T05:05:00" },
  period: "30d", range_label: "기간은 9월 2일부터 10월 1일까지입니다.", from: "2026-09-02", to: "2026-10-01",
};

function renderStats(path = "/ai-usage?tab=ai-usage-stats") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <AiUsageStats />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const statsCalls = () => apiMock.mock.calls.map((c) => String(c[0])).filter((p) => p.startsWith("/api/admin/ai/usage/stats"));

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/admin/ai/usage/catalog")) {
      return Promise.resolve({ actions: [{ key: "assistant.chat", label: "AI 도우미", retired: false },
        { key: "chat.answer", label: "채팅 답변(이전 방식)", retired: true }] });
    }
    if (p.startsWith("/api/admin/ai/usage/stats")) return Promise.resolve(STATS);
    return Promise.resolve({});
  });
});

describe("AI 사용 통계 화면", () => {
  it("지표 한 줄과 서버가 쓴 기간 문장을 보인다", async () => {
    renderStats();
    await screen.findByTestId("ai-usage-range");
    const metrics = screen.getByRole("group", { name: "이 기간의 지표" });
    for (const [name, value] of [["AI 요청", "1,284"], ["성공률", "98%"], ["실패", "31"], ["정책 차단", "3"],
      ["입력 토큰", "2.1M"], ["출력 토큰", "640K"], ["평균 응답", "3.2초"]]) {
      expect(within(metrics).getByText(name)).toBeInTheDocument();
      expect(within(metrics).getByText(value)).toBeInTheDocument();
    }
    expect(screen.getByTestId("ai-usage-range")).toHaveTextContent("기간은 9월 2일부터 10월 1일까지입니다.");
    expect(statsCalls()[0]).toContain("period=30d");
  });

  it("최근 사용은 표의 날짜 · 시각 칸 규약(24시간제 압축)이다 — 긴 「오후」 형식은 11rem 칸 밖으로 넘쳤다(랩 1366)", async () => {
    renderStats();
    await screen.findByRole("columnheader", { name: /최근 사용/ });
    const row = screen.getByRole("row", { name: /AI 도우미/ });
    expect(within(row).getByText("2026-10-01 14:05")).toBeInTheDocument();
    expect(row.textContent).not.toMatch(/오후|오전/);
  });

  it("보기 기준은 조건이 아니다 — 첫 열 이름이 바뀌고 조건 칩이 생기지 않는다", async () => {
    const user = userEvent.setup();
    renderStats();
    await screen.findByRole("columnheader", { name: /기능/ });
    await user.click(screen.getByRole("tab", { name: "사용자" }));
    await waitFor(() => expect(statsCalls().some((p) => p.includes("group_by=user"))).toBe(true));
    expect(await screen.findByRole("columnheader", { name: /사용자/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /필터 지우기/ })).toBeNull();
    expect(screen.queryByText(/보기 기준:/)).toBeNull();
  });

  it("직접 선택은 날짜 둘을 고른 뒤에 묻고, 검색은 서버로 간다", async () => {
    const user = userEvent.setup();
    renderStats();
    await screen.findByRole("group", { name: "이 기간의 지표" });
    const before = statsCalls().length;
    await user.click(screen.getByRole("tab", { name: "직접 선택" }));
    expect(statsCalls().length).toBe(before);
    await user.type(screen.getByLabelText("시작"), "2026-09-10");
    await user.type(screen.getByLabelText("끝"), "2026-09-20");
    await user.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(statsCalls().some((p) => p.includes("period=custom") && p.includes("from=2026-09-10")
      && p.includes("to=2026-09-20"))).toBe(true));

    await user.type(screen.getByRole("searchbox", { name: "사용자나 기능 검색" }), "앨리스{Enter}");
    await waitFor(() => expect(statsCalls().some((p) => p.includes("q=" + encodeURIComponent("앨리스")))).toBe(true));
  });

  it("행은 같은 기간 · 조건의 호출 기록으로 간다", () => {
    const href = recordsHref({ key: "assistant.chat" }, { group_by: "action", status: "error" }, STATS);
    expect(href).toBe("#/ai-usage?tab=ai-usage-records&from=2026-09-02&to=2026-10-01&status=error&action=assistant.chat");
    const byUser = recordsHref({ key: "u-1" }, { group_by: "user" }, STATS);
    expect(byUser).toContain("user_id=u-1");
    const byDept = recordsHref({ key: "플랫폼팀" }, { group_by: "department" }, STATS);
    expect(byDept).not.toContain("플랫폼팀");
  });
});
