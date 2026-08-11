import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 알림 벨의 딥링크 — 서버가 계산한 목적지(related_route)를 따른다.
 *
 * 목적지 매핑의 **출처는 서버의 표 하나**다(app/notifications/destinations.py 의
 * RELATED_DESTINATIONS). 예전엔 이 지식이 벨의 OBJ_ROUTE/OBJ_ID_PARAM 과 registry.js 에
 * 흩어져 있어, 새 유형이 생길 때마다 프런트에 if 가 한 줄씩 늘고 서로 어긋났다.
 *
 * 특히 채팅 초대는 **일반 사용자(role=user)에게 간다**. 벨의 기존 게이트는 '일반 사용자는
 * 아무 항목도 못 누른다'였다 — 관리자 화면으로만 가는 폴백 표 때문이었지, 딥링크 일반
 * 금지가 아니었다. 그 게이트가 채팅 초대까지 막으면 알림이 알려주기만 하고 데려다주지 못한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { NotificationBell } from "./NotificationBell.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROOM_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7";

function noti(overrides = {}) {
  return {
    id: "n1", type: "chat_invited", title: "홍길동님이 대화에 초대했습니다.",
    body: null, read_at: null,
    related_object_type: "chat_room", related_object_id: ROOM_ID,
    related_route: `/chat-rooms/${ROOM_ID}`,
    created_at: "2026-08-03T01:00:00",
    ...overrides,
  };
}

function mount(items) {
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
              <Routes>
                <Route path="/me" element={<NotificationBell isUser />} />
                <Route path="/chat-rooms/:id" element={<div>채팅방 화면</div>} />
              </Routes>
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

describe("채팅 초대 알림 딥링크", () => {
  it("일반 사용자도 눌러서 그 채팅방으로 이동한다", async () => {
    const user = userEvent.setup();
    mount([noti()]);
    await openBell(user);

    const row = await screen.findByRole("button", { name: /채팅 초대/ });
    await user.click(row);

    expect(await screen.findByText("채팅방 화면")).toBeInTheDocument();
  });

  it("한국어 유형 라벨을 쓴다 — raw enum(chat_invited)이 새지 않는다", async () => {
    const user = userEvent.setup();
    mount([noti()]);
    await openBell(user);
    expect(await screen.findByText("채팅 초대")).toBeInTheDocument();
    expect(screen.queryByText("chat_invited")).toBeNull();
  });

  it("누르면 읽음 처리도 함께 나간다", async () => {
    const user = userEvent.setup();
    mount([noti()]);
    await openBell(user);
    await user.click(await screen.findByRole("button", { name: /채팅 초대/ }));
    await waitFor(() =>
      expect(apiMock.mock.calls.some((c) => c[0] === "/api/notifications/n1/read")).toBe(true)
    );
  });

  it("목적지가 없는(related_route=null) 알림은 아무 데도 데려가지 않는다", async () => {
    const user = userEvent.setup();
    mount([noti({
      id: "n2", type: "maintenance_announcement", title: "8월 3일 정기 점검 안내",
      related_object_type: null, related_object_id: null, related_route: null,
    })]);
    await openBell(user);
    const row = await screen.findByText("8월 3일 정기 점검 안내");
    await user.click(row);
    // 화면이 그대로다 — 없는 목적지로 튀지 않는다.
    expect(screen.queryByText("채팅방 화면")).toBeNull();
  });

  it("서버가 앱 밖 주소를 줘도 따라가지 않는다 — 상대 경로만 받는다", async () => {
    const user = userEvent.setup();
    mount([noti({ related_route: "//evil.example/steal" })]);
    await openBell(user);
    await screen.findByText("채팅 초대");
    // 화면이 이동하지 않는다(팝오버가 그대로 열려 있다).
    expect(screen.queryByText("채팅방 화면")).toBeNull();
  });
});

/* APPR-01 회귀 방지 — 서버가 related_route를 계산해 준다고 그 화면의 실제 접근 권한이
 * 달라지는 게 아니다. job_failed는 그 작업을 만든 사람(이 파일 전체가 고정한 role="user"
 * 포함)에게 가는데 /jobs는 operator+ 전용이라, srvRoute만 보고 무조건 눌리게 하면 일반
 * 사용자에게 늘 403인 클릭 가능한 링크가 생긴다 — RG-02 커밋 직후 발견해 같은 커밋에서
 * 고쳤다(NotificationBell.jsx의 ROUTE_ROLES를 서버 경로에도 적용). */
describe("관리 콘솔 대상 알림 — 서버 값이 있어도 role이 안 맞으면 눌리지 않는다 (APPR-01 회귀 방지)", () => {
  it("job_failed(일반 사용자에게 감) — 서버가 related_route를 줘도 이동 버튼이 안 뜬다", async () => {
    const user = userEvent.setup();
    mount([noti({
      id: "n3", type: "job_failed", title: "요청 처리에 실패했습니다",
      related_object_type: "job", related_object_id: "j-1", related_route: "/jobs?job_id=j-1",
    })]);
    await openBell(user);
    // 항목 자체는 여전히 보인다(정적으로) — 이동 가능한 항목이라면 아래 버튼 쿼리가 잡는
    // <button title="관련 항목 보기">로 그려졌을 것이다(role="user"에겐 눌러도 403일 뿐이다).
    await screen.findByText("요청 처리에 실패했습니다");
    expect(screen.queryByRole("button", { name: /작업 실패/ })).toBeNull();
  });

  it("account_locked(user 유형, 관리자 전용) — 일반 사용자에겐 여전히 정적 항목이다", async () => {
    const user = userEvent.setup();
    mount([noti({
      id: "n4", type: "account_locked", title: "계정 잠금 발생: someone@goodmit.co.kr",
      related_object_type: "user", related_object_id: "u-9", related_route: "/users?id=u-9",
    })]);
    await openBell(user);
    await screen.findByText("계정 잠금 발생: someone@goodmit.co.kr");
    expect(screen.queryByRole("button", { name: /계정 잠금/ })).toBeNull();
  });
});
