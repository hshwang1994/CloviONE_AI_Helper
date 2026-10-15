import { useCallback, useMemo, useRef } from "react";
import { useMarbleRace } from "./useMarbleRace.js";
import { participantHue } from "./render/theme.js";
import { stageBounds } from "./render/camera.js";
import { STAGES, stageOf } from "./engine/stages/index.js";
import { FLAG_FINISHED } from "./engine/core.js";

/* 구슬 방 하나의 경주 상태 (D-564 · D-578) — 방 단위로 한 번 돈다.
 *
 * 판(캔버스) · 순위 레일 · 툴바(「완주 3/12」) · 결과 대화 상자가 같은 값을 읽는다. 예전에는 판(`MarbleStage`) 안에 있어 레일이
 * 판 옆에 붙어야만 순위를 알았고, 그래서 방의 오른쪽 레일과 판 옆 순위 레일이 따로 섰다.
 *
 * - 참가자: 진행 중 · 종료는 경주에 박힌 목록, 대기 중은 설정의 목록(없으면 지금 있는 구성원). 색(hue)은 참가자 번호 순이다.
 * - 경주 계산은 `useMarbleRace`(워커). 끝나면 결과를 한 번 올린다 — 방장 finish · 나머지 attest(경주당 한 번).
 * - 발표는 서버가 확정한 결과(`announceable`)만이다. `disputed` 는 발표 · 축포가 없다.
 * 구슬 방이 아니면 아무것도 돌리지 않는다(`isMarble` 거짓, 경주 비활성). */

export function useMarbleRoom({ data, mutations }) {
  const room = data && data.room;
  const isMarble = !!room && room.game_type === "marble_race";
  const g = (isMarble && data.state) || {};
  const members = (data && data.members) || [];
  const you = (data && data.you) || null;
  const phase = g.phase || "idle";
  const waiting = !isMarble || room.status === "waiting" || phase === "idle";
  const config = g.config || {};

  const participants = useMemo(() => {
    if (!isMarble) return [];
    let list;
    if (!waiting && Array.isArray(g.participants) && g.participants.length) list = g.participants;
    else if (Array.isArray(config.participants) && config.participants.length) list = config.participants;
    else list = members.filter((m) => m.role !== "spectator" && m.present !== false).map((m) => ({ key: `u:${m.user_id}`, name: m.name, user_id: m.user_id }));
    return list.map((p, i) => ({ ...p, index: i, hue: participantHue(i, list.length) }));
  }, [isMarble, waiting, g.participants, config.participants, members]);
  const byKey = useMemo(() => new Map(participants.map((p) => [p.key, p])), [participants]);
  const winnersN = waiting ? (config.winners || 1) : (g.winners_n || 1);
  const pickLast = waiting ? !!config.pick_last : !!g.pick_last;
  const speed = waiting ? (config.speed || 1) : (g.speed || 1);
  const stageKey = (waiting ? config.map : g.map) || "wheel";
  const stage = stageOf(stageKey);
  const bounds = stageBounds(stage);

  /* 결과 제출 — 경주당 한 번(훅이 보장), 방 안의 사람만, 아직 안 올렸을 때만, 확정 전일 때만. */
  const latest = useRef(null);
  latest.current = { g, you, isHost: !!(you && you.is_host), mutations };
  const onFinished = useCallback((result) => {
    const { g: s, you: y, isHost, mutations: m } = latest.current;
    if (!y || !y.in_room || s.you_submitted || s.finalized_at) return;
    const body = { race_id: s.race_id, ranking: result.ranking, finish_steps: result.finish_steps, digest: result.digest };
    (isHost ? m.marbleFinish : m.marbleAttest).mutate(body);
  }, []);

  const race = useMarbleRace({
    raceId: g.race_id, seed: g.seed, startedAt: g.started_at, speed: g.speed,
    participants: g.participants, winners: g.winners_n, pickLast: !!g.pick_last, stageKey: g.map,
    serverNow: data ? data.now : null,
    active: isMarble && !waiting && phase !== "abandoned" && Array.isArray(g.participants) && g.participants.length >= 2,
    onFinished,
  });

  const serverResult = isMarble && phase === "finished" && g.result ? g.result : null;
  const announceable = !!(g.announceable && serverResult);
  const integrity = g.integrity || {};
  const winnerKeys = useMemo(() => new Set(announceable ? serverResult.winners || [] : []), [announceable, serverResult]);
  const winnerSet = useMemo(() => new Set(Array.from(winnerKeys).map((k) => byKey.get(k)).filter(Boolean).map((p) => p.index)), [winnerKeys, byKey]);
  const verifying = isMarble && !waiting && phase !== "finished" && phase !== "abandoned" && (phase === "verifying" || race.status === "finished");
  const snap = race.snapshotRef.current;
  const finishedCount = snap && !waiting ? snap.finishedCount : 0;

  return {
    isMarble, phase, waiting, config, participants, byKey, winnersN, pickLast, speed, stageKey, stage, bounds,
    race, serverResult, announceable, integrity, winnerKeys, winnerSet, verifying, finishedCount,
  };
}

/** 순위 레일의 줄 순서 — 확정 뒤엔 서버 순위, 진행 중엔 실시간(완주한 구슬 먼저), 대기 중엔 참가자 순. */
export function rankOrder({ participants, snapshot, finalRanking }) {
  if (finalRanking) {
    const byKey = new Map(participants.map((p) => [p.key, p]));
    return finalRanking.map((k) => byKey.get(k)).filter(Boolean);
  }
  if (snapshot && snapshot.ranking && snapshot.ranking.length) return Array.from(snapshot.ranking).map((i) => participants[i]).filter(Boolean);
  return participants;
}

export function finishedOf(p, snapshot, finalRanking) {
  return finalRanking ? true : !!(snapshot && snapshot.flags && (snapshot.flags[p.index] & FLAG_FINISHED));
}

export { STAGES };
