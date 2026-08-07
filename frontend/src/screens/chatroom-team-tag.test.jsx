import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 방 목록(ChatRooms.jsx RoomRow)은 내 팀 방에 "내 팀" 태그를 붙인다(department_id 로
 * 판단). 방 안(ChatRoom.jsx RoomDetailPanel)의 헤더는 같은 어휘를 쓴다고 주석에 적혀
 * 있었지만("목록에서 보던 표식이 방에 들어오면 사라지면 안 된다"), 실제 태그 계산에는
 * department_id 분기가 아예 없어 "그룹 N"으로 떨어졌다 — 목록에서는 "내 팀"이라고 하고
 * 방에 들어가면 "그룹 3"이라고 하는 자기모순이었다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { RoomDetailPanel } from "./ChatRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function meta(room = {}) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "플랫폼팀", member_count: 3, ...room },
    members: [],
    messages: [],
    seq: 0,
    you: { user_id: "u1", role: "member", last_read_seq: 0, is_member: true,
           can_disband: false, can_hide: false, can_manage: false },
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
                <Route path="/chat-rooms/:id" element={<RoomDetailPanel id="r1" />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("방 헤더의 종류 태그", () => {
  it("부서 방(department_id 있음)은 목록과 같은 '내 팀' 태그를 보여준다", async () => {
    mount(meta({ department_id: "dept-1" }));
    expect(await screen.findByText("내 팀")).toBeInTheDocument();
    expect(screen.queryByText("그룹 3")).toBeNull();
  });

  it("일반 그룹 방(department_id 없음)은 그대로 '그룹 N'을 보여준다", async () => {
    mount(meta({ department_id: null }));
    expect(await screen.findByText("그룹 3")).toBeInTheDocument();
    expect(screen.queryByText("내 팀")).toBeNull();
  });
});
