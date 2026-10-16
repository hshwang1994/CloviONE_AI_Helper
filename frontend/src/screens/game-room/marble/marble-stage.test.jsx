import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 구슬 레이스 무대 (D-564 · D-575 · D-578) — 게임방 전체를 띄워 잰다.
 *
 *   1) 대기 중: 툴바의 구슬 메타(판 · 구슬 · 당첨 · 배속), 방장만 [설정](판 고르기 · 「확인됨」의 뜻 한 줄). 판 옆 [정보]는 없다 —
 *      출처 고지는 사용자 메뉴의 「오픈소스 고지」다(D-579).
 *   2) 진행 중: 서버가 준 seed · started_at · speed 로 이 브라우저가 경주를 **실제로 계산**해 끝내고(워커가 없으면 같은 스레드)
 *      결과를 한 번 올린다 — 방장은 finish, 참가자는 attest. 지문은 64자리 16진수이고 순위는 참가자 전체의 순열이다.
 *   3) 종료: 서버가 확정한 결과(announceable)만 결과 대화 상자로 발표한다. disputed 는 대화 상자 없이 판 위 알림이다. 늦게 들어온
 *      사람(첫 로드)은 전환 없이 결과를 본다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("canvas-confetti", () => {
  const fn = () => {};
  fn.create = () => () => {};
  return { default: fn };
});

import { GameRoom } from "../../GameRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../../../ui/kit.jsx";
import { ThemeModeProvider } from "../../../ui/ThemeModeProvider.jsx";
import { SUBMIT_MARGIN_MS, submitDelayMs } from "./useMarbleRoom.js";

function renderRoom() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/games/m1"]}>
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

const PARTICIPANTS = [
  { key: "u:u1", name: "김운영", user_id: "u1" },
  { key: "n:abc", name: "박개발", user_id: null },
];
const CONFIG = { participants: PARTICIPANTS, winners: 1, pick_last: false, map: "wheel", speed: 4 };
const base = (over = {}) => ({
  room: { id: "m1", title: "점심 내기", game_type: "marble_race", status: "waiting", player_count: 1, max_players: 8, host_user_id: "u1" },
  you: { user_id: "u1", in_room: true, is_host: true, role: "player", ready: false },
  members: [{ user_id: "u1", name: "김운영", role: "host" }],
  state: { phase: "idle", config: CONFIG },
  events: [], seq: 1, result_seq: null, now: new Date().toISOString(),
  ...over,
});
function running(over = {}) {
  return base({
    room: { ...base().room, status: "playing" },
    state: {
      phase: "running", race_id: "0123456789abcdef0123456789abcdef", seed: "00112233aabbccdd",
      started_at: new Date(Date.now() - 240000).toISOString(), speed: 4, map: "wheel", winners_n: 1, pick_last: false,
      host_user_id: "u1", participants: PARTICIPANTS, submissions: [], verify_until: null, result: null, finalized_at: null,
      config: CONFIG, you_submitted: false, announceable: false,
    },
    seq: 2,
    ...over,
  });
}
const FINISHED = {
  ranking: ["n:abc", "u:u1"], finish_steps: [3200, 4100], digest: "f".repeat(64), winners: ["n:abc"],
};
function finished(integrity = "confirmed") {
  const r = running();
  const announceable = integrity !== "disputed";
  return {
    ...r,
    room: { ...r.room, status: "finished" },
    state: {
      ...r.state, phase: "finished", result: announceable ? FINISHED : null, finalized_at: new Date().toISOString(),
      integrity: { status: integrity, agree: 1, disagree: integrity === "disputed" ? 1 : 0, source: "host", submissions: 2 },
      announceable, you_submitted: true,
    },
    seq: 4, result_seq: 4,
  };
}

beforeEach(() => {
  apiMock.mockReset();
  // jsdom 에는 캔버스가 없다 — 그리기는 건너뛰고 상태 · 제출만 잰다.
  HTMLCanvasElement.prototype.getContext = () => null;
});
afterEach(() => { vi.restoreAllMocks(); });

