import { useCallback, useEffect, useRef, useState } from "react";
import { createEngineClient } from "./engine/client.js";

/* 경주 한 판을 돌리는 훅 (D-564) — 논리 시간 = (서버 시각 − 시작 시각) × 배속.
 *
 * - 서버 시각은 폴링 응답의 `now` 로 맞춘다(`serverNow`). 이 브라우저의 시계가 틀려도, 늦게 들어왔어도, 탭이 잠들었다
 *   깨어나도 같은 논리 시간까지 빨리 감는다 — 모든 브라우저가 같은 스텝에 선다.
 * - 물리 손잡이(`engine/client.js`)에는 한 번에 요청 하나만 보낸다(앞 스냅샷이 오기 전엔 다음을 안 보낸다). 스냅샷은
 *   `snapshotRef` 에 쌓이고 구독자(캔버스)가 그린다 — React 리렌더 없이. 순위 레일 같은 DOM 은 `tick`(≈ 5Hz)으로 그린다.
 * - 끝나면 `result` 가 차고 `onFinished(result)` 를 **한 번** 부른다(경주당 한 번 — 다시 그려도 두 번 올리지 않는다).
 * - 경주(`raceId`)가 바뀌면 손잡이를 버리고 새로 만든다. 설정 · 참가자는 경주 시작 때 서버가 박은 값이다. */

const TICK_MS = 200;
const raf = typeof requestAnimationFrame === "function"
  ? (fn) => requestAnimationFrame(fn)
  : (fn) => setTimeout(() => fn(Date.now()), 16);
const caf = typeof cancelAnimationFrame === "function" ? (h) => cancelAnimationFrame(h) : (h) => clearTimeout(h);

export function logicalMsOf({ startedAt, speed, serverOffsetMs, now = Date.now() }) {
  const started = Date.parse(startedAt || "");
  if (!Number.isFinite(started)) return 0;
  return Math.max(0, (now + (serverOffsetMs || 0) - started) * (Number(speed) || 1));
}

export function useMarbleRace({
  raceId, seed, startedAt, speed = 1, participants, winners = 1, pickLast = false, stageKey = "wheel",
  serverNow, active, onFinished, worker = true,
}) {
  const snapshotRef = useRef(null);
  const listenersRef = useRef(new Set());
  const offsetRef = useRef(0);
  const onFinishedRef = useRef(onFinished);
  const finishedForRef = useRef(null);
  const [tick, setTick] = useState(0);
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [engine, setEngine] = useState(null);

  onFinishedRef.current = onFinished;

  /* 서버 시각 보정 — 폴링마다 갱신. 왕복 지연의 절반쯤 늦게 보이지만 모든 브라우저가 같은 쪽으로 치우치므로 상대 차이는 작다. */
  useEffect(() => {
    const t = Date.parse(serverNow || "");
    if (Number.isFinite(t)) offsetRef.current = t - Date.now();
  }, [serverNow]);

  useEffect(() => {
    snapshotRef.current = null;
    setResult(null);
    setError(null);
    setEngine(null);
    if (!active || !raceId || !seed || !Array.isArray(participants) || participants.length < 2) {
      setStatus("idle");
      return undefined;
    }
    setStatus("loading");
    let cancelled = false;
    let client = null;
    let pending = false;
    let handle = 0;
    let lastTick = 0;
    const startedAtValue = startedAt;
    const speedValue = speed;

    const loop = () => {
      if (cancelled) return;
      if (client && !pending && !finishedForRef.current) {
        pending = true;
        client.advance(logicalMsOf({ startedAt: startedAtValue, speed: speedValue, serverOffsetMs: offsetRef.current }));
      }
      handle = raf(loop);
    };

    createEngineClient({ worker }).then((c) => {
      if (cancelled) { c.terminate(); return; }
      client = c;
      setEngine(c.kind);
      c.onError((e) => { if (!cancelled) { setError(e); setStatus("error"); } });
      c.onSnapshot((snap) => {
        pending = false;
        snapshotRef.current = snap;
        listenersRef.current.forEach((fn) => { try { fn(snap); } catch (e) { /* 그리기 오류는 경주를 멈추지 않는다 */ } });
        const now = Date.now();
        if (now - lastTick >= TICK_MS) { lastTick = now; setTick((t) => t + 1); }
      });
      c.onFinished((res) => {
        if (cancelled || finishedForRef.current === raceId) return;
        finishedForRef.current = raceId;
        setResult(res);
        setStatus("finished");
        setTick((t) => t + 1);
        onFinishedRef.current && onFinishedRef.current(res);
      });
      c.init({ stageKey, participants, seed, winners, pickLast, raceId });
      setStatus("running");
      handle = raf(loop);
    }).catch((e) => { if (!cancelled) { setError(e); setStatus("error"); } });

    return () => {
      cancelled = true;
      caf(handle);
      if (client) client.terminate();
      if (finishedForRef.current === raceId) finishedForRef.current = null;
    };
  }, [raceId, active]); // eslint-disable-line react-hooks/exhaustive-deps

  const subscribe = useCallback((fn) => {
    listenersRef.current.add(fn);
    return () => listenersRef.current.delete(fn);
  }, []);

  return {
    status, result, error, engine, tick, snapshotRef, subscribe,
    logicalMs: () => logicalMsOf({ startedAt, speed, serverOffsetMs: offsetRef.current }),
  };
}
