import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 이 앱은 HashRouter SPA다 — 다른 게임방으로 가는 링크(예: 슬랙에서 붙여넣은 두 번째 초대
 * 링크)를 이미 게임방 화면(/games/<id>)이 열린 탭에서 열면, 해시만 바뀌어 GameRoom이 마운트
 * 해제되지 않은 채 useParams().id만 바뀐다(App.jsx가 HashRouter를 쓰고, /games/:id는 같은
 * 라우트 엘리먼트다).
 *
 * useGameRoomController.js의 자동 입장 이펙트는 컴포넌트 인스턴스당 한 번만 도는
 * joinedRef(useRef(false))로 지켜진다 — "이 방에 입장 시도를 했는지"가 아니라 "이 컴포넌트
 * 인스턴스가 어떤 방이든 입장 시도를 한 적이 있는지"를 기억한다. 그래서 첫 방에서 자동
 * 입장(join)이 한 번 일어나고 나면, 마운트를 유지한 채 다른 방으로 넘어가도 그 새 방에서
 * you.in_room이 false여도 다시는 join을 시도하지 않는다 — 참여자가 새 방에 조용히
 * "입장하지 않은" 채로 남는다(투표·준비 등 참여 동작이 전부 막힌다). */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("canvas-confetti", () => ({ default: vi.fn() }));

import { GameRoom } from "../GameRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

function roomState(id, title) {
  return {
    room: { id, title, game_type: "quick_vote", status: "waiting", player_count: 1, max_players: 8, host_user_id: "other" },
    you: { user_id: "u1", in_room: false, is_host: false, role: "player", ready: false },
    members: [{ user_id: "other", name: "다른사람", role: "host" }],
    state: {},
    events: [],
  };
}

// 앱 안의 링크를 눌러 같은 라우트 엘리먼트 안에서 id만 바뀌는 것을 흉내낸다(HashRouter는
// 전체 리로드 없이 이렇게 이동한다).
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
  apiMock.mockImplementation((path, opts) => {
    if (opts && opts.method === "POST" && path.endsWith("/join")) return Promise.resolve({ ok: true });
    if (path.startsWith("/api/games/rooms/r1/state")) return Promise.resolve(roomState("r1", "첫 번째 방"));
    if (path.startsWith("/api/games/rooms/r2/state")) return Promise.resolve(roomState("r2", "두 번째 방"));
    return Promise.resolve({ ok: true });
  });
});

afterEach(() => {
  delete window.matchMedia;
});

function joinCallsFor(roomId) {
  return apiMock.mock.calls.filter(
    (c) => c[0] === `/api/games/rooms/${roomId}/join` && c[1] && c[1].method === "POST"
  ).length;
}

describe("게임방을 마운트 해제 없이 다른 방으로 전환", () => {
  it("두 번째 방에서도 자동 입장을 시도한다", async () => {
    renderRooms();

    // 첫 방: you.in_room=false라 자동 입장 한 번. 제목은 h1 하나로 좁혀서 본다(무대의
    // 투표 질문도 question이 비어 room.title로 같은 문구를 그린다 — findByText면 중복으로 잡힌다).
    await waitFor(() => expect(joinCallsFor("r1")).toBe(1));
    expect(await screen.findByRole("heading", { name: "첫 번째 방" })).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "다른 방으로 이동(테스트용)" }));

    // 두 번째 방도 화면은 넘어간다.
    expect(await screen.findByRole("heading", { name: "두 번째 방" })).toBeInTheDocument();
    // 두 번째 방도 you.in_room=false이므로 자동 입장을 시도해야 한다.
    await waitFor(() => expect(joinCallsFor("r2")).toBe(1));
  });
});
