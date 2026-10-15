import { useEffect, useReducer, useRef } from "react";

/* 결과 발표의 상태 기계 (D-576) — 결과 하나(열쇠)에 「발표 → 공개」를 한 번 돌리고, 축포는 열쇠당 한 번이다.
 *
 * 열쇠는 방 id + 결과 번호(`deriveResultKey`)다. 상태는 셋이다 — `none`(결과 없음) · `announcing`(「결과를 발표합니다」) ·
 * `revealed`(당첨자 공개). 대화 상자가 열려 있는가(`open`)는 단계와 따로 간다: 닫아도 판은 마지막 장면으로 남고 툴바의
 * [결과 보기]가 같은 단계 그대로 다시 연다(다시 발표하지 않고 축포도 없다).
 *
 *   RESET     결과가 사라졌다(초기화) — 단계를 비우고 닫는다.
 *   INSTANT   이 방을 처음 열었을 때 이미 있던 결과(늦은 입장 · 새로고침) — 발표 없이 공개 상태로 연다. 축포 없음.
 *   ANNOUNCE  새로 나온 결과 — 발표 단계로 연다. `ANNOUNCE_MS` 뒤 같은 열쇠면 REVEAL.
 *   REVEAL    발표가 끝났다 — 공개. 아직 같은 열쇠일 때만(그 사이 결과가 바뀌었으면 버린다).
 *   CLOSE     대화 상자를 닫는다(단계 그대로).
 *   OPEN      다시 연다(단계 그대로 — 재발표 · 축포 없음). 결과가 없으면 아무 일도 없다.
 *
 * 축포는 기계 밖의 일이다 — REVEAL 이 일어나는 순간 훅이 `fire(key)` 를 부르되, 승자가 있는 결과이고 그 열쇠에 아직 안 쏘았을
 * 때만이다(`firedKey`). 폴링 · 리렌더 · 창 크기 · 테마 · 대화 상자 열고 닫기 어느 것도 다시 쏘게 하지 않는다. */

export const ANNOUNCE_MS = 800;
export const REVEAL_INITIAL = { key: null, phase: "none", open: false };

export function reduceReveal(state, action) {
  const s = state || REVEAL_INITIAL;
  switch (action && action.type) {
    case "RESET":
      return s.key == null && s.phase === "none" && !s.open ? s : REVEAL_INITIAL;
    case "INSTANT":
      return { key: action.key, phase: "revealed", open: true };
    case "ANNOUNCE":
      return { key: action.key, phase: "announcing", open: true };
    case "REVEAL":
      return s.key === action.key && s.phase === "announcing" ? { ...s, phase: "revealed" } : s;
    case "CLOSE":
      return s.open ? { ...s, open: false } : s;
    case "OPEN":
      return s.key != null && !s.open ? { ...s, open: true } : s;
    default:
      return s;
  }
}

/** 열쇠의 변화가 어느 전이인가 — 순수 함수. `instant` 는 「이 방을 처음 열었을 때 본 열쇠」인가다(컨트롤러가 렌더 중에 정한다). */
export function transitionFor(prevKey, key, instant) {
  if (key == null) return prevKey == null ? null : { type: "RESET" };
  if (key === prevKey) return null;
  return instant ? { type: "INSTANT", key } : { type: "ANNOUNCE", key };
}

/**
 * 발표 기계 훅. `fire(key)` 는 축포(공개 순간 한 번) — 실패해도 결과 표시를 막지 않는다.
 * 돌려주는 것: `{ key, phase, open, openDialog, closeDialog }`.
 */
export function useRevealMachine({ key, instant, hasWinners, fire }) {
  const [state, dispatch] = useReducer(reduceReveal, REVEAL_INITIAL);
  const firedRef = useRef(null);
  const hasWinnersRef = useRef(hasWinners);
  const fireRef = useRef(fire);
  hasWinnersRef.current = hasWinners;
  fireRef.current = fire;

  const next = transitionFor(state.key, key == null ? null : key, !!instant);
  useEffect(() => {
    if (next) dispatch(next);
  }, [next && next.type, next && next.key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (state.phase !== "announcing" || state.key == null) return undefined;
    const k = state.key;
    const t = setTimeout(() => {
      dispatch({ type: "REVEAL", key: k });
      if (hasWinnersRef.current && firedRef.current !== k) {
        firedRef.current = k;
        try { if (fireRef.current) fireRef.current(k); } catch (e) { /* 축포 실패는 결과를 막지 않는다 */ }
      }
    }, ANNOUNCE_MS);
    return () => clearTimeout(t);
  }, [state.phase, state.key]);

  return {
    key: state.key,
    phase: state.phase,
    open: state.open,
    openDialog: () => dispatch({ type: "OPEN" }),
    closeDialog: () => dispatch({ type: "CLOSE" }),
  };
}
