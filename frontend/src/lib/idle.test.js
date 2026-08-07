import { describe, it, expect } from "vitest";
import { IDLE_AFTER_MS, ACTIVITY_EVENTS, isIdle } from "./idle.js";

/* 유휴 판정 (X12) — "퇴근한 사람이 접속 중" 을 끄는 신호.
 *
 * 여기서 지키려는 것은 **비대칭**이다. 늦게 꺼지는 것은 불편이고, 일하는 사람이 꺼지는 것은
 * 고장이다. 그래서 애매한 입력은 전부 '유휴 아님' 으로 떨어져야 한다.
 */

const NOW = 1_800_000_000_000;

describe("유휴 임계값", () => {
  it("온라인 창(120초)보다 훨씬 크다 — 잠깐 멈춘 사람이 깜빡이면 안 된다", () => {
    // app/team_chat/service.py ONLINE_SECONDS = 120.0 과 짝이다. 이 값을 그 근처로 내리면
    // 자리에 앉아 글을 읽는 사람이 오프라인으로 깜빡이기 시작한다.
    expect(IDLE_AFTER_MS).toBeGreaterThanOrEqual(120 * 1000 * 4);
  });

  it("읽기만 하는 동작(마우스 움직임, 스크롤)을 활동으로 센다", () => {
    // 이 둘을 빼면 긴 글을 읽는 사람이 유휴로 잡힌다 — 가장 흔한 오탐이다.
    expect(ACTIVITY_EVENTS).toContain("pointermove");
    expect(ACTIVITY_EVENTS).toContain("scroll");
    expect(ACTIVITY_EVENTS).toContain("keydown");
  });
});

describe("isIdle", () => {
  it("임계값을 넘게 아무 입력이 없으면 유휴다", () => {
    expect(isIdle(NOW - IDLE_AFTER_MS - 1, NOW)).toBe(true);
    expect(isIdle(NOW - IDLE_AFTER_MS, NOW)).toBe(true);
  });

  it("임계값 안이면 유휴가 아니다", () => {
    expect(isIdle(NOW - IDLE_AFTER_MS + 1, NOW)).toBe(false);
    expect(isIdle(NOW - 1000, NOW)).toBe(false);
    expect(isIdle(NOW, NOW)).toBe(false);
  });

  it("한 번 움직이면 곧바로 유휴에서 빠져나온다", () => {
    const away = NOW - IDLE_AFTER_MS - 60_000;
    expect(isIdle(away, NOW)).toBe(true);
    // 사람이 돌아와 마우스를 한 번 움직였다 → 마지막 활동이 지금이 된다.
    expect(isIdle(NOW, NOW)).toBe(false);
  });

  it("입력을 아직 한 번도 못 본 상태는 유휴가 아니다", () => {
    // 모른다는 이유로 사람을 지우지 않는다.
    expect(isIdle(null, NOW)).toBe(false);
    expect(isIdle(undefined, NOW)).toBe(false);
    expect(isIdle(NaN, NOW)).toBe(false);
  });

  it("시계가 뒤로 가도 유휴로 몰지 않는다", () => {
    expect(isIdle(NOW + 60_000, NOW)).toBe(false);
  });

  it("임계값은 인자로 바꿀 수 있다(테스트가 실제 10분을 기다리지 않도록)", () => {
    expect(isIdle(NOW - 5000, NOW, 1000)).toBe(true);
    expect(isIdle(NOW - 500, NOW, 1000)).toBe(false);
  });
});
