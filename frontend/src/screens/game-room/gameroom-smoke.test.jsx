import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 게임방 구조 분리(2026-08) 스모크 테스트.
 *
 * gameroom.test.jsx는 축포/접근성 계약만 다루고, "당첨자가 확정된 랜덤 추첨"과 "팀 나누기"
 * 결과 화면만 렌더한다 — GameStage.jsx의 quick_vote/waiting 분기, RoomRail/MembersList/
 * ChatPanel은 그 테스트로는 한 번도 렌더되지 않는다. 이 파일에서 값 변경 없이 GameRoom.jsx를
 * game-room/ 아래 여러 파일로 옮기며 조립 배선(누구에게 어떤 prop을 넘기는지)이 가장 틀리기
 * 쉬운 지점이었다 — 그 배선이 살아있는지 최소한으로 확인한다.
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
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

    // 툴바(RoomToolbar) — 게임 종류 · 상태 라벨. 상태 낱말은 페이지에 한 번이다(D-575).
    expect(await screen.findByText("빠른 투표")).toBeInTheDocument();
    expect(screen.getAllByText("대기 중")).toHaveLength(1);
    expect(screen.getByText("참여 1/8")).toBeInTheDocument();

    // 판(BoardFrame → VoteBoard) — 대기 중에도 판이 선다(질문 · 보기 미리 보기).
    expect(document.querySelector('[data-vote-board="waiting"]')).not.toBeNull();

    // 참여자 레일(RoomRail → MembersRows). 인원수는 툴바가 말하므로 머리글은 「참여자」뿐이다.
    expect(screen.getByRole("heading", { name: "참여자" })).toBeInTheDocument();
    expect(screen.getAllByText("김운영").length).toBeGreaterThan(0);
    expect(screen.getAllByText("방장").length).toBeGreaterThan(0);

    // 채팅 레일(RoomRail → ChatPanel) — 메시지가 없을 때의 안내문(kit EmptyState, DS-14).
    expect(screen.getByText("메시지가 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("첫 메시지를 보내 대화를 시작하세요.")).toBeInTheDocument();

    // 방장 + 대기 상태 → 툴바의 시작 버튼 · 나가기 · 넘침(방 파하기).
    expect(screen.getByRole("button", { name: "투표 시작" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "나가기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "방 동작 더 보기" })).toBeInTheDocument();
  });
});

describe("게임방 채팅 — 같은 말을 두 번 보내지 않는다 (P4)", () => {
  it("같은 틱에 Enter 가 두 번 와도 채팅 요청은 한 번이다", async () => {
    /* 채팅은 입력 칸의 Enter 처리기가 직접 보낸다. 그 처리기가 보는 `isPending` 은 지난 렌더의 값이라, 다시
       그려지기 전에 온 둘째 Enter 는 같은 말을 한 번 더 보냈다. 응답을 붙잡아 그 창을 연다. */
    const sent = [];
    apiMock.mockImplementation((url, opts) => {
      if (url === "/api/games/rooms/r2/chat" && opts && opts.method === "POST") {
        sent.push(opts.body);
        return new Promise(() => {});
      }
      return Promise.resolve(WAITING_VOTE);
    });
    renderRoom();
    const input = await screen.findByRole("textbox", { name: "메시지 입력" });
    fireEvent.change(input, { target: { value: "점심은 국수로 하죠" } });
    act(() => {
      fireEvent.keyDown(input, { key: "Enter" });
      fireEvent.keyDown(input, { key: "Enter" });
    });
    await waitFor(() => expect(sent).toHaveLength(1));
    await act(async () => {});
    expect(sent).toEqual([{ text: "점심은 국수로 하죠" }]);
  });
});
