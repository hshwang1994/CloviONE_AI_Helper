/* 경주 하나 — seed 와 참가자로 결정되는 결정적 경주 (D-564 · D-578). 원본 roulette.ts 의 루프 · 순위 · 완주 규칙을 옮겼다.
 *
 * - 논리 시간: 부르는 쪽이 「(서버 시각 − 시작 시각) × 배속」 밀리초를 주면 그 시간까지 10ms 스텝을 누적한다. 프레임 · 탭 상태 · 기기와
 *   무관하다 — 늦게 들어온 사람도 같은 스텝 수까지 빨리 감아 같은 자리에 선다.
 * - 완주: 결승선(goalY)을 넘은 순서가 순위다. 남은 구슬이 하나면 그 등수는 확정이다(원본의 early finish). 모두 완주하거나
 *   상한 스텝에 닿으면 끝난다 — 상한에 걸린 구슬은 진행도 지도의 남은 거리로 순위를 매긴다(결정적).
 * - 결과 `{ranking, finish_steps}` 와 그 지문만이 서버에 올라간다. 카메라 · 효과는 그리기 전용이라 여기 없다.
 *
 * ## 슬로 모션 — 엔진의 시간 매핑 (D-578)
 *
 * 원본은 결승 근처에서 물리 스텝 크기를 줄인다(`step(0.01 × timeScale)`). 그러면 물리가 달라져 결과 · 지문이 프레임마다 갈린다 —
 * 우리는 그러지 않는다. 물리 스텝은 언제나 10ms 이고, 바뀌는 것은 **한 스텝이 쓰는 논리 시간**이다: 스텝 k 의 값
 * `c_k = STEP_MS / timeScale(S_k)` 를 누적한 `T_k` 가 논리 시간 L 이하인 동안 스텝을 밟는다. `S_k` 는 k 스텝 뒤의 경주 상태라
 * 모든 브라우저에서 같고(D-564), 그래서 `T_k` 도 같다 → 논리 시간 L 에서 정확히 `max{k : T_k ≤ L}` 스텝 — 프레임률 · 입장 시각 ·
 * 나눠 부르는 크기와 무관하다. `finish_steps` 는 스텝 색인이라 그대로이고 지문(`raceDigest`)도 그대로다. 슬로 모션은 벽시계만 늘린다.
 *
 * `timeScale(S)` — 당첨이 이미 정해졌으면 1. 아니면 **당첨 경계의 살아 있는 구슬**(꼴찌 당첨이면 맨 뒤 구슬)의 `d = |zoomY − y|`
 * 로 `clamp(d / 12, 0.25, 1)` 을 0.05 단위로 자른다. 경계 구슬은 진행도 지도의 날 거리(지수 평활 없음)로 매 스텝 고른다 — 화면의
 * 순위 레일은 평활한 순위라 나눠 부르는 크기에 따라 다를 수 있어 시간 매핑에 쓰지 않는다. 자른 값은 정수 칸(5 ~ 20)이라 비용
 * `200 / 칸` 이 모든 엔진에서 같은 부동소수다.
 *
 * 🔴 import 순서: `determinism.js` → `world.js`(planck). 이 모듈을 들여오는 쪽이 그 순서를 지킨다(이 파일이 지킨다). */

import "./determinism.js";
import { createRng } from "./rng.js";
import { createWorld, spawnPosition } from "./world.js";
import { ProgressMap } from "./progressMap.js";
import { raceDigest } from "./sha256.js";

export const STEP_MS = 10;
/* 240초 — 원본 판에서 100개 구슬도 2분 안에 끝난다. 상한은 「영원히 끝나지 않는 경주」를 막는 안전띠다(물리 스텝 수다). */
export const MAX_STEPS = 24000;
export const RANK_EMA_SEC = 0.4;
export const RANK_MARGIN = 0.25;
/* 슬로 모션 — 경계 구슬이 zoomY 에서 12 단위 안이면 느려지기 시작해 0.25 배까지. 0.05 단위(정수 칸 5 ~ 20)로 자른다. */
export const ZOOM_THRESHOLD = 12;
export const SLOWMO_MIN = 0.25;
export const SLOWMO_QUANT = 0.05;
const QUANT_STEPS = Math.round(1 / SLOWMO_QUANT); // 20
const MIN_QUANT = Math.round(SLOWMO_MIN * QUANT_STEPS); // 5

/** 경계 구슬의 거리 → 시간 칸(정수 5 ~ 20). 순수 함수 — 시험이 표로 잰다. */
export function slowmoQuant(d) {
  const ratio = d / ZOOM_THRESHOLD;
  const clamped = ratio >= 1 ? 1 : ratio <= SLOWMO_MIN ? SLOWMO_MIN : ratio;
  const q = Math.round(clamped * QUANT_STEPS);
  return q < MIN_QUANT ? MIN_QUANT : q > QUANT_STEPS ? QUANT_STEPS : q;
}

