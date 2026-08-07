import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 팀(사용자) 알림과 관리자 알림을 한 벨에서도 구분한다 (0051).
 *
 * 원인: `Notification` 에는 자유 텍스트 `type` 만 있고 "누구를 위한 것인가"(audience)가
 * 없어, 관리자이자 사용자인 사람의 알림 벨에는 자기 티켓 배정 알림과 백업 실패 같은 운영
 * 알림이 구분 없이 섞여 나왔다. 서버가 이제 각 알림에 `audience: "user"|"admin"` 을
 * 실어 준다(app/notifications/router.py `_view`) — 벨은 완전히 숨기지 않고 그룹 헤더로
 * 구분한다("관리" / "내 업무").
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "admin", id: "u1" } }) }));

import { NotificationBell } from "./NotificationBell.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function noti(overrides = {}) {
  return {
    id: "n1", type: "ticket_assigned", title: "티켓 배정", audience: "user",
    body: null, read_at: null,
    related_object_type: null, related_object_id: null, related_route: null,
    created_at: "2026-08-07T01:00:00",
    ...overrides,
  };
}

function mount(items, { isUser } = {}) {
  apiMock.mockImplementation((url) => {
    if (url.startsWith("/api/notifications/unread-count")) return Promise.resolve({ unread: items.length });
    if (url.startsWith("/api/notifications?")) return Promise.resolve({ items, total: items.length, unread: items.length, page: 1, page_size: 8 });
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/me"]}>
              <NotificationBell isUser={isUser} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

async function openBell(user) {
  await waitFor(() => expect(apiMock).toHaveBeenCalled());
  await user.click(screen.getByRole("button", { name: /알림/ }));
}

beforeEach(() => { apiMock.mockReset(); });

describe("알림 벨의 관리/내 업무 구분", () => {
  it("두 audience가 섞이면 그룹 헤더 둘 다 뜬다", async () => {
    const user = userEvent.setup();
    mount([
      noti({ id: "n1", title: "티켓 배정", audience: "user" }),
      noti({ id: "n2", title: "백업 실패", type: "backup_failed", audience: "admin" }),
    ], { isUser: false });
    await openBell(user);

    expect(await screen.findByText("관리")).toBeInTheDocument();
    expect(screen.getByText("내 업무")).toBeInTheDocument();
  });

  it("관리자 콘솔(isUser=false)에서는 관리 알림이 먼저 온다", async () => {
    const user = userEvent.setup();
    mount([
      noti({ id: "n1", title: "티켓 배정", audience: "user" }),
      noti({ id: "n2", title: "백업 실패", type: "backup_failed", audience: "admin" }),
    ], { isUser: false });
    await openBell(user);

    const body = document.querySelector(".noti-pop-body");
    const text = within(body).getByText("관리").compareDocumentPosition(within(body).getByText("내 업무"));
    // "관리" 헤더가 "내 업무" 헤더보다 문서 순서상 앞에 온다(DOCUMENT_POSITION_FOLLOWING = 4).
    // eslint-disable-next-line no-bitwise
    expect(text & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("사용자 콘솔(isUser=true)에서는 내 업무 알림이 먼저 온다", async () => {
    const user = userEvent.setup();
    mount([
      noti({ id: "n1", title: "백업 실패", type: "backup_failed", audience: "admin" }),
      noti({ id: "n2", title: "티켓 배정", audience: "user" }),
    ], { isUser: true });
    await openBell(user);

    const body = document.querySelector(".noti-pop-body");
    const rel = within(body).getByText("내 업무").compareDocumentPosition(within(body).getByText("관리"));
    // eslint-disable-next-line no-bitwise
    expect(rel & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("한 audience뿐이면 그룹 헤더를 그리지 않는다 — 불필요한 소음을 더하지 않는다", async () => {
    const user = userEvent.setup();
    mount([
      noti({ id: "n1", title: "티켓 배정 1", audience: "user" }),
      noti({ id: "n2", title: "티켓 배정 2", audience: "user" }),
    ], { isUser: true });
    await openBell(user);

    await screen.findByText("티켓 배정 1");
    expect(screen.queryByText("내 업무")).toBeNull();
    expect(screen.queryByText("관리")).toBeNull();
  });

  it("audience가 없는(옛 캐시) 항목은 '내 업무'로 안전하게 취급한다", async () => {
    const user = userEvent.setup();
    mount([
      noti({ id: "n1", title: "옛 알림", audience: undefined }),
      noti({ id: "n2", title: "백업 실패", type: "backup_failed", audience: "admin" }),
    ], { isUser: true });
    await openBell(user);

    expect(await screen.findByText("내 업무")).toBeInTheDocument();
    expect(screen.getByText("관리")).toBeInTheDocument();
  });
});
