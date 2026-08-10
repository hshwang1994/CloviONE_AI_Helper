import { describe, it, expect } from "vitest";

import { REGISTRY } from "../registry.js";

/* FN-07: 문서 "재시도" 버튼이 POST /{id}/retry(같은 레코드를 그대로 재큐잉 — round30
 * 감사 E High가 만든 idempotency 충돌 해결책) 대신 계속 '+ 문서 생성' 폼을 재오픈해
 * /generate를 불렀다 — 재시도가 아니라 새 생성이었고, 멱등성·연결이 사라졌다.
 * jobs·schedule-runs 재시도와 같은 confirm+path 패턴으로 맞춘다. */

describe("문서 '재시도' 액션이 진짜 재시도 엔드포인트를 부른다", () => {
  it("path가 POST /api/admin/documents/{id}/retry다(생성 폼 재오픈이 아니다)", () => {
    const action = REGISTRY.documents.actions.find((a) => a.label === "재시도");
    expect(action).toBeTruthy();
    expect(action.path({ id: "gen-1" })).toBe("/api/admin/documents/gen-1/retry");
  });

  it("확인 문구가 있고, 새 생성 폼(fields/initial)을 쓰지 않는다", () => {
    const action = REGISTRY.documents.actions.find((a) => a.label === "재시도");
    expect(typeof action.confirm).toBe("string");
    expect(action.fields).toBeUndefined();
    expect(action.initial).toBeUndefined();
  });

  it("실패·품질 미달 행에서만 보인다", () => {
    const action = REGISTRY.documents.actions.find((a) => a.label === "재시도");
    expect(action.when({ status: "failed" })).toBe(true);
    expect(action.when({ status: "quality_failed" })).toBe(true);
    expect(action.when({ status: "completed" })).toBe(false);
  });
});