/* 순위 흔들림 줄이기(원본 _sortMarbles) — 표시 전용. 지문에는 들어가지 않는다. */
function emaAlpha(dtSeconds) {
  // exp 는 결정적 수학에 없으므로 표시용 EMA 는 1차 근사로 — 지문과 무관한 값이라 엔진 차이가 결과에 닿지 않는다.
  const r = dtSeconds / RANK_EMA_SEC;
  return r >= 1 ? 1 : r;
}

export function createRace({ stage, participants, seed, winners = 1, pickLast = false, slowmo = true }) {
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
  const zoomY = Number.isFinite(stage.zoomY) ? stage.zoomY : stage.goalY;
  let lastRankKeys = new Map();
  let live = marbles.map((m) => m.key);
  let done = false;
  let result = null;
  let settled = 0;
  /* 시간 매핑 — `T` 는 지금까지 밟은 스텝이 쓴 논리 시간(ms), `quant` 는 다음 스텝의 시간 칸(20 이면 보통 속도). */
  let T = 0;
  let quant = QUANT_STEPS;

  /* 다음 스텝의 시간 칸 — 지금 상태(S_k)만 본다. 결정적: 날 거리 · 위치 · 열쇠만 쓴다. */
  function nextQuant() {
    if (!slowmo || done) return QUANT_STEPS;
    const n = winners > 0 ? winners : 1;
    if (!pickLast && finishOrder.length >= n) return QUANT_STEPS; // 당첨이 이미 정해졌다
    const bodies = world.marbles;
    let near = false;
    for (let i = 0; i < bodies.length; i += 1) {
      const m = bodies[i];
      if (m.finished || !m.body) continue;
      const y = m.body.getPosition().y;
      const d = zoomY > y ? zoomY - y : y - zoomY;
      if (d < ZOOM_THRESHOLD) { near = true; break; }
    }
    if (!near) return QUANT_STEPS; // 경계 구슬이 어디 있든 12 단위 밖이다
    const rows = [];
    for (let i = 0; i < bodies.length; i += 1) {
      const m = bodies[i];
      if (m.finished || !m.body) continue;
      const p = m.body.getPosition();
      rows.push({ key: m.key, y: p.y, d: map.distanceAt(p.x, p.y) });
    }
    if (rows.length < 2) return QUANT_STEPS;
    rows.sort((a, b) => (a.d - b.d) || (b.y - a.y) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
    const remaining = n - finishOrder.length;
    const focus = pickLast ? rows[rows.length - 1] : rows[Math.min(rows.length, remaining) - 1];
    const d = zoomY > focus.y ? zoomY - focus.y : focus.y - zoomY;
    return slowmoQuant(d);
  }
  quant = nextQuant(); // S_0 — 출발 자리(판마다 zoomY 에서 멀다)

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
    /** 지금까지 밟은 스텝이 쓴 논리 시간(ms) — 스텝 k 의 `T_k`. */
    get logicalMs() { return T; },
    /** 다음 스텝의 배속(1 이면 보통, 0.25 까지 느려진다). */
    get timeScale() { return quant / QUANT_STEPS; },
    /* 논리 시간(ms)까지 스텝을 누적한다. 돌린 스텝 수를 돌려준다. 끝나면 `result` 가 찬다. */
    stepTo(logicalMs, raceId) {
      if (done) return 0;
      let ran = 0;
      while (!done && world.step < MAX_STEPS) {
        const cost = (STEP_MS * QUANT_STEPS) / quant;
        if (T + cost > logicalMs) break;
        const crossed = world.advance(stage.goalY);
        T += cost;
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
        quant = nextQuant();
      }
      if (ran > 0 && !done && live.length > 1) rankLive(ran * STEP_MS / 1000);
      return ran;
    },
    /* 그리기용 한 장 — 위치 · 각 · 완주 여부 · 실시간 순위(완주한 구슬이 먼저, 그 뒤 진행도 순) · 사라진 장애물 · 배속. */
    snapshot() {
      const positions = world.positions();
      const ranking = finishOrder.concat(live.filter((k) => !finishSteps.has(k)));
      return {
        step: world.step,
        finished: done,
        positions,
        entityAngles: world.entityAngles(),
        entityGone: world.entityGone(),
        ranking,
        finishedCount: finishOrder.length,
        finishSteps: Object.fromEntries(finishSteps),
        timeScale: done ? 1 : quant / QUANT_STEPS,
        logicalMs: T,
      };
    },
    byKey(key) { return byKey.get(key); },
    settle() { settled += 1; return settled; },
  };
}
