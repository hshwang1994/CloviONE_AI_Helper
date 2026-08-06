/* 목록에서 읽음 처리하면 **상단 벨도 같이** 갱신된다 (X10).
 *
 * 예전에는 알림 화면이 자기 키(`[config.key]`)만 무효화했고, 벨은 다른 키(`["noti-unread"]`)로
 * 60초 폴링했다 — '모두 읽음' 을 눌러도 **최대 1분 동안 벨이 옛 숫자**를 들고 있었다.
 * 코드 주석이 이 결함을 예고해 놓고 그대로 남아 있었다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const CONFIG = {
  key: "notifications",
  title: "알림",
  endpoint: "/api/notifications",
  paginated: true,
  columns: [{ key: "title", label: "제목" }],
  detailFields: [],
  headerActions: [
    { key: "read-all", label: "모두 읽음", path: () => "/api/notifications/read-all",
      method: "POST" },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [{ id: "n1", title: "알림 하나" }], page: 1, page_size: 20, total: 1 });
});

function renderScreen(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><DataScreen config={CONFIG} /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("화면 밖 값 갱신", () => {
  it("알림 화면의 작업이 벨의 캐시(noti-unread)까지 무효화한다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, "invalidateQueries");
    renderScreen(qc);
    await screen.findByText("알림 하나");

    fireEvent.click(screen.getByRole("button", { name: "모두 읽음" }));

    await waitFor(() => {
      const keys = spy.mock.calls.map((c) => JSON.stringify(c[0] && c[0].queryKey));
      expect(keys).toContain(JSON.stringify(["noti-unread"]));
    }, { timeout: 3000 });
  });
});
