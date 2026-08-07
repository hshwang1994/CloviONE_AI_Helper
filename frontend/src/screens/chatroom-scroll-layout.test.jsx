import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 채팅방 페이지의 스크롤·헤더 정합성 회귀 테스트.
 *
 * 사용자 지적: 대화창이 이중 스크롤 때문에 위로 올라가 보이고, 방 목록과 대화창의
 * 구분선이 안 맞는다.
 *
 * 원인: ChatRoom.jsx 가 MemberStrip + ChatPane 을 감싸는 Box 에 overflowY:"auto" 를 걸어
 * 두고 있었는데, 그 그릇은 flex 구조가 아니었다. ChatPane 은 스스로 맨 아래로 스크롤하는
 * 자기 완결형 컴포넌트라 그 안에 이미 overflowY:auto 로그 상자가 있다 — 두 겹의 overflowY:auto
 * 가 생기면 안쪽은 이미 맨 아래로 스크롤돼 있는데 바깥 그릇은 scrollTop:0 에서 시작해
 * 대화가 "위로 밀려 보이는" 것처럼 됐다(중첩 스크롤).
 *
 * 또한 방 목록(제목줄 + 검색줄, 2행 헤더)과 대화창(1행 헤더)의 헤더 높이가 달라 두 칸의
 * 경계선(헤더와 본문 사이 구분선)이 나란히 읽히지 않았다.
 *
 * 여기서 고정하는 것:
 *  1. 화면에 overflowY:auto 를 만드는 요소가 ChatPane 자신의 로그 상자, 딱 하나뿐이다.
 *  2. 대화창 헤더 제목줄 아래에 목록의 검색줄과 같은 치수의 빈 자리가 있어 총 헤더 높이가
 *     같아진다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { RoomDetailPanel } from "./ChatRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function payload() {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "우리방", member_count: 2 },
    members: [
      { user_id: "u1", name: "나", online: true, last_read_seq: 1 },
      { user_id: "u2", name: "동료", online: false, last_read_seq: 1 },
    ],
    messages: [
      { seq: 1, kind: "text", sender_user_id: "u2", sender_name: "동료",
        body: "안녕하세요", created_at: "2026-08-07T09:00:00", images: [] },
    ],
    seq: 1,
    people: {},
    you: { user_id: "u1", role: "member", last_read_seq: 1, is_member: true,
           can_disband: false, can_hide: false },
  };
}

function mount() {
  apiMock.mockImplementation((url) => {
    if (String(url).startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(payload());
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/chat-rooms/r1"]}>
              <Routes>
                <Route path="/chat-rooms/:id" element={<RoomDetailPanel id="r1" />} />
                <Route path="/chat-rooms" element={<div>채팅방 목록</div>} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function overflowAutoEls(container) {
  return Array.from(container.querySelectorAll("*")).filter(
    (el) => getComputedStyle(el).overflowY === "auto",
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("채팅방 스크롤은 겹치지 않는다", () => {
  it("overflowY:auto 를 가진 요소가 화면에 하나뿐이다(ChatPane 자신의 로그)", async () => {
    const { container } = mount();
    await screen.findByText("안녕하세요");

    const scrollers = overflowAutoEls(container);
    expect(
      scrollers.length,
      `overflowY:auto 요소 ${scrollers.length}개 — 바깥 그릇과 ChatPane 로그가 각자 스크롤을 만들면 안 된다`,
    ).toBe(1);
  });
});

describe("대화창 헤더는 방 목록 헤더(제목줄+검색줄)와 총 높이가 같다", () => {
  it("제목줄 아래에 목록 검색줄과 같은 치수(여백 1.25 + 기본 컨트롤 높이 2.5rem)의 빈 자리가 있다", async () => {
    const { container } = mount();
    await screen.findByText("안녕하세요");

    // 목록의 검색줄(ChatRooms.jsx listPanel) 치수: px:2, py:1.25, borderBottom:1 를 감싸는
    // Box 안에 TextField(size="small", 높이 2.5rem = MuiButton.styleOverrides.root.minHeight:40 /
    // 기준선 .field·.btn min-height:40px 와 같은 값)가 있다.
    const spacer = container.querySelector('[data-testid="chatroom-header-spacer"]');
    expect(spacer, "헤더 아래 검색줄 자리 표시자가 없다").toBeTruthy();

    const outer = getComputedStyle(spacer);
    expect(outer.borderBottomWidth).toBe("1px");
    expect(outer.paddingTop).toBe("0.625rem");
    expect(outer.paddingBottom).toBe("0.625rem");

    const inner = getComputedStyle(spacer.firstChild);
    expect(inner.height).toBe("2.5rem");
  });
});
