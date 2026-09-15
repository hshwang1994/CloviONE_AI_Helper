import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 방 머리가 한 줄(제목 + 종류 · 참여자 요약과 얼굴 · 동작)에서 두 줄 이름표(1줄 제목 + 종류 배지, 2줄 「참여자 N명, 보는 중 M명」) + 얼굴 스택 + 동작으로 옮겼다(UI 3차 조합 계약 C-6 · 채팅방 시안). 묶음 이름을 identity · members · actions 로 옮기고, 요약이 제목 줄 아래 · 얼굴 묶음 밖에 서는지와 선 토큰을 더 잰다. */
/* qa-contract-change: 목록과 대화가 한 판을 가르던 두 칸에서 두 판(핸드오프 RULES §9 · 계획 E)이 되어 「대화창 머리 아래에 목록 검색줄과 같은 빈 자리」 계약이 뜻을 잃었다. 머리는 이제 세 묶음(제목 + 종류 · 참여자 · 동작)이 묶음 단위로 접히는 줄이다 — 그 구조를 잰다(스크롤 하나 계약은 그대로). */

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

describe("방 머리는 두 줄 이름표 · 얼굴 · 동작 세 묶음이다 (핸드오프 RULES §9 · 채팅방 시안 · 조합 계약 C-6)", () => {
  it("이름표(1줄 제목 + 종류, 2줄 참여자 요약) · 얼굴 · 동작 세 묶음이 순서대로 서고, 줄은 묶음 단위로 접힌다", async () => {
    const { container } = mount();
    await screen.findByText("안녕하세요");
    // 옛 빈 자리는 없다 — 목록과 대화가 다른 판이라 맞출 경계가 없다.
    expect(container.querySelector('[data-testid="chatroom-header-spacer"]')).toBeNull();

    const head = container.querySelector("[data-room-head]");
    expect(head, "방 머리가 없다").toBeTruthy();
    const groups = [...head.children].map((el) => el.getAttribute("data-room-head-group"));
    expect(groups).toEqual(["identity", "members", "actions"]);
    expect(getComputedStyle(head).flexWrap).toBe("wrap");
    expect(getComputedStyle(head).borderBottomWidth).toBe("1px");

    const identity = head.querySelector('[data-room-head-group="identity"]');
    const titleRow = identity.querySelector('[data-room-head-group="title"]');
    expect(titleRow, "이름표 첫 줄(제목 + 종류)이 없다").toBeTruthy();
    const title = titleRow.querySelector("h2");
    expect(title).toHaveTextContent("우리방");
    // 긴 제목은 한 줄에서 말줄임되고 전체 이름은 이름표가 든다.
    expect(title).toHaveAttribute("title", "우리방");
    expect(getComputedStyle(title).whiteSpace).toBe("nowrap");
    expect(getComputedStyle(head.querySelector('[data-room-head-group="actions"]')).flexWrap).toBe("nowrap");

    // 둘째 줄 — 참여자 요약은 제목 줄 **아래**(이름표 안 다음 형제)이고, 제목 줄 · 얼굴 묶음 안에 서지 않는다.
    const summary = within(head).getByText("참여자 2명, 보는 중 1명");
    expect(identity.contains(summary)).toBe(true);
    expect(titleRow.contains(summary)).toBe(false);
    expect(titleRow.nextElementSibling).toBe(summary);
    expect(getComputedStyle(identity).display).toBe("grid");
    expect(head.querySelector('[data-room-head-group="members"]').contains(summary)).toBe(false);
    // 얼굴 스택은 요약과 따로 선다.
    expect(within(head.querySelector('[data-room-head-group="members"]')).getByRole("list", { name: "참여자" })).toBeInTheDocument();
  });
});
