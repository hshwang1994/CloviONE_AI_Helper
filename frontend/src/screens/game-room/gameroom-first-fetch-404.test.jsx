import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 방이 사라진 뒤 공유된 옛 /games/<id> 링크로 처음 들어오는 경우(§useGameRoomController.js) —
 * 그 방의 "첫" fetch 자체가 404로 온다. react-query에는 아직 한 번도 성공한 데이터가 없으니
 * state.data는 undefined인 채 isError만 true다. 고치기 전에는 이 조합이 두 조기 return 가드를
 * 모두 지나쳐(notFound라서 "error" phase로도, isPending도 이미 false라 "pending" phase로도 안
 * 빠짐) `const { room } = state.data`가 undefined를 구조분해해 "Cannot destructure property
 * 'room' of 'state.data' as it is undefined" 로 화면이 통째로 크래시했다.
 *
 * 대비되는 "중간 폴링 404"(방장이 파한 직후 남은 참여자의 다음 폴링)는 react-query가 이전
 * 성공 데이터를 그대로 들고 있어 이 경로를 타지 않는다 — 이미 정상 동작해서 여기서는 다루지
 * 않는다(gameroom-host-handoff.test.jsx 등 다른 방 상태 폴링 흐름과 겹치지 않게, 첫 fetch부터
 * 404인 경우만 재현한다). */

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
            <MemoryRouter initialEntries={["/games/gone-room"]}>
              <Routes>
                <Route path="/games/:id" element={<GameRoom />} />
                <Route path="/games" element={<div>게임 목록</div>} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

function notFoundError() {
  const err = new Error("요청한 항목을 찾을 수 없습니다.");
  err.status = 404;
  return err;
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockRejectedValue(notFoundError());
});

afterEach(() => {
  delete window.matchMedia;
});

describe("사라진 방으로 첫 진입", () => {
  it("첫 fetch가 404여도 크래시하지 않고 '방이 사라졌습니다' 안내 후 목록으로 이동한다", async () => {
    renderRoom();

    // 고치기 전에는 렌더 도중 state.data를 구조분해하다 던져서 이 지점에 닿지 못했다.
    expect(await screen.findByText("방이 사라졌습니다.")).toBeInTheDocument();
    expect(await screen.findByText("게임 목록")).toBeInTheDocument();
  });
});
