import { describe, it, expect } from "vitest";
import { shouldRetryQuery } from "./queryRetry.js";

/* PA-RC-0034: 확정적 4xx(예: 없는 상세 id의 404)는 다시 불러도 같은 응답이 온다 —
 * react-query 기본값(retry:3)을 그대로 물려받으면 /board/<없는 id>가 4번(1+3) 왕복한
 * 뒤에야 "찾을 수 없습니다"가 떴다(20~30초). 이 판정 함수 하나가 QueryClient
 * defaultOptions에 그대로 꽂히므로(main.jsx), 여기서는 그 판정 자체만 순수 함수로 고정한다.
 */
describe("shouldRetryQuery — 4xx는 재시도하지 않는다", () => {
  it("404는 재시도하지 않는다(첫 실패에서 바로 포기)", () => {
    expect(shouldRetryQuery(0, { status: 404 })).toBe(false);
  });

  it("400·401·403·409·429도 전부 재시도하지 않는다 — 4xx는 다시 불러도 같은 응답이 온다", () => {
    for (const status of [400, 401, 403, 409, 429]) {
      expect(shouldRetryQuery(0, { status })).toBe(false);
    }
  });

  it("5xx는 최대 2번까지 재시도한다 — 일시적일 수 있다", () => {
    expect(shouldRetryQuery(0, { status: 500 })).toBe(true);
    expect(shouldRetryQuery(1, { status: 500 })).toBe(true);
    expect(shouldRetryQuery(2, { status: 500 })).toBe(false);
  });

  it("네트워크 오류(lib/api.js가 status를 안 붙인다)도 최대 2번까지 재시도한다", () => {
    expect(shouldRetryQuery(0, { kind: "network" })).toBe(true);
    expect(shouldRetryQuery(1, { kind: "network" })).toBe(true);
    expect(shouldRetryQuery(2, { kind: "network" })).toBe(false);
  });

  it("error 자체가 없어도(방어적) 크래시하지 않고 재시도 쪽으로 떨어진다", () => {
    expect(shouldRetryQuery(0, undefined)).toBe(true);
    expect(shouldRetryQuery(0, null)).toBe(true);
  });
});
