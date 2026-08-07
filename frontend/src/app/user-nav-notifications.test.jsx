import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 사용자 콘솔의 왼쪽 사이드바에도 '알림'이 있고 안 읽음 숫자가 붙는다
 * (사용자 지적: "신규 알람 하면 왼쪽 사이드바나 알림창에 뜨기로 했는데 왜 안 됨??").
 *
 * 그동안 `badge:"notifUnread"` 는 **관리자 메뉴(NAV)에만** 있었다. `USER_NAV` 에는 알림
 * 항목 자체가 없어서, 일반 사용자의 사이드바에는 붙일 자리가 아예 없었다 — 배선이 끊긴
 * 것이 아니라 항목이 없던 것이다(라우트 `/notifications` 는 UserRoutes 에 이미 있었다).
 *
 * 숫자의 출처는 서버가 계산해 주는 `badge` 다(app/notifications/router.py). 방해금지와
 * 뮤트를 이미 반영한 값이라 화면이 다시 세지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/me"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={USER_NAV} ariaLabel="사용자 메뉴" isUser showMenu>
                <div>본문</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("사용자 콘솔 사이드바의 알림", () => {
  beforeEach(() => {
    apiMock.mockReset();
    wideViewport();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/team-chat/rooms")) {
        return Promise.resolve({ items: [], global: null, unread_total: 0 });
      }
      if (path.startsWith("/api/notifications/unread-count")) {
        return Promise.resolve({ unread: 4, badge: 4, quiet: false, by_type: { ticket_assigned: 4 } });
      }
      if (path.startsWith("/api/notifications")) return Promise.resolve({ items: [], unread: 4 });
      return Promise.resolve({});
    });
  });

  it("메뉴에 '알림' 항목이 있고 안 읽음 배지 키를 선언한다", () => {
    const items = USER_NAV.flatMap((g) => g.items);
    const noti = items.find((it) => it.to === "/notifications");
    expect(noti, "USER_NAV 에 /notifications 항목이 있어야 한다").toBeTruthy();
    expect(noti.badge).toBe("notifUnread");
  });

  it("안 읽음이 있으면 사이드바에 숫자가 뜬다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByLabelText("안 읽음 4건")).toHaveTextContent("4"));
  });
});
