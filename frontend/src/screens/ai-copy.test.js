import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";

/* AI 화면의 문구(계획 3.12, D-521). 화면은 **실제로 하는 일만** 말한다 - 런타임이 프롬프트와 정책을 읽기 전에는 도움말이
 * 「발행하면 쓰입니다」라고 말했고, 사용 통계는 「스케줄이 참조하지 않음」을 「쓰이지 않음」이라고 불렀다. 여기서 지키는 것:
 *
 *  1. 네 화면의 도움말과 빈 화면 문구가 지금의 동작을 말한다(프롬프트는 다음 호출부터, 정책은 다음 요청부터, 한도가 없으면
 *     제한이 없고, 기록이 없으면 AI 연결부터 설정한다).
 *  2. 네 AI 화면(프롬프트, 정책, 사용 한도, 사용 통계)에는 저장된 뷰가 없다 - 행이 수십 줄이고 조건이 한두 개라 이름
 *     붙여 저장할 탐색이 없다. 호출 기록 탭만은 180일치 서버 페이지 목록에 조건이 넷이라 저장된 뷰 기준(D-506)을 따른다.
 *  3. 없어진 개념(테스트 · 검토 단계, 스케줄 참조, 「쓰이지 않음」)을 말하지 않는다.
 */

const AI_SCREENS = ["prompts", "policies", "ai-quotas", "ai-usage-stats", "ai-usage-records", "prompt-usage", "policy-usage"];
// 저장된 뷰가 없는 화면. 호출 기록은 빠진다 - 서버 페이지 목록이라 기준이 정한다.
const NO_SAVED_VIEWS = AI_SCREENS.filter((key) => key !== "ai-usage-records");

describe("AI 화면 문구", () => {
  it("도움말과 빈 화면이 지금의 동작을 말한다", () => {
    expect(REGISTRY.prompts.help).toContain("다음 AI 호출부터");
    expect(REGISTRY.policies.help).toContain("다음 AI 요청부터");
    expect(REGISTRY["ai-quotas"].emptyTitle).toBe("한도가 없으면 제한 없이 사용합니다");
    expect(REGISTRY["ai-usage-stats"].emptyTitle).toBe("아직 AI 호출 기록이 없습니다");
    expect(REGISTRY["ai-usage-stats"].emptyHelp).toContain("AI 연결을 먼저 설정하세요");
    // AI 설정 탭은 「AI 연결」 화면이 됐다(D-539).
    expect(REGISTRY["ai-usage-stats"].emptyRelatedLink.href).toBe("#/ai-connection");
  });

  it("AI 화면에는 저장된 뷰가 없고, 호출 기록만 저장된 뷰 기준을 따른다", () => {
    for (const key of NO_SAVED_VIEWS) {
      expect(REGISTRY[key].smallSet, key + " 에 저장된 뷰가 선다").toBe(true);
    }
    const records = REGISTRY["ai-usage-records"];
    expect(records.paginated).toBe(true);
    expect(records.smallSet, "호출 기록이 다시 쓸 조건 조합을 잃는다").toBeFalsy();
  });

  it("없어진 개념을 말하지 않는다", () => {
    for (const key of AI_SCREENS) {
      const cfg = REGISTRY[key];
      const text = [cfg.help, cfg.emptyTitle, cfg.emptyHelp].filter(Boolean).join(" ");
      for (const gone of ["테스트로", "검토로", "스케줄", "쓰이지 않음", "러너"]) {
        expect(text, key + " 가 「" + gone + "」를 말한다").not.toContain(gone);
      }
    }
  });
});
