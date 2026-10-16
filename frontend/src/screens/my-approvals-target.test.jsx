import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 승인 표의 「대상」 칸은 사람 말이다 (r23 #28).
 *
 * 예전 칸은 서버의 내부 종류 키와 id 를 그대로 붙였다 — 「user user-01」 · 「integration integration-04」 · 「schedule schedule-06」.
 * 이제 서버가 요청에 실은 이름(역할 변경은 `target_name`, 외부 연동은 `config.name`, 실행 일정은 `definition.name`)을 쓰고, 이름이
 * 없으면 종류 낱말만 쓴다. 원래 id 는 칸의 툴팁(`title`)에 남는다. 결재 확인 문장도 같은 함수를 쓴다(`approvalTargetText`).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../ui/celebrate.js", () => ({ celebrateIfCleared: () => {}, celebrateIfCompleted: () => {} }));

import { MyApprovals, approvalTargetText } from "./MyApprovals.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROWS = [
  { id: "A1", request_type: "user.role_change", status: "pending", object_type: "user", object_id: "user-01",
    requested_at: "2026-08-24T01:00:00", requester_name: "박민준", request_payload: { role: "admin", target_name: "김지훈" } },
  { id: "A2", request_type: "integration.change_config", status: "pending", object_type: "integration", object_id: "integration-04",
    requested_at: "2026-08-24T02:00:00", requester_name: "최유나", request_payload: { config: { name: "사내 Jira" }, before: {} } },
  { id: "A3", request_type: "schedule.enable", status: "pending", object_type: "schedule", object_id: "schedule-06",
    requested_at: "2026-08-24T03:00:00", requester_name: "김지훈", request_payload: { definition: { name: "야간 백업" } } },
  { id: "A4", request_type: "schedule.enable", status: "pending", object_type: "schedule", object_id: "schedule-07",
    requested_at: "2026-08-24T04:00:00", requester_name: "이서연", request_payload: {} },
];

function mount(rows) {
  apiMock.mockImplementation(() => Promise.resolve({ items: rows, total: rows.length, page: 1, page_size: 20, can_decide: true }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/my-approvals"]}>
          <Routes><Route path="/my-approvals" element={<MyApprovals />} /></Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("승인 표의 대상 칸", () => {
  it("서버가 실은 이름을 쓰고, 이름이 없으면 종류 낱말만 쓴다", () => {
    expect(approvalTargetText(ROWS[0])).toBe("김지훈");
    expect(approvalTargetText(ROWS[1])).toBe("사내 Jira");
    expect(approvalTargetText(ROWS[2])).toBe("야간 백업");
    expect(approvalTargetText(ROWS[3])).toBe("실행 일정");
    expect(approvalTargetText({ object_type: null, request_payload: {} })).toBe("");
  });

  it("표에 내부 종류 키와 id 가 보이지 않고, id 는 툴팁에 남는다", async () => {
    mount(ROWS);
    expect(await screen.findByText("사내 Jira")).toBeInTheDocument();
    expect(screen.getByText("야간 백업")).toBeInTheDocument();
    expect(screen.queryByText(/integration integration-04/)).toBeNull();
    expect(screen.queryByText(/user user-01/)).toBeNull();
    expect(screen.getByText("실행 일정")).toHaveAttribute("title", "schedule schedule-07");
  });
});
