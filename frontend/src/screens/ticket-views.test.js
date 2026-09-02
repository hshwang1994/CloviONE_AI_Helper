import { describe, it, expect } from "vitest";
import { TICKET_VIEW_KEYS, invalidateTicketViews } from "./ticket-views.js";

/* 무효화 폭의 계약 (E6 · 요청 경제).
 *
 * 🔴 예전에는 `["tickets"]` 접두 전체를 무효화해서, 드래그 한 번에 **바뀐 것이 없는**
 * 후보 목록(프로젝트·메타·담당자, ticket-options.js)까지 다시 불렀다 — 편집·이동이
 * 잦은 판에서 이 셋이 매번 재요청되는 것이 429 를 거들었다. 목록 질의(둘째 마디가
 * "/api/…" 경로)는 계속 잡히고, 후보 목록만 빠진다.
 */

function fakeQc() {
  const calls = [];
  return { calls, invalidateQueries: (arg) => calls.push(arg) };
}

describe("invalidateTicketViews", () => {
  it("🔴 후보 목록(meta·projects·assignees)은 무효화에서 빠진다", () => {
    const qc = fakeQc();
    invalidateTicketViews(qc);
    const withPredicate = qc.calls.filter((c) => typeof c.predicate === "function");
    expect(withPredicate).toHaveLength(1);
    const p = withPredicate[0].predicate;
    expect(p({ queryKey: ["tickets", "meta"] })).toBe(false);
    expect(p({ queryKey: ["tickets", "projects"] })).toBe(false);
    expect(p({ queryKey: ["tickets", "assignees", "p-1"] })).toBe(false);
    // 진짜 목록 질의는 계속 잡힌다 — 여기가 풀리면 「저장했는데 안 바뀐다」로 돌아간다.
    expect(p({ queryKey: ["tickets", "/api/my-tickets", "q="] })).toBe(true);
    // 이 predicate 는 tickets 접두 몫이다 — 다른 접두사는 아래 개별 호출이 잡는다.
    expect(p({ queryKey: ["home", "today"] })).toBe(false);
  });

  it("나머지 접두사는 전부 개별 무효화되고 옵션이 그대로 흐른다", () => {
    const qc = fakeQc();
    invalidateTicketViews(qc, { refetchType: "all" });
    const prefixes = qc.calls.filter((c) => c.queryKey).map((c) => c.queryKey[0]);
    for (const key of TICKET_VIEW_KEYS.filter((k) => k[0] !== "tickets")) {
      expect(prefixes).toContain(key[0]);
    }
    expect(qc.calls.every((c) => c.refetchType === "all")).toBe(true);
  });
});
