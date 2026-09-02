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

describe("api() — 422 검증 실패의 details (UX-40)", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("error.details가 있으면 그 사유가 message에 실제로 실린다 — 예전엔 130여 호출부가 영어 상수만 봤다", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(422, {
      error: {
        code: "validation_error",
        message: "Invalid request data",
        details: [
          { loc: ["body", "timezone"], msg: "Input should be a valid string" },
          { loc: ["body", "timeout_seconds"], msg: "Input should be a valid integer" },
        ],
      },
    }));
    await expect(api("/api/admin/schedules", { method: "POST", body: {} })).rejects.toMatchObject({
      message: "Invalid request data Input should be a valid string Input should be a valid integer",
    });
  });

  it("details가 객체 배열이어도 [object Object]가 새지 않는다", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(422, {
      error: { code: "validation_error", message: "Invalid request data", details: [{ weird: "shape" }] },
    }));
    const err = await api("/api/x", { method: "POST", body: {} }).catch((e) => e);
    expect(err.message).not.toContain("[object Object]");
  });

  it("details가 없으면 봉투 문구 그대로다(동작 변화 없음)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(409, {
      error: { code: "conflict", message: "이미 존재합니다." },
    }));
    await expect(api("/api/x", { method: "POST", body: {} })).rejects.toMatchObject({
      message: "이미 존재합니다.",
    });
  });
});

describe("api() — PATCH 본문 직렬화", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("body가 객체이면 JSON으로 직렬화하고 Content-Type을 붙인다", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, { ok: true }));
    await api("/api/tickets/t-1", { method: "PATCH", body: { status: "진행" } });
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.headers["Content-Type"]).toBe("application/json");
    expect(opts.body).toBe(JSON.stringify({ status: "진행" }));
  });

  it("body를 미리 stringify 하면 Content-Type이 빠진다 — 서버가 본문을 못 읽는다", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, { ok: true }));
    await api("/api/tickets/t-1", { method: "PATCH", body: JSON.stringify({ status: "진행" }) });
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.headers["Content-Type"]).toBeUndefined();
  });
});

/* PA-RC-0002 — docs/UX_WRITING.md "회복 절을 고르는 법". 서버가 봉투 문구를 안 준
 * 대비책(fallbackMessage)과 네트워크 자체 실패는 각각 이 파일 한 곳에서만 만들어진다 —
 * 여기서 막다른 길이면 그 문구를 보는 화면 전부가 막다른 길이다(공용 진입점).
 * "다시 시도"·"확인"처럼 사용자가 지금 할 수 있는 행동이 문구 안에 있는지만 본다 —
 * 정확한 단어를 강제하면 docs/UX_WRITING.md를 고칠 때마다 이 테스트도 갈아엎어야 한다. */
describe("api() — 오류 문구에 회복 절이 있다 (PA-RC-0002)", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("🔴 서버가 문구를 안 준 알 수 없는 상태 코드도 막다른 길이 아니다", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(451, {}));
    const err = await api("/api/x").catch((e) => e);
    expect(err.message).toMatch(/다시 시도|확인/);
  });

  it("🔴 네트워크 자체가 끊겨도 막다른 길이 아니다", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = await api("/api/x").catch((e) => e);
    expect(err.kind).toBe("network");
    expect(err.message).toMatch(/다시 시도|확인/);
  });

  it("알려진 상태 코드(429)는 이미 회복 절이 있다(회귀 확인)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(429, {}));
    const err = await api("/api/x").catch((e) => e);
    expect(err.message).toMatch(/다시 시도/);
  });
});

/* 429 의 본문은 「언제 다시 되는가」다 — api()가 그 값을 오류 객체(retryAfterSeconds)로
 * 실어야 ErrorState 가 재시도 버튼을 잠글 수 있다. 출처는 셋: 앱 리미터의 봉투,
 * Retry-After 헤더(봉투가 없을 때), 아무것도 없는 프록시 429(null). */
describe("api() — 429 retryAfterSeconds", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("봉투의 retry_after_seconds 를 싣는다", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(429, { error: { code: "rate_limited", message: "요청이 너무 많습니다.", retry_after_seconds: 6.2 } })
    );
    const err = await api("/api/x").catch((e) => e);
    expect(err.retryAfterSeconds).toBe(6.2);
  });

  it("봉투가 없으면 Retry-After 헤더를 읽는다", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({}),
      headers: { get: (name) => (name === "Retry-After" ? "12" : null) },
    });
    const err = await api("/api/x").catch((e) => e);
    expect(err.retryAfterSeconds).toBe(12);
  });

  it("프록시 층의 429(HTML 본문·헤더 없음)는 null 이다", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(garbageResponse(429));
    const err = await api("/api/x").catch((e) => e);
    expect(err.status).toBe(429);
    expect(err.retryAfterSeconds).toBeNull();
  });
});
