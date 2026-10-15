import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { GameStage } from "./GameStage.jsx";
import { tileSize } from "./boards/PersonTile.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* 판의 얼굴 (D-577) — 사람이 서는 판마다 사람 수만큼 얼굴(`.k-avatar`)이 있고, 방을 나간 사람도 신원 지도(`people`)로 이름 · 얼굴이 풀린다.
 * 대기 판도 점선 한 줄이 아니라 얼굴 격자다(판이 접히지 않는다, D-575). */

const people = {
  u1: { user_id: "u1", name: "김운영" },
  u2: { user_id: "u2", name: "박개발" },
  u9: { user_id: "u9", name: "나간사람" },
};

function makeC(over) {
  const room = { id: "r1", title: "방", game_type: "random_draw", status: "finished", host_user_id: "u1", ...(over.room || {}) };
  return {
    room, you: { user_id: "u1", role: "host", in_room: true }, members: [{ user_id: "u1", name: "김운영", role: "host" }, { user_id: "u2", name: "박개발", role: "player" }],
    people, gstate: {}, isDraw: false, isTeam: false, isLadder: false, isVote: false, isNumber: false, isRps: false, isQuiz: false, isMarble: false,
    drawWinners: [], teams: [], ladderAssignments: [], reveal: { phase: "revealed" }, mutations: { vote: {}, pick: {}, rps: {}, quizAnswer: {} },
    voteOptionSx: () => ({}), liveScores: [],
    ...over,
    room, // 부분 방(`over.room`)이 합친 방을 덮지 않게 맨 뒤에 둔다
  };
}

function renderStage(c) {
  return render(
    <ThemeModeProvider><ToastProvider><ConfirmProvider>
      <GameStage c={c} />
    </ConfirmProvider></ToastProvider></ThemeModeProvider>
  );
}

const avatars = () => document.querySelectorAll(".k-avatar").length;

