import { describe, expect, it } from "vitest";

import {
  DISABLED_CODES, LIST_STATES, LIST_STATE_COPY, canRetry, errorCode, isFailureState, resolveListState,
} from "./listState.js";

/* 목록 상태 일곱 갈래 (F4 · D-530). 예전에는 조건이 하나라도 걸리면 0건이 「검색 결과가 없습니다」였고 실패는 거의 다 같은 오류
 * 판이었다 — 권한이 없는 사람, 꺼진 기능, 닿지 못한 서버, 정말 비어 있는 새 설치가 같은 얼굴이었다. 판정 순서표를 그대로 단언한다. */

const err = (props) => Object.assign(new Error("x"), props);

describe("판정 순서표", () => {
  const cases = [
    ["첫 요청 진행 중", { loading: true }, "loading"],
    ["401", { error: err({ status: 401 }) }, "forbidden"],
    ["403 — 조건이 있어도 권한이 먼저다", { error: err({ status: 403 }), hasCondition: true }, "forbidden"],
    ["기능 꺼짐 사유 코드", { error: err({ status: 409, body: { error: { code: "ai_unavailable" } } }) }, "disabled"],
    ["기능 깃발 문은 404 로 와도 꺼짐이다", { error: err({ status: 404, body: { error: { code: "feature_disabled" } } }) }, "disabled"],
    ["네트워크 오류", { error: err({ kind: "network" }) }, "unreachable"],
    ["502", { error: err({ status: 502 }) }, "unreachable"],
    ["503", { error: err({ status: 503 }) }, "unreachable"],
    ["504", { error: err({ status: 504 }) }, "unreachable"],
    ["500", { error: err({ status: 500 }) }, "error"],
    ["해석 못 한 응답", { error: err({ kind: "invalid_response", status: 200 }) }, "error"],
    ["조건 있음 · 0건", { hasCondition: true, count: 0 }, "filtered-empty"],
    ["조건 없음 · 0건", { count: 0 }, "empty"],
    ["행 있음", { count: 3 }, "ready"],
    ["행 있음 · 조건 있음", { count: 3, hasCondition: true }, "ready"],
  ];
  it.each(cases)("%s → %s", (_label, input, want) => {
    expect(resolveListState(input)).toBe(want);
  });

  it("받아 둔 행이 있는 다시 받기는 불러오는 중이 아니다 — 호출부는 첫 요청일 때만 loading 을 넘긴다", () => {
    expect(resolveListState({ loading: false, count: 5 })).toBe("ready");
  });

  it("오류가 있으면 불러오는 중보다 오류가 먼저다", () => {
    expect(resolveListState({ loading: true, error: err({ status: 500 }) })).toBe("error");
  });
});

describe("갈래마다 다른 말 · 다른 동작", () => {
  it("기능 꺼짐 · 연결 장애 · 서버 오류 · 권한 없음 · 조건 0건 · 자료 없음은 서로 다른 제목이다", () => {
    const titles = ["disabled", "unreachable", "error", "forbidden", "filtered-empty", "empty"].map((s) => LIST_STATE_COPY[s].title);
    expect(new Set(titles).size).toBe(titles.length);
    for (const t of titles) expect(t).toMatch(/다\.$/);
    for (const s of ["forbidden", "disabled", "unreachable", "error"]) expect(LIST_STATE_COPY[s].help).toMatch(/요\.$|다\.$/);
  });

  it("다시 시도는 연결 장애와 서버 오류에서만 뜻이 있다", () => {
    expect(LIST_STATES.filter(canRetry)).toEqual(["unreachable", "error"]);
  });

  it("오류 판으로 그리는 갈래는 넷이다 — 불러오는 중 · 조건 0건 · 자료 없음 · 행은 오류가 아니다", () => {
    expect(LIST_STATES.filter(isFailureState)).toEqual(["forbidden", "disabled", "unreachable", "error"]);
  });

  it("사유 코드는 오류 봉투에서 읽는다", () => {
    expect(errorCode(err({ body: { error: { code: "feature_disabled" } } }))).toBe("feature_disabled");
    expect(errorCode(err({}))).toBeNull();
    expect(DISABLED_CODES).toContain("ai_unavailable");
  });
});
