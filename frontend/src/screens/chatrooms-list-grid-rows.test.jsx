import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 채팅방 목록이 패널 아래쪽부터 쌓이던 회귀 (사용자 지적: "채팅방이 아래부터 만들어짐").
 *
 * 원인: listPanel 의 grid 컨테이너가 자식 셋(제목줄·검색줄·목록)을 항상 그리는데
 * gridTemplateRows 는 "auto 1fr" 두 트랙뿐이었다. grid 는 셋째 자식(목록)을 암시(auto,
 * 내용 높이만) 행으로 밀어내고, 검색줄이 남는 세로 공간(1fr)을 통째로 차지했다 — 목록이
 * 패널 맨 아래, 내용 높이만큼만 차지하고 그 위는 빈 채로 남는다.
 *
 * 고정: 트랙을 자식 수만큼(auto auto 1fr) 줘서 목록이 남는 공간(1fr)을 갖는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatRooms } from "./ChatRooms.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROOMS = {
  team: null,
  global: null,
  items: [
    { id: "r1", kind: "group", title: "인프라 팀", member_count: 4, unread: 0, last_preview: "", last_at: null },
  ],
  unread_total: 0,
};

function mount() {
  apiMock.mockImplementation((url) => {
    if (url === "/api/team-chat/rooms") return Promise.resolve(ROOMS);
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/chat-rooms"]}>
              <Routes>
                <Route path="/chat-rooms" element={<ChatRooms />} />
                <Route path="/chat-rooms/:id" element={<ChatRooms />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

describe("채팅방 목록은 패널 위쪽부터 쌓인다 (grid 트랙 수 = 자식 수)", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("grid 트랙이 자식 셋(제목줄·검색줄·목록)만큼 있어 목록이 암시 행으로 밀려나지 않는다", async () => {
    mount();
    await screen.findByText("인프라 팀");

    const grid = screen.getByTestId("chatroom-list-grid");
    expect(grid.children.length).toBe(3);

    const tracks = getComputedStyle(grid).gridTemplateRows.trim().split(/\s+/);
    expect(tracks.length, `gridTemplateRows에 트랙이 ${tracks.length}개뿐이다 — 자식 수(3)만큼 있어야 셋째 자식(목록)이 암시 행으로 밀려나지 않는다`).toBe(3);

    // 목록 상자가 grid의 세 번째(마지막) 자식이어야 남는 공간(1fr) 트랙을 받는다.
    const list = screen.getByTestId("chatroom-list-rows");
    expect(grid.children[2]).toBe(list);
  });
});
