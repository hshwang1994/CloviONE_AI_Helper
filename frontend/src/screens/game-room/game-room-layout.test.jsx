import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 놀이방 껍데기 (D-575) — 모드 · 레일 · 판 틀 · 전체 화면을 방 전체로 잰다. 실제 기하(픽셀)는 실브라우저 하네스(`games_e2e.py
 * --layout`)가 잰다 — 여기서는 모드 판정 · 배선 · 속성 계약이다.
 *
 *   1) 채움: 앱 틀에 채움을 등록하고 창이 기준을 넘으면 `fill`, 아니면 `flow`, md 미만은 `mobile`(탭 — 채팅 탭이 입력 칸을 보인다).
 *   2) 판 틀의 모서리는 8px 이다(숫자 `RADIUS.md` 를 `sx` 에 넣어 64px 이 되던 회귀).
 *   3) 참여자 40명이면 목록이 자기 칸(ScrollArea) 안에서 넘친다 — 채팅을 밀어내지 않는다.
 *   4) 전체 화면: 툴바 라벨이 바뀌고, 결과 대화 상자가 방 루트 안에 그려지고, 축포 캔버스는 전체 화면 동안만 루트 안에 선다.
 *   5) 전체 화면을 켜고 꺼도 경주 엔진을 다시 만들지 않는다(`createEngineClient` 한 번). */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("canvas-confetti", () => {
  const fn = vi.fn();
  fn.create = vi.fn(() => vi.fn());
  return { default: fn };
});
const engineCalls = { count: 0 };
vi.mock("./marble/engine/client.js", () => ({
  createEngineClient: vi.fn(async () => {
    engineCalls.count += 1;
    return {
      kind: "inline", init() {}, advance() {}, onReady() {}, onSnapshot() {}, onFinished() {}, onError() {}, terminate() {},
    };
  }),
}));

import { GameRoom } from "../GameRoom.jsx";
import { WORKSPACE_FILL_QUERY, WorkspaceShellContext, useWorkspaceShellState } from "../../ui/Workspace.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

let media = { fill: true, mobile: false, wide: true };
const realMatchMedia = window.matchMedia;

function Shell({ children }) {
  const ws = useWorkspaceShellState();
  return <WorkspaceShellContext.Provider value={ws.api}>{children}</WorkspaceShellContext.Provider>;
}

function renderRoom({ shell = true } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const inner = (
    <MemoryRouter initialEntries={["/games/r1"]}>
      <Routes><Route path="/games/:id" element={<GameRoom />} /></Routes>
    </MemoryRouter>
  );
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        {shell ? <Shell>{inner}</Shell> : inner}
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
}

const member = (i, role = "player") => ({ user_id: `u${i}`, name: `참여자${i}`, role, active: true, present: true });
const waitingDraw = (over = {}) => ({
  room: { id: "r1", title: "점심 추첨", game_type: "random_draw", status: "waiting", player_count: 2, max_players: 8, host_user_id: "u1" },
  you: { user_id: "u1", in_room: true, is_host: true, role: "host", ready: false },
  members: [member(1, "host"), member(2)], people: {}, state: {}, events: [], seq: 1, result_seq: null, now: new Date().toISOString(),
  ...over,
});
const finishedDraw = () => waitingDraw({
  room: { id: "r1", title: "점심 추첨", game_type: "random_draw", status: "finished", player_count: 2, max_players: 8, host_user_id: "u1" },
  state: { result: [{ user_id: "u2", name: "참여자2" }], pool: [{ user_id: "u1", name: "참여자1" }, { user_id: "u2", name: "참여자2" }] },
  seq: 3, result_seq: 3,
});

beforeEach(() => {
  media = { fill: true, mobile: false, wide: true };
  engineCalls.count = 0;
  apiMock.mockReset();
  apiMock.mockResolvedValue(waitingDraw());
  window.matchMedia = (query) => ({
    matches: query === WORKSPACE_FILL_QUERY ? media.fill
      : /max-width:899\.95px/.test(query) ? media.mobile
        : /min-width:58rem/.test(query) ? media.wide : false,
    media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  });
  HTMLCanvasElement.prototype.getContext = () => null;
});
afterEach(() => {
  window.matchMedia = realMatchMedia;
  delete HTMLElement.prototype.requestFullscreen;
  delete document.exitFullscreen;
  delete document.fullscreenElement;
});

describe("모드", () => {
  it("앱 틀에 채움을 등록하고 창이 기준을 넘으면 fill", async () => {
    renderRoom();
    await screen.findByRole("button", { name: "추첨 시작" });
    expect(document.querySelector('[data-game-room-layout="fill"]')).not.toBeNull();
    expect(document.querySelector('[data-room-rail="fill"]')).not.toBeNull();
  });

  it("창이 기준 밑이면 flow — 레일이 판 아래 두 칸", async () => {
    media.fill = false;
    renderRoom();
    await screen.findByRole("button", { name: "추첨 시작" });
    expect(document.querySelector('[data-game-room-layout="flow"]')).not.toBeNull();
    expect(document.querySelector('[data-room-rail="flow"]')).not.toBeNull();
  });

  it("md 미만은 mobile — 「참여자 | 채팅」 탭에서 채팅을 고르면 입력 칸이 보인다", async () => {
    media = { fill: false, mobile: true, wide: false };
    renderRoom();
    await screen.findByRole("button", { name: "추첨 시작" });
    expect(document.querySelector('[data-game-room-layout="mobile"]')).not.toBeNull();
    const chatPane = document.querySelector('[data-rail-pane="chat"]');
    expect(chatPane).toHaveAttribute("hidden");
    fireEvent.click(screen.getByRole("tab", { name: "채팅" }));
    expect(chatPane).not.toHaveAttribute("hidden");
    expect(within(chatPane).getByRole("textbox", { name: "메시지 입력" })).toBeVisible();
  });
});

