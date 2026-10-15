/* 엔진 알맹이 — 워커와 같은 스레드 갈래가 **같이** 쓰는 「경주 하나」 (D-564).
 *
 * 메시지를 받아 엔진을 돌리고 스냅샷을 전송할 모양으로 싼다. 워커(`worker.js`)도, 워커가 없을 때의 같은 스레드 갈래
 * (`client.js`)도 이 함수를 부르므로 두 갈래의 결과 · 모양이 갈라질 자리가 없다.
 *
 * 스냅샷 모양: { step, finished, finishedCount, timeScale, positions(Float32Array n*3: x, y, angle), flags(Uint8Array n: 1 완주 · 2 사라짐),
 *               entityAngles(Float32Array), entityFlags(Uint8Array 엔티티 수: 1 사라진 장애물), ranking(Int16Array 참가자 번호) }
 * — 배열은 transferable 로 넘긴다. `timeScale` 은 다음 스텝의 배속(슬로 모션이면 1 미만, D-578)이다. */

import { STAGES } from "./stages/index.js";

export const FLAG_FINISHED = 1;
export const FLAG_GONE = 2;
export const ENTITY_GONE = 1;

export function packSnapshot(snap, indexByKey) {
  const n = snap.positions.length;
  const positions = new Float32Array(n * 3);
  const flags = new Uint8Array(n);
  for (let i = 0; i < n; i += 1) {
    const p = snap.positions[i];
    const idx = indexByKey.get(p.key);
    positions[idx * 3] = p.x;
    positions[idx * 3 + 1] = p.y;
    positions[idx * 3 + 2] = p.angle;
    flags[idx] = (p.finished ? FLAG_FINISHED : 0) | (p.gone ? FLAG_GONE : 0);
  }
  const ranking = new Int16Array(snap.ranking.length);
  for (let i = 0; i < snap.ranking.length; i += 1) ranking[i] = indexByKey.get(snap.ranking[i]);
  const gone = snap.entityGone || [];
  const entityFlags = new Uint8Array(snap.entityAngles.length);
  for (let i = 0; i < gone.length; i += 1) entityFlags[i] = gone[i] ? ENTITY_GONE : 0;
  return {
    type: "snapshot",
    step: snap.step,
    finished: snap.finished,
    finishedCount: snap.finishedCount,
    timeScale: snap.timeScale == null ? 1 : snap.timeScale,
    positions,
    flags,
    entityAngles: Float32Array.from(snap.entityAngles),
    entityFlags,
    ranking,
  };
}

export function transferables(msg) {
  return msg.type === "snapshot"
    ? [msg.positions.buffer, msg.flags.buffer, msg.entityAngles.buffer, msg.entityFlags.buffer, msg.ranking.buffer]
    : [];
}

export function createEngineCore(createRaceFn) {
  let race = null;
  let raceId = null;
  let indexByKey = null;
  let finishedSent = false;
  return {
    init(msg) {
      const stage = STAGES[msg.stageKey] || STAGES.wheel;
      race = createRaceFn({
        stage, participants: msg.participants, seed: msg.seed, winners: msg.winners, pickLast: !!msg.pickLast,
      });
      raceId = msg.raceId || null;
      indexByKey = new Map(msg.participants.map((p, i) => [p.key, i]));
      finishedSent = false;
      return { type: "ready", entities: stage.entities.length, goalY: stage.goalY };
    },
    /* 논리 시간까지 돌리고 스냅샷(과 끝났으면 결과)을 돌려준다. */
    advance(logicalMs) {
      if (!race) throw new Error("경주를 먼저 준비해야 한다(init)");
      race.stepTo(logicalMs, raceId);
      const out = [packSnapshot(race.snapshot(), indexByKey)];
      if (race.finished && !finishedSent) {
        finishedSent = true;
        out.push({ type: "finished", result: race.result });
      }
      return out;
    },
  };
}
