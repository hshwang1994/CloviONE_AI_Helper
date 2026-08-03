import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 게임방 계약 테스트 — 축포와 접근성.
 *
 * 이 화면은 업무 위험이 가장 낮아서 연출을 얹은 화면이다. 그래서 오히려 접근성이 문제가 된다:
 * canvas-confetti는 **JS로** 캔버스를 그린다. theme.js의 전역 `prefers-reduced-motion` CSS
 * 규칙은 여기에 닿지 않는다 — 화면 코드가 직접 판단해서 쏘지 않아야 한다. 라이브러리의
 * disableForReducedMotion 옵션 하나에 접근성을 통째로 맡기면, 옵션 이름이 바뀌거나 우리가
 * 다른 연출을 추가하는 순간 조용히 무너진다.
 *
 * 동시에 '동작 최소화'는 **연출만** 끄는 것이지 정보를 끄는 게 아니다 — 당첨자 이름은 어떤
 * 설정에서도 똑같이 보여야 한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
const confettiMock = vi.fn();
vi.mock("canvas-confetti", () => ({ default: (...args) => confettiMock(...args) }));

import { GameRoom, prefersReducedMotion } from "./GameRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function setMatchMedia(reduce) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: /prefers-reduced-motion/.test(query) ? reduce : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

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

// 랜덤 추첨이 끝나 당첨자가 확정된 상태(= 축포 트리거 조건).
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

beforeEach(() => {
  apiMock.mockReset();
  confettiMock.mockReset();
  apiMock.mockResolvedValue(FINISHED_DRAW);
});

afterEach(() => {
  delete window.matchMedia;
});

describe("prefers-reduced-motion", () => {
  it("동작 최소화를 켠 사용자에게는 축포를 쏘지 않는다", async () => {
    setMatchMedia(true);
    renderRoom();

    // 결과는 그대로 보인다 — 연출만 끄는 것이지 정보를 끄는 게 아니다.
    // ('박개발'은 참여자 목록에도 있으므로 여러 번 나온다 — 당첨 무대에 나오는지가 요점이다.)
    expect(await screen.findByText("당첨")).toBeInTheDocument();
    expect(screen.getAllByText("박개발").length).toBeGreaterThan(1);
    expect(confettiMock).not.toHaveBeenCalled();
  });

  it("기본 사용자에게는 축포를 쏘되 결과당 한 번만 쏜다", async () => {
    setMatchMedia(false);
    renderRoom();

    await screen.findByText("당첨");
    // 축포는 가운데 → 왼쪽 → 오른쪽으로 나눠 터진다(뒤 두 발은 예약된 타이머다).
    // 여기서 끝까지 기다리지 않으면 그 타이머가 **다음 테스트** 도중에 발사돼 엉뚱한 곳에서 잡힌다.
    await new Promise((r) => setTimeout(r, 400));
    const burst = confettiMock.mock.calls.length;
    expect(burst).toBeGreaterThan(0);

    // deriveCelebrateKey가 같은 결과에 같은 키를 주므로 1.2초 폴링을 한 바퀴 돌아도 재발화하지 않는다.
    await new Promise((r) => setTimeout(r, 1500));
    expect(confettiMock.mock.calls.length).toBe(burst);
  });

  it("matchMedia가 없는 환경에서도 예외 없이 false를 돌려준다", () => {
    delete window.matchMedia;
    expect(prefersReducedMotion()).toBe(false);
  });
});

describe("승자가 없는 결과에는 축포를 쓰지 않는다", () => {
  it("팀 나누기는 결과가 있어도 '승자'가 아니므로 축포가 없다", async () => {
    setMatchMedia(false);
    apiMock.mockResolvedValue({
      ...FINISHED_DRAW,
      room: { ...FINISHED_DRAW.room, game_type: "team_split", title: "축구 팀 나누기" },
      state: { result: { teams: [[{ user_id: "u1", name: "김운영" }], [{ user_id: "u2", name: "박개발" }]] } },
    });
    renderRoom();

    expect(await screen.findByText("1팀")).toBeInTheDocument();
    expect(confettiMock).not.toHaveBeenCalled();
  });
});