describe("대기 중", () => {
  it("툴바의 구슬 메타 · 상태 한 번 · 방장의 설정(판 고르기 · 「확인됨」의 뜻)", async () => {
    apiMock.mockResolvedValue(base());
    renderRoom();
    expect(await screen.findByText("운명의 바퀴")).toBeInTheDocument();
    for (const part of ["구슬 2", "당첨 1", "4배속"]) expect(screen.getByText(part)).toBeInTheDocument();
    expect(screen.getAllByText("대기 중")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "경주 시작" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "정보" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "설정" }));
    expect(await screen.findByText(/조작이 없었다는 증명은 아닙니다/)).toBeInTheDocument();
    expect(screen.getByText("맵 선택")).toBeInTheDocument();
  });

  it("방장이 아니면 설정 단추가 없다", async () => {
    apiMock.mockResolvedValue(base({ you: { user_id: "u9", in_room: true, is_host: false, role: "player", ready: false } }));
    renderRoom();
    await screen.findByText("운명의 바퀴");
    expect(screen.queryByRole("button", { name: "설정" })).toBeNull();
    expect(screen.queryByRole("button", { name: "경주 시작" })).toBeNull();
  });
});

describe("진행 중 — 이 브라우저가 경주를 계산해 결과를 한 번 올린다", () => {
  it("방장은 finish 로, 순위는 순열이고 지문은 SHA-256 이다", async () => {
    apiMock.mockImplementation((url) => {
      if (String(url).includes("/marble/finish")) return Promise.resolve({ recorded: true, late: false, state: {} });
      return Promise.resolve(running());
    });
    renderRoom();
    expect((await screen.findAllByText("진행 중")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(apiMock.mock.calls.some((c) => String(c[0]).includes("/marble/finish"))).toBe(true);
    }, { timeout: 20000 });
    const calls = apiMock.mock.calls.filter((c) => String(c[0]).includes("/marble/finish"));
    expect(calls.length).toBe(1);
    const body = calls[0][1].body;
    expect(calls[0][1].method).toBe("POST");
    expect(body.race_id).toBe("0123456789abcdef0123456789abcdef");
    expect([...body.ranking].sort()).toEqual(["n:abc", "u:u1"]);
    expect(body.finish_steps.length).toBe(2);
    expect(body.digest).toMatch(/^[0-9a-f]{64}$/);
    // 제출 뒤 확인 창 안내가 선다. 판 위 알림이 서면 선두 칩은 걷힌다(둘이 위쪽에서 겹치지 않는다).
    expect(await screen.findByText(/결과를 확인하는 중입니다/)).toBeInTheDocument();
    expect(document.querySelector("[data-lead-chips]")).toBeNull();
  }, 30000);

  it("참가자는 attest 로 올리고, 이미 올렸으면 다시 올리지 않는다", async () => {
    apiMock.mockImplementation((url) => {
      if (String(url).includes("/marble/attest")) return Promise.resolve({ recorded: true, late: false, state: {} });
      return Promise.resolve(running({ you: { user_id: "u9", in_room: true, is_host: false, role: "player", ready: false } }));
    });
    renderRoom();
    await waitFor(() => {
      expect(apiMock.mock.calls.some((c) => String(c[0]).includes("/marble/attest"))).toBe(true);
    }, { timeout: 20000 });
    expect(apiMock.mock.calls.some((c) => String(c[0]).includes("/marble/finish"))).toBe(false);
  }, 30000);

  it("서버의 최소 경과 전에 끝난 경주는 그때까지 기다렸다 올린다(D-580)", async () => {
    apiMock.mockImplementation((url) => {
      if (String(url).includes("/marble/finish")) return Promise.resolve({ recorded: true, late: false, state: {} });
      const data = running();
      data.state.min_race_seconds = 100000; // 배속 4 → 2만 5천 초. 시험 안에서는 오지 않는 시각이다.
      return Promise.resolve(data);
    });
    renderRoom();
    expect(await screen.findByText(/결과를 확인하는 중입니다/, undefined, { timeout: 20000 })).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 1500));
    expect(apiMock.mock.calls.some((c) => String(c[0]).includes("/marble/finish"))).toBe(false);
  }, 30000);

  it("서버가 이미 받은 사람(you_submitted)은 올리지 않는다", async () => {
    const data = running();
    data.state.you_submitted = true;
    apiMock.mockResolvedValue(data);
    renderRoom();
    await screen.findAllByText("진행 중");
    await new Promise((r) => setTimeout(r, 3000));
    expect(apiMock.mock.calls.some((c) => String(c[0]).includes("/marble/"))).toBe(false);
  }, 15000);
});