describe("판마다 얼굴", () => {
  it("대기 판 — 참여자 얼굴 격자 + 문장(관전자는 빼고)", () => {
    renderStage(makeC({
      room: { status: "waiting" }, isDraw: true,
      members: [{ user_id: "u1", name: "김운영", role: "host" }, { user_id: "u2", name: "박개발", role: "player" }, { user_id: "u3", name: "관전", role: "spectator" }],
    }));
    expect(document.querySelector("[data-waiting-board]")).not.toBeNull();
    expect(avatars()).toBe(2);
    expect(screen.getByText("참여자가 모이면 방장이 추첨을 시작합니다.")).toBeInTheDocument();
  });

  it("추첨 판 — 대상 전원의 얼굴, 나간 당첨자도 풀린다", () => {
    renderStage(makeC({
      isDraw: true, drawWinners: [{ user_id: "u9", name: "나간사람" }],
      gstate: { pool: [{ user_id: "u1", name: "김운영" }, { user_id: "u2", name: "박개발" }, { user_id: "u9", name: "나간사람" }] },
    }));
    expect(avatars()).toBe(3);
    const winner = document.querySelector('[data-person-tile="winner"]');
    expect(within(winner).getByText("나간사람")).toBeInTheDocument();
    expect(screen.getByText("3명 중 1명을 뽑았습니다.")).toBeInTheDocument();
  });

  it("팀 판 — 사람 줄마다 얼굴", () => {
    renderStage(makeC({ room: { game_type: "team_split" }, isTeam: true, teams: [[{ user_id: "u1", name: "김운영" }], [{ user_id: "u2", name: "박개발" }, { user_id: "u9", name: "나간사람" }]] }));
    expect(avatars()).toBe(3);
    expect(screen.getByText("3명을 2팀으로 나눴습니다.")).toBeInTheDocument();
  });

  it("사다리 판 — 열 머리에 얼굴", () => {
    renderStage(makeC({
      room: { game_type: "ladder" }, isLadder: true,
      ladderAssignments: [{ user_id: "u1", name: "김운영", outcome: "당첨" }, { user_id: "u9", name: "나간사람", outcome: "꽝" }],
      gstate: { result: { columns: [{ user_id: "u1", name: "김운영" }, { user_id: "u9", name: "나간사람" }], outcomes: ["당첨", "꽝"], rungs: [], rows: 6 } },
    }));
    expect(avatars()).toBe(2);
  });

  it("숫자 · 손 · 점수 판", () => {
    const { unmount } = renderStage(makeC({
      room: { game_type: "number" }, isNumber: true,
      numResult: { winner: { user_id: "u9", name: "나간사람", number: 2 }, picks: [{ user_id: "u1", name: "김운영", number: 5 }, { user_id: "u9", name: "나간사람", number: 2 }] },
    }));
    expect(avatars()).toBe(2);
    unmount();
    const r2 = renderStage(makeC({
      room: { game_type: "rps" }, isRps: true,
      rpsResult: { outcome: "win", win_choice: "바위", winners: [{ user_id: "u1", name: "김운영" }], reveal: [{ user_id: "u1", name: "김운영", choice: "바위" }, { user_id: "u2", name: "박개발", choice: "가위" }] },
    }));
    expect(avatars()).toBe(2);
    r2.unmount();
    const r3 = renderStage(makeC({
      room: { game_type: "rps" }, isRps: true,
      rpsResult: { mode: "tournament", champion: { user_id: "u1", name: "김운영" }, rounds: [[{ a: "u1", b: "u9", a_name: "김운영", b_name: "나간사람", winner: "u1" }]] },
    }));
    expect(avatars()).toBe(2); // 「얼굴 — vs — 얼굴」
    r3.unmount();
    renderStage(makeC({
      room: { game_type: "quiz" }, isQuiz: true,
      quizResult: { total_rounds: 2, scoreboard: [{ user_id: "u1", name: "김운영", score: 2 }, { user_id: "u9", name: "나간사람", score: 1 }], winner_ids: ["u1"] },
    }));
    expect(avatars()).toBe(2);
    expect(document.querySelector('[data-score-row="winner"]')).not.toBeNull();
  });
});

describe("판 크기에 맞춘 얼굴 크기 (tileSize)", () => {
  /* 실측 판 크기: 1366 채움 734 × 509 · 1024 흐름 728 × 410 · 390 전화 358 × 268. 칸 수는 격자 칸의 최대 폭으로 센다. */
  it("판을 모르면(결과 대화 상자의 상세) 사람 수만 본다", () => {
    expect(tileSize(2)).toBe("xl");
    expect(tileSize(12)).toBe("lg");
    expect(tileSize(40)).toBe("md");
    expect(tileSize(2, { width: 0, height: 0 })).toBe("xl");
  });

  it("전화 판에서 두 사람은 72px 세로 두 칸이 아니라 40px 한 줄이다", () => {
    expect(tileSize(2, { width: 358, height: 268 })).toBe("lg");
    expect(tileSize(2, { width: 358, height: 268 }, "tall")).toBe("lg");
  });

  it("넓은 판은 그대로 크게 — 1366 · 1024 에서 여섯까지 72px", () => {
    expect(tileSize(2, { width: 734, height: 509 })).toBe("xl");
    expect(tileSize(6, { width: 734, height: 509 })).toBe("xl");
    expect(tileSize(6, { width: 728, height: 410 })).toBe("xl");
    expect(tileSize(12, { width: 734, height: 509 })).toBe("lg");
  });

  it("키 큰 칸(숫자 · 손)은 들어가는 크기까지 내리고, 아무것도 안 들어가면 가장 작은 크기다", () => {
    expect(tileSize(6, { width: 728, height: 410 }, "tall")).toBe("lg");
    expect(tileSize(12, { width: 734, height: 509 }, "tall")).toBe("md");
    expect(tileSize(24, { width: 358, height: 268 })).toBe("md");
  });
});
