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
