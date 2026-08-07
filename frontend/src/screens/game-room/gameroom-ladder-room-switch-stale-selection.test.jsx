import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* LadderBoard(사다리타기 결과)는 `useState(initial >= 0 ? initial : null)`로 "선택한 이름"
 * (sel)을 컴포넌트 로컬 상태로 들고 있다 - useState 초기화 함수는 첫 마운트에서만 돈다.
 *
 * HashRouter인 이 앱에서 다른 게임방 링크를 이미 열린 게임방 탭에서 열면 GameRoom은 마운트
 * 해제 없이 useParams().id만 바뀐다(gameroom-room-switch-rejoin.test.jsx와 같은 전제). 방
 * 전환은 보통 react-query가 "pending"(스켈레톤)을 거치며 그 순간 무대 서브트리 전체가 마운트
 * 해제/재마운트돼 LadderBoard의 sel도 함께 리셋된다 - 그런데 옮겨가는 방의 데이터가 **이미
 * 캐시에 있으면**(예: 채팅에 올라온 두 사다리 링크를 번갈아 열어 봤다면, 즉 같은 QueryClient에
 * 그 방 쿼리 결과가 이미 있으면) react-query가 캐시된 데이터를 즉시 내려줘 isPending이 절대
 * true가 되지 않는다 - 스켈레톤을 거치지 않으므로 GameStage 트리는 마운트된 채 그대로 남고,
 * LadderBoard도 같은 컴포넌트 인스턴스로 재사용된다(리스트의 같은 자리, key 없음).
 *
 * 그러면 이전 방에서 골랐던 sel(참여자 인덱스)이 새 방까지 그대로 남는다 - 새 방의 참여자
 * 수가 이전 방보다 적으면 `cols[sel]`이 배열 범위를 벗어나 `undefined`가 되고, 그 아래
 * `cols[sel].name`을 그대로 읽어 화면 전체가 크래시한다. */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("canvas-confetti", () => ({ default: vi.fn() }));

import { GameRoom } from "../GameRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

// 4명이 사다리를 탄 방 - 마지막 이름("지훈", 인덱스 3)을 고를 것이다.
const ROOM1 = {
  room: { id: "r1", title: "첫 번째 사다리", game_type: "ladder", status: "finished", player_count: 4, max_players: 8, host_user_id: "h1" },
  you: { user_id: "viewer", in_room: true, is_host: false, role: "spectator", ready: false },
  members: [
    { user_id: "p1", name: "철수", role: "player" },
    { user_id: "p2", name: "영희", role: "player" },
    { user_id: "p3", name: "민수", role: "player" },
    { user_id: "p4", name: "지훈", role: "player" },
  ],
  state: {
    result: {
      columns: [
        { user_id: "p1", name: "철수" },
        { user_id: "p2", name: "영희" },
        { user_id: "p3", name: "민수" },
        { user_id: "p4", name: "지훈" },
      ],
      outcomes: ["1등", "2등", "3등", "4등"],
      rungs: [],
      rows: 8,
      assignments: [
        { user_id: "p1", name: "철수", outcome: "1등", end_col: 0 },
        { user_id: "p2", name: "영희", outcome: "2등", end_col: 1 },
        { user_id: "p3", name: "민수", outcome: "3등", end_col: 2 },
        { user_id: "p4", name: "지훈", outcome: "4등", end_col: 3 },
      ],
    },
  },
  events: [],
};

// 2명뿐인 방 - sel=3이 넘어오면 cols[3]이 undefined다.
const ROOM2 = {
  room: { id: "r2", title: "두 번째 사다리", game_type: "ladder", status: "finished", player_count: 2, max_players: 8, host_user_id: "h2" },
  you: { user_id: "viewer", in_room: true, is_host: false, role: "spectator", ready: false },
  members: [
    { user_id: "q1", name: "동수", role: "player" },
    { user_id: "q2", name: "지민", role: "player" },
  ],
  state: {
    result: {
      columns: [
        { user_id: "q1", name: "동수" },
        { user_id: "q2", name: "지민" },
      ],
      outcomes: ["1등", "2등"],
      rungs: [],
      rows: 8,
      assignments: [
        { user_id: "q1", name: "동수", outcome: "1등", end_col: 0 },
        { user_id: "q2", name: "지민", outcome: "2등", end_col: 1 },
      ],
    },
  },
  events: [],
};

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
    if (path.startsWith("/api/games/rooms/r1/state")) return Promise.resolve(ROOM1);
    if (path.startsWith("/api/games/rooms/r2/state")) return Promise.resolve(ROOM2);
    return Promise.resolve({ ok: true });
  });
});

afterEach(() => {
  delete window.matchMedia;
});

describe("사다리타기 결과 화면 - 캐시된 다른 방으로 전환", () => {
  it("이전 방에서 고른 이름 선택이 인원이 더 적은 새 방까지 넘어가 크래시하지 않는다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // r2는 "이미 이 세션에서 한 번 열어 본" 방을 흉내낸다 - 캐시에 데이터가 이미 있으면
    // 방을 전환해도 react-query가 pending(스켈레톤)을 거치지 않는다.
    qc.setQueryData(["game-room", "r2"], ROOM2);

    renderRooms(qc);

    // 첫 방 사다리에서 마지막 이름(지훈, 인덱스 3)을 고른다.
    const user = userEvent.setup();
    const chip = await screen.findByRole("button", { name: "지훈" });
    await user.click(chip);
    expect(await screen.findByText("4등", { selector: "b" })).toBeInTheDocument();

    // 인원이 더 적은(2명) 두 번째 방으로 넘어간다 - 이미 캐시돼 있어 스켈레톤을 거치지 않는다.
    await user.click(screen.getByRole("button", { name: "다른 방으로 이동(테스트용)" }));

    expect(await screen.findByRole("heading", { name: "두 번째 사다리" })).toBeInTheDocument();
    // 새 방은 아직 아무도 고르지 않은 상태여야 한다 - 이전 방의 선택(인덱스 3)이 새 방의
    // 참여자 배열(길이 2)을 벗어나 남아있으면 여기 도달하기 전에 렌더가 크래시한다.
    expect(await screen.findByText("이름을 누르면 사다리 경로가 보입니다.")).toBeInTheDocument();
  });
});
