import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

vi.mock("canvas-confetti", () => ({ default: vi.fn() }));

import { ResultDialog } from "./ResultDialog.jsx";
import { buildResultModel, objectParticle } from "./resultModel.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* 결과 대화 상자 (D-576) — 여덟 게임의 결과 발표가 같은 상자 하나다.
 *
 * 못박는 것: 발표 단계는 「결과를 발표합니다」뿐이고 당첨자가 아직 없다 · 한 명은 영웅 자리(「당첨을 축하합니다!」 · 96px 얼굴 · 이름 ·
 * 표지 · 문장), 순위가 있는 여럿은 시상대, 순위 없는 여럿은 격자(12명 넘으면 목록), 승자가 없으면 제목과 문장만 · 상세는 접는 칸 ·
 * 다시 하기는 방장만 · 마스코트가 없다 · 결과 복사. 그리고 게임마다의 문장(`buildResultModel`). */

const reveal = (phase = "revealed", over = {}) => ({ key: "r:1", phase, open: true, openDialog: vi.fn(), closeDialog: vi.fn(), ...over });

function renderDialog(props) {
  return render(
    <ThemeModeProvider>
      <ToastProvider>
        <ConfirmProvider>
          <ResultDialog isHost={false} onReplay={vi.fn()} {...props} />
        </ConfirmProvider>
      </ToastProvider>
    </ThemeModeProvider>
  );
}

const person = (id, name) => ({ id, name, user_id: id, person: { user_id: id, name }, kind: "person" });
const single = {
  gameType: "random_draw", game: "랜덤 추첨", mood: "win", heroTitle: "당첨을 축하합니다!", headline: "당첨자를 발표합니다",
  sentence: "5명 중 1명을 뽑았습니다.", winners: [person("u2", "박개발")], ranked: false, winnerLabel: "당첨",
  detail: null, detailLabel: "전체 결과", detailDefaultOpen: false, copyText: "랜덤 추첨 결과\n당첨: 박개발", note: null, size: "md",
};

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true });
});

describe("단계", () => {
  it("발표 중엔 「결과를 발표합니다」뿐이고 당첨자는 아직 없다", () => {
    renderDialog({ model: single, reveal: reveal("announcing") });
    const dialog = screen.getByRole("dialog", { name: "랜덤 추첨 결과 발표" });
    expect(within(dialog).getByText(/결과를 발표합니다/)).toBeInTheDocument();
    expect(document.querySelector('[data-result-panel="announcing"]')).not.toBeNull();
    expect(within(dialog).queryByText("박개발")).toBeNull();
    expect(within(dialog).queryByRole("button", { name: "결과 복사" })).toBeNull();
  });

  it("한 명 — 영웅 자리: 축하 문장 · 96px 얼굴 · 이름(title) · 표지 · 문장, 마스코트 없음", () => {
    renderDialog({ model: single, reveal: reveal() });
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("당첨을 축하합니다!")).toBeInTheDocument();
    const hero = dialog.querySelector('[data-result-winners="single"]');
    expect(hero).not.toBeNull();
    expect(hero.querySelector('[title="박개발"]')).not.toBeNull();
    expect(hero.querySelector(".k-avatar")).not.toBeNull();
    expect(within(dialog).getByText("당첨")).toBeInTheDocument();
    expect(within(dialog).getByText("5명 중 1명을 뽑았습니다.")).toBeInTheDocument();
    expect(Array.from(dialog.querySelectorAll("img")).some((img) => /mascot/i.test(img.getAttribute("src") || ""))).toBe(false);
  });
});

