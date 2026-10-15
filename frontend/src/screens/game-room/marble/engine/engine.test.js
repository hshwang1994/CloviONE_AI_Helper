import { describe, it, expect, afterEach, vi } from "vitest";

/* 구슬 레이스 엔진 — 결정성과 완주 (D-564).
 *
 * 못박는 것:
 *   1) 결정적 수학: 알려진 값과 맞고, 원래 Math 와 1e-15 안에서 같다(두 구현이 다른 함수를 계산하지 않는다는 증거).
 *   2) 같은 seed 두 번 = 같은 순위 · 같은 완주 스텝 · 같은 지문. 다른 seed 는 다른 경주다.
 *   3) 논리 시간을 어떤 크기로 나눠 누적해도 결과가 같다(배속 · 프레임 · 탭 상태와 무관).
 *   4) 20개 · 100개 구슬이 상한 안에 전부 결승에 닿고, 순위는 참가자 전체의 순열이다.
 *   5) 경주 중 `Math.random` 호출이 없다 — 무작위는 seed 에서만 온다.
 *   6) 지문은 서버(`app/games/marble.py::digest_of`)와 같은 글의 SHA-256 이다.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { atan2, cos, hypot, isInstalled, selfTest, sin, stats } from "./determinism.js";
import { createRace, MAX_STEPS, STEP_MS, slowmoQuant, SLOWMO_MIN } from "./race.js";
import { raceDigest, sha256Hex } from "./sha256.js";
import { ProgressMap } from "./progressMap.js";
import { WHEEL } from "./stages/wheel.js";
import { STAGES, STAGE_KEYS } from "./stages/index.js";
import { createRng } from "./rng.js";

function participants(n) {
  return Array.from({ length: n }, (_, i) => ({ key: `n:${String(i).padStart(3, "0")}`, name: `참가자 ${i + 1}` }));
}

/* 슬로 모션이 한 스텝의 논리 시간을 최대 1/0.25 배로 늘리므로(D-578) 상한은 물리 스텝 상한의 네 배 논리 시간이다. */
const LOGICAL_CAP_MS = (MAX_STEPS / SLOWMO_MIN + 1000) * STEP_MS;

function runToEnd(race, raceId, chunkMs) {
  let t = 0;
  while (!race.finished) {
    t += typeof chunkMs === "function" ? chunkMs() : chunkMs;
    race.stepTo(t, raceId);
    if (t > LOGICAL_CAP_MS) break;
  }
  return race.result;
}

afterEach(() => vi.restoreAllMocks());

describe("결정적 수학", () => {
  it("설치돼 있고 알려진 값과 맞다", () => {
    expect(isInstalled()).toBe(true);
    const report = selfTest();
    expect(report.failures).toEqual([]);
    expect(report.ok).toBe(true);
  });

  it("원래 Math 와 1e-15 안에서 같고 축소 범위 안에서는 물러나지 않는다", () => {
    const rng = createRng("math-check");
    const native = { sin: Math.sin, cos: Math.cos, atan2: Math.atan2 };
    // 설치된 Math.sin 은 우리 것이라 비교 대상이 아니다 - 원래 함수를 새 Function 으로 되찾는다.
    const fresh = new Function("return [Math.sin, Math.cos, Math.atan2]")();
    const same = (a, b) => Math.abs(a - b) <= 1e-15 * Math.max(1, Math.abs(b));
    const before = stats.fallbacks;
    for (let i = 0; i < 5000; i += 1) {
      const x = rng.range(-1e5, 1e5);
      const y = rng.range(-50, 50);
      expect(same(sin(x), fresh[0](x))).toBe(true);
      expect(same(cos(x), fresh[1](x))).toBe(true);
      expect(same(atan2(y, x), fresh[2](y, x))).toBe(true);
    }
    expect(stats.fallbacks).toBe(before);
    expect(hypot(3, 4)).toBe(5);
    expect(native).toBeTruthy();
  });
});

