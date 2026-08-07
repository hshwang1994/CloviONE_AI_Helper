import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 방장이 나가고 다른 참여자에게 위임되면(app/games/service.py::leave_room) 서버가
 * `{"text": "<새 방장>님이 방장이 되었습니다."}` 를 담은 system 이벤트를 남긴다 — 하지만
 * 프런트는 events 중 kind==="chat" 만 걸러 채팅 패널에 흘려보내고 system은 어디에도 그리지
 * 않았다. 남은 참여자는 참여자 목록의 '방장' 배지가 다음 폴링(1.2초)에서 바뀌는 것 말고는
 * 아무 안내도 받지 못한다 — 방이 파해질 때(disband)는 토스트+이동으로 안내하면서, 방이
 * 이어질 때(host handoff)는 안내가 통째로 빠져 있었다. */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("canvas-confetti", () => ({ default: vi.fn() }));

import { GameRoom } from "../GameRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

function renderRoom() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/games/r3"]}>
              <Routes>
                <Route path="/games/:id" element={<GameRoom />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

// 원래 방장(김운영)이 나가고 박개발에게 위임된 직후 — 남은 참여자(박개발) 시점.
const AFTER_HOST_HANDOFF = {
  room: {
    id: "r3", title: "점심 메뉴 투표", game_type: "quick_vote", status: "playing",
    player_count: 1, max_players: 8, host_user_id: "u2",
  },
  you: { user_id: "u2", in_room: true, is_host: true, role: "player", ready: false },
  members: [{ user_id: "u2", name: "박개발", role: "host" }],
  state: { question: "점심 뭐 먹지", options: ["김밥", "라면"], votes: {} },
  events: [
    { seq: 1, kind: "chat", actor_user_id: "u1", payload: { name: "김운영", text: "저는 먼저 갈게요" }, created_at: "2026-08-07T05:00:00" },
    { seq: 2, kind: "system", actor_user_id: null, payload: { text: "박개발님이 방장이 되었습니다." }, created_at: "2026-08-07T05:00:01" },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue(AFTER_HOST_HANDOFF);
});

afterEach(() => {
  delete window.matchMedia;
});

describe("방장 위임 안내", () => {
  it("방장이 나가 위임되면 남은 참여자의 채팅 로그에 위임 안내가 보인다", async () => {
    renderRoom();

    // 기존 채팅은 그대로 보인다.
    expect(await screen.findByText("저는 먼저 갈게요")).toBeInTheDocument();
    // 서버가 만든 위임 안내문이 화면 어딘가에 보여야 한다 — 지금은 어디에도 그려지지 않는다.
    expect(await screen.findByText("박개발님이 방장이 되었습니다.")).toBeInTheDocument();
  });
});
