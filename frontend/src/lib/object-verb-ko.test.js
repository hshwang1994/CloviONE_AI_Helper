import { describe, it, expect } from "vitest";

import { objKo, actionKo, approvalTypeKo } from "./format.js";

/* organization/feature_flag는 OBJ_ROUTE(registry/shared.js)에 먼저 추가됐지만 표시용 사전
 * (OBJECT_KO/VERB_KO)엔 한 번도 안 들어와 있었다 — 감사 로그의 '대상'/'작업' 칸에 영어 원문이
 * 샜다. ai_quota/approval_delegation/announcement/offboarding(.run/.undo)도 MEGA CYCLE G의
 * 크로스링크 조사에서 같은 결함 부류로 함께 발견했다.
 */
describe("감사 로그 '대상' 칸 — 새로 채운 object_type 번역", () => {
  it.each([
    ["organization", "조직"],
    ["feature_flag", "기능 플래그"],
    ["ai_quota", "AI 사용 한도"],
    ["approval_delegation", "승인 위임"],
    ["announcement", "공지"],
    ["offboarding_run", "오프보딩"],
  ])("objKo('%s') === '%s' — 영어 원문이 새지 않는다", (raw, ko) => {
    expect(objKo(raw)).toBe(ko);
  });
});

/* qa-contract-change: 감사 동작은 쉼표로 이은 두 낱말(「오프보딩, 실행」)이 아니라 「대상 동작」 명사구(「오프보딩 실행」)다(계획 5절).
   같은 두 사례의 기대값만 새 모양으로 바꾸고, 승인 유형 사전이 서버 낱말과 같다는 단언을 더한다. */
describe("감사 로그 '작업' 칸 — offboarding.run/offboarding.undo", () => {
  it("offboarding.run은 '오프보딩 실행'으로 번역된다(예전엔 'offboarding, 실행')", () => {
    expect(actionKo("offboarding.run")).toBe("오프보딩 실행");
  });

  it("offboarding.undo는 '오프보딩 되돌리기'로 번역된다(예전엔 'offboarding, undo')", () => {
    expect(actionKo("offboarding.undo")).toBe("오프보딩 되돌리기");
  });

  it("두 낱말을 쉼표로 잇지 않는다 — 「스케줄 활성화」", () => {
    expect(actionKo("schedule.enable")).toBe("스케줄 활성화");
    expect(actionKo("schedule.enable")).not.toMatch(/,/);
  });
});

describe("승인 요청 유형 — 서버와 같은 낱말", () => {
  it.each([
    ["user.role_change", "역할 변경"],
    ["integration.change_config", "연동 설정 변경"],
    ["schedule.enable", "스케줄 활성화"],
    ["ai.document_create", "AI 문서 만들기"],
  ])("approvalTypeKo('%s') === '%s'", (raw, ko) => {
    expect(approvalTypeKo(raw)).toBe(ko);
  });

  it("사전에 없는 유형은 감사 동작 번역으로 대신하고 빈 값은 「-」다", () => {
    expect(approvalTypeKo("offboarding.run")).toBe("오프보딩 실행");
    expect(approvalTypeKo("")).toBe("-");
  });
});
