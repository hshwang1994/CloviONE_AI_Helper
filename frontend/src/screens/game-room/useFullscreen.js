import { useCallback, useEffect, useRef, useState } from "react";

/* 놀이방 전체 화면 (D-575) — 방의 루트 하나를 창 전체로 올린다. 여덟 게임이 같은 길을 쓴다.
 *
 * - 표준 API(`requestFullscreen`)가 먼저, 없으면 webkit 접두(옛 Safari), 그것도 없으면(iPhone Safari) **흉내**(`pseudo`)다 —
 *   루트를 `position: fixed; inset: 0` 으로 세우고 문서 굴림을 잠근다(그리기는 `GameRoomLayout` 이 `data-fullscreen` 으로 한다).
 * - 상태의 정본은 브라우저다: `fullscreenchange`(+ webkit)가 올 때 「지금 전체 화면인 요소가 내 루트인가」를 다시 읽는다. 브라우저의
 *   Esc · 탭 전환 · 다른 요소의 전체 화면이 그대로 반영된다.
 * - Esc 는 두 모드 모두 우리가 받는다. 결과 대화 상자가 열려 있으면 MUI 가 먼저 받아 대화 상자만 닫는다(그 처리기가 전파를 멈춘다).
 * - 화면을 떠나면(언마운트) · 방이 바뀌면(`resetKey`) 풀린다 — 다른 화면이 전체 화면에 갇히지 않는다.
 *
 * 돌려주는 것: `{ active, pseudo, supported, enter, exit, toggle }`. `supported` 가 거짓인 곳은 없다(흉내가 언제나 된다). */

function fullscreenElement(doc) {
  return doc.fullscreenElement || doc.webkitFullscreenElement || null;
}

export function fullscreenApi(el) {
  if (!el) return null;
  if (typeof el.requestFullscreen === "function") return "native";
  if (typeof el.webkitRequestFullscreen === "function") return "webkit";
  return null;
}

export function useFullscreen(rootRef, { resetKey } = {}) {
  const [state, setState] = useState({ active: false, pseudo: false });
  const stateRef = useRef(state);
  stateRef.current = state;

  /* 문서 굴림 잠금 — 흉내 모드에서만. 원래 값을 기억해 두었다가 그대로 돌려놓는다. */
  const lockRef = useRef(null);
  const lockBody = useCallback((on) => {
    if (typeof document === "undefined") return;
    const body = document.body;
    if (on && lockRef.current == null) {
      lockRef.current = body.style.overflow;
      body.style.overflow = "hidden";
    } else if (!on && lockRef.current != null) {
      body.style.overflow = lockRef.current;
      lockRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const onChange = () => {
      const el = rootRef.current;
      const on = !!el && fullscreenElement(document) === el;
      setState((prev) => {
        if (prev.pseudo) return prev; // 흉내 모드는 브라우저 상태와 무관하다
        return prev.active === on ? prev : { active: on, pseudo: false };
      });
    };
    document.addEventListener("fullscreenchange", onChange);
    document.addEventListener("webkitfullscreenchange", onChange);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      document.removeEventListener("webkitfullscreenchange", onChange);
    };
  }, [rootRef]);

  const exit = useCallback(async () => {
    const cur = stateRef.current;
    if (cur.pseudo) {
      lockBody(false);
      setState({ active: false, pseudo: false });
      return;
    }
    if (typeof document === "undefined") return;
    const el = rootRef.current;
    if (!el || fullscreenElement(document) !== el) {
      setState({ active: false, pseudo: false });
      return;
    }
    try {
      if (typeof document.exitFullscreen === "function") await document.exitFullscreen();
      else if (typeof document.webkitExitFullscreen === "function") document.webkitExitFullscreen();
    } catch (e) {
      /* 이미 풀렸다 — 상태만 맞춘다 */
    }
    setState({ active: false, pseudo: false });
  }, [rootRef, lockBody]);

  const enter = useCallback(async () => {
    const el = rootRef.current;
    if (!el) return;
    const api = fullscreenApi(el);
    try {
      if (api === "native") {
        await el.requestFullscreen();
        setState({ active: true, pseudo: false });
        return;
      }
      if (api === "webkit") {
        el.webkitRequestFullscreen();
        setState({ active: true, pseudo: false });
        return;
      }
    } catch (e) {
      /* 브라우저가 거절했다(사용자 동작 밖 · 정책) — 흉내로 내려간다 */
    }
    lockBody(true);
    setState({ active: true, pseudo: true });
  }, [rootRef, lockBody]);

  const toggle = useCallback(() => (stateRef.current.active ? exit() : enter()), [enter, exit]);

  /* Esc — 두 모드 모두 우리가 받는다. 흉내 모드는 브라우저가 대신 풀어 주지 않고, 표준 모드도 브라우저가 Esc 를 쓰지 않는 자리
     (자동화 · 일부 기기)가 있다. 브라우저가 먼저 풀었으면 `exit` 는 상태만 맞춘다. 결과 대화 상자가 열려 있으면 MUI 가 Esc 를 먼저
     받아 대화 상자만 닫는다(전파를 멈춘다) — 다음 Esc 가 전체 화면을 푼다. */
  useEffect(() => {
    if (!state.active || typeof document === "undefined") return undefined;
    const onKey = (e) => {
      if (e.key === "Escape" && !e.defaultPrevented) exit();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [state.active, exit]);

  /* 방이 바뀌거나 화면을 떠나면 푼다. */
  useEffect(() => () => {
    const cur = stateRef.current;
    if (!cur.active) return;
    if (cur.pseudo) {
      lockBody(false);
    } else if (typeof document !== "undefined" && fullscreenElement(document)) {
      try {
        if (typeof document.exitFullscreen === "function") document.exitFullscreen().catch(() => {});
        else if (typeof document.webkitExitFullscreen === "function") document.webkitExitFullscreen();
      } catch (e) { /* 이미 풀렸다 */ }
    }
    setState({ active: false, pseudo: false });
  }, [resetKey, lockBody]);

  return { active: state.active, pseudo: state.pseudo, supported: true, enter, exit, toggle };
}
