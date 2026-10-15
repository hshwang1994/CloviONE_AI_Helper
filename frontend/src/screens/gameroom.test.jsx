import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 게임방 계약 테스트 — 축포와 접근성, 그리고 발표 단위 (D-563).
 *
 * 이 화면은 업무 위험이 가장 낮아서 연출을 얹은 화면이다. 그래서 오히려 접근성이 문제가 된다:
 * canvas-confetti는 **JS로** 캔버스를 그린다. theme.js의 전역 `prefers-reduced-motion` CSS
 * 규칙은 여기에 닿지 않는다 — 화면 코드가 직접 판단해서 쏘지 않아야 한다. 라이브러리의
 * disableForReducedMotion 옵션 하나에 접근성을 통째로 맡기면, 옵션 이름이 바뀌거나 우리가
 * 다른 연출을 추가하는 순간 조용히 무너진다.
 *
 * 동시에 '동작 최소화'는 **연출만** 끄는 것이지 정보를 끄는 게 아니다 — 당첨자 이름은 어떤
 * 설정에서도 똑같이 보여야 한다.
 *
 * 발표 단위(D-563 · D-576): 축포는 **결과가 확정되는 순간**(진행 중 → 종료) 한 번이다. 이미 끝난 방을 열거나 새로고침한 사람은
 * 발표를 본 것이 아니므로 결과 대화 상자가 공개 상태로 바로 열리고 축포가 없다. 같은 결과를 폴링으로 다시 받아도 다시 터지지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
const confettiMock = vi.fn();
vi.mock("canvas-confetti", () => ({ default: (...args) => confettiMock(...args) }));

import { GameRoom } from "./GameRoom.jsx";
import { resetBurstCooldown } from "../ui/celebrate.js";
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

// 랜덤 추첨이 끝나 당첨자가 확정된 상태(= 발표 조건).
const FINISHED_DRAW = {
  room: { id: "r1", title: "점심 커피 추첨", game_type: "random_draw", status: "finished", player_count: 2, max_players: 8, host_user_id: "u1" },
  you: { user_id: "u1", in_room: true, is_host: true, role: "player", ready: true },
  members: [
    { user_id: "u1", name: "김운영", role: "host" },
    { user_id: "u2", name: "박개발", role: "player" },
  ],
  state: { result: [{ user_id: "u2", name: "박개발" }] },
  events: [],
  seq: 2,
  result_seq: 2,
  now: "2026-10-12T09:00:00+00:00",
};
// 같은 방이 아직 진행 중인 상태 — 첫 폴링이 이것이고 다음 폴링이 결과다(= 「확정되는 순간」).
const PLAYING_DRAW = { ...FINISHED_DRAW, room: { ...FINISHED_DRAW.room, status: "playing" }, state: {}, seq: 1, result_seq: null };

