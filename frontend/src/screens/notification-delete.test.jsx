/* 알림 삭제 액션(FN-03) — 고아였던 DELETE /api/notifications/{id} 에 처음 생긴 화면 호출부.
 *
 * 실제 registry 설정(registry/notifications.js)을 그대로 쓴다 — 여기서만 흉내 낸 설정을 쓰면
 * roles를 잘못 붙이는 실수(소유권 기반 삭제인데 역할로 숨기는, FN-03이 실제로 겪을 뻔한 회귀)를
 * 이 테스트가 못 잡는다.
 *
 *  1) role과 무관하게(일반 사용자 포함) "삭제" 버튼이 보인다 — 백엔드가 소유권으로만 막는다.
 *  2) 누르면 확인 문구가 먼저 뜬다.
 *  3) 확인하면 DELETE를 부르고, 목록에서 사라지며, 벨 배지/팝오버 캐시까지 함께 무효화된다
 *     (다른 알림 액션과 같은 CROSS_SCREEN_KEYS 배선).
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

let authRole = "user";
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: authRole, id: "u-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { NOTIFICATIONS_SCREEN } from "./registry/notifications.js";
import { NOTI_UNREAD, notiListKey } from "../app/notification-keys.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROW = { id: "n-1", title: "내 알림", type: "generic", read_at: null, body: "본문", related_object_type: null, created_at: "2026-08-10T00:00:00Z" };

function mockApi() {
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    if (opts && opts.method === "DELETE" && p === "/api/notifications/n-1") return Promise.resolve({ ok: true });
    if (p.startsWith("/api/notifications")) return Promise.resolve({ items: [ROW], page: 1, page_size: 20, total: 1, unread: 1 });
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
  authRole = "user";
  mockApi();
});

function renderScreen(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><DataScreen config={NOTIFICATIONS_SCREEN.notifications} /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

async function openRow(text) {
  const cell = await screen.findByText(text);
  await userEvent.click(within(cell.closest("tr")).getByRole("button", { name: /상세/ }));
  return screen.findByRole("dialog");
}

describe("알림 — 삭제 액션 (FN-03)", () => {
  it("일반 사용자에게도 삭제 버튼이 보인다(소유권 기반, role 게이트 없음)", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderScreen(qc);
    const drawer = await openRow("내 알림");
    expect(within(drawer).getByRole("button", { name: "삭제" })).toBeInTheDocument();
  });

  it("삭제를 확인하면 DELETE를 부르고 목록에서 사라지며 벨/팝오버 캐시까지 무효화한다", async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(NOTI_UNREAD, { unread: 1, badge: 1, by_type: {} });
    qc.setQueryData(notiListKey("unread"), { items: [ROW] });

    renderScreen(qc);
    const drawer = await openRow("내 알림");
    await user.click(within(drawer).getByRole("button", { name: "삭제" }));

    const confirmDialog = await screen.findByRole("dialog", { name: "확인" });
    expect(within(confirmDialog).getByText(/삭제할까요/)).toBeInTheDocument();
    await user.click(within(confirmDialog).getByRole("button", { name: "삭제" }));

    await waitFor(() => {
      const called = apiMock.mock.calls.some(([p, opts]) => p === "/api/notifications/n-1" && opts && opts.method === "DELETE");
      expect(called, "DELETE 호출").toBe(true);
    });
    await waitFor(() => expect(qc.getQueryState(NOTI_UNREAD).isInvalidated, "벨 배지").toBe(true));
    expect(qc.getQueryState(notiListKey("unread")).isInvalidated, "팝오버 목록").toBe(true);
  });
});
