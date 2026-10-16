import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 좁은 화면(390)의 채팅방 목록 — r23 화면 대장 EX-C2.
 *
 * `/chat-rooms` 로 들어오면 내 팀 방을 연다(Q6). 그런데 그 규칙이 화면 폭과 상관없이 돌아, 좁은 화면에서 방 머리의
 * 「목록」(→ `/chat-rooms`)을 누르면 그 자리에서 다시 팀 방으로 튕겼다 — 휴대폰에서는 방 목록에 닿을 길이 없었고, 다른 방으로
 * 옮길 수도 없었다. 넓은 화면은 목록이 옆에 서 있으니 팀 방을 여는 것이 맞다. 두 갈래를 다 못박는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
// 대화 판은 이 시험의 대상이 아니다 — 어느 방이 열렸는지만 본다.
vi.mock("./ChatRoom.jsx", () => ({ RoomDetailPanel: ({ id }) => <div data-testid="room-panel">{id}</div> }));

import { ChatRooms } from "./ChatRooms.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROOMS = {
  team: { id: "team-1", kind: "group", title: "플랫폼개발팀", department_id: "d1", member_count: 3, unread: 0, last_preview: "", last_at: null },
  global: { id: "all-1", kind: "group", title: "전체 채팅", is_global: true, member_count: 9, unread: 0, last_preview: "", last_at: null },
  items: [{ id: "r1", kind: "group", title: "장애 대응", member_count: 5, unread: 0, last_preview: "", last_at: null }],
  unread_total: 0,
};

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{loc.pathname}</output>;
}

function stubWidth(wide) {
  /* MUI `useMediaQuery` 는 `matchMedia` 를 읽는다. 넓은 화면이면 `min-width` 질의가 맞는다. */
  window.matchMedia = (query) => ({
    matches: wide ? /min-width/.test(query) : /max-width/.test(query),
    media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  });
}

function mount(path) {
  apiMock.mockImplementation((url) => (url === "/api/team-chat/rooms" ? Promise.resolve(ROOMS) : Promise.resolve({ items: [] })));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <Where />
              <Routes>
                <Route path="/chat-rooms" element={<ChatRooms />} />
                <Route path="/chat-rooms/:id" element={<ChatRooms />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const original = window.matchMedia;
beforeEach(() => { apiMock.mockReset(); });
afterEach(() => { window.matchMedia = original; });

describe("좁은 화면의 채팅방 목록", () => {
  it("`/chat-rooms` 는 방 목록이다 — 팀 방으로 튕기지 않는다", async () => {
    stubWidth(false);
    mount("/chat-rooms");
    expect(await screen.findByText("장애 대응")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("채팅방 검색")).toBeInTheDocument();
    // 기다려도 그대로다(팀 방을 여는 효과가 돌았다면 여기서 주소가 바뀐다).
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/chat-rooms$/);
    expect(screen.queryByTestId("room-panel")).toBeNull();
  });

  it("방 머리의 「목록」을 누르면 방 목록에 닿는다", async () => {
    stubWidth(false);
    const user = userEvent.setup();
    mount("/chat-rooms/team-1");
    expect(await screen.findByTestId("room-panel")).toHaveTextContent("team-1");
    await user.click(screen.getByRole("button", { name: "목록" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(/^\/chat-rooms$/));
    expect(await screen.findByText("장애 대응")).toBeVisible();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/chat-rooms$/);
  });
});

describe("넓은 화면은 목록이 옆에 서므로 내 팀 방을 연다 (Q6)", () => {
  it("`/chat-rooms` 로 들어오면 팀 방이 열린다", async () => {
    stubWidth(true);
    mount("/chat-rooms");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/chat-rooms/team-1"));
    expect(await screen.findByTestId("room-panel")).toHaveTextContent("team-1");
  });
});
