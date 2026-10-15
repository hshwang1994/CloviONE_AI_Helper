import React from "react";
import { CHAT_LAYOUT_REM } from "./layout.js";

export const CHAT_LAYOUT_MODES = ["wide", "medium", "narrow", "mobile"];

/** 카드 폭(px)과 루트 글자 크기(px) → 틀 모드. 순수 함수라 시험이 폭마다 잰다. */
export function chatLayoutMode(widthPx, rootPx = 16) {
  const rem = widthPx / (rootPx || 16);
  if (!Number.isFinite(rem) || rem <= 0) return "medium";
  if (rem >= CHAT_LAYOUT_REM.wide) return "wide";
  if (rem >= CHAT_LAYOUT_REM.medium) return "medium";
  if (rem >= CHAT_LAYOUT_REM.mobile) return "narrow";
  return "mobile";
}

function rootFontPx() {
  if (typeof window === "undefined" || !window.getComputedStyle) return 16;
  const value = parseFloat(window.getComputedStyle(document.documentElement).fontSize);
  return Number.isFinite(value) && value > 0 ? value : 16;
}

/** 판이 놓인 폭을 재서 틀 모드를 낸다. 창 크기가 아니라 **그 자리의 폭**이다(앱 사이드바 · 확대 · 4K 루트 글자가 다 반영된다).
 *  첫 그림 전에 한 번 재고(`useLayoutEffect`), 이후는 `ResizeObserver` 가 바뀔 때만 다시 그린다. */
export function useChatLayout(ref) {
  const [mode, setMode] = React.useState("medium");
  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => setMode(chatLayoutMode(el.getBoundingClientRect().width || el.offsetWidth || 0, rootFontPx()));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return mode;
}
