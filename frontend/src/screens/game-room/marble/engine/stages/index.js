/* 경주 판 목록 (D-578) — 열쇠 · 자료. 자료(`wheel.js` · `pot.js` · …)는 원본(lazygyu/roulette 의 `src/data/maps.ts`)에서
 * `scripts/marble_import_maps.py` 가 만든 파일이고 손으로 고치지 않는다. 이름은 우리 것이다(`labels.js` — 원본 이름은 쓰지 않는다).
 * 서버의 `app/games/marble.py::MAPS` 와 열쇠가 같아야 한다 — 시험(`engine.test.js`)이 둘을 대조한다.
 * 기본 목록은 100개 구슬 1배속 경주가 상한(240초) 안에 끝나는 판만이다(시험이 잰다). */

import { WHEEL } from "./wheel.js";
import { POT } from "./pot.js";
import { BUBBLE } from "./bubble.js";
import { YORU } from "./yoru.js";

export { STAGE_KEYS, STAGE_LABELS } from "./labels.js";

export const STAGES = { wheel: WHEEL, pot: POT, bubble: BUBBLE, yoru: YORU };

export function stageOf(key) {
  return STAGES[key] || STAGES.wheel;
}
