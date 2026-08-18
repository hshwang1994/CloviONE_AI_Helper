import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 팀(사용자) 알림과 관리자 알림은 **서버가 갈라서** 준다 (0051 → 0060).
 *
 * 0051 의 원인 진단은 그대로다: `Notification` 에 "누구를 위한 것인가"(audience)가 없어,
 * 관리자이자 사용자인 사람의 벨에 자기 티켓 배정과 백업 실패가 구분 없이 섞였다.
 *
 * 0051 의 **처방**은 한 벨이 둘을 다 받아 정렬로 구분하는 것이었다(지금 콘솔의 audience 를
 * 앞에 모으고 섞였을 때만 그룹 헤더). 0060 에서 그것을 바꾼다:
 *
 *   * 사용자 알림과 관리자 알림은 **경로부터 다른 화면**이다(`/notifications` vs
 *     `/admin-notifications`) — 섞어서 정렬하는 것과 애초에 안 섞는 것은 다른 일이다.
 *   * 무엇보다 **배지 숫자**가 갈라져야 한다. 섞어 두면 관리자 사이드바의 "관리 알림 3"이
 *     실제로는 개인 알림 2건을 포함한 숫자가 되어, 눌러 봐야 3건이 아니다.
 *
 * 그래서 벨은 자기 콘솔의 audience 만 서버에 묻는다. 이 파일이 그 계약을 고정한다.
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

/** 서버 대역 — **audience 파라미터를 실제로 보고** 그에 맞는 것만 돌려준다.
 *  화면에서 거르는 것이 아니라 서버가 거르는 것이 계약이므로, 대역도 그렇게 굴어야
 *  "화면이 몰래 필터링해서 통과하는" 가짜 초록을 만들지 않는다. */
function mount(itemsByAudience, { isUser } = {}) {
  const seen = [];
  apiMock.mockImplementation((url) => {
    seen.push(url);
    const audience = /audience=(\w+)/.exec(url)?.[1];
    const items = itemsByAudience[audience] || [];
    if (url.startsWith("/api/notifications/unread-count")) {
      return Promise.resolve({ unread: items.length, badge: items.length });
    }
    if (url.startsWith("/api/notifications?")) {
      return Promise.resolve({
        items, total: items.length, unread: items.length, page: 1, page_size: 8,
      });
    }
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const view = render(
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
  return { ...view, seen };
}

async function openBell(user) {
  await waitFor(() => expect(apiMock).toHaveBeenCalled());
  await user.click(screen.getByRole("button", { name: /알림/ }));
}

beforeEach(() => { apiMock.mockReset(); });

describe("알림 벨 — 콘솔별로 서버가 갈라서 준다", () => {
  it("관리자 콘솔(isUser=false)의 벨은 관리자 알림만 묻고 개인 알림은 아예 안 받는다", async () => {
    const user = userEvent.setup();
    const { seen } = mount({
      user: [noti({ id: "n1", title: "티켓 배정", audience: "user" })],
      admin: [noti({ id: "n2", title: "백업 실패", type: "backup_failed", audience: "admin" })],
    }, { isUser: false });
    await openBell(user);

    // '백업 실패' 는 유형 라벨과 제목 두 군데에 나온다 — 개수가 아니라 존재만 본다.
    expect((await screen.findAllByText("백업 실패")).length).toBeGreaterThan(0);
    expect(screen.queryByText("티켓 배정")).toBeNull();
    expect(seen.every((u) => u.includes("audience=admin"))).toBe(true);
  });

  it("사용자 콘솔(isUser=true)의 벨은 개인 알림만 묻는다", async () => {
    const user = userEvent.setup();
    const { seen } = mount({
      user: [noti({ id: "n1", title: "티켓 배정", audience: "user" })],
      admin: [noti({ id: "n2", title: "백업 실패", type: "backup_failed", audience: "admin" })],
    }, { isUser: true });
    await openBell(user);

    expect((await screen.findAllByText("티켓 배정")).length).toBeGreaterThan(0);
    expect(screen.queryByText("백업 실패")).toBeNull();
    expect(seen.every((u) => u.includes("audience=user"))).toBe(true);
  });

  it("배지 숫자도 콘솔별로 갈라진다 — 섞이면 '관리 알림 N'이 실제 N이 아니다", async () => {
    const user = userEvent.setup();
    mount({
      user: [noti({ id: "u1" }), noti({ id: "u2" }), noti({ id: "u3" })],
      admin: [noti({ id: "a1", type: "backup_failed", audience: "admin" })],
    }, { isUser: false });

    // 관리자 콘솔의 벨은 1건만 센다(개인 알림 3건은 이 숫자에 안 들어간다).
    expect(await screen.findByText("1")).toBeInTheDocument();
    await openBell(user);
    expect(screen.queryByText("3")).toBeNull();
  });

  it("그룹 헤더는 더 이상 그리지 않는다 — 섞이지 않으니 구분할 것이 없다", async () => {
    const user = userEvent.setup();
    mount({
      user: [noti({ id: "n1", title: "티켓 배정 1" }), noti({ id: "n2", title: "티켓 배정 2" })],
      admin: [],
    }, { isUser: true });
    await openBell(user);

    await screen.findByText("티켓 배정 1");
    expect(screen.queryByText("내 업무")).toBeNull();
    expect(screen.queryByText("관리")).toBeNull();
  });
});