describe("초점", () => {
  it("스스로 열린 대화 상자는 판이 아니라 몸에 초점을 준다 — 판(Paper)에 전역 초점 링이 서지 않는다", async () => {
    renderDialog({ model: single, reveal: reveal() });
    const body = document.querySelector("[data-result-dialog]");
    await waitFor(() => expect(document.activeElement).toBe(body));
    expect(document.activeElement).not.toBe(screen.getByRole("dialog"));
  });

  it("「결과 보기」로 열고 닫으면 초점이 그 단추로 돌아간다", async () => {
    function Harness() {
      const [open, setOpen] = React.useState(false);
      return (
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <button type="button" onClick={() => setOpen(true)}>결과 보기</button>
          <ResultDialog model={single} isHost={false} onReplay={vi.fn()} reveal={reveal("revealed", { open, closeDialog: () => setOpen(false) })} />
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "결과 보기" });
    opener.focus();
    fireEvent.click(opener);
    await waitFor(() => expect(document.activeElement).toBe(document.querySelector("[data-result-dialog]")));
    fireEvent.click(within(document.querySelector("[data-result-actions]")).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(opener);
  });
});

describe("여럿 · 차분", () => {
  it("순위가 있는 여럿은 시상대(1 · 2 · 3) 뒤에 나머지 줄", () => {
    const winners = ["가", "나", "다", "라"].map((n, i) => ({ ...person(`u${i}`, n), rank: i + 1 }));
    renderDialog({ model: { ...single, game: "구슬 레이스", winners, ranked: true, headline: "당첨자를 발표합니다" }, reveal: reveal() });
    const ranked = document.querySelector('[data-result-winners="ranked"]');
    expect(ranked).not.toBeNull();
    expect(ranked.querySelectorAll('[aria-label="1등"]').length).toBe(1);
    expect(ranked.querySelectorAll('[aria-label="4등"]').length).toBe(1);
    expect(Array.from(ranked.querySelectorAll("[title]")).map((e) => e.getAttribute("title")).sort()).toEqual(["가", "나", "다", "라"]);
  });

  it("순위 없는 여럿은 같은 무게의 격자, 12명을 넘으면 목록", () => {
    const three = ["가", "나", "다"].map((n, i) => person(`u${i}`, n));
    const { unmount } = renderDialog({ model: { ...single, winners: three }, reveal: reveal() });
    const grid = document.querySelector('[data-result-winners="grid"]');
    expect(grid).not.toBeNull();
    expect(grid.hasAttribute("data-result-list")).toBe(false);
    unmount();
    const many = Array.from({ length: 13 }, (_, i) => person(`m${i}`, `사람${i}`));
    renderDialog({ model: { ...single, winners: many }, reveal: reveal() });
    expect(document.querySelector('[data-result-winners="grid"]').hasAttribute("data-result-list")).toBe(true);
  });

  it("승자가 없으면 제목과 문장만 — 상세는 펼친 채", () => {
    const calm = {
      ...single, mood: "calm", winners: [], headline: "팀을 나눴습니다", sentence: "4명을 2팀으로 나눴습니다.",
      detail: <div>1팀 명단</div>, detailLabel: "팀 구성", detailDefaultOpen: true,
    };
    renderDialog({ model: calm, reveal: reveal() });
    expect(screen.getByText("팀을 나눴습니다")).toBeInTheDocument();
    expect(document.querySelector("[data-result-winners]")).toBeNull();
    expect(document.querySelector('[data-result-detail="open"]')).not.toBeNull();
    expect(screen.getByRole("button", { name: "팀 구성 접기" })).toBeInTheDocument();
  });
});

describe("상세 · 발 · 복사", () => {
  it("상세는 접는 칸이다", async () => {
    renderDialog({ model: { ...single, detail: <div>완주 순위 표</div>, detailLabel: "전체 순위" }, reveal: reveal() });
    expect(document.querySelector('[data-result-detail="closed"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "전체 순위 보기" }));
    expect(document.querySelector('[data-result-detail="open"]')).not.toBeNull();
    expect(await screen.findByText("완주 순위 표")).toBeInTheDocument();
  });

  it("다시 하기는 방장만, 닫기는 모두", () => {
    const onReplay = vi.fn();
    const { unmount } = renderDialog({ model: single, reveal: reveal(), isHost: true, onReplay });
    fireEvent.click(screen.getByRole("button", { name: "다시 하기" }));
    expect(onReplay).toHaveBeenCalledTimes(1);
    unmount();
    const r = reveal();
    renderDialog({ model: single, reveal: r, isHost: false });
    expect(screen.queryByRole("button", { name: "다시 하기" })).toBeNull();
    const closes = screen.getAllByRole("button", { name: "닫기" }); // 머리의 × 와 발의 [닫기]
    fireEvent.click(closes[closes.length - 1]);
    expect(r.closeDialog).toHaveBeenCalled();
  });

  it("결과 복사 — 전체 화면에서는 그 자리에서 「복사했습니다」", async () => {
    renderDialog({ model: single, reveal: reveal(), fullscreen: true });
    fireEvent.click(screen.getByRole("button", { name: "결과 복사" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("랜덤 추첨 결과\n당첨: 박개발"));
    expect(await screen.findByText("복사했습니다")).toBeInTheDocument();
  });
});

describe("게임마다의 문장 (buildResultModel)", () => {
  const base = (over) => ({
    room: { id: "r", status: "finished", game_type: "random_draw", title: "방" }, you: { user_id: "u1" }, people: {}, members: [],
    gstate: {}, isMarble: false, isDraw: false, isTeam: false, isLadder: false, isVote: false, isNumber: false, isRps: false, isQuiz: false,
    drawWinners: [], teams: [], ladderAssignments: [], ...over,
  });

  it("추첨 — 「n명 중 k명을 뽑았습니다.」", () => {
    const m = buildResultModel(base({
      isDraw: true, drawWinners: [{ user_id: "u2", name: "박개발" }],
      gstate: { pool: [{ user_id: "u1", name: "김" }, { user_id: "u2", name: "박개발" }, { user_id: "u3", name: "이" }] },
    }));
    expect(m.sentence).toBe("3명 중 1명을 뽑았습니다.");
    expect(m.heroTitle).toBe("당첨을 축하합니다!");
    expect(m.winnerLabel).toBe("당첨");
  });

  it("투표 — 「total표 중 count표를 받았습니다.」", () => {
    const m = buildResultModel(base({
      room: { id: "r", status: "finished", game_type: "quick_vote", title: "점심" }, isVote: true, maxCount: 3,
      voteResult: { question: "점심", options: ["국밥", "김밥"], counts: [3, 1], winner_indexes: [0] },
    }));
    expect(m.sentence).toBe("4표 중 3표를 받았습니다.");
    expect(m.winnerLabel).toBe("선택됨");
  });

  it("숫자 — 조사까지 맞는다(3을 · 2를)", () => {
    expect(objectParticle(3)).toBe("을");
    expect(objectParticle(2)).toBe("를");
    expect(objectParticle(10)).toBe("을");
    const m = buildResultModel(base({
      room: { id: "r", status: "finished", game_type: "number", title: "숫자" }, isNumber: true,
      numResult: { winner: { user_id: "u1", name: "김", number: 2 }, picks: [{ user_id: "u1", name: "김", number: 2 }, { user_id: "u2", name: "박", number: 5 }] },
    }));
    expect(m.sentence).toBe("2명 중 가장 낮은 유일한 숫자 2를 냈습니다.");
  });

  it("가위바위보 · 토너먼트 · 퀴즈", () => {
    const rps = buildResultModel(base({
      room: { id: "r", status: "finished", game_type: "rps", title: "가위" }, isRps: true,
      rpsResult: { outcome: "win", win_choice: "바위", winners: [{ user_id: "u1", name: "김" }], reveal: [{ user_id: "u1", name: "김", choice: "바위" }, { user_id: "u2", name: "박", choice: "가위" }] },
    }));
    expect(rps.sentence).toBe("2명 중 바위를 내서 이겼습니다.");
    const t = buildResultModel(base({
      room: { id: "r", status: "finished", game_type: "rps", title: "가위" }, isRps: true,
      rpsResult: { mode: "tournament", champion: { user_id: "u1", name: "김" }, rounds: [[], []] },
    }));
    expect(t.sentence).toBe("2라운드를 이기고 우승했습니다.");
    expect(t.game).toBe("가위바위보 토너먼트");
    const q = buildResultModel(base({
      room: { id: "r", status: "finished", game_type: "quiz", title: "퀴즈" }, isQuiz: true,
      quizResult: { total_rounds: 5, scoreboard: [{ user_id: "u1", name: "김", score: 4 }, { user_id: "u2", name: "박", score: 2 }], winner_ids: ["u1"] },
    }));
    expect(q.sentence).toBe("5문제 중 4문제를 맞혀 우승했습니다.");
  });

  it("구슬 — 먼저 · 여럿 · 꼴찌 문장, 확정 안 된 결과는 없다", () => {
    const marble = (over) => base({
      room: { id: "r", status: "finished", game_type: "marble_race", title: "구슬" }, isMarble: true,
      marble: {
        announceable: true, pickLast: false, integrity: { status: "confirmed", agree: 1 },
        participants: [{ key: "a", name: "가", hue: 0 }, { key: "b", name: "나", hue: 120 }, { key: "c", name: "다", hue: 240 }],
        byKey: new Map([["a", { key: "a", name: "가", hue: 0 }], ["b", { key: "b", name: "나", hue: 120 }], ["c", { key: "c", name: "다", hue: 240 }]]),
        winnerKeys: new Set(["a"]), serverResult: { ranking: ["a", "b", "c"], finish_steps: [100, 200, 300], winners: ["a"] }, ...over,
      },
    });
    expect(buildResultModel(marble()).sentence).toBe("3명 중 가장 먼저 결승선을 통과했습니다.");
    expect(buildResultModel(marble({ serverResult: { ranking: ["a", "b", "c"], finish_steps: [1, 2, 3], winners: ["a", "b"] } })).sentence)
      .toBe("3명 중 2명이 먼저 결승선을 통과했습니다.");
    expect(buildResultModel(marble({ pickLast: true, serverResult: { ranking: ["a", "b", "c"], finish_steps: [1, 2, 3], winners: ["c"] } })).sentence)
      .toBe("3명 중 가장 늦게 들어왔습니다.");
    expect(buildResultModel(marble()).note).toBe("참가자 1명의 화면과 일치한 결과입니다.");
    expect(buildResultModel(marble({ announceable: false }))).toBeNull();
  });
});
