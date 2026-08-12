import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";

/* WF1 R4 — AI 사용 상한 화면의 help가 "상한이 걸리는 곳은 아래 표 위의 '상한이 걸리는 곳'
 * 목록에 서버가 직접 알려 줍니다"라고 말했다. 그런 이름의 목록을 그리는 코드는 저장소에
 * 없다 — 실제로 표 위에 뜨는 건 config.summary(app/quotas/router.py의 /usage 집계, "오늘/
 * 이번 달 전체 AI 호출")뿐이고, 어느 대상이 상한에 걸렸는지는 안 말한다. 없는 기능을
 * 광고하던 문장을 지웠다.
 */
describe("AI 사용 상한 — help 문구가 존재하지 않는 기능을 광고하지 않는다", () => {
  it("'상한이 걸리는 곳' 목록을 더 이상 약속하지 않는다", () => {
    const help = REGISTRY["ai-quotas"].help;
    expect(help).not.toContain("상한이 걸리는 곳");
  });

  it("실제로 존재하는 요약 카드(오늘/이번 달 집계)는 여전히 정확히 설명한다", () => {
    const help = REGISTRY["ai-quotas"].help;
    expect(help).toContain("요약 카드는 조직 전체 합계");
  });
});
