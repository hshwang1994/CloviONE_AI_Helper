import { describe, it, expect } from "vitest";
import { REGISTRY } from "./registry.js";

/* 저장된 뷰는 **다시 쓸 조건 조합이 있을 만한 목록**에만 선다 (계획 2.9 · 3.18, D-506).
 *
 * 저장된 뷰는 「이 조건 조합을 다음에도 쓰겠다」는 도구다. 행이 몇십 건이고 필터가 한두 개뿐인 목록
 * (프롬프트 · 정책 · AI 사용 한도)에 그 단추가 서면 사람은 무엇을 저장하라는지 모르고, 단추 하나가
 * 화면의 위계를 흐린다. 그래서 기준을 코드로 정한다:
 *
 *   **서버 페이지(`paginated`)이고 조건 칸(검색 포함)이 셋 이상**일 때만 저장된 뷰를 둔다.
 *
 * 그 밖의 목록은 registry 가 `smallSet: true` 로 선언해야 한다. 새 화면이 선언을 빠뜨리면 이 시험이
 * 잡는다. 반대로 기준을 넘는 목록이 `smallSet` 을 달면 조건 조합을 다시 쓸 길을 조용히 잃으므로 그것도 잡는다. */

function conditionCount(config) {
  return (config.filters || []).length + (config.searchable ? 1 : 0);
}

export function wantsSavedViews(config) {
  return !!config.paginated && conditionCount(config) >= 3;
}

describe("registry — 저장된 뷰는 기준을 넘는 목록에만 선다", () => {
  const entries = Object.entries(REGISTRY);

  it("기준에 못 미치는 목록은 전부 smallSet 을 선언한다", () => {
    const missing = entries
      .filter(([, c]) => !wantsSavedViews(c) && !c.smallSet)
      .map(([key, c]) => `${key}(paginated=${!!c.paginated}, 조건=${conditionCount(c)})`);
    expect(missing).toEqual([]);
  });

  it("기준을 넘는 목록은 smallSet 을 달지 않는다 — 다시 쓸 조건 조합을 잃지 않게", () => {
    const hidden = entries.filter(([, c]) => wantsSavedViews(c) && c.smallSet).map(([key]) => key);
    expect(hidden).toEqual([]);
  });

  it("반례 — 기준 판정이 비어 있지 않다(둘 다 있는 세계다)", () => {
    expect(entries.some(([, c]) => wantsSavedViews(c))).toBe(true);
    expect(entries.some(([, c]) => !wantsSavedViews(c))).toBe(true);
  });
});
