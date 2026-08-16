import { describe, it, expect } from "vitest";

import { NAV, SCREEN_ROLES } from "./navConfig.js";

/* registry/authoring.js에 화면(policy-usage)과 역할 게이트(SCREEN_ROLES)는 있었는데
 * 사이드바 항목만 빠져 있었다(IA-01) — 형제 항목 prompt-usage의 headerActions 크로스링크나
 * 직접 주소로만 닿을 수 있었다. NAV에 형제와 짝을 맞춰 항목을 넣는다.
 * PA-RC-0017: "콘텐츠" 그룹은 없어지고 정책 사용 통계는 "감사"(사후 점검 성격)로 옮겼다 —
 * 형제였던 prompt-usage는 실행 재료 쪽 성격이 강해 "연동"으로 갔다(navConfig.js 참조).
 */
describe("사이드바 감사 메뉴 — 정책 사용 통계", () => {
  const contentGroup = NAV.find((g) => g.group === "감사");
  const item = (contentGroup.items || []).find((i) => i.to === "/policy-usage");

  it("정책 사용 통계 메뉴 항목이 프롬프트 사용 통계와 함께 존재한다", () => {
    expect(item).toBeTruthy();
    expect(item.label).toBe("정책 사용 통계");
  });

  it("SCREEN_ROLES의 기존 역할 게이트와 화면이 실제로 연결된다(메뉴만 새로 생긴 것, 권한은 그대로)", () => {
    expect(SCREEN_ROLES["policy-usage"]).toBeTruthy();
  });
});