describe("판 틀 · 레일", () => {
  it("판 틀의 모서리는 8px 이다(64px 회귀 금지)", async () => {
    renderRoom();
    await screen.findByRole("button", { name: "추첨 시작" });
    const frame = document.querySelector("[data-board-frame]");
    expect(getComputedStyle(frame).borderRadius).toBe("8px");
  });

  it("참여자 40명이면 목록이 자기 칸 안에서 넘친다", async () => {
    const many = Array.from({ length: 40 }, (_, i) => member(i + 1, i === 0 ? "host" : "player"));
    apiMock.mockResolvedValue(waitingDraw({ members: many, room: { ...waitingDraw().room, player_count: 40, max_players: 50 } }));
    const sh = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight");
    const ch = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight");
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get() { return this.classList.contains("k-scrollarea") ? 2000 : 0; } });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get() { return this.classList.contains("k-scrollarea") ? 208 : 0; } });
    try {
      renderRoom();
      await screen.findByRole("button", { name: "추첨 시작" });
      await waitFor(() => expect(document.querySelector('.k-scrollarea[data-overflows="true"]')).not.toBeNull());
    } finally {
      if (sh) Object.defineProperty(HTMLElement.prototype, "scrollHeight", sh);
      if (ch) Object.defineProperty(HTMLElement.prototype, "clientHeight", ch);
    }
  });
});

describe("전체 화면", () => {
  function installNative() {
    let current = null;
    Object.defineProperty(document, "fullscreenElement", { configurable: true, get: () => current });
    HTMLElement.prototype.requestFullscreen = vi.fn(function req() { current = this; document.dispatchEvent(new Event("fullscreenchange")); return Promise.resolve(); });
    document.exitFullscreen = vi.fn(() => { current = null; document.dispatchEvent(new Event("fullscreenchange")); return Promise.resolve(); });
  }

  it("툴바 라벨이 바뀌고, 결과 대화 상자 · 축포 캔버스가 방 루트 안에 선다", async () => {
    installNative();
    apiMock.mockResolvedValue(finishedDraw());
    renderRoom();
    const dialog = await screen.findByRole("dialog");
    const root = document.querySelector("[data-game-room-layout]");
    expect(root.contains(dialog)).toBe(false); // 평소엔 문서의 포털
    expect(document.querySelector("[data-celebrate-canvas]")).toBeNull();
    // 대화 상자를 닫고 툴바에서 전체 화면 — 결과 보기로 다시 연다.
    const closes = within(dialog).getAllByRole("button", { name: "닫기" });
    fireEvent.click(closes[closes.length - 1]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    expect(root).toHaveAttribute("data-fullscreen", "on");
    expect(screen.getByRole("button", { name: "전체 화면 종료" })).toHaveAttribute("aria-pressed", "true");
    const canvas = document.querySelector("[data-celebrate-canvas]");
    expect(canvas).not.toBeNull();
    expect(root.contains(canvas)).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "결과 보기" }));
    const again = await screen.findByRole("dialog");
    expect(root.contains(again)).toBe(true);
    // 전체 화면에서는 설정 · 나가기 · 넘침이 없다(그 메뉴 · 확인 창은 문서의 포털이라 가려진다).
    expect(screen.queryByRole("button", { name: "나가기", hidden: true })).toBeNull();
    expect(screen.queryByRole("button", { name: "방 동작 더 보기", hidden: true })).toBeNull();
  });

  it("켜고 꺼도 경주 엔진을 다시 만들지 않는다", async () => {
    installNative();
    const parts = [{ key: "u:u1", name: "참여자1", user_id: "u1" }, { key: "n:a", name: "자유", user_id: null }];
    apiMock.mockResolvedValue(waitingDraw({
      room: { id: "r1", title: "구슬", game_type: "marble_race", status: "playing", player_count: 1, max_players: 8, host_user_id: "u1" },
      state: {
        phase: "running", race_id: "0123456789abcdef0123456789abcdef", seed: "00112233aabbccdd", started_at: new Date().toISOString(),
        speed: 1, map: "wheel", winners_n: 1, pick_last: false, participants: parts, submissions: [], result: null, finalized_at: null,
        config: { participants: parts, winners: 1, map: "wheel", speed: 1 }, you_submitted: false, announceable: false,
      },
    }));
    renderRoom();
    await screen.findByRole("button", { name: "전체 화면" });
    await waitFor(() => expect(engineCalls.count).toBe(1));
    const stage = document.querySelector("[data-marble-stage]");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면 종료" })); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "전체 화면" })); });
    expect(engineCalls.count).toBe(1);
    expect(document.querySelector("[data-marble-stage]")).toBe(stage);
  });
});
