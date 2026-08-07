import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* HashRouter라 다른 게임방 링크를 이미 열린 게임방 탭에서 열면 GameRoom이 마운트 해제 없이
 * useParams().id만 바뀐다(gameroom-room-switch-rejoin.test.jsx와 같은 전제). 그 테스트는
 * joinedRef(자동 입장)만 다뤘다 — useGameRoomController가 들고 있는 다른 "이 방 한정" 상태는
 * 여전히 새 id로 안 바뀌었다.
 *
 * 1) prevChatCountRef(자동 스크롤 판단 기준)가 id 변경에 안 걸려 있었다. 방을 바꾸면 컴포넌트가
 *    "pending"(스켈레톤)을 거쳐 채팅 로그 DOM이 통째로 새로 마운트되는데, 그 순간엔 ref가 null이라
 *    prevChatCountRef 갱신이 건너뛰어진다 - 이전 방에서 남은 값(0이 아님)이 새 방까지 그대로
 *    남아 "첫 로드" 판정이 거짓이 된다. 새 방 채팅창을 처음 열었는데도 오래된 대화를 보고 있는
 *    것처럼 취급돼 맨 아래로 스크롤하지 않는다.
 * 2) draft(채팅 입력창 초안)도 같은 훅의 useState라 방을 바꿔도 안 비워진다 - 이전 방에 쓰다 만
 *    문구가 새 방 입력창에 그대로 남아, 방을 착각하고 그대로 보내기를 누르면 엉뚱한 방에 전송될
 *    뻔한다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("canvas-confetti", () => ({ default: vi.fn() }));

import { GameRoom } from "../GameRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

function chatEvents(prefix, count) {
  return Array.from({ length: count }, (_, i) => ({
    seq: i + 1,
    kind: "chat",
    actor_user_id: "other",
    payload: { text: `${prefix}-${i + 1}`, name: "다른사람" },
    created_at: "2026-08-07T09:00:00",
  }));
}

function roomState(id, title, chatCount) {
  return {
    room: { id, title, game_type: "quick_vote", status: "waiting", player_count: 2, max_players: 8, host_user_id: "other" },
    you: { user_id: "u1", in_room: true, is_host: false, role: "player", ready: false },
    members: [
      { user_id: "u1", name: "나", role: "player" },
      { user_id: "other", name: "다른사람", role: "host" },
    ],
    state: {},
    events: chatEvents(id, chatCount),
  };
}

// 앱 안의 링크를 눌러 같은 라우트 엘리먼트 안에서 id만 바뀌는 것을 흉내낸다(HashRouter는
// 전체 리로드 없이 이렇게 이동한다). gameroom-room-switch-rejoin.test.jsx와 같은 패턴.
function GoToRoom2() {
  const nav = useNavigate();
  return <button onClick={() => nav("/games/r2")}>다른 방으로 이동(테스트용)</button>;
}

function renderRooms() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/games/r1"]}>
              <Routes>
                <Route path="/games/:id" element={<><GoToRoom2 /><GameRoom /></>} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/games/rooms/r1/state")) return Promise.resolve(roomState("r1", "첫 번째 방", 3));
    if (path.startsWith("/api/games/rooms/r2/state")) return Promise.resolve(roomState("r2", "두 번째 방", 5));
    return Promise.resolve({ ok: true });
  });

  // jsdom은 레이아웃을 계산하지 않아 scrollHeight/clientHeight가 항상 0이다 - 스크롤이 필요할
  // 만큼 내용이 쌓인 채팅창을 흉내내려면 값을 고정으로 스텁해야 한다. scrollTop은 jsdom이
  // 실제로 읽고 쓸 수 있는 값이라 그대로 둔다.
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, value: 1000 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 300 });
});

afterEach(() => {
  delete window.matchMedia;
});

describe("게임방을 마운트 해제 없이 다른 방으로 전환 - 채팅 스크롤/초안", () => {
  it("새 방으로 넘어가면 그 방 채팅도 처음 연 것으로 보고 맨 아래로 스크롤한다", async () => {
    renderRooms();

    const log1 = await screen.findByTestId("game-chat-log");
    await waitFor(() => expect(log1.scrollTop).toBe(1000));

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "다른 방으로 이동(테스트용)" }));

    expect(await screen.findByRole("heading", { name: "두 번째 방" })).toBeInTheDocument();
    const log2 = await screen.findByTestId("game-chat-log");
    await waitFor(() => expect(log2.scrollTop).toBe(1000));
  });

  it("새 방으로 넘어가면 이전 방에 쓰다 만 채팅 초안이 남아있지 않다", async () => {
    renderRooms();
    await screen.findByTestId("game-chat-log");

    const user = userEvent.setup();
    const input = screen.getByPlaceholderText("메시지 입력");
    await user.type(input, "첫 번째 방에서 쓰다 만 말");
    expect(input).toHaveValue("첫 번째 방에서 쓰다 만 말");

    await user.click(screen.getByRole("button", { name: "다른 방으로 이동(테스트용)" }));

    expect(await screen.findByRole("heading", { name: "두 번째 방" })).toBeInTheDocument();
    const input2 = await screen.findByPlaceholderText("메시지 입력");
    expect(input2).toHaveValue("");
  });
});
