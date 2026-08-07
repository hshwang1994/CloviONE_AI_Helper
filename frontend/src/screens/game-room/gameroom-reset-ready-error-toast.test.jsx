import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* useGameRoomController.js의 ready/reset 뮤테이션에는 다른 모든 뮤테이션(join/start/vote/
 * finish/pick/rps/quizAnswer/reveal/nextQ/leave/disband/chat)과 달리 onError가 없다 —
 * 서버가 실패를 돌려줘도 토스트 없이 그냥 조용히 아무 일도 없었던 것처럼 끝난다. 사용자는
 * 버튼을 눌렀는데 상태가 안 바뀐 이유를 알 방법이 없다(coding-style.md "Never silently
 * swallow errors"). 이 테스트는 실패 응답에도 안내 토스트가 뜨는지 고정한다. */

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
            <MemoryRouter initialEntries={["/games/r1"]}>
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

const FINISHED_DRAW = {
  room: { id: "r1", title: "점심 커피 추첨", game_type: "random_draw", status: "finished", player_count: 2, max_players: 8, host_user_id: "u1" },
  you: { user_id: "u1", in_room: true, is_host: true, role: "player", ready: true },
  members: [
    { user_id: "u1", name: "김운영", role: "host" },
    { user_id: "u2", name: "박개발", role: "player" },
  ],
  state: { result: [{ user_id: "u2", name: "박개발" }] },
  events: [],
};

function serverError(message) {
  const err = new Error(message);
  err.status = 500;
  return err;
}

beforeEach(() => {
  apiMock.mockReset();
});

afterEach(() => {
  delete window.matchMedia;
});

describe("게임방 뮤테이션 실패 안내", () => {
  it("'다시 하기'(reset)가 실패하면 오류 토스트가 뜬다(현재는 조용히 아무 일도 없었던 것처럼 끝난다)", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST" && path.endsWith("/reset")) {
        return Promise.reject(serverError("다시 시작할 수 없습니다."));
      }
      return Promise.resolve(FINISHED_DRAW);
    });
    renderRoom();

    const resetBtn = await screen.findByRole("button", { name: "다시 하기" });
    await userEvent.click(resetBtn);

    expect(await screen.findByText(/다시 시작하지 못했습니다|다시 시작할 수 없습니다/)).toBeInTheDocument();
  });
});
