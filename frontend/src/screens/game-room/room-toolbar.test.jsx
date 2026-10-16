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
 * 때만 · 넘침 메뉴에 방 파하기(방장) · 전체 화면 변형은 설정 · 나가기 · 넘침을 숨기고 「전체 화면 종료」(aria-pressed).
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

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
    fireEvent.click(screen.getByRole("menuitem", { name: "게임방 종료" }));
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

/* 맵 선택 (D-593) — 방장만, 대기 중에만 쓴다. 「다시 하기」 뒤도 대기다. 진행 · 끝난 방에서는 막고 까닭을 보인다. */
function makeMarble({ host = true, status = "waiting", waiting = true, stageKey = "wheel" } = {}) {
  const c = makeC({
    room: { game_type: "marble_race", status },
    you: host ? { user_id: "u1", role: "host", is_host: true } : { user_id: "u2", role: "player", is_host: false },
  });
  const marbleConfig = { mutate: vi.fn(), mutateAsync: vi.fn(() => Promise.resolve({})), isPending: false };
  return {
    ...c, isMarble: true, isHost: host, isDraw: false,
    marble: { isMarble: true, waiting, stageKey },
    mutations: { ...c.mutations, marbleConfig },
  };
}

describe("맵 선택 (D-593)", () => {
  it("방장 · 대기 중: 메뉴에 맵 넷이 서고 지금 맵이 표시되며, 고르면 그 맵을 서버에 보낸다", async () => {
    const c = makeMarble();
    renderBar(c);
    const button = screen.getByRole("button", { name: "맵 선택" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    const items = await screen.findAllByRole("menuitemradio");
    expect(items.map((el) => el.textContent)).toEqual(["운명의 바퀴", "탐욕의 항아리", "비눗방울", "밤을 달리다"]);
    expect(screen.getByRole("menuitemradio", { name: "운명의 바퀴" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("menuitemradio", { name: "탐욕의 항아리" }));
    expect(c.mutations.marbleConfig.mutateAsync).toHaveBeenCalledWith({ map: "pot" });
  });

  it("같은 맵을 다시 고르면 요청을 보내지 않는다", async () => {
    const c = makeMarble({ stageKey: "bubble" });
    renderBar(c);
    fireEvent.click(screen.getByRole("button", { name: "맵 선택" }));
    fireEvent.click(await screen.findByRole("menuitemradio", { name: "비눗방울" }));
    expect(c.mutations.marbleConfig.mutateAsync).not.toHaveBeenCalled();
  });

  it("🔴 경주 중에는 막히고 까닭이 단추에 연결된다 — 지우지 않는다", () => {
    renderBar(makeMarble({ status: "playing", waiting: false, stageKey: "yoru" }));
    const button = screen.getByRole("button", { name: "맵 선택" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(/경주 중에는 맵을 바꿀 수 없습니다/);
  });

  it("끝난 방은 「다시 하기」 뒤에 바꿀 수 있다고 말한다", () => {
    renderBar(makeMarble({ status: "finished", waiting: false }));
    expect(screen.getByRole("button", { name: "맵 선택" })).toHaveAccessibleDescription("'다시 하기'를 누른 뒤 변경할 수 있습니다.");
  });

  it("참가자에게는 맵 선택이 없다(서버도 방장만 받는다)", () => {
    renderBar(makeMarble({ host: false }));
    expect(screen.queryByRole("button", { name: "맵 선택" })).toBeNull();
  });

  it("전체 화면에서는 숨긴다 — 메뉴가 문서의 포털이라 가려진다", () => {
    renderBar(makeMarble(), { active: true, toggle: vi.fn() });
    expect(screen.queryByRole("button", { name: "맵 선택" })).toBeNull();
  });
});
