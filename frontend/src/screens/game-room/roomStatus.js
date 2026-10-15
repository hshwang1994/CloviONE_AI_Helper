/* 방 상태의 정본 하나 (게임 공통 G2) — 순수 함수. 툴바가 이것만 그린다.
 *
 * 예전에는 상태 줄이 둘이었다: 껍데기의 「대기 중」 배지와 구슬 무대의 「대기 중 · 1명 참가 …」 띠. 같은 사실이 두 자리에 서면 하나가
 * 늦게 바뀌는 순간 화면이 모순을 말한다. 이제 상태 낱말은 페이지에 정확히 한 번이다(`RoomToolbar`, G8 하네스가 센다). */

export const STATUS_META = {
  waiting: { label: "대기 중", kind: "info" },
  playing: { label: "진행 중", kind: "warn" },
  verifying: { label: "결과 확인 중", kind: "warn" },
  finished: { label: "종료", kind: "ok" },
  disputed: { label: "확정 실패", kind: "danger" },
  abandoned: { label: "중단", kind: "warn" },
};

/** `{ key, label, kind, spectating }` — 구슬 레이스는 서버의 단계(`phase`) · 무결성이 방 상태보다 더 정확한 말이다. */
export function deriveRoomStatus({ room, gstate, you }) {
  const g = gstate || {};
  let key = room.status;
  if (room.game_type === "marble_race") {
    const phase = g.phase;
    const integrity = (g.integrity || {}).status;
    if (phase === "abandoned") key = "abandoned";
    else if (room.status === "playing") key = phase === "verifying" ? "verifying" : "playing";
    else if (room.status === "finished") key = integrity === "disputed" ? "disputed" : "finished";
  }
  const meta = STATUS_META[key] || { label: room.status, kind: "neutral" };
  return { key, label: meta.label, kind: meta.kind, spectating: !!you && you.role === "spectator" };
}

/** 툴바 왼쪽의 숫자들 — 등록 참가자 · 정원 · 관전 · 구슬 설정. `marble` 은 진행 중 경주의 완주 수(화면이 계산한 값)다. */
export function participantSummary({ room, gstate, members, marble }) {
  const g = gstate || {};
  const list = members || [];
  const out = {
    players: Number(room.player_count) || 0,
    max: Number(room.max_players) || 0,
    spectators: list.filter((m) => m.role === "spectator").length,
    marbles: 0, winnersN: 0, pickLast: false, speed: 1, finishedCount: 0,
    winnersCount: 0,
  };
  if (room.game_type === "marble_race") {
    const waiting = room.status === "waiting" || !g.phase || g.phase === "idle";
    const config = g.config || {};
    const participants = !waiting && Array.isArray(g.participants) && g.participants.length ? g.participants
      : Array.isArray(config.participants) && config.participants.length ? config.participants
        : list.filter((m) => m.role !== "spectator" && m.present !== false);
    out.marbles = participants.length;
    out.winnersN = waiting ? (config.winners || 1) : (g.winners_n || 1);
    out.pickLast = waiting ? !!config.pick_last : !!g.pick_last;
    out.speed = waiting ? (config.speed || 1) : (g.speed || 1);
    out.finishedCount = marble && Number.isFinite(marble.finishedCount) ? marble.finishedCount : 0;
    out.winnersCount = g.announceable && g.result && Array.isArray(g.result.winners) ? g.result.winners.length : 0;
  }
  return out;
}

/** 구슬 설정의 사실들 — 「구슬 12」 「당첨 1(꼴찌)」 「2배속」. 툴바가 한 사실씩 따로 세운다(사이 기호를 글자에 넣지 않는다). */
export function marbleMetaParts(summary) {
  return [`구슬 ${summary.marbles}`, `당첨 ${summary.winnersN}${summary.pickLast ? "(꼴찌)" : ""}`, `${summary.speed}배속`];
}
