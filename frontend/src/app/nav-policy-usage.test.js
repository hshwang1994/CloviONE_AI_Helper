import { describe, it, expect } from "vitest";

import { NAV, SCREEN_ROLES } from "./navConfig.js";

/* 정책 사용 통계에 닿는 길이 있는가.
 *
 * ## 이 파일이 무엇을 대체했는가
 *
 * 원래 결함(IA-01)은 "화면과 역할 게이트는 있는데 **사이드바 항목만 없어서** 형제 화면의
 * 크로스링크나 직접 주소로만 닿을 수 있었다" 였다. 그 결함은 여전히 막아야 한다.
 *
 * 지시 30 재구성으로 정책 사용 통계와 프롬프트 사용 통계는 같은 모양의 리포트 둘이라
 * 한 화면의 탭이 됐다(`/ai-usage`, AdminRoutes.jsx TAB_GROUPS). 그래서 "사이드바에 자기
 * 항목이 있다"가 아니라 **"사이드바에서 닿는 길이 있다"** 로 계약을 옮긴다 — 원래 막으려던
 * 것(닿을 수 없는 화면)은 그대로 막힌다.
 */
describe("사이드바에서 사용 통계에 닿는다", () => {
  const aiGroup = NAV.find((g) => g.group === "AI");
  const item = (aiGroup.items || []).find((i) => i.to === "/ai-usage");

  it("AI 묶음에 '사용 통계' 항목이 있다", () => {
    expect(item).toBeTruthy();
    expect(item.label).toBe("사용 통계");
  });

  it("두 통계 화면의 역할 게이트가 그대로 살아 있고, 그릇도 같은 집합이다", () => {
    expect(SCREEN_ROLES["policy-usage"]).toBeTruthy();
    expect(SCREEN_ROLES["prompt-usage"]).toEqual(SCREEN_ROLES["policy-usage"]);
    // 그릇의 역할이 안쪽 탭보다 넓으면 못 보는 사람이 빈 화면을 보게 된다.
    expect(SCREEN_ROLES["ai-usage"]).toEqual(SCREEN_ROLES["policy-usage"]);
  });
});