/* 첫 요청은 진행 중, 그 뒤 요청은 결과. 폴링(1.2초)이 결과를 가져오는 순간이 발표다. */
function playingThenFinished() {
  let n = 0;
  apiMock.mockImplementation(() => { n += 1; return Promise.resolve(n === 1 ? PLAYING_DRAW : FINISHED_DRAW); });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

beforeEach(() => {
  // 축포는 한 벌이 끝나기 전 두 번째 요청을 접는다(ui/celebrate.js 의 겹침 방지).
  // 그 기억은 모듈 전역이라 시험 사이에 새므로 여기서 비운다.
  resetBurstCooldown();
  apiMock.mockReset();
  confettiMock.mockReset();
  apiMock.mockResolvedValue(FINISHED_DRAW);
});

afterEach(() => {
  delete window.matchMedia;
});

describe("축포는 OS 설정과 무관하게 터진다", () => {
  /* 🔴 정책이 뒤집혔다 (2026-09-03 — `ui/motion.js` 머리말). 예전에는 이 자리가
   * 「동작 최소화면 안 쏜다」를 못박았다. 지금은 **쏜다** — 이 조직의 Windows 설정을
   * 읽은 Firefox 에서 축포가 통째로 사라진 것이 그 판정 때문이었다. */
  it("동작 최소화를 켠 사용자에게도 축포를 쏜다", async () => {
    setMatchMedia(true);
    playingThenFinished();
    renderRoom();

    // 결과는 폴링 한 바퀴(1.2초) 뒤 발표 전환(0.8초)을 거쳐 공개된다.
    // ('박개발'은 참여자 목록에도 있으므로 여러 번 나온다 — 당첨 자리에 나오는지가 요점이다.)
    expect(await screen.findByText("당첨을 축하합니다!", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getAllByText("박개발").length).toBeGreaterThan(1);
    await waitFor(() => expect(confettiMock).toHaveBeenCalled(), { timeout: 3000 });
    // 뒤 두 발은 예약된 타이머다 — 여기서 걷지 않으면 다음 시험 도중에 발사된다.
    await sleep(400);
  });

  it("기본 사용자에게는 축포를 쏘되 결과당 한 번만 쏜다", async () => {
    setMatchMedia(false);
    playingThenFinished();
    renderRoom();

    await screen.findByText("당첨을 축하합니다!", {}, { timeout: 5000 });
    await waitFor(() => expect(confettiMock).toHaveBeenCalled(), { timeout: 3000 });
    // 축포는 가운데 → 왼쪽 → 오른쪽으로 나눠 터진다(뒤 두 발은 예약된 타이머다).
    await sleep(400);
    const burst = confettiMock.mock.calls.length;
    expect(burst).toBeGreaterThan(0);

    // 같은 결과 번호(result_seq)를 폴링으로 다시 받아도 재발화하지 않는다.
    await sleep(1500);
    expect(confettiMock.mock.calls.length).toBe(burst);
  });

  it("matchMedia 가 아예 없는 환경에서도 축포는 터진다", async () => {
    delete window.matchMedia;
    playingThenFinished();
    renderRoom();
    await screen.findByText("당첨을 축하합니다!", {}, { timeout: 5000 });
    await waitFor(() => expect(confettiMock).toHaveBeenCalled(), { timeout: 3000 });
    await sleep(400);
  });
});

describe("발표 단위 (D-563)", () => {
  it("이미 끝난 방을 열면 결과는 바로 보이지만 축포는 없다 — 발표를 본 것이 아니다", async () => {
    setMatchMedia(false);
    renderRoom();
    expect(await screen.findByText("당첨을 축하합니다!")).toBeInTheDocument();
    expect(document.querySelector('[data-result-panel="revealed"]')).not.toBeNull();
    await sleep(1500);
    expect(confettiMock).not.toHaveBeenCalled();
  });

  it("발표 전환 동안은 「결과를 발표합니다」이고 당첨자는 아직 없다", async () => {
    setMatchMedia(false);
    playingThenFinished();
    renderRoom();
    expect(await screen.findByText(/결과를 발표합니다/, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText("당첨을 축하합니다!")).toBeNull();
    expect(await screen.findByText("당첨을 축하합니다!", {}, { timeout: 3000 })).toBeInTheDocument();
    await sleep(400);
  });
});

describe("결과 대화 상자의 다시 열기 · 초기화 (D-576)", () => {
  it("닫았다가 [결과 보기]로 다시 열면 발표 · 축포 없이 공개 상태 그대로다", async () => {
    setMatchMedia(false);
    playingThenFinished();
    renderRoom();
    await screen.findByText("당첨을 축하합니다!", {}, { timeout: 5000 });
    await waitFor(() => expect(confettiMock).toHaveBeenCalled(), { timeout: 3000 });
    await sleep(400);
    const fired = confettiMock.mock.calls.length;
    const closes = within(screen.getByRole("dialog")).getAllByRole("button", { name: "닫기" });
    fireEvent.click(closes[closes.length - 1]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "결과 보기" }));
    expect(await screen.findByText("당첨을 축하합니다!")).toBeInTheDocument();
    expect(document.querySelector('[data-result-panel="revealed"]')).not.toBeNull();
    await sleep(1200);
    expect(confettiMock.mock.calls.length).toBe(fired);
  });

  it("초기화 뒤 새 결과(새 열쇠)는 다시 발표하고 축포를 쏜다 — 처음 연 방의 지난 결과는 쏘지 않는다", async () => {
    setMatchMedia(false);
    const waiting = { ...FINISHED_DRAW, room: { ...FINISHED_DRAW.room, status: "waiting" }, state: {}, seq: 3, result_seq: null };
    const again = { ...FINISHED_DRAW, seq: 5, result_seq: 5 };
    const seq = [FINISHED_DRAW, waiting];
    let n = 0;
    apiMock.mockImplementation(() => { n += 1; return Promise.resolve(seq[n - 1] || again); });
    renderRoom();
    await screen.findByText("당첨을 축하합니다!");
    expect(confettiMock).not.toHaveBeenCalled(); // 지난 결과 — 발표를 본 것이 아니다
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull(), { timeout: 4000 }); // 초기화 → 닫힘
    expect(await screen.findByText(/결과를 발표합니다/, {}, { timeout: 4000 })).toBeInTheDocument();
    await waitFor(() => expect(confettiMock).toHaveBeenCalled(), { timeout: 3000 });
    await sleep(400);
  });
});

describe("승자가 없는 결과에는 축포를 쓰지 않는다", () => {
  it("팀 나누기는 결과가 있어도 '승자'가 아니므로 축포가 없다", async () => {
    setMatchMedia(false);
    const teamFinished = {
      ...FINISHED_DRAW,
      room: { ...FINISHED_DRAW.room, game_type: "team_split", title: "축구 팀 나누기" },
      state: { result: { teams: [[{ user_id: "u1", name: "김운영" }], [{ user_id: "u2", name: "박개발" }]] } },
    };
    const teamPlaying = { ...teamFinished, room: { ...teamFinished.room, status: "playing" }, state: {}, seq: 1, result_seq: null };
    let n = 0;
    apiMock.mockImplementation(() => { n += 1; return Promise.resolve(n === 1 ? teamPlaying : teamFinished); });
    renderRoom();
    expect((await screen.findAllByText("1팀", {}, { timeout: 5000 })).length).toBeGreaterThan(0);
    await sleep(600);
    expect(confettiMock).not.toHaveBeenCalled();
  });
});
