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
