import React from "react";

/* 유휴 감지 — "퇴근한 사람이 접속 중" 을 끄는 신호 (X12).
 *
 * ## 왜 가시성으로는 못 고치나
 *
 * `document.hidden` 은 '탭이 가려졌는가' 만 안다. 모니터 전원을 끄고 간 사람, 화면을 잠근
 * 사람, 회의에 간 사람은 **탭이 그대로 보이는 상태**다. 그 탭의 폴링은 계속 돌고, 서버는
 * 폴링을 '아직 여기 있다'로 읽어 초록 점을 밤새 켜 둔다. 감사가 확인한 그대로다.
 *
 * 반대로 탭이 정말 숨는 경우는 이미 막혀 있다: react-query 는 `refetchIntervalInBackground`
 * 기본값이 false 라 숨은 탭에서 주기 갱신을 멈춘다(app/polling-visibility.test.js). 그래서
 * 남은 구멍은 정확히 하나, **'탭은 보이는데 사람은 없다'** 다.
 *
 * ## 그래서 무엇을 신호로 쓰나 — 사람의 입력
 *
 * 브라우저가 사람의 존재에 대해 알 수 있는 것은 입력뿐이다. 아래 이벤트 중 하나라도 오면
 * '방금 사람이 있었다'로 본다:
 *
 *   pointermove  — 읽기만 하는 사람도 마우스는 움직인다. 이걸 빼면 **긴 글을 읽는 사람이
 *                  유휴로 잡힌다.** 가장 흔한 오탐을 막는 항목이라 반드시 넣는다.
 *   scroll/wheel — 읽는 동작 그 자체다.
 *   keydown      — 타이핑. (input 이벤트는 따로 안 본다, keydown 이 앞선다)
 *   pointerdown  — 클릭·탭.
 *   touchstart   — 터치 기기의 클릭.
 *
 * 일부러 뺀 것: `mousemove` 대신 `pointermove` 만 쓴다(같은 동작이 두 번 잡힌다).
 * `focus`/`blur` 도 안 쓴다 — 창을 옮겨 다니는 것은 자리에 있다는 뜻도, 없다는 뜻도 아니다.
 *
 * ## 왜 10분인가
 *
 * 두 방향의 실패 비용이 **대칭이 아니다.**
 *   - 너무 길면: 퇴근한 사람이 그만큼 더 오래 켜져 있다. 손해는 '조금 더 늦게 꺼진다'.
 *   - 너무 짧으면: **일하고 있는 사람이 오프라인으로 그려진다.** 동료가 말 걸기를 포기한다.
 * 두 번째가 훨씬 나쁘다. 그래서 넉넉히 잡는다.
 *
 * 10분은 온라인 창(app/team_chat/service.py `ONLINE_SECONDS` = 120초)의 다섯 배다. 잠깐
 * 멈춘 사람(문서를 읽거나, 옆 사람과 말하거나, 커피를 가져오는)은 절대 꺼지지 않는다.
 * 반대로 마우스·키보드·스크롤을 **10분 동안 한 번도** 건드리지 않은 상태를 '읽는 중'으로
 * 설명하기는 어렵다 — 자리 비움 쪽이 훨씬 그럴듯하다.
 *
 * 그리고 오탐의 비용이 작다: 돌아와 한 번만 움직이면 다음 폴링이 `idle` 을 떼고 나가고,
 * 그때 `last_seen` 은 이미 30초 스로틀을 지나 있어 **즉시** 다시 켜진다.
 *
 * ## 모르는 것은 유휴로 치지 않는다
 *
 * 아직 입력을 한 번도 못 본 상태(마운트 직후, 서버 렌더 등)는 '유휴 아님'이다. 모른다는
 * 이유로 사람을 지우지 않는다 — 위에서 정한 비대칭 그대로다.
 */

// 이 값을 줄이려면 위 '왜 10분인가' 를 먼저 읽어라. ONLINE_SECONDS 와 짝이다.
export const IDLE_AFTER_MS = 10 * 60 * 1000;

export const ACTIVITY_EVENTS = [
  "pointermove", "pointerdown", "keydown", "wheel", "scroll", "touchstart",
];

/** 순수 판정 — 테스트가 시각을 직접 넣는다(타이머에 의존하지 않게). */
export function isIdle(lastActivityAt, now, afterMs = IDLE_AFTER_MS) {
  // 모르면 유휴가 아니다(위 docstring). null·undefined·NaN 전부 여기로 떨어진다.
  if (typeof lastActivityAt !== "number" || !Number.isFinite(lastActivityAt)) return false;
  const elapsed = now - lastActivityAt;
  // 시계가 뒤로 간 경우(음수)도 유휴가 아니다 — 시계 때문에 사람을 지우지 않는다.
  if (!(elapsed >= 0)) return false;
  return elapsed >= afterMs;
}

/* 지금 유휴인지 **묻는 함수**를 돌려준다.
 *
 * 왜 boolean 상태가 아니라 getter 인가: `pointermove` 는 초당 수십 번 온다. 그걸 상태로
 * 올리면 마우스를 움직이는 동안 화면 전체가 계속 다시 그려진다. 값은 ref 에만 쌓고,
 * 실제로 필요한 순간(폴링이 주소를 만들 때) 한 번 계산한다 — 별도 타이머도 필요 없다.
 */
export function useIdleGetter(afterMs = IDLE_AFTER_MS) {
  const lastRef = React.useRef(Date.now());

  React.useEffect(() => {
    const mark = () => { lastRef.current = Date.now(); };
    // 탭이 다시 보이면 사람이 돌아온 것으로 본다 — 화면을 다시 켜는 것도 사람의 행동이다.
    const onVisible = () => { if (!document.hidden) mark(); };
    // passive: 스크롤 성능을 건드리지 않는다. capture: 안쪽에서 stopPropagation 해도 놓치지 않는다.
    const opts = { passive: true, capture: true };
    ACTIVITY_EVENTS.forEach((name) => window.addEventListener(name, mark, opts));
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, mark, opts));
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return React.useCallback(() => isIdle(lastRef.current, Date.now(), afterMs), [afterMs]);
}
