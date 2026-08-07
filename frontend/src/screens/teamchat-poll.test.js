import { describe, it, expect } from "vitest";
import { idlePollDelayMs, IDLE_BACKOFF_FACTOR } from "./teamchat-poll.js";

/* 조용한 방에서 물러나는 규칙 (PF1).
 *
 * 여기서 지키려는 성질은 셋이다:
 *   1. 대화 중에는 느려지지 않는다 — 변화가 있으면 항상 base.
 *   2. 조용하면 물러나되, 상한을 넘지 않는다.
 *   3. 폴링을 끈 호출은 끈 채로 둔다(테스트·비활성 방이 조용히 되살아나면 안 된다).
 *
 * **값이 실제로 달라지는 표본**을 쓴다 — base·quiet·max 를 다 같은 값으로 넣으면
 * 어떤 계산을 넣어도 통과한다.
 */

describe("idlePollDelayMs", () => {
  it("방금 바뀐 방은 base 그대로다 (대화 중에 느려지지 않는다)", () => {
    expect(idlePollDelayMs(3000, 0, 30000)).toBe(3000);
    expect(idlePollDelayMs(2000, 0, 10000)).toBe(2000);
  });

  it("조용한 시간이 base 보다 짧으면 여전히 base 다", () => {
    expect(idlePollDelayMs(3000, 1200, 30000)).toBe(3000);
  });

  it("조용한 만큼 기다린다 — 세 표본이 서로 다른 값을 낸다", () => {
    expect(idlePollDelayMs(3000, 6000, 30000)).toBe(6000);
    expect(idlePollDelayMs(3000, 12000, 30000)).toBe(12000);
    expect(idlePollDelayMs(3000, 24000, 30000)).toBe(24000);
  });

  it("상한을 넘지 않는다", () => {
    expect(idlePollDelayMs(3000, 90000, 30000)).toBe(30000);
    expect(idlePollDelayMs(3000, 1e9, 30000)).toBe(30000);
  });

  it("상한을 안 주면 base 의 기본 배수까지만 물러난다", () => {
    expect(idlePollDelayMs(2000, 999999)).toBe(2000 * IDLE_BACKOFF_FACTOR);
    // base 보다 작은 상한은 무시한다 — 그걸 따르면 base 를 준 뜻이 뒤집힌다.
    expect(idlePollDelayMs(2000, 999999, 500)).toBe(2000 * IDLE_BACKOFF_FACTOR);
  });

  it("폴링을 끈 호출은 살려내지 않는다", () => {
    expect(idlePollDelayMs(false, 60000, 30000)).toBe(false);
    expect(idlePollDelayMs(0, 60000, 30000)).toBe(false);
  });

  it("이상한 값(NaN·음수)은 '방금 바뀐 것'으로 본다 — 느려지는 쪽으로 틀리지 않는다", () => {
    expect(idlePollDelayMs(3000, NaN, 30000)).toBe(3000);
    expect(idlePollDelayMs(3000, -5000, 30000)).toBe(3000);
  });

  it("60초 창에서 실제로 요청이 줄어든다 — 규칙을 그대로 돌려 센다", () => {
    // 3초 고정이면 20회. 이 규칙이면 몇 회인가를 손이 아니라 코드로 센다.
    const simulate = (delayOf) => {
      let t = 0, n = 0, quiet = 0;
      while (t < 60000) {
        const d = delayOf(quiet);
        t += d; quiet += d;
        if (t <= 60000) n += 1;
      }
      return n;
    };
    expect(simulate(() => 3000)).toBe(20);
    expect(simulate((quiet) => idlePollDelayMs(3000, quiet, 30000))).toBe(5);
  });
});
