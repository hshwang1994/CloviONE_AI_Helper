/* 구슬 레이스 엔진 지문 실행기 (`games_e2e.py --digest`) — 엔진 폴더 하나를 받아 정해진 seed · 판 · 참가자로 경주를 끝까지 돌리고
 * 결과(순위 · 완주 스텝 · 당첨 · 지문 · 스텝 수)를 JSON 한 줄로 낸다. 같은 경주를 논리 시간 조각 크기를 바꿔 여러 번 돌린다 — 조각
 * 크기와 무관하게 같은 결과여야 한다(D-564 · D-578).
 *
 * 엔진마다 프로세스를 따로 띄운다. `determinism.js` 가 전역 Math 를 결정적 함수로 바꿔 끼우므로 두 엔진(이 트리 · 기준 커밋)을 한
 * 프로세스에 올리면 나중 것이 앞의 설치를 덮는다. 엔진 폴더는 `frontend/` 아래여야 한다 — `world.js` 의 `import "planck"` 가
 * `frontend/node_modules` 에서 풀린다(두 엔진이 같은 planck 를 쓴다).
 *
 *   node scripts/ui_qa/marble_digest_runner.mjs <엔진 폴더> <spec.json>
 *   spec = { races: [{ map, seed, n, winners, pickLast, raceId, chunks: [1000, 37] }] } */

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [engineDir, specPath] = process.argv.slice(2);
if (!engineDir || !specPath) {
  process.stderr.write("usage: marble_digest_runner.mjs <engineDir> <spec.json>\n");
  process.exit(2);
}
const spec = JSON.parse(readFileSync(specPath, "utf8"));
const at = (rel) => pathToFileURL(path.join(engineDir, rel)).href;
const race = await import(at("race.js"));
/* 판 목록 — 판이 넷이 된 뒤(D-578)는 `stages/index.js`, 그 전(D-564)은 바퀴 판 하나(`stages/wheel.js`)뿐이다. */
const STAGES = existsSync(path.join(engineDir, "stages", "index.js"))
  ? (await import(at("stages/index.js"))).STAGES
  : { wheel: (await import(at("stages/wheel.js"))).WHEEL };
const stepMs = race.STEP_MS || 10;
/* 슬로 모션은 한 스텝의 논리 시간을 최대 1 / SLOWMO_MIN 배로 늘린다 — 상한은 물리 스텝 상한의 그만큼 배인 논리 시간이다(engine.test.js 와 같다). */
const capMs = (race.MAX_STEPS / (race.SLOWMO_MIN || 1) + 1000) * stepMs;

const out = [];
for (const c of spec.races) {
  const participants = Array.from({ length: c.n }, (_, i) => ({ key: `n:${String(i).padStart(3, "0")}`, name: `참가자 ${i + 1}` }));
  const runs = [];
  for (const chunk of c.chunks) {
    /* 그 엔진에 없는 판(예: 판이 하나뿐이던 옛 커밋)은 경주 하나의 오류로 적고 다음으로 간다 — 대조가 그 줄을 실패로 센다. */
    try {
      const r = race.createRace({ stage: STAGES[c.map], participants, seed: c.seed, winners: c.winners, pickLast: c.pickLast });
      const t0 = Date.now();
      let t = 0;
      while (!r.finished && t <= capMs) {
        t += chunk;
        r.stepTo(t, c.raceId);
      }
      const res = r.result || {};
      runs.push({
        chunk, finished: r.finished, steps: r.step, wall_ms: Date.now() - t0,
        ranking: res.ranking || null, finish_steps: res.finish_steps || null, winners: res.winners || null, digest: res.digest || null,
      });
    } catch (e) {
      runs.push({ chunk, finished: false, steps: null, error: String((e && e.message) || e), ranking: null, finish_steps: null, winners: null, digest: null });
    }
  }
  out.push({ ...c, runs });
}
process.stdout.write(JSON.stringify({ engineDir, stepMs, maxSteps: race.MAX_STEPS, races: out }));
