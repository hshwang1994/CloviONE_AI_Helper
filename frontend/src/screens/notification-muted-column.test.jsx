/* 알림 목록의 '뮤트 유형' 열 (RG-03).
 *
 * 서버는 각 알림이 사용자가 뮤트한 유형인지(muted) 이미 내려주고 있었다(app/notifications/
 * router.py::_view) — "목록에서 빼지 않고 표시만 한다"는 그 필드 자체의 존재 이유가 화면에
 * 안 보이면 성립하지 않는다: 뮤트해 놓고도 계속 알림이 온다고만 보이지, 왜 오는지는 알 길이
 * 없었다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u-1" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { NOTIFICATIONS_SCREEN } from "./registry/notifications.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROWS = [
  { id: "n-1", title: "뮤트된 유형 알림", type: "chat_mention", read_at: null, body: "", related_object_type: null, created_at: "2026-08-10T00:00:00Z", muted: true },
  { id: "n-2", title: "보통 알림", type: "approval_requested", read_at: null, body: "", related_object_type: null, created_at: "2026-08-10T00:00:00Z", muted: false },
];

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/notifications")) return Promise.resolve({ items: ROWS, page: 1, page_size: 20, total: 2, unread: 2 });
    return Promise.resolve({});
  });
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><DataScreen config={NOTIFICATIONS_SCREEN.notifications} /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("알림 목록 — 뮤트 유형 열 (RG-03)", () => {
  it("뮤트한 유형의 알림에는 '뮤트된 유형' 배지가 보인다", async () => {
    renderScreen();
    const row = (await screen.findByText("뮤트된 유형 알림")).closest("tr");
    expect(within(row).getByText("뮤트된 유형")).toBeInTheDocument();
  });

  it("뮤트 안 한 유형은 배지 없이 '-'만 보인다(뮤트 상태를 지어내지 않는다)", async () => {
    renderScreen();
    const row = (await screen.findByText("보통 알림")).closest("tr");
    expect(within(row).queryByText("뮤트된 유형")).toBeNull();
  });
});
