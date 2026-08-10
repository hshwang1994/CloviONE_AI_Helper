import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";
import { OBJ_ROUTE, canReachObjRoute } from "./registry/shared.js";

/* 감사 로그의 '관련 항목 보기'/'관련 목록 열기'가 organization·feature_flag 대상 행에서 사라져 있었다.
 *
 * governance.js의 audit 화면은 자기 필터 드롭다운(object_type select)에는 이미 'organization'·
 * 'feature_flag' 옵션을 보강해 뒀다(F15 수정 주석 참고, 이 두 값이 OBJTYPE_OPTS에 없다는 것을
 * 발견하고 고친 자리). 그런데 같은 파일의 '관련 항목 보기'/'관련 목록 열기' 액션은 그 필터가
 * 아니라 shared.js의 OBJ_ROUTE 맵으로 대상 화면 주소를 찾는다 — 그 맵에는 organization·feature_flag가
 * 여전히 없었다. org.js('조직 관리')와 platform.js('기능 플래그')는 각각 이미 "감사 로그에서 보기"로
 * ?object_type=organization / ?object_type=feature_flag 딥링크를 감사 화면으로 걸어 두고 있는데,
 * 정작 그 감사 로그 행에서 되돌아올 버튼이 없어(when이 항상 false) 한쪽 방향 링크만 존재했다.
 */

describe("감사 로그의 '관련 항목 보기'/'관련 목록 열기' — organization·feature_flag", () => {
  it("OBJ_ROUTE가 조직·기능 플래그 화면 주소를 안다(org.js·platform.js의 감사 로그 딥링크와 짝이 맞는다)", () => {
    expect(OBJ_ROUTE.organization).toBe("#/organizations");
    expect(OBJ_ROUTE.feature_flag).toBe("#/feature-flags");
  });

  it("'관련 목록 열기'가 organization 대상 행에서 admin에게 보인다", () => {
    const action = REGISTRY.audit.actions.find((a) => a.label === "관련 목록 열기");
    const row = { object_type: "organization", object_id: "org-1" };
    expect(action.when(row, { role: "admin" })).toBe(true);
    expect(action.navigate(row)).toBe("#/organizations");
  });

  it("'관련 목록 열기'가 feature_flag 대상 행에서 admin에게 보인다", () => {
    const action = REGISTRY.audit.actions.find((a) => a.label === "관련 목록 열기");
    const row = { object_type: "feature_flag", object_id: "chat.enabled" };
    expect(action.when(row, { role: "admin" })).toBe(true);
    expect(action.navigate(row)).toBe("#/feature-flags");
  });

  it("조직 관리 화면은 auditor를 허용하지 않는다 — organization 행의 버튼도 auditor에게는 숨어야 403 막다른 길이 안 생긴다", () => {
    // navConfig.js SCREEN_ROLES.organizations = ["admin", "system_admin"] (auditor 제외).
    expect(canReachObjRoute("organization", "auditor")).toBe(false);
    expect(canReachObjRoute("organization", "admin")).toBe(true);
    const action = REGISTRY.audit.actions.find((a) => a.label === "관련 목록 열기");
    const row = { object_type: "organization", object_id: "org-1" };
    expect(action.when(row, { role: "auditor" })).toBe(false);
  });
});

/* 같은 결함 부류(F15)를 MEGA CYCLE G 조사가 4개 더 찾았다 — ai_quota/approval_delegation/
 * announcement/offboarding_run. 백엔드는 이미 이 object_type들로 감사 기록을 남기고
 * (app/quotas, app/approvals의 delegations_router, app/announcements, app/offboarding) 각
 * 화면도 forward "감사 로그에서 보기" 딥링크를 걸고 있었는데, OBJ_ROUTE에 없어 감사 로그 쪽에서
 * 돌아오는 버튼이 항상 숨겨졌다(offboarding_run은 hand-rolled 화면이라 forward 링크 자체도 없었다).
 */
describe("감사 로그의 '관련 목록 열기' — MEGA CYCLE G에서 새로 찾은 4건", () => {
  it("OBJ_ROUTE가 네 화면 주소를 안다", () => {
    expect(OBJ_ROUTE.ai_quota).toBe("#/ai-quotas");
    expect(OBJ_ROUTE.approval_delegation).toBe("#/approval-delegations");
    expect(OBJ_ROUTE.announcement).toBe("#/announcements");
    expect(OBJ_ROUTE.offboarding_run).toBe("#/offboarding");
  });

  it.each([
    ["ai_quota", "#/ai-quotas"],
    ["approval_delegation", "#/approval-delegations"],
    ["announcement", "#/announcements"],
  ])("'%s' 대상 행은 admin에게 '관련 목록 열기'가 보이고 %s로 이동한다(role 제한 없음)", (objectType, route) => {
    const action = REGISTRY.audit.actions.find((a) => a.label === "관련 목록 열기");
    const row = { object_type: objectType, object_id: "x-1" };
    expect(action.when(row, { role: "admin" })).toBe(true);
    expect(action.navigate(row)).toBe(route);
  });

  it("offboarding_run 대상 행은 admin에게는 보이지만 auditor에게는 숨는다(오프보딩 화면 자체가 admin/system_admin 전용)", () => {
    expect(canReachObjRoute("offboarding_run", "auditor")).toBe(false);
    expect(canReachObjRoute("offboarding_run", "admin")).toBe(true);
    const action = REGISTRY.audit.actions.find((a) => a.label === "관련 목록 열기");
    const row = { object_type: "offboarding_run", object_id: "run-1" };
    expect(action.when(row, { role: "admin" })).toBe(true);
    expect(action.when(row, { role: "auditor" })).toBe(false);
    expect(action.navigate(row)).toBe("#/offboarding");
  });

  it("audit 화면의 object_type 필터 드롭다운에도 네 옵션이 보강돼 있다", () => {
    const field = REGISTRY.audit.filters.find((f) => f.key === "object_type");
    const values = field.options.map((o) => o.value);
    expect(values).toEqual(expect.arrayContaining(["ai_quota", "approval_delegation", "announcement", "offboarding_run"]));
  });

  it("ai-quotas·announcements·approval-delegations 화면에 forward '감사 로그에서 보기' 액션이 있다", () => {
    expect(REGISTRY["ai-quotas"].actions.some((a) => a.label === "감사 로그에서 보기")).toBe(true);
    expect(REGISTRY.announcements.actions.some((a) => a.label === "감사 로그에서 보기")).toBe(true);
    expect(REGISTRY["approval-delegations"].actions.some((a) => a.label === "감사 로그에서 보기")).toBe(true);
  });
});
