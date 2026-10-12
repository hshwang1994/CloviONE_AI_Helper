/* 구슬 레이스 물리 워커 (D-564) — 메인 스레드는 그리기만 하고, 스텝은 여기서 돈다.
 *
 * 🔴 import 순서가 결정성이다: `determinism.js` 가 전역 Math 를 바꾼 **뒤에** planck(`race.js` → `world.js`)가 평가돼야 한다.
 * planck 는 모듈 평가 때 `Math.sin` 등을 변수에 받아 두므로, 순서가 바뀌면 엔진의 libm 이 그대로 쓰여 브라우저마다 결과가
 * 달라질 수 있다(`disputed`). 이 파일의 첫 줄이 그 순서를 지킨다.
 *
 * 메시지 규약은 `client.js` 머리말에, 스냅샷 모양은 `core.js` 에 있다. 스냅샷 배열은 transferable 로 넘긴다. */

import "./determinism.js";
import { createRace } from "./race.js";
import { createEngineCore, transferables } from "./core.js";

const core = createEngineCore(createRace);

self.onmessage = (e) => {
  const msg = e.data;
  if (!msg || typeof msg.type !== "string") return;
  try {
    if (msg.type === "init") {
      self.postMessage(core.init(msg));
    } else if (msg.type === "advance") {
      for (const out of core.advance(Number(msg.logicalMs) || 0)) {
        self.postMessage(out, transferables(out));
      }
    }
  } catch (err) {
    self.postMessage({ type: "error", message: err && err.message ? err.message : String(err) });
  }
};
