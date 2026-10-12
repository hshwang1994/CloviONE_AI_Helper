/* 경주 하나 — seed 와 참가자로 결정되는 결정적 경주 (D-564). 원본 roulette.ts 의 루프 · 순위 · 완주 규칙을 옮겼다.
 *
 * - 논리 시간: 부르는 쪽이 「(서버 시각 − 시작 시각) × 배속」 밀리초를 주면 그 시간까지 10ms 스텝을 누적한다. 프레임 · 탭 상태 · 기기와
 *   무관하다 — 늦게 들어온 사람도 같은 스텝 수까지 빨리 감아 같은 자리에 선다.
 * - 완주: 결승선(goalY)을 넘은 순서가 순위다. 남은 구슬이 하나면 그 등수는 확정이다(원본의 early finish). 모두 완주하거나
 *   상한 스텝에 닿으면 끝난다 — 상한에 걸린 구슬은 진행도 지도의 남은 거리로 순위를 매긴다(결정적).
 * - 슬로 모션 · 카메라는 그리기 전용이라 여기 없다. 결과 `{ranking, finish_steps}` 와 그 지문만이 서버에 올라간다.
 *
 * 🔴 import 순서: `determinism.js` → `world.js`(planck). 이 모듈을 들여오는 쪽이 그 순서를 지킨다(이 파일이 지킨다). */

import "./determinism.js";
import { createRng } from "./rng.js";
import { createWorld, spawnPosition } from "./world.js";
import { ProgressMap } from "./progressMap.js";
import { raceDigest } from "./sha256.js";

export const STEP_MS = 10;
/* 240초 — 원본 판에서 100개 구슬도 2분 안에 끝난다. 상한은 「영원히 끝나지 않는 경주」를 막는 안전띠다. */
export const MAX_STEPS = 24000;
export const RANK_EMA_SEC = 0.4;
export const RANK_MARGIN = 0.25;

/* 순위 흔들림 줄이기(원본 _sortMarbles) — 표시 전용. 지문에는 들어가지 않는다. */
function emaAlpha(dtSeconds) {
  // exp 는 결정적 수학에 없으므로 표시용 EMA 는 1차 근사로 — 지문과 무관한 값이라 엔진 차이가 결과에 닿지 않는다.
  const r = dtSeconds / RANK_EMA_SEC;
  return r >= 1 ? 1 : r;
}

export function createRace({ stage, participants, seed, winners = 1, pickLast = false }) {
  if (!stage || !Array.isArray(participants) || participants.length < 2) throw new Error("경주에는 판과 참가자 둘 이상이 필요하다");
  const rng = createRng(seed);
  const total = participants.length;
  const orders = rng.shuffle(participants.map((_, i) => i));
  const marbles = participants.map((p, i) => {
    const order = orders[i];
    const at = spawnPosition(order, total);
    // 색상(hue)은 참가자 번호 순이다 — 순위 레일 · 결과 판(DOM)이 같은 식으로 같은 색을 낸다(`render/theme.js::participantHue`). 물리 · 지문과 무관하다.
    return { key: p.key, name: p.name, order, hue: (360 / total) * i, x: at.x, y: at.y };
  });
  const world = createWorld(stage, marbles, rng);
  const map = ProgressMap.for(stage);
  const byKey = new Map(marbles.map((m) => [m.key, m]));
  const finishOrder = [];
  const finishSteps = new Map();
  let lastRankKeys = new Map();
  let live = marbles.map((m) => m.key);
  let done = false;
  let result = null;
  let settled = 0;

  function rankLive(dtSeconds) {
    const alpha = emaAlpha(dtSeconds);
    const keys = new Map();
    const positions = new Map(world.positions().map((p) => [p.key, p]));
    let known = 0;
    for (const key of live) {
      const p = positions.get(key);
      const raw = map.distanceAt(p.x, p.y);
      const prev = lastRankKeys.get(key);
      if (prev !== undefined) known += 1;
      keys.set(key, prev !== undefined ? prev + (raw - prev) * alpha : raw);
    }
    lastRankKeys = keys;
    if (known < live.length / 2) {
      live.sort((a, b) => (keys.get(a) - keys.get(b)) || (positions.get(b).y - positions.get(a).y) || (a < b ? -1 : 1));
      return;
    }
    for (let i = 1; i < live.length; i += 1) {
      const m = live[i];
      const k = keys.get(m) + RANK_MARGIN;
      let j = i;
      while (j > 0 && k < keys.get(live[j - 1])) {
        live[j] = live[j - 1];
        j -= 1;
      }
      live[j] = m;
    }
  }

  function finalize(raceId) {
    const remaining = live.filter((k) => !finishSteps.has(k));
    if (remaining.length) {
      // 상한에 걸린 구슬: 남은 거리 순(결정적), 완주 스텝은 상한.
      const positions = new Map(world.positions().map((p) => [p.key, p]));
      remaining.sort((a, b) => {
        const da = map.distanceAt(positions.get(a).x, positions.get(a).y);
        const db = map.distanceAt(positions.get(b).x, positions.get(b).y);
        return (da - db) || (a < b ? -1 : 1);
      });
      for (const k of remaining) {
        finishOrder.push(k);
        finishSteps.set(k, MAX_STEPS);
      }
    }
    const ranking = finishOrder.slice();
    const steps = ranking.map((k) => finishSteps.get(k));
    const n = Math.max(1, Math.min(winners, ranking.length));
    const won = pickLast ? ranking.slice(-n).reverse() : ranking.slice(0, n);
    result = { ranking, finish_steps: steps, winners: won, digest: raceId ? raceDigest(raceId, ranking, steps) : null };
    done = true;
    return result;
  }

  return {
    marbles,
    stage,
    get step() { return world.step; },
    get finished() { return done; },
    get result() { return result; },
    /* 논리 시간(ms)까지 스텝을 누적한다. 돌린 스텝 수를 돌려준다. 끝나면 `result` 가 찬다. */
    stepTo(logicalMs, raceId) {
      if (done) return 0;
      const target = Math.min(MAX_STEPS, Math.floor(logicalMs / STEP_MS));
      let ran = 0;
      while (world.step < target && !done) {
        const crossed = world.advance(stage.goalY);
        ran += 1;
        for (const key of crossed) {
          finishOrder.push(key);
          finishSteps.set(key, world.step);
          live = live.filter((k) => k !== key);
        }
        if (live.length === 1 && finishOrder.length === total - 1) {
          // 남은 구슬이 하나면 그 등수는 확정이다(원본의 early finish).
          const last = live[0];
          finishOrder.push(last);
          finishSteps.set(last, world.step);
          live = [];
        }
        if (live.length === 0 || world.step >= MAX_STEPS) {
          finalize(raceId);
          break;
        }
      }
      if (ran > 0 && !done && live.length > 1) rankLive(ran * STEP_MS / 1000);
      return ran;
    },
    /* 그리기용 한 장 — 위치 · 각 · 완주 여부 · 실시간 순위(완주한 구슬이 먼저, 그 뒤 진행도 순). */
    snapshot() {
      const positions = world.positions();
      const ranking = finishOrder.concat(live.filter((k) => !finishSteps.has(k)));
      return {
        step: world.step,
        finished: done,
        positions,
        entityAngles: world.entityAngles(),
        ranking,
        finishedCount: finishOrder.length,
        finishSteps: Object.fromEntries(finishSteps),
      };
    },
    byKey(key) { return byKey.get(key); },
    settle() { settled += 1; return settled; },
  };
}
