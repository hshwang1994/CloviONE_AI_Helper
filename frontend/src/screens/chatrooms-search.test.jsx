import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 채팅방 목록의 '채팅방 검색'.
 *
 * 왜 이 테스트가 필요한가: 목록 행은 서버가 준 `title` 로 그린다(app/team_chat/router.py 의
 * `_room_title`). 그런데 거르는 쪽이 다른 이름을 보고 있으면, 화면에는 이름이 멀쩡히 보이는데
 * 한 글자만 쳐도 목록이 통째로 비는 상태가 된다 — 사용자에게는 "채팅방이 깨졌다" 로 보인다.
 * 보이는 글자와 거르는 글자가 같은 값이어야 한다는 것을 여기서 못박는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatRooms } from "./ChatRooms.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROOMS = {
  // 팀 방·전체 방을 비워 두면 ChatRooms 가 자동으로 방을 열어 목록만 보는 상태를 만들 수 없다.
  team: null,
  global: null,
  items: [
    { id: "r1", kind: "group", title: "인프라 팀", member_count: 4, unread: 0, last_preview: "", last_at: null },
    { id: "r2", kind: "group", title: "디자인 회의", member_count: 3, unread: 0, last_preview: "", last_at: null },
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

describe("채팅방 검색", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("이름의 일부를 치면 그 방만 남는다 — 목록에 보이는 그 글자로 걸러야 한다", async () => {
    const user = userEvent.setup();
    mount();
    expect(await screen.findByText("인프라 팀")).toBeInTheDocument();
    expect(screen.getByText("디자인 회의")).toBeInTheDocument();

    await user.type(screen.getByLabelText("채팅방 이름으로 거르기"), "인프라");

    await waitFor(() => expect(screen.queryByText("디자인 회의")).not.toBeInTheDocument());
    expect(screen.getByText("인프라 팀")).toBeInTheDocument();
  });
});

describe("새 그룹 방 이름 글자 수 상한", () => {
  beforeEach(() => { apiMock.mockReset(); });

  // 서버(app/team_chat/schemas.py::GroupCreate, MAX_TITLE=200)가 받아 주는 길이까지 화면이
  // 미리 막지 않아야 한다 — 예전에는 80으로 잘라 서버가 허용하는 81~200자 이름을 아예 칠 수
  // 없었다(폼↔API 불일치).
  it("입력 상한이 서버의 MAX_TITLE(200)과 같다", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole("button", { name: "새 그룹" }));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByLabelText(/방 이름/);
    expect(input).toHaveAttribute("maxlength", "200");
  });
});
