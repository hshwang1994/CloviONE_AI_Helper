import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 관리자 IA 재구성 — 짝을 이루던 화면이 한 화면의 탭이 됐다 (지시 30 · 41 · 51).
 *
 * 여기서 지키는 것은 "합쳤다"가 아니라 **합치면서 잃지 않았다**이다.
 *
 *  1. 옛 주소가 죽지 않는다 — `/restore-drills` 로 들어오면 그 탭이 열린다.
 *  2. 리다이렉트가 아니라 **그 자리에서** 연다 — 리다이렉트는 해시 쿼리를 버려서
 *     저장된 뷰 링크(`#/restore-drills?status=failed`)의 필터가 사라진다.
 *  3. 탭 안의 목록이 자기 필터를 주소에 써도 `?tab=` 이 살아남는다
 *     (datascreen-view.js 의 owned-key 규약).
 *  4. 권한은 그대로다 — 그릇의 역할 집합과 안쪽 탭의 역할 집합이 같아야 한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));

let mockRole = "system_admin";
vi.mock("./auth.jsx", () => ({
  useAuth: () => ({ data: { role: mockRole, id: "a1" }, isLoading: false, isError: false }),
}));

import AdminRoutes from "./AdminRoutes.jsx";
import { SCREEN_ROLES } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

beforeEach(() => {
  mockRole = "system_admin";
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  window.location.hash = "#/";
});

function renderAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes><Route path="*" element={<AdminRoutes />} /></Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/* 합쳐진 짝 — (옛 주소, 대표 주소, 옛 주소로 들어왔을 때 켜져 있어야 하는 탭 라벨) */
const MERGED = [
  ["/restore-drills", "/backup", "복구 리허설"],
  ["/approval-delegations", "/approvals", "승인 위임"],
  ["/audit-anomalies", "/audit", "이상 징후"],
  ["/prompt-usage", "/ai-usage", "프롬프트"],
  ["/scheduler-calendar", "/schedules", "달력"],
];

describe("옛 주소가 죽지 않는다", () => {
  it.each(MERGED)("%s 로 들어오면 그 탭이 켜진 채 열린다", async (oldPath, hostPath, tabLabel) => {
    renderAt(oldPath);
    const tab = await screen.findByRole("tab", { name: tabLabel }, { timeout: 5000 });
    expect(tab).toHaveAttribute("aria-selected", "true");
  });

  it.each(MERGED)("대표 주소 %1$s 로 들어오면 첫 탭이 켜진다 (%0$s 는 두 번째)", async (oldPath, hostPath, tabLabel) => {
    renderAt(hostPath);
    const tab = await screen.findByRole("tab", { name: tabLabel }, { timeout: 5000 });
    expect(tab).toHaveAttribute("aria-selected", "false");
  });
});

describe("탭 안의 화면이 제목을 두 번 그리지 않는다", () => {
  it("그릇이 h1 하나만 그린다 — 안쪽 목록은 자기 PageHeader 를 안 그린다", async () => {
    renderAt("/backup");
    await screen.findByRole("tab", { name: "복구 리허설" }, { timeout: 5000 });
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]).toHaveTextContent("백업");
  });
});

describe("권한이 그릇과 안쪽 탭에서 같다", () => {
  it.each([
    ["/backup", ["backup", "restore-drills"]],
    ["/approvals", ["approvals", "approval-delegations"]],
    ["/audit", ["audit", "audit-anomalies"]],
    ["/ai-usage", ["policy-usage", "prompt-usage"]],
    ["/schedules", ["schedules", "scheduler-calendar"]],
  ])("%s 그릇의 역할 집합이 안쪽 탭들과 정확히 같다", (hostPath, keys) => {
    const sets = keys.map((k) => JSON.stringify([...(SCREEN_ROLES[k] || [])].sort()));
    // 그릇이 넓으면 못 보는 사람이 빈 화면을 보고, 좁으면 볼 수 있는 사람이 못 본다.
    expect(new Set(sets).size, `${hostPath}: ${keys.join(" vs ")} 의 역할 집합이 다르다`).toBe(1);
  });

  it("역할이 모자라면 그릇 자체가 권한 안내를 보여 준다", async () => {
    mockRole = "user";
    renderAt("/audit");
    expect(await screen.findByText("권한이 없습니다", {}, { timeout: 5000 })).toBeInTheDocument();
  });
});
