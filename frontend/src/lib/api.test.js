/* 공통 API 클라이언트가 "200인데 본문이 JSON이 아니다"를 실패로 던지는가 (FAIL-01/FAIL-02).
 *
 * 프록시 중간 페이지·SSO 리다이렉트·WAF 차단면은 전부 200+HTML이다. 예전엔 이 응답의
 * `r.json()` 실패를 조용히 삼켜 `body = null`을 정상 반환했다 — 화면은 그걸 "데이터 없음"으로
 * 그렸다(빈 상태와 오류 상태가 같은 화면을 쓰던 시절의 가장 심한 사례). 여기서는 실제 fetch를
 * 흉내 내 응답 자체를 만들고, api()가 반드시 던지는지만 본다 — 화면 쪽 렌더링은 각 화면의
 * 테스트가 이미 `isError` 분기를 검증한다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { api } from "./api.js";

function garbageResponse(status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => { throw new SyntaxError("Unexpected token < in JSON"); },
    headers: { get: (name) => (name === "X-Request-ID" ? "req-garbage-1" : null) },
  };
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: { get: () => null },
  };
}

describe("api() — 200 + 비JSON 본문", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("조용히 null을 반환하지 않고 던진다", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(garbageResponse(200));
    await expect(api("/api/my-tickets")).rejects.toThrow();
  });

  it("던지는 오류가 status/requestId를 실어 ErrorState가 구분할 수 있게 한다", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(garbageResponse(200));
    await expect(api("/api/my-tickets")).rejects.toMatchObject({
      status: 200,
      kind: "invalid_response",
      requestId: "req-garbage-1",
    });
  });

  it("정상 200 + 유효한 JSON은 그대로 통과한다(회귀 없음)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, { items: [1, 2, 3] }));
    await expect(api("/api/my-tickets")).resolves.toEqual({ items: [1, 2, 3] });
  });

  it("200 + JSON `null` 본문(빈 응답이 정상인 엔드포인트)은 던지지 않는다", async () => {
    // r.json()이 리터럴 null을 성공적으로 파싱하는 경우(진짜 빈 JSON 본문)까지 실패로
    // 오분류하면 안 된다 — 이건 파싱 성공이지 파싱 실패가 아니다.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, null));
    await expect(api("/api/some-endpoint")).resolves.toBeNull();
  });

  it("비JSON 500(서버가 봉투를 만들기 전에 죽은 경우)은 기존처럼 상태코드 기반 오류를 던진다", async () => {
    // r.ok가 false인 경로는 이번 수정과 무관해야 한다 — 회귀 확인.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(garbageResponse(500));
    await expect(api("/api/my-tickets")).rejects.toMatchObject({ status: 500 });
  });
});
