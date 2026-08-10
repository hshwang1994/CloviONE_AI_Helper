import { describe, it, expect } from "vitest";

import { objKo, actionKo } from "./format.js";

/* organization/feature_flag는 OBJ_ROUTE(registry/shared.js)에 먼저 추가됐지만 표시용 사전
 * (OBJECT_KO/VERB_KO)엔 한 번도 안 들어와 있었다 — 감사 로그의 '대상'/'작업' 칸에 영어 원문이
 * 샜다. ai_quota/approval_delegation/announcement/offboarding(.run/.undo)도 MEGA CYCLE G의
 * 크로스링크 조사에서 같은 결함 부류로 함께 발견했다.
 */
describe("감사 로그 '대상' 칸 — 새로 채운 object_type 번역", () => {
  it.each([
    ["organization", "조직"],
    ["feature_flag", "기능 플래그"],
    ["ai_quota", "AI 사용 상한"],
    ["approval_delegation", "승인 위임"],
    ["announcement", "공지"],
    ["offboarding_run", "오프보딩"],
  ])("objKo('%s') === '%s' — 영어 원문이 새지 않는다", (raw, ko) => {
    expect(objKo(raw)).toBe(ko);
  });
});

describe("감사 로그 '작업' 칸 — offboarding.run/offboarding.undo", () => {
  it("offboarding.run은 '오프보딩, 실행'으로 번역된다(예전엔 'offboarding, 실행')", () => {
    expect(actionKo("offboarding.run")).toBe("오프보딩, 실행");
  });

  it("offboarding.undo는 '오프보딩, 되돌리기'로 번역된다(예전엔 'offboarding, undo')", () => {
    expect(actionKo("offboarding.undo")).toBe("오프보딩, 되돌리기");
  });
});
