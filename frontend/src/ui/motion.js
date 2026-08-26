import React from "react";
import { MOTION } from "./theme.js";

/* 동작 줄이기(prefers-reduced-motion) 판정 한 곳.
 *
 * CSS 애니메이션은 theme.js 의 전역 규칙이 끈다. 그런데 **JS 가 켜는 연출**(축포처럼
 * 캔버스에 직접 그리는 것, 타이머로 좌표를 옮기는 것)에는 그 규칙이 닿지 않는다 —
 * 화면 코드가 직접 판단해서 시작하지 않아야 한다.
 *
 * 왜 별도 파일인가: 이 판정이 GameRoom.jsx 안에 있었다. 그 화면은 React.lazy 로 분리된
 * 지연 청크라, 초기 로드에 들어가는 코드가 그 함수를 쓰려고 import 하면 게임방 화면
 * 전체가 초기 번들로 끌려 들어온다(번들 예산 문제로 바로 돌아온다).
 */

/** 사용자가 OS 에서 '동작 최소화'를 켰는가.
 *
 * matchMedia 가 없는 환경(jsdom, 아주 오래된 브라우저)에서는 false 로 본다 —
 * 없다고 예외를 던지면 이 함수를 쓰는 화면이 통째로 렌더되지 않는다. */
export function prefersReducedMotion() {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    return !!(mq && mq.matches);
  } catch (e) {
    return false;
  }
}

/* ── 짧은 연출 둘 ────────────────────────────────────────────────────────────
 *
 * 여기 있는 것은 **기다리게 하지 않는 연출**뿐이다. 사용자가 값을 읽기 전에 끝나야 하고
 * (`theme.js::MOTION` 이 그 예산이다), 동작 최소화를 켠 사람에게는 아예 시작하지 않는다.
 *
 * 전역 CSS 규칙이 이미 transition 을 0.01ms 로 만든다. 그래도 여기서 한 번 더 보는 이유는
 * **시작 상태** 때문이다 — 막대를 0 폭에서 켜는 연출은 전환이 없으면 「0 이었다가 갑자기
 * 최종값」이 되어 깜빡임으로 보인다. 동작 최소화면 처음부터 최종 상태로 그린다. */

/* 이미 재생한 지문. 컴포넌트가 언마운트돼도 남아야 **탭을 다시 볼 때 반복 재생되지
   않는다** — 그것이 이 Set 이 모듈 전역에 있는 유일한 이유다. 무한히 자라지 않게
   오래된 것부터 버린다(Set 은 삽입 순서를 지킨다). */
const REVEALED = new Set();
const REVEAL_MEMORY = 200;

function rememberReveal(key) {
  REVEALED.add(key);
  if (REVEALED.size > REVEAL_MEMORY) {
    const oldest = REVEALED.values().next();
    if (!oldest.done) REVEALED.delete(oldest.value);
  }
}

/** 시험 전용 — 지문 기억을 비운다. 제품 코드에서는 부르지 않는다. */
export function resetRevealMemory() {
  REVEALED.clear();
}

/** 데이터 지문 `key` 가 **처음 보이는 것일 때만** 한 번 재생한다.
 *
 * 돌려주는 값이 `false` 인 프레임이 시작 상태이고, 다음 프레임에 `true` 가 된다.
 * 같은 지문으로 다시 마운트되면(탭을 떠났다 돌아오면) 처음부터 `true` 라 안 움직인다.
 *
 * 지문에는 **값**이 들어가야 한다. `"trend"` 처럼 이름만 넣으면 값이 바뀌어도 다시 재생하지
 * 않고, 렌더마다 새로 만든 문자열을 넣으면 볼 때마다 재생한다.
 *
 * 지문이 `null`/`undefined` 면 **연출 자체를 안 건다**(항상 최종 상태). 부품이 이 훅을
 * 늘 부르되 호출부가 지문을 줄 때만 움직이게 하려는 것이다 — 훅은 조건부로 못 부른다. */
export function useRevealOnce(key) {
  const off = key == null;
  const k = off ? "" : String(key);
  const [shown, setShown] = React.useState(() => off || REVEALED.has(k) || prefersReducedMotion());

  React.useEffect(() => {
    if (off) {
      setShown(true);
      return undefined;
    }
    const skip = REVEALED.has(k) || prefersReducedMotion()
      || typeof requestAnimationFrame !== "function";
    rememberReveal(k);
    if (skip) {
      setShown(true);
      return undefined;
    }
    setShown(false);
    /* 같은 프레임에 0 → 1 을 쓰면 브라우저가 중간 상태를 못 봐 전환이 안 생긴다. */
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, [k, off]);

  return shown;
}

/* 전환이 끝났다고 보는 시각. `MOTION.base` 보다 조금 길게 둬서 마지막 프레임이
   `overflow: hidden` 안에서 끝나게 한다. */
const AUTO_HEIGHT_SETTLE_MS = 260;

/** 내용이 바뀔 때 **높이만** 부드럽게 잇는다.
 *
 * 탭을 옮기면 내용 높이가 달라지고, 그 순간 아래 있는 것들이 툭 튄다. 높이를 재서
 * 전환하면 그 튐이 사라진다.
 *
 * `overflow` 를 상시 `hidden` 으로 두지 않는다 — 포커스 링(바깥쪽 2px)과 툴팁이 잘린다.
 * 높이가 실제로 움직이는 동안에만 감춘다.
 *
 * `ResizeObserver` 가 없는 환경(jsdom)에서는 아무것도 안 한다 — 높이는 `auto` 로 남고
 * 화면은 그대로 정상이다. */
export function useAutoHeight() {
  const ref = React.useRef(null);
  const [height, setHeight] = React.useState(null);
  const [moving, setMoving] = React.useState(false);

  React.useEffect(() => {
    if (prefersReducedMotion()) return undefined;
    if (typeof ResizeObserver !== "function") return undefined;
    const node = ref.current;
    if (!node) return undefined;

    let last = null;
    let timer = null;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0] && entries[0].contentRect;
      if (!rect) return;
      const next = rect.height;
      // 1px 미만의 흔들림(글꼴 로딩·소수점 반올림)에는 반응하지 않는다.
      if (last != null && Math.abs(last - next) < 1) return;
      const first = last == null;
      last = next;
      setHeight(next);
      // 첫 측정은 «바뀐 것»이 아니라 «처음 안 것»이다 — 전환을 걸지 않는다.
      if (first) return;
      setMoving(true);
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => setMoving(false), AUTO_HEIGHT_SETTLE_MS);
    });
    ro.observe(node);
    return () => {
      ro.disconnect();
      if (timer) clearTimeout(timer);
    };
  }, []);

  return {
    ref,
    /* 바깥 상자에 그대로 펴 넣는다. 아직 못 쟀으면 `undefined` — 높이는 `auto` 다. */
    sx: height == null ? undefined : {
      height,
      overflow: moving ? "hidden" : "visible",
      transition: `height ${MOTION.base} ${MOTION.ease}`,
    },
  };
}
