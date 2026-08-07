import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";

/* 감사 로그의 '관련 목록 열기'가 schedule_run 대상 행에서 사라져 있었다.
 *
 * governance.js의 audit 화면은 '관련 목록 열기'에서 object_type==='schedule_run'을 명시적으로
 * 제외한다. 그 주석은 "알림 화면의 동일한 제외(registry.js notifications.actions)와 맞춘다"고
 * 적혀 있지만, notifications.js는 이미 그 제외를 없앴다(주석: "schedule_run도 이제 여기 포함한다
 * — 목록 전체로라도 보내는 게 아무 동작도 없는 것보다는 낫다"). 즉 감사 화면의 주석은 더 이상
 * 사실이 아닌 근거를 대고 있고, 그 결과 schedule_run 감사 행(OBJTYPE_OPTS에 있고 필터로도 고를
 * 수 있는 유효한 대상 유형)은 감사 화면에서 어디로도 이동할 방법이 없는 막다른 길로 남았다 —
 * 알림 화면의 동일한 행은 '#/schedules'로 이동할 수 있는데 감사 화면만 못 간다.
 */

describe("감사 로그의 '관련 목록 열기' — schedule_run", () => {
  it("schedule_run 대상 행에서도 admin에게 '관련 목록 열기'가 보인다(알림 화면과 동일하게)", () => {
    const action = REGISTRY.audit.actions.find((a) => a.label === "관련 목록 열기");
    const row = { object_type: "schedule_run", object_id: "run-1" };
    expect(action.when(row, { role: "admin" })).toBe(true);
    expect(action.navigate(row)).toBe("#/schedules");
  });
});
