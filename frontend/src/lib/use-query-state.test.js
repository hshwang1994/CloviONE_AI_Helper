/* 화면 상태를 URL 에 두는 훅 (사용자 지적 #3).
 *
 * 사용자가 말한 증상은 하나였다: "티켓 상세로 갔다 오면 필터가 풀린다"(문서 화면도 같다).
 * 원인은 필터가 `React.useState` 에만 있었다는 것이다 — 화면이 언마운트되면 같이 사라진다.
 *
 * 그래서 이 훅이 지켜야 하는 것은 네 가지고, 아래 검사가 그 넷을 하나씩 못박는다.
 *   1) 고른 값이 **주소에 실린다**(그래야 뒤로가기·새로고침·링크 공유가 한 번에 풀린다)
 *   2) 주소에 실린 값으로 **처음부터** 시작한다(마운트 뒤 setState 로 넣으면 한 번 더 조회한다)
 *   3) 기본값은 주소에 **안 쓴다**(안 그러면 아무것도 안 고른 화면의 주소가 지저분해지고,
 *      "이게 필터가 걸린 상태인가" 를 주소만 봐서는 알 수 없다)
 *   4) 필터를 바꾸면 페이지가 처음으로 돌아간다(다른 필터의 3페이지에 머무르지 않게)
 *
 * 오탐 방지: 스펙에 없는 키(딥링크가 실어 준 `?id=`)를 건드리지 않는 것까지 함께 본다 —
 * 훅이 쿼리스트링을 통째로 갈아 끼우면 그 딥링크가 조용히 사라진다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { useQueryState, decodeQuery, encodeQuery } from "./useQueryState.js";

const SPEC = { q: "", status: "", favorites: false, page: 1 };
const OPTIONS = { reset: ["page"] };

function useProbe() {
  const [state, setState] = useQueryState(SPEC, OPTIONS);
  const loc = useLocation();
  return { state, setState, search: loc.search };
}

function renderProbe(entry = "/list") {
  return renderHook(useProbe, {
    wrapper: ({ children }) =>
      React.createElement(MemoryRouter, { initialEntries: [entry] }, children),
  });
}

describe("useQueryState — 주소가 화면 상태를 든다", () => {
  it("아무것도 안 고르면 주소에 쿼리를 쓰지 않는다", () => {
    const { result } = renderProbe();
    expect(result.current.state).toEqual({ q: "", status: "", favorites: false, page: 1 });
    expect(result.current.search).toBe("");
  });

  it("값을 고르면 주소에 실린다", () => {
    const { result } = renderProbe();
    act(() => result.current.setState({ status: "진행" }));
    expect(new URLSearchParams(result.current.search).get("status")).toBe("진행");
    expect(result.current.state.status).toBe("진행");
  });

  it("주소에 실린 값으로 시작한다 (새로고침, 링크 공유)", () => {
    const { result } = renderProbe("/list?status=검증&page=3&favorites=1&q=배포");
    expect(result.current.state).toEqual({
      q: "배포", status: "검증", favorites: true, page: 3,
    });
  });

  it("기본값으로 되돌리면 그 키를 주소에서 뺀다", () => {
    const { result } = renderProbe("/list?status=검증");
    act(() => result.current.setState({ status: "" }));
    expect(result.current.search).toBe("");
  });

  it("필터를 바꾸면 페이지가 1로 돌아간다", () => {
    const { result } = renderProbe("/list?page=4");
    act(() => result.current.setState({ status: "진행" }));
    expect(result.current.state.page).toBe(1);
    expect(new URLSearchParams(result.current.search).has("page")).toBe(false);
  });

  it("페이지만 바꿀 때는 필터를 그대로 둔다", () => {
    const { result } = renderProbe("/list?status=진행");
    act(() => result.current.setState({ page: 2 }));
    expect(result.current.state).toMatchObject({ status: "진행", page: 2 });
  });

  it("스펙에 없는 키는 건드리지 않는다 (딥링크 파라미터 보존)", () => {
    const { result } = renderProbe("/list?id=abc-1");
    act(() => result.current.setState({ status: "진행" }));
    const p = new URLSearchParams(result.current.search);
    expect(p.get("id")).toBe("abc-1");
    expect(p.get("status")).toBe("진행");
  });

  it("주소에 이상한 값이 실려 있으면 기본값으로 떨어진다", () => {
    const { result } = renderProbe("/list?page=0&favorites=nope");
    expect(result.current.state.page).toBe(1);
    expect(result.current.state.favorites).toBe(false);
  });

  // react-router 의 setSearchParams 갱신 함수는 "이 렌더에서 캡처된" 옛 검색어를 기준으로
  // 다음 값을 계산한다(react-router-dom useSearchParams 구현: nextInit(new
  // URLSearchParams(searchParams)), searchParams 는 useCallback 의존성으로 그 렌더에 고정됨).
  // 그래서 리렌더 없이 setState 를 두 번 연달아 부르면(같은 핸들러 안에서 필터 두 개를
  // 바꾸는 식) 두 번째 호출이 첫 번째 호출의 patch 를 못 보고 옛 주소 위에 다시 얹는다 —
  // 먼저 바꾼 값이 조용히 사라진다. 두 patch 는 합쳐져야 한다.
  it("같은 틱에서 setState 를 두 번 부르면 두 patch 가 모두 반영된다", () => {
    const { result } = renderProbe();
    act(() => {
      result.current.setState({ q: "hello" });
      result.current.setState({ status: "진행" });
    });
    expect(result.current.state).toMatchObject({ q: "hello", status: "진행" });
    const p = new URLSearchParams(result.current.search);
    expect(p.get("q")).toBe("hello");
    expect(p.get("status")).toBe("진행");
  });
});

describe("decodeQuery / encodeQuery", () => {
  it("타입은 기본값이 정한다", () => {
    const got = decodeQuery(new URLSearchParams("page=7&favorites=1&q=가"), SPEC);
    expect(got).toEqual({ q: "가", status: "", favorites: true, page: 7 });
  });

  it("기본값과 같은 값은 쿼리에 넣지 않는다", () => {
    const out = encodeQuery({ q: "", status: "", favorites: false, page: 1 }, SPEC);
    expect(out.toString()).toBe("");
  });

  it("기본이 참인 불리언은 꺼졌을 때만 실린다", () => {
    const spec = { active: true };
    expect(encodeQuery({ active: true }, spec).toString()).toBe("");
    expect(encodeQuery({ active: false }, spec).get("active")).toBe("0");
    expect(decodeQuery(new URLSearchParams("active=0"), spec).active).toBe(false);
  });

  it("배열 기본값은 반복 파라미터로 읽고 쓴다", () => {
    const spec = { status: [] };
    expect(decodeQuery(new URLSearchParams("status=계획&status=진행"), spec).status).toEqual(["계획", "진행"]);
    const out = encodeQuery({ status: ["계획", "진행"] }, spec);
    expect(out.getAll("status")).toEqual(["계획", "진행"]);
    expect(encodeQuery({ status: [] }, spec).toString()).toBe("");
  });

  it("배열 스펙에 문자열 하나를 넣어도 반복 파라미터로 실린다", () => {
    const spec = { status: [] };
    const out = encodeQuery({ status: "진행" }, spec);
    expect(out.getAll("status")).toEqual(["진행"]);
  });
});
