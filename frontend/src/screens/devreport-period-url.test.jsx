import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 개발자 월간 리포트가 보고 있는 달은 **주소에** 있다 (audit-10).
 *
 * 실측: 월 드롭다운을 3월로 바꾸면 요청은 `period=2026-03` 으로 나가고 표 제목도 3월인데,
 * 주소는 `#/dev-report` 그대로였다. 새로고침하면 다시 9월을 받았고, 「3월 리포트 좀 봐 달라」고
 * 링크를 건네는 일이 아예 안 됐다. 같은 상태에서 화면 위 설명문은 어떤 달을 골라도
 * 「마감일이 이번 달인 티켓을…」이라고 말했다 — 지금 보고 있는 달과 어긋난 문장이다.
 *
 * 관리자 콘솔의 다른 목록 화면은 이미 조건을 주소에 싣는다(S15 · `lib/useQueryState.js`).
 * 이 화면만 컴포넌트 지역 상태였다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }) }));

import { DevReport, periodLabel } from "./DevReport.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const EMPTY_TEAM = {
  total: 0, done: 0, in_progress: 0, verify: 0, plan: 0, cancel: 0,
  overdue: 0, est_done_total: 0, est_all_total: 0,
};

let asked = [];

function AddressProbe() {
  const loc = useLocation();
  return <div data-testid="addr">{loc.pathname + loc.search}</div>;
}

function renderReport(entry = "/dev-report") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[entry]}>
          <AddressProbe />
          <Routes><Route path="/dev-report" element={<DevReport />} /></Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
}

const addr = () => screen.getByTestId("addr").textContent;

beforeEach(() => {
  asked = [];
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    asked.push(p);
    const period = new URLSearchParams(p.slice(p.indexOf("?") + 1)).get("period");
    return Promise.resolve({ ok: true, period, configured: true, developers: [], team: EMPTY_TEAM, unassigned: { total: 0 } });
  });
});

describe("periodLabel — 화면 설명이 지금 보고 있는 달을 그대로 말한다", () => {
  it("'YYYY-MM' 을 사람이 읽는 달로 바꾼다", () => {
    expect(periodLabel("2026-03")).toBe("2026년 3월");
    expect(periodLabel("2026-11")).toBe("2026년 11월");
  });

  it("반례 — 모양이 다르면 지어내지 않고 원문을 그대로 둔다", () => {
    expect(periodLabel("")).toBe("");
    expect(periodLabel(null)).toBe("");
    expect(periodLabel("2026")).toBe("2026");
  });
});

describe("개발자 월간 리포트 — 고른 달이 주소에 실린다", () => {
  it("주소에 달이 있으면 그 달을 받는다(새로고침·링크 공유가 같은 화면을 연다)", async () => {
    renderReport("/dev-report?period=2026-03");
    await waitFor(() => expect(asked.length).toBeGreaterThan(0));
    expect(asked[0]).toContain("period=2026-03");
    expect(await screen.findByText(/마감일이 2026년 3월인 티켓을/)).toBeInTheDocument();
  });

  it("월을 바꾸면 주소가 따라오고 설명문도 그 달을 말한다", async () => {
    const user = userEvent.setup();
    renderReport("/dev-report?period=2026-03");
    await screen.findByText(/마감일이 2026년 3월인 티켓을/);

    await user.click(screen.getByLabelText("월"));
    await user.click(await screen.findByRole("option", { name: "5월" }));

    await waitFor(() => expect(addr()).toContain("period=2026-05"));
    await waitFor(() => expect(asked.some((u) => u.includes("period=2026-05"))).toBe(true));
    expect(await screen.findByText(/마감일이 2026년 5월인 티켓을/)).toBeInTheDocument();
  });

  it("반례 — 아무것도 안 고른 주소는 깨끗하게 두고 이번 달을 받는다", async () => {
    renderReport("/dev-report");
    await waitFor(() => expect(asked.length).toBeGreaterThan(0));
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    expect(asked[0]).toContain("period=" + month);
    expect(addr()).toBe("/dev-report");
  });
});
