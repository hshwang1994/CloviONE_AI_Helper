import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* VIS-59 — 로그인/로그아웃이 같은 대상 ID로 수십 행씩 연속돼, 실제로 봐야 할 사건
 * (실패·설정 변경 등)이 그 사이에 묻힌다. `action` 필터(정확 일치, 하나만 골라 좁힘)와는
 * 반대 방향이 필요해서 `exclude_actions`를 별도로 뒀다 — 이것만 빼고 전부 보여준다.
 * 서버는 이미 이 조건을 받는다(app/audit/router.py `_filtered_stmt`, 목록과 CSV 내보내기가
 * 같은 질의를 쓴다). 여기서는 화면에 실제로 필터가 있고, 고르면 서버 조회에 실제로
 * 실리는지를 확인한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "auditor", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderAudit() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/me/views")) return Promise.resolve({ items: [] });
    return Promise.resolve({ items: [], total: 0, page: 1, page_size: 100 });
  });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY.audit} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function auditCalls() {
  return apiMock.mock.calls.map((c) => c[0]).filter((p) => p.startsWith("/api/admin/audit"));
}

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "#/audit";
});
afterEach(() => { window.location.hash = ""; });

describe("감사 로그 — 로그인/로그아웃 제외 필터 (VIS-59)", () => {
  it("화면에 '표시 범위' 필터가 있다", async () => {
    renderAudit();
    expect(await screen.findByLabelText(/표시 범위/)).toBeInTheDocument();
  });

  it("'로그인/로그아웃 제외'를 고르면 서버 조회에 exclude_actions가 실린다", async () => {
    const user = userEvent.setup();
    renderAudit();
    await screen.findByLabelText(/표시 범위/);

    await user.click(screen.getByRole("combobox", { name: "표시 범위" }));
    await user.click(await screen.findByRole("option", { name: "로그인/로그아웃 제외" }));

    await waitFor(() => {
      const calls = auditCalls();
      expect(calls.length).toBeGreaterThan(0);
      expect(calls.some((url) => url.includes("exclude_actions=user.login%2Cuser.logout")
        || url.includes("exclude_actions=user.login,user.logout"))).toBe(true);
    });
  });

  it("CSV 내보내기 버튼도 같은 exclude_actions 조건을 그대로 싣는다(목록과 다른 데이터를 받으면 안 된다)", () => {
    const action = REGISTRY.audit.headerActions.find((a) => a.label === "CSV 내보내기");
    expect(action).toBeTruthy();
    const href = action.download("exclude_actions=user.login%2Cuser.logout&page=2");
    expect(href).toContain("exclude_actions=user.login%2Cuser.logout");
    expect(href).not.toContain("page=2");  // page/page_size는 내보내기 의미와 안 맞아 뺀다(기존 규약)
  });
});
