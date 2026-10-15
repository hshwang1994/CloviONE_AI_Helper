import { describe, it, expect } from "vitest";
import { STATUS_META, deriveRoomStatus, marbleMetaParts, participantSummary } from "./roomStatus.js";
import { STATUS_LABELS } from "./constants.js";

/* 방 상태의 정본 하나 (D-575) — 툴바가 이것만 그린다. 「종료」 낱말은 목록 · 툴바 · 대화 상자가 같다. */

const room = (over = {}) => ({ id: "r", game_type: "random_draw", status: "waiting", player_count: 3, max_players: 8, ...over });

describe("deriveRoomStatus", () => {
  it.each([
    [{ status: "waiting" }, {}, "waiting", "대기 중", "info"],
    [{ status: "playing" }, {}, "playing", "진행 중", "warn"],
    [{ status: "finished" }, {}, "finished", "종료", "ok"],
  ])("일반 게임 %j → %s", (r, g, key, label, kind) => {
    expect(deriveRoomStatus({ room: room(r), gstate: g, you: { role: "player" } })).toEqual({ key, label, kind, spectating: false });
  });

  it("구슬 레이스는 서버의 단계 · 무결성이 더 정확한 말이다", () => {
    const m = (status, gstate) => deriveRoomStatus({ room: room({ game_type: "marble_race", status }), gstate, you: null }).key;
    expect(m("playing", { phase: "running" })).toBe("playing");
    expect(m("playing", { phase: "verifying" })).toBe("verifying");
    expect(m("finished", { phase: "finished", integrity: { status: "confirmed" } })).toBe("finished");
    expect(m("finished", { phase: "finished", integrity: { status: "disputed" } })).toBe("disputed");
    expect(m("finished", { phase: "abandoned" })).toBe("abandoned");
    expect(STATUS_META.disputed).toEqual({ label: "확정 실패", kind: "danger" });
    expect(STATUS_META.verifying.label).toBe("결과 확인 중");
  });

  it("관전자는 따로 표시한다", () => {
    expect(deriveRoomStatus({ room: room(), gstate: {}, you: { role: "spectator" } }).spectating).toBe(true);
  });

  it("「종료」 낱말은 목록과 같다", () => {
    expect(STATUS_LABELS.finished).toBe("종료");
    expect(STATUS_META.finished.label).toBe(STATUS_LABELS.finished);
  });
});

describe("participantSummary · marbleMetaParts", () => {
  it("참여 · 정원 · 관전을 센다", () => {
    const s = participantSummary({ room: room(), gstate: {}, members: [{ role: "host" }, { role: "player" }, { role: "spectator" }] });
    expect(s).toMatchObject({ players: 3, max: 8, spectators: 1, marbles: 0 });
  });

  it("구슬 설정 — 대기 중엔 설정, 진행 중엔 경주에 박힌 값", () => {
    const waiting = participantSummary({
      room: room({ game_type: "marble_race" }), members: [],
      gstate: { phase: "idle", config: { participants: [{ key: "a" }, { key: "b" }, { key: "c" }], winners: 2, pick_last: true, speed: 4 } },
    });
    expect(marbleMetaParts(waiting)).toEqual(["구슬 3", "당첨 2(꼴찌)", "4배속"]);
    const running = participantSummary({
      room: room({ game_type: "marble_race", status: "playing" }), members: [], marble: { finishedCount: 2 },
      gstate: { phase: "running", participants: [{ key: "a" }, { key: "b" }], winners_n: 1, pick_last: false, speed: 2, config: {} },
    });
    expect(marbleMetaParts(running)).toEqual(["구슬 2", "당첨 1", "2배속"]);
    expect(running.finishedCount).toBe(2);
  });
});
