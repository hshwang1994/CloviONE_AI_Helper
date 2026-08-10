import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 게임방 구조 분리(2026-08) 스모크 테스트.
 *
 * gameroom.test.jsx는 축포/접근성 계약만 다루고, "당첨자가 확정된 랜덤 추첨"과 "팀 나누기"
 * 결과 화면만 렌더한다 — GameStage.jsx의 quick_vote/waiting 분기, RoomSidebar/MembersList/
 * ChatPanel은 그 테스트로는 한 번도 렌더되지 않는다. 이 파일에서 값 변경 없이 GameRoom.jsx를
 * game-room/ 아래 여러 파일로 옮기며 조립 배선(누구에게 어떤 prop을 넘기는지)이 가장 틀리기
 * 쉬운 지점이었다 — 그 배선이 살아있는지 최소한으로 확인한다. */

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
            <MemoryRouter initialEntries={["/games/r2"]}>
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

// 아직 시작하지 않은 빠른 투표 방 — 방장 시점. GameStage의 isVote 분기(대기 상태 미리보기),
// RoomSidebar(참여자 목록 + 빈 채팅), 액션 버튼(투표 시작)을 한 번에 지나간다.
const WAITING_VOTE = {
  room: {
    id: "r2", title: "점심 메뉴 투표", game_type: "quick_vote", status: "waiting",
    player_count: 1, max_players: 8, host_user_id: "u1",
  },
  you: { user_id: "u1", in_room: true, is_host: true, role: "player", ready: false },
  members: [{ user_id: "u1", name: "김운영", role: "host" }],
  state: {},
  events: [],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue(WAITING_VOTE);
});

afterEach(() => {
  delete window.matchMedia;
});

describe("게임방 구조 분리 스모크", () => {
  it("대기 중인 빠른 투표 방을 배선 그대로 렌더한다(무대·참여자·채팅·액션 버튼)", async () => {
    renderRoom();

    // 무대(GameStage) 위 배지 — 게임 종류/상태 라벨.
    expect(await screen.findByText("빠른 투표")).toBeInTheDocument();
    expect(screen.getByText("대기 중")).toBeInTheDocument();

    // 참여자 레일(RoomSidebar → MembersList).
    expect(screen.getByText("참여자 1명")).toBeInTheDocument();
    expect(screen.getByText("김운영")).toBeInTheDocument();
    expect(screen.getByText("방장")).toBeInTheDocument();

    // 채팅 레일(RoomSidebar → ChatPanel) — 메시지가 없을 때의 안내문(kit EmptyState, DS-14).
    expect(screen.getByText("아직 메시지가 없습니다")).toBeInTheDocument();
    expect(screen.getByText("먼저 인사해 보세요.")).toBeInTheDocument();

    // 방장 + 대기 상태 → 시작 버튼.
    expect(screen.getByRole("button", { name: "투표 시작" })).toBeInTheDocument();
  });
});
