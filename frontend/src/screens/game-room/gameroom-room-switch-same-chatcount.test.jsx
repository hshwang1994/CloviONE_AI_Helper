import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* gameroom-room-switch-stale-state.test.jsx가 잡은 "prevChatCountRef가 id 변경에 안 걸려
 * 있었다" 버그는 고쳐졌지만, 그 수정이 기대는 자동 스크롤 이펙트(useGameRoomController.js의
 * `useEffect(..., [chatCount])`)가 방을 바꾼 렌더에서 **반드시 다시 실행된다**는 전제다.
 * 그 전제는 두 방의 채팅(kind=chat/시스템) 이벤트 개수가 우연히 같으면 깨진다:
 *
 *   1) 방 A(4건)를 보다가 이미 캐시에 있는(=이전에 한 번 연) 방 B(마찬가지로 4건)로 전환하면,
 *      HashRouter라 GameRoom은 마운트 해제 없이 id만 바뀌고, 캐시가 있어 "pending"(스켈레톤)도
   *    거치지 않는다 - 즉 채팅 로그 DOM(chatLogRef)이 이 전환 내내 살아있다.
 *   2) id가 바뀌면 `useEffect(..., [id])`가 prevChatCountRef.current를 0으로 되돌리지만,
 *      **자동 스크롤을 실제로 수행하는 이펙트**는 의존성 배열이 `[chatCount]`뿐이다. 방 A의
 *      마지막 커밋에서 chatCount가 4였고 방 B도 4면, React는 "의존값이 안 바뀌었다"고 보고
 *      그 이펙트 콜백을 아예 다시 실행하지 않는다 - prevChatCountRef를 0으로 되돌린 것이
 *      무의미해진다(아무도 읽지 않는다).
 *   3) 그 결과 방 B로 넘어갔는데도 방 A에서 위로 올려 옛 대화를 읽던 스크롤 위치가 그대로
 *      남는다 - 방금 연 방인데 대화 중간을 보고 있는 것처럼 보인다. 다음 채팅(개수가 바뀌는
 *      사건)이 와야 비로소 "첫 로드" 판정이 뒤늦게 걸려 스스로 고쳐진다.
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

function renderRooms(qc) {
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
    if (path.startsWith("/api/games/rooms/r1/state")) return Promise.resolve(roomState("r1", "첫 번째 방", 4));
    if (path.startsWith("/api/games/rooms/r2/state")) return Promise.resolve(roomState("r2", "두 번째 방", 4));
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

describe("게임방을 마운트 해제 없이 다른 방으로 전환 - 메시지 개수가 같은 방", () => {
  it("이미 캐시된, 채팅 개수가 같은 방으로 넘어가도 그 방 맨 아래로 스크롤한다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 방 B(r2)를 미리 캐시에 채워 둔다 - 이미 한 번 열어 본 방으로 되돌아가는 흔한 경우를
    // 흉내낸다. 캐시가 있으면 전환 중 "pending"(스켈레톤)을 거치지 않아 채팅 로그 DOM이
    // 마운트 해제되지 않는다.
    qc.setQueryData(["game-room", "r2"], roomState("r2", "두 번째 방", 4));

    renderRooms(qc);

    const log = await screen.findByTestId("game-chat-log");
    await waitFor(() => expect(log.scrollTop).toBe(1000));

    // 방 A에서 위로 올려 옛 대화를 읽던 상태를 흉내낸다.
    log.scrollTop = 0;

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "다른 방으로 이동(테스트용)" }));

    expect(await screen.findByRole("heading", { name: "두 번째 방" })).toBeInTheDocument();
    // 방 B는 채팅 개수가 방 A와 같아도(4건) 처음 여는 채팅이니 맨 아래로 스크롤해야 한다.
    await waitFor(() => expect(log.scrollTop).toBe(1000));
  });
});
