import React from "react";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { RoomToolbar } from "./RoomToolbar.jsx";
import { deriveRoomStatus, participantSummary } from "./roomStatus.js";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* 방 툴바 (D-575) — 상태 정본 하나 · 동작 줄 하나.
 *
 * 못박는 것: 상태 칩이 DOM 에 정확히 하나 · 방장 / 참가자 / 관전자의 단계별 동작 · 결과 보기는 끝난 결과가 있고 대화 상자가 닫혔을
 * 때만 · 넘침 메뉴에 방 파하기(방장) · 전체 화면 변형은 설정 · 나가기 · 넘침을 숨기고 「전체 화면 종료」(aria-pressed). */

const mutation = () => ({ mutate: vi.fn(), isPending: false });

function makeC(over = {}) {
  const room = { id: "r1", game_type: "random_draw", status: "waiting", player_count: 2, max_players: 8, host_user_id: "u1", ...(over.room || {}) };
  const you = { user_id: "u1", role: "host", is_host: true, ready: false, in_room: true, ...(over.you || {}) };
  const members = over.members || [{ user_id: "u1", role: "host" }, { user_id: "u2", role: "player" }];
  const gstate = over.gstate || {};
  return {
    room, you, members, gstate, isTournament: false, isDraw: room.game_type === "random_draw", isMarble: false, drawWinners: [],
    marble: { isMarble: false, waiting: true, stageKey: "wheel" },
    status: deriveRoomStatus({ room, gstate, you }), summary: participantSummary({ room, gstate, members }),
    reveal: { key: null, phase: "none", open: false, openDialog: vi.fn(), closeDialog: vi.fn(), ...(over.reveal || {}) },
    submissionActive: false, remaining: null, submittedCount: 0, activePlayers: members,
    mutations: { leave: mutation(), disband: mutation() },
    disbandWithConfirm: vi.fn(),
    actions: { primary: null, ready: null, showResult: false, settings: false, disband: !!you.is_host, ...(over.actions || {}) },
  };
}

function renderBar(c, fs = { active: false, toggle: vi.fn() }) {
  return render(
    <ThemeModeProvider><ToastProvider><ConfirmProvider>
      <RoomToolbar c={c} fs={fs} onOpenSettings={vi.fn()} />
    </ConfirmProvider></ToastProvider></ThemeModeProvider>
  );
}

describe("상태 칩", () => {
  it("상태 낱말은 DOM 에 정확히 한 번이다", () => {
    renderBar(makeC());
    expect(document.querySelectorAll("[data-room-status]")).toHaveLength(1);
    expect(screen.getAllByText("대기 중")).toHaveLength(1);
    expect(screen.getByText("참여 2/8")).toBeInTheDocument();
  });

  it("관전자는 「관전 중」이 따로 선다", () => {
    renderBar(makeC({ you: { user_id: "u9", role: "spectator", is_host: false } }));
    expect(screen.getByText("관전 중")).toBeInTheDocument();
  });
});

describe("동작", () => {
  it("방장 대기: 주 동작 + 전체 화면 + 나가기 + 넘침(방 파하기)", () => {
    const start = vi.fn();
    const c = makeC({ actions: { primary: { key: "start", label: "추첨 시작", onClick: start } } });
    renderBar(c);
    fireEvent.click(screen.getByRole("button", { name: "추첨 시작" }));
    expect(start).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "전체 화면" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "나가기" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "방 동작 더 보기" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "방 파하기" }));
    expect(c.disbandWithConfirm).toHaveBeenCalled();
  });

  it("참가자 대기(추첨): 준비 · 준비 해제, 방 파하기 없음", () => {
    const c = makeC({ you: { user_id: "u2", role: "player", is_host: false }, actions: { ready: { key: "ready", label: "준비", on: false, onClick: vi.fn() } } });
    renderBar(c);
    expect(screen.getByRole("button", { name: "준비" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "방 동작 더 보기" })).toBeNull();
  });

  it("결과 보기는 끝난 결과가 있고 대화 상자가 닫혔을 때만", () => {
    const open = makeC({ room: { status: "finished" }, reveal: { key: "r1:3", phase: "revealed", open: true }, actions: { showResult: false } });
    const { unmount } = renderBar(open);
    expect(screen.queryByRole("button", { name: "결과 보기" })).toBeNull();
    unmount();
    const closed = makeC({ room: { status: "finished" }, reveal: { key: "r1:3", phase: "revealed", open: false }, actions: { showResult: true } });
    renderBar(closed);
    fireEvent.click(screen.getByRole("button", { name: "결과 보기" }));
    expect(closed.reveal.openDialog).toHaveBeenCalled();
    expect(screen.getAllByText("종료")).toHaveLength(1);
  });

  it("전체 화면 변형 — 설정 · 나가기 · 넘침을 숨기고 「전체 화면 종료」", () => {
    const toggle = vi.fn();
    const c = makeC({ actions: { settings: true, primary: { key: "start", label: "경주 시작", onClick: vi.fn() } } });
    renderBar(c, { active: true, toggle });
    expect(screen.queryByRole("button", { name: "설정" })).toBeNull();
    expect(screen.queryByRole("button", { name: "나가기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "방 동작 더 보기" })).toBeNull();
    const exit = screen.getByRole("button", { name: "전체 화면 종료" });
    expect(exit).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(exit);
    expect(toggle).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "경주 시작" })).toBeInTheDocument();
  });
});