describe("지문", () => {
  it("SHA-256 이 표준 값을 내고 서버와 같은 글을 쓴다", () => {
    expect(sha256Hex("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    expect(sha256Hex("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    // Python: hashlib.sha256(b"race1|a,b|12,34").hexdigest()
    expect(raceDigest("race1", ["a", "b"], [12, 34])).toBe(sha256Hex("race1|a,b|12,34"));
  });
});

describe("경주", () => {
  it("같은 seed 는 같은 경주이고 다른 seed 는 다른 경주다 - 20개 구슬이 전부 결승에 닿는다", () => {
    const spy = vi.spyOn(Math, "random");
    const a = runToEnd(createRace({ stage: WHEEL, participants: participants(20), seed: "deadbeef00112233", winners: 2 }), "r1", 1000);
    const b = runToEnd(createRace({ stage: WHEEL, participants: participants(20), seed: "deadbeef00112233", winners: 2 }), "r1", 1000);
    expect(spy).not.toHaveBeenCalled();
    expect(a.ranking).toHaveLength(20);
    expect([...a.ranking].sort()).toEqual(participants(20).map((p) => p.key).sort());
    expect(a.finish_steps.every((s) => Number.isInteger(s) && s > 0 && s < MAX_STEPS)).toBe(true);
    expect(b).toEqual(a);
    expect(a.winners).toEqual(a.ranking.slice(0, 2));
    const c = runToEnd(createRace({ stage: WHEEL, participants: participants(20), seed: "0000000000000001", winners: 2 }), "r1", 1000);
    expect(c.ranking).not.toEqual(a.ranking);
  }, 60_000);

  it("논리 시간을 어떻게 나눠도 결과가 같고, 꼴찌 당첨은 뒤에서 센다", () => {
    const base = runToEnd(createRace({ stage: WHEEL, participants: participants(12), seed: "cafe", winners: 3, pickLast: true }), "r2", 1000);
    const fine = runToEnd(createRace({ stage: WHEEL, participants: participants(12), seed: "cafe", winners: 3, pickLast: true }), "r2", 37);
    expect(fine).toEqual(base);
    expect(base.winners).toEqual(base.ranking.slice(-3).reverse());
    expect(base.digest).toBe(raceDigest("r2", base.ranking, base.finish_steps));
  }, 60_000);

  it("100개 구슬도 상한 안에 전부 결승에 닿는다", () => {
    const race = createRace({ stage: WHEEL, participants: participants(100), seed: "ffffffffffffffff", winners: 5 });
    const result = runToEnd(race, "r3", 2000);
    expect(result.ranking).toHaveLength(100);
    expect(Math.max(...result.finish_steps)).toBeLessThan(MAX_STEPS);
    const snap = race.snapshot();
    expect(snap.finished).toBe(true);
    expect(snap.ranking).toEqual(result.ranking);
  }, 120_000);

  it("진행도 지도는 결승선 아래가 0 이고 출발 자리가 더 멀다", () => {
    const map = ProgressMap.for(WHEEL);
    expect(map.distanceAt(12, WHEEL.goalY + 0.5)).toBe(0);
    expect(map.distanceAt(12, 2)).toBeGreaterThan(50);
    expect(map.distanceAt(12, 100)).toBeLessThan(map.distanceAt(12, 2));
  });
});

describe("슬로 모션 — 엔진의 시간 매핑 (D-578)", () => {
  /* 물리 스텝은 언제나 10ms 이고 바뀌는 것은 한 스텝이 쓰는 논리 시간뿐이다 — 그래서 순위 · 완주 스텝 · 지문이 슬로 모션과 무관하다.
     논리 시간 L 에서 정확히 max{k : T_k ≤ L} 스텝이고, T_k 는 모든 브라우저에서 같은 상태 S_k 로만 정해진다. */
  it("켜고 끄고 순위 · 완주 스텝 · 지문이 같다", () => {
    const on = runToEnd(createRace({ stage: WHEEL, participants: participants(16), seed: "slow-1", winners: 2 }), "s1", 100);
    const off = runToEnd(createRace({ stage: WHEEL, participants: participants(16), seed: "slow-1", winners: 2, slowmo: false }), "s1", 100);
    expect(on.ranking).toEqual(off.ranking);
    expect(on.finish_steps).toEqual(off.finish_steps);
    expect(on.digest).toBe(off.digest);
  }, 60_000);

  it("논리 시간을 무작위로 나눠 불러도 결과가 같다(프레임률 · 입장 시각과 무관)", () => {
    const base = runToEnd(createRace({ stage: WHEEL, participants: participants(12), seed: "split", winners: 1, pickLast: true }), "r5", 1000);
    const rng = createRng("splits");
    const jitter = runToEnd(createRace({ stage: WHEEL, participants: participants(12), seed: "split", winners: 1, pickLast: true }), "r5", () => 1 + rng.int(400));
    expect(jitter).toEqual(base);
  }, 60_000);

  it("T_k 는 스텝마다 늘고 L 을 넘지 않으며, 스텝 수는 논리 시간에 단조다", () => {
    const race = createRace({ stage: WHEEL, participants: participants(10), seed: "mono", winners: 1 });
    let lastSteps = 0;
    let lastT = 0;
    let slowSteps = 0;
    for (let L = 0; !race.finished && L < LOGICAL_CAP_MS; L += 37) {
      const before = race.step;
      race.stepTo(L, "r6");
      expect(race.step).toBeGreaterThanOrEqual(lastSteps);
      expect(race.logicalMs).toBeGreaterThanOrEqual(lastT);
      expect(race.logicalMs).toBeLessThanOrEqual(L + 1e-9);
      if (race.step > before && race.logicalMs - lastT > (race.step - before) * STEP_MS + 1e-9) slowSteps += 1;
      lastSteps = race.step;
      lastT = race.logicalMs;
    }
    expect(race.finished).toBe(true);
    expect(slowSteps).toBeGreaterThan(0); // 결승 근처에서 실제로 느려졌다
    expect(race.logicalMs).toBeGreaterThan(race.step * STEP_MS);
  }, 60_000);

  it("배속은 0.25 ~ 1 이고 0.05 단위다", () => {
    expect([0, 1, 3, 3.6, 6, 9, 12, 40].map(slowmoQuant)).toEqual([5, 5, 5, 6, 10, 15, 20, 20]);
    const race = createRace({ stage: WHEEL, participants: participants(8), seed: "ts", winners: 1 });
    const seen = new Set();
    for (let L = 0; !race.finished && L < LOGICAL_CAP_MS; L += 50) {
      race.stepTo(L, "r7");
      const ts = race.snapshot().timeScale;
      expect(ts).toBeGreaterThanOrEqual(0.25);
      expect(ts).toBeLessThanOrEqual(1);
      expect(Math.abs(ts * 20 - Math.round(ts * 20))).toBeLessThan(1e-9);
      seen.add(ts);
    }
    expect(seen.size).toBeGreaterThan(2);
  }, 60_000);

  it("비눗방울 판 — 두 실행이 같은 스텝에 같은 장애물을 뺀다", () => {
    const a = createRace({ stage: STAGES.bubble, participants: participants(20), seed: "pop", winners: 1 });
    const b = createRace({ stage: STAGES.bubble, participants: participants(20), seed: "pop", winners: 1 });
    let removed = 0;
    for (let L = 0; !a.finished && L < LOGICAL_CAP_MS; L += 100) {
      a.stepTo(L, "r8");
      b.stepTo(L, "r8");
      expect(b.step).toBe(a.step);
      const ga = a.snapshot().entityGone;
      expect(b.snapshot().entityGone).toEqual(ga);
      removed = ga.filter(Boolean).length;
    }
    expect(removed).toBeGreaterThan(0);
    expect(b.result).toEqual(a.result);
  }, 120_000);

  it("판마다 20개 구슬이 상한 안에 끝난다", () => {
    for (const key of STAGE_KEYS) {
      const result = runToEnd(createRace({ stage: STAGES[key], participants: participants(20), seed: `cap-${key}`, winners: 1 }), "r9", 1000);
      expect(result.ranking).toHaveLength(20);
      expect(Math.max(...result.finish_steps)).toBeLessThan(MAX_STEPS);
    }
  }, 240_000);

  it("항아리 · 비눗방울 · 밤을 달리다도 100개 구슬이 상한 안에 끝난다(기본 목록의 조건)", () => {
    for (const key of ["pot", "bubble", "yoru"]) {
      const race = createRace({ stage: STAGES[key], participants: participants(100), seed: `cap100-${key}`, winners: 3 });
      const result = runToEnd(race, "r10", 2000);
      expect(result.ranking).toHaveLength(100);
      expect(Math.max(...result.finish_steps)).toBeLessThan(MAX_STEPS);
      // 1배속 벽시계 = 끝난 경주의 논리 시간(슬로 모션 포함). 240초 안이어야 기본 목록에 선다.
      expect(race.logicalMs).toBeLessThan(MAX_STEPS * STEP_MS);
    }
  }, 600_000);

  it("판 열쇠가 서버의 MAPS 와 같다", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const py = fs.readFileSync(path.resolve(here, "../../../../../../app/games/marble.py"), "utf-8");
    const m = /^MAPS = \(([^)]*)\)/m.exec(py);
    expect(m).not.toBeNull();
    const server = m[1].split(",").map((x) => x.trim().replace(/^"|"$/g, "")).filter(Boolean);
    expect(STAGE_KEYS).toEqual(server);
    expect(Object.keys(STAGES)).toEqual(STAGE_KEYS); // 이름 목록(labels.js)과 자료 목록이 같다
  });
});
