/* 팀 채팅 폴링 간격 — 조용한 방은 천천히 묻는다 (PF1).
 *
 * 왜 필요한가. 홈 하단 팀 채팅 위젯은 3초마다 방을 다시 물었다. 홈을 열어 둔 채 회의에
 * 다녀오면 **아무도 아무 말도 안 한 방에** 분당 20요청이 나갔다 — 실제로 재 보니 홈 전체
 * 분당 24요청 중 20이 이것 하나였다(src/app/home-request-budget.test.jsx).
 *
 * 규칙은 한 줄이다: **조용했던 만큼 기다린다.**
 *   다음 간격 = clamp(마지막 변화 이후 흐른 시간, base, max)
 *
 * 이 규칙을 고른 이유:
 *   - 대화가 오가는 동안에는 변화가 계속 생겨 흐른 시간이 0 에 가깝다 → 항상 base(실시간감 유지).
 *   - 조용해질수록 간격이 저절로 배로 늘어난다(3 → 6 → 12 → 24 → 상한). 따로 카운터를
 *     들고 다닐 필요가 없다.
 *   - **순수 함수다.** 같은 상태로 여러 번 불러도 같은 답이 나온다. react-query 는
 *     갱신마다 이 콜백을 다시 부르므로, 부를 때마다 값이 달라지는 계산(호출 횟수 누적)을
 *     넣으면 구독·옵션 변경 같은 무관한 이유로도 간격이 흔들린다.
 *
 * 순수 함수로 뽑아 둔 이유는 하나 더 있다: `refetchInterval` 콜백 안에 인라인으로 두면
 * 가짜 타이머로 검증할 방법이 없다(chat-helpers.js 의 pollDelayMs 가 남긴 교훈 그대로).
 */

/** 상한을 따로 안 줬을 때 base 의 몇 배까지 물러날 것인가. */
export const IDLE_BACKOFF_FACTOR = 3;

/**
 * @param {number|false} base    변화가 있을 때의 간격(ms). 0/false 면 폴링하지 않는다.
 * @param {number} quietMs       마지막으로 방이 바뀐 뒤 흐른 시간(ms).
 * @param {number} [max]         상한(ms). 생략하면 base * IDLE_BACKOFF_FACTOR.
 * @returns {number|false}
 */
export function idlePollDelayMs(base, quietMs, max) {
  // 폴링을 끈 호출(테스트·비활성 방)은 끈 채로 둔다 — 여기서 살려내면 호출자의 뜻이
  // 조용히 뒤집힌다.
  if (!base || base <= 0) return false;
  const cap = max && max > base ? max : base * IDLE_BACKOFF_FACTOR;
  const quiet = Number.isFinite(quietMs) && quietMs > 0 ? quietMs : 0;
  return Math.min(Math.max(base, quiet), cap);
}
