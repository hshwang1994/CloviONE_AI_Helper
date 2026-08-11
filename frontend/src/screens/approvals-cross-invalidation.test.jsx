import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* WF7(whole-product 재감사, L축 — 화면 간 반영): 승인 실행기 5종(app/approvals/service.py
 * APPROVAL_EXECUTORS)이 각각 users/integrations/runners/schedules/documents 중 하나를
 * 실제로 바꾼다. data-screen/crossScreenKeys.js에 "approvals" 매핑이 없어서, 승인 화면과
 * 그 대상 화면이 다른 탭에 함께 열려 있으면(관리 콘솔에서 흔한 사용 패턴) 대상 화면은 자기
 * 폴링/재마운트 전까지 옛 값을 계속 보여줬다 — jobs -> dashboard와 같은 부류의 결함
 * (schedules-calendar-cross-invalidation.test.jsx와 동일 기법으로 확인한다).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
  AuthProvider: ({ children }) => children,
}));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

describe("승인 화면 -> 대상 화면(users/integrations/runners/schedules/documents) 캐시", () => {
  const APPROVALS_CONFIG = {
    key: "approvals",
    title: "승인",
    endpoint: "/api/admin/approvals",
    columns: [{ key: "request_type", label: "유형" }],
    detailFields: [],
    actions: [
      { label: "승인", when: (r) => r.status === "pending",
        path: (r) => "/api/admin/approvals/" + r.id + "/approve" },
    ],
  };

  const TARGET_KEYS = [
    ["users"], ["integrations"], ["runners"], ["schedules"], ["documents"],
  ];

  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue({
      items: [{ id: "a-1", request_type: "user.role_change", status: "pending" }],
      page: 1, page_size: 20, total: 1,
    });
  });

  function renderScreen(qc) {
    return render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <MemoryRouter><DataScreen config={APPROVALS_CONFIG} /></MemoryRouter>
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>,
    );
  }

  it("승인 하나로 다섯 대상 화면 캐시가 전부 무효화된다(어느 유형인지 다시 안 가린다 — jobs->dashboard와 같은 판단)", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 대상 화면들이 이미 값을 들고 있는 상태를 만든다 — 그래야 '무효화됐다'가 뜻을 가진다.
    for (const key of TARGET_KEYS) {
      qc.setQueryData(key, { items: [] });
      expect(qc.getQueryState(key).isInvalidated, key.join(".")).toBe(false);
    }

    renderScreen(qc);
    await screen.findByText("user.role_change");
    apiMock.mockResolvedValueOnce({ ok: true });

    fireEvent.click(screen.getByText("user.role_change"));
    fireEvent.click(await screen.findByRole("button", { name: "승인" }));

    await waitFor(() => {
      for (const key of TARGET_KEYS) {
        expect(qc.getQueryState(key).isInvalidated, key.join(".")).toBe(true);
      }
    }, { timeout: 3000 });
  });
});
