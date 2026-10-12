/* 엔진 손잡이 — 화면이 물리를 부르는 한 가지 길 (D-564).
 *
 * 물리는 Web Worker 에서 돈다(메인 스레드는 그리기만). 워커를 쓸 수 없는 자리(jsdom 시험 · 아주 옛 브라우저)에서는 같은 API 로
 * 같은 스레드에서 돈다 — 결과 · 지문은 같다(엔진이 같다, `core.js`). 화면은 어느 쪽인지 모른다.
 *
 * 규약(워커와 같다):
 *   init({ stageKey, participants, seed, winners, pickLast, raceId })
 *   advance(logicalMs)   → 한 번에 하나만 보낸다(앞 스냅샷이 오기 전에는 다음 요청을 안 보낸다 — 밀린 요청이 쌓이지 않는다)
 *   onReady(cb) · onSnapshot(cb) · onFinished(cb) · onError(cb) · terminate()
 *
 * 🔴 이 모듈은 planck 를 정적으로 들여오지 않는다 — 같은 스레드 갈래만 그때 `race.js` 를 받는다(물리 청크는 워커와 그 갈래의 것이다). */

const HAS_WORKER = typeof Worker !== "undefined" && typeof URL !== "undefined";

/* 같은 스레드 갈래. 콜백은 동기적으로 부른다 — 시험이 기다릴 것이 없다. */
async function createInlineClient() {
  const [{ createRace }, { createEngineCore }] = await Promise.all([import("./race.js"), import("./core.js")]);
  const core = createEngineCore(createRace);
  const handlers = { snapshot: null, finished: null, error: null, ready: null };
  return {
    kind: "inline",
    init(msg) {
      try {
        const ready = core.init(msg);
        handlers.ready && handlers.ready(ready);
      } catch (e) {
        handlers.error && handlers.error(e);
      }
    },
    advance(logicalMs) {
      try {
        for (const m of core.advance(logicalMs)) {
          if (m.type === "snapshot") handlers.snapshot && handlers.snapshot(m);
          else if (m.type === "finished") handlers.finished && handlers.finished(m.result);
        }
      } catch (e) {
        handlers.error && handlers.error(e);
      }
    },
    onReady(cb) { handlers.ready = cb; },
    onSnapshot(cb) { handlers.snapshot = cb; },
    onFinished(cb) { handlers.finished = cb; },
    onError(cb) { handlers.error = cb; },
    terminate() { handlers.snapshot = handlers.finished = handlers.error = handlers.ready = null; },
  };
}

function createWorkerClient() {
  const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  const handlers = { snapshot: null, finished: null, error: null, ready: null };
  worker.onmessage = (e) => {
    const m = e.data;
    if (!m) return;
    if (m.type === "snapshot") handlers.snapshot && handlers.snapshot(m);
    else if (m.type === "finished") handlers.finished && handlers.finished(m.result);
    else if (m.type === "ready") handlers.ready && handlers.ready(m);
    else if (m.type === "error") handlers.error && handlers.error(new Error(m.message || "경주 계산에서 오류가 났습니다."));
  };
  worker.onerror = (e) => {
    handlers.error && handlers.error(new Error(e && e.message ? e.message : "경주 계산을 시작하지 못했습니다."));
  };
  return {
    kind: "worker",
    init(msg) { worker.postMessage({ type: "init", ...msg }); },
    advance(logicalMs) { worker.postMessage({ type: "advance", logicalMs }); },
    onReady(cb) { handlers.ready = cb; },
    onSnapshot(cb) { handlers.snapshot = cb; },
    onFinished(cb) { handlers.finished = cb; },
    onError(cb) { handlers.error = cb; },
    terminate() {
      worker.terminate();
      handlers.snapshot = handlers.finished = handlers.error = handlers.ready = null;
    },
  };
}

/** 손잡이 하나. `worker:false` 면 같은 스레드에서 돈다(시험). 약속은 손잡이로 풀린다. */
export async function createEngineClient({ worker = true } = {}) {
  if (worker && HAS_WORKER) {
    try {
      return createWorkerClient();
    } catch (e) {
      // 워커를 못 띄우는 환경(CSP · file:// · 옛 브라우저) — 같은 스레드로 내려간다. 결과는 같다.
    }
  }
  return createInlineClient();
}
