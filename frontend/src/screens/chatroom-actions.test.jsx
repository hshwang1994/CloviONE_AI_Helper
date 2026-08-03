import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 채팅방 헤더의 파괴적 동작 — 파하기(그룹·방장) / 숨기기(1:1) / 나가기.
 *
 * 이 화면이 틀리기 쉬운 지점은 **버튼을 누가 보느냐**가 아니라 **어디서 판단하느냐**다.
 * 방장인지·1:1인지·전체 채팅인지를 프런트가 다시 계산하면 서버 규칙과 어긋나는 순간
 * '보이는데 누르면 403/409'가 된다. 그래서 서버가 준 you.can_disband / you.can_hide 만 본다.
 *
 * 그리고 파하기와 숨기기는 다른 일이다: 그룹은 모두에게서 사라지고(soft delete), 1:1 은
 * 파할 수 없어(dm_key unique) 내 목록에서만 숨긴다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatRoom } from "./ChatRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function meta(you, room = {}) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "우리방", member_count: 3, ...room },
    members: [],
    messages: [],
    seq: 0,
    you: { user_id: "u1", role: "member", last_read_seq: 0, is_member: true,
           can_disband: false, can_hide: false, ...you },
  };
}

function mount(payload) {
  apiMock.mockImplementation((url) => {
    if (url.startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(payload);
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
                <Route path="/chat-rooms/:id" element={<ChatRoom />} />
                {/* 동작 후 목록으로 되돌아간다 — 라우트가 없으면 경고만 남고 이동이 검증되지 않는다. */}
                <Route path="/chat-rooms" element={<div>채팅방 목록</div>} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const posted = (path) => apiMock.mock.calls.filter((c) => c[0] === path && c[1] && c[1].method === "POST");

beforeEach(() => { apiMock.mockReset(); });

describe("방 파하기 버튼", () => {
  it("서버가 can_disband 를 주면 보이고, 확인 후 disband 를 호출한다", async () => {
    const user = userEvent.setup();
    mount(meta({ role: "owner", can_disband: true }));

    const btn = await screen.findByRole("button", { name: "방 파하기" });
    await user.click(btn);
    // 되돌릴 수 없는 동작이라 확인을 받는다.
    await user.click(await screen.findByRole("button", { name: "파하기" }));

    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/disband")).toHaveLength(1));
  });

  it("can_disband 가 false 면 버튼 자체가 없다(1:1·전체·비방장)", async () => {
    mount(meta({ role: "member", can_disband: false }));
    await screen.findByRole("button", { name: "목록" });
    expect(screen.queryByRole("button", { name: "방 파하기" })).toBeNull();
  });

  it("확인 창에서 취소하면 아무 요청도 나가지 않는다", async () => {
    const user = userEvent.setup();
    mount(meta({ role: "owner", can_disband: true }));
    await user.click(await screen.findByRole("button", { name: "방 파하기" }));
    await user.click(await screen.findByRole("button", { name: "취소" }));
    expect(posted("/api/team-chat/rooms/r1/disband")).toHaveLength(0);
  });
});

describe("1:1 숨기기 버튼", () => {
  it("1:1 방에서는 '파하기'가 아니라 '숨기기'가 나온다", async () => {
    const user = userEvent.setup();
    mount(meta({ can_hide: true, can_disband: false },
               { kind: "direct", title: "상대이름", member_count: 2 }));

    expect(await screen.findByRole("button", { name: "숨기기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "방 파하기" })).toBeNull();
    // 1:1 은 '나가기'도 없다(그룹 전용).
    expect(screen.queryByRole("button", { name: "나가기" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "숨기기" }));
    // 확인 모달의 확정 버튼(헤더 버튼과 같은 이름이라 마지막 것을 고른다).
    const confirms = await screen.findAllByRole("button", { name: "숨기기" });
    await user.click(confirms[confirms.length - 1]);
    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/hide")).toHaveLength(1));
    // 숨기고 나면 목록으로 돌아간다.
    expect(await screen.findByText("채팅방 목록")).toBeInTheDocument();
  });
});

describe("전체 채팅 방", () => {
  it("파하기·나가기·숨기기가 모두 없다 — 서버가 409 로 막는 동작을 화면에 보이지 않는다", async () => {
    mount(meta({ role: null, is_member: false, can_disband: false, can_hide: false },
               { is_global: true, title: "전체 채팅", member_count: 0 }));
    await screen.findByRole("button", { name: "목록" });
    expect(screen.queryByRole("button", { name: "방 파하기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "나가기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "숨기기" })).toBeNull();
  });
});