describe("제출 대기 — 서버의 최소 경과(D-580)", () => {
  it("최소 경과(배속으로 나눔)에 못 미친 만큼 + 여유만 기다린다", () => {
    expect(submitDelayMs({ minRaceSeconds: 8, speed: 1, logicalMs: 7000 })).toBe(1000 + SUBMIT_MARGIN_MS);
    expect(submitDelayMs({ minRaceSeconds: 8, speed: 4, logicalMs: 6000 })).toBe(500 + SUBMIT_MARGIN_MS); // 벽시계 1.5초 · 최소 2초
    expect(submitDelayMs({ minRaceSeconds: 8, speed: 1, logicalMs: 30000 })).toBe(0);
    expect(submitDelayMs({ minRaceSeconds: 8, speed: 2, logicalMs: 16000 + 2 * SUBMIT_MARGIN_MS })).toBe(0);
  });
  it("서버가 최소 경과를 알려 주지 않거나 논리 시간을 모르면 기다리지 않는다", () => {
    expect(submitDelayMs({ minRaceSeconds: undefined, speed: 1, logicalMs: 1000 })).toBe(0);
    expect(submitDelayMs({ minRaceSeconds: 8, speed: 1, logicalMs: null })).toBe(0);
  });
});

describe("종료", () => {
  it("확정된 결과만 발표한다 — 늦게 들어온 사람은 전환 없이 결과 대화 상자를 본다", async () => {
    apiMock.mockResolvedValue(finished("confirmed"));
    renderRoom();
    const dialog = await screen.findByRole("dialog", { name: "구슬 레이스 결과 발표" });
    expect(within(dialog).getByText("당첨을 축하합니다!")).toBeInTheDocument();
    expect(document.querySelector('[data-result-panel="revealed"]')).not.toBeNull();
    expect(within(dialog).getByText("참가자 1명의 화면과 일치한 결과입니다.")).toBeInTheDocument();
    expect(within(dialog).getByText("2명 중 가장 먼저 결승선을 통과했습니다.")).toBeInTheDocument();
    expect(dialog.querySelector('[data-result-winners] [title="박개발"]')).not.toBeNull();
    expect(within(dialog).getByRole("button", { name: "전체 순위 보기" })).toBeInTheDocument();
  });

  it("방장 화면뿐인 결과는 그 사실을 적는다", async () => {
    apiMock.mockResolvedValue(finished("host_only"));
    renderRoom();
    expect(await screen.findByText("방장 화면의 결과입니다. 대조할 참가자 화면이 없었습니다.")).toBeInTheDocument();
  });

  it("브라우저 간 결과가 다르면(disputed) 발표하지 않는다", async () => {
    apiMock.mockResolvedValue(finished("disputed"));
    renderRoom();
    expect(await screen.findByText(/브라우저 간 결과가 달라 확정하지 못했습니다/)).toBeInTheDocument();
    expect(screen.queryByText("당첨을 축하합니다!")).toBeNull();
    expect(document.querySelector("[data-result-panel]")).toBeNull();
    expect(screen.getAllByText("확정 실패")).toHaveLength(1);
  });
});
