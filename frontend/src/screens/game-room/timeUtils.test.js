/* timeUtils.js — 순수 함수 unit 테스트.
 *
 * 배경 — 이 파일은 지금까지 직접 테스트가 없었다(gameroom.test.jsx/gameroom-smoke.test.jsx는
 * GameRoom 전체를 렌더해 카운트다운이 "어쨌든 숫자로 보인다"만 확인했지, toDate()의 UTC
 * 파싱 규칙 자체는 한 번도 단정하지 않았다). 파일 자체 docstring이 명시한 회귀 위험:
 * "Z를 붙여 UTC로 파싱해야 브라우저가 로컬(KST)로 오해하지 않는다 ... 빼먹으면 마감이
 * 9시간 과거로 계산돼 카운트다운이 즉시 0이 되고 가위바위보가 바로 자동 처리되는 버그".
 * 그 규칙을 여기서 직접 고정한다. */
import { describe, it, expect } from "vitest";
import { toDate, fmtTime } from "./timeUtils.js";

describe("toDate — 타임존 표기 없는 백엔드 isoformat을 UTC로 파싱한다", () => {
  it("입력값 없음/빈 문자열이면 null", () => {
    expect(toDate(null)).toBeNull();
    expect(toDate(undefined)).toBeNull();
    expect(toDate("")).toBeNull();
  });

  it("Z/오프셋이 없는 문자열은 UTC로 취급한다 — KST로 오해해 9시간 어긋나지 않는다", () => {
    const d = toDate("2026-07-29T05:30:00");
    expect(d).not.toBeNull();
    // Z를 붙여 파싱했다면 getTime()이 명시적 UTC 파싱과 정확히 같아야 한다.
    expect(d.getTime()).toBe(new Date("2026-07-29T05:30:00Z").getTime());
    // 회귀 방지: 로컬(KST, UTC+9)로 오해해 파싱했다면 9시간(32,400,000ms) 달라진다.
    const misparsedAsLocalKst = new Date("2026-07-29T05:30:00+09:00").getTime();
    expect(d.getTime()).not.toBe(misparsedAsLocalKst);
  });

  it("이미 Z가 붙어 있으면 다시 붙이지 않는다(중복 부착으로 깨지지 않음)", () => {
    const d = toDate("2026-07-29T05:30:00Z");
    expect(d.getTime()).toBe(Date.UTC(2026, 6, 29, 5, 30, 0));
  });

  it("소문자 z, 명시적 오프셋(+09:00)도 그대로 존중한다", () => {
    expect(toDate("2026-07-29T05:30:00z").getTime()).toBe(Date.UTC(2026, 6, 29, 5, 30, 0));
    const withOffset = toDate("2026-07-29T14:30:00+09:00");
    // +09:00 14:30 == UTC 05:30 — 오프셋이 존중되면 Z로 강제 파싱했을 때와 같은 순간이어야 한다.
    expect(withOffset.getTime()).toBe(Date.UTC(2026, 6, 29, 5, 30, 0));
  });

  it("밀리초가 있어도 UTC로 파싱한다", () => {
    const d = toDate("2026-07-29T05:30:00.500");
    expect(d.getTime()).toBe(Date.UTC(2026, 6, 29, 5, 30, 0, 500));
  });

  it("파싱 불가능한 문자열은 예외 없이 null", () => {
    expect(toDate("이건-날짜가-아니다")).toBeNull();
    expect(toDate("2026-13-99T99:99:99")).toBeNull();
  });
});

describe("fmtTime — 채팅 시각 표시, 파싱 실패 시 빈 문자열", () => {
  it("파싱 가능한 시각은 두 자리 시:분 문자열을 낸다", () => {
    const out = fmtTime("2026-07-29T05:30:00");
    expect(out).toMatch(/\d{1,2}:\d{2}/);
  });

  it("null/빈 값/파싱 불가 문자열은 빈 문자열(예외를 던지지 않음)", () => {
    expect(fmtTime(null)).toBe("");
    expect(fmtTime(undefined)).toBe("");
    expect(fmtTime("")).toBe("");
    expect(fmtTime("이건-날짜가-아니다")).toBe("");
  });
});
