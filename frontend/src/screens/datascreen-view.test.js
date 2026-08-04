import { describe, it, expect } from "vitest";
import {
  buildViewQuery, describeView, hashPath, hashQuery, parseView, withHashQuery,
} from "./datascreen-view.js";

/* 목록 화면의 뷰 ↔ URL 변환. 저장된 뷰와 링크 공유가 전부 이 함수들 위에 서 있으므로
 * 값으로 고정한다(서버·DOM 없이 도는 순수 함수).
 *
 * 특히 두 가지를 못박는다:
 *   1) **왕복이 안정적이다.** parse → build 를 거쳐도 같은 문자열이 나온다. 안 그러면
 *      화면을 열기만 해도 주소가 계속 달라져 '같은 뷰'인지 비교할 수 없다.
 *   2) **모르는 키는 다루지 않는다.** ?id= 같은 딥링크 파라미터는 DataScreen 의 onQuery 가
 *      소비하는 별개 규약이다 — 여기서 읽거나 쓰면 두 규약이 서로를 지운다.
 */

const CONFIG = {
  key: "audit",
  filters: [
    { key: "action", label: "작업" },
    { key: "status", label: "결과", options: [{ value: "failed", label: "실패" }] },
    { key: "since", label: "시작", type: "datetime-local" },
  ],
};

describe("parseView", () => {
  it("아는 키만 읽는다", () => {
    const view = parseView("q=hello&status=failed&id=abc&nope=1", CONFIG);
    expect(view.q).toBe("hello");
    expect(view.filters).toEqual({ status: "failed" });
    expect(view.filters.id).toBeUndefined();
  });

  it("빈 값은 버린다 — 빈 필터가 '전체'와 다른 것처럼 보이면 안 된다", () => {
    expect(parseView("status=&q=", CONFIG).filters).toEqual({});
    expect(parseView("status=&q=", CONFIG).q).toBe("");
  });

  it("page 는 1 이상 정수만 인정한다", () => {
    expect(parseView("page=3", CONFIG).page).toBe(3);
    expect(parseView("page=0", CONFIG).page).toBe(1);
    expect(parseView("page=abc", CONFIG).page).toBe(1);
    expect(parseView("", CONFIG).page).toBe(1);
  });

  it("퍼센트 인코딩된 한글을 원래대로 돌려준다", () => {
    expect(parseView("q=%EC%8B%A4%ED%8C%A8", CONFIG).q).toBe("실패");
  });

  it("filters 정의가 없는 화면에서도 죽지 않는다", () => {
    expect(parseView("q=x&status=failed", { key: "x" })).toEqual({ q: "x", page: 1, filters: {} });
  });
});

describe("buildViewQuery", () => {
  it("기본값은 싣지 않는다 — 아무것도 안 건드린 화면의 주소는 깨끗해야 한다", () => {
    expect(buildViewQuery({ q: "", page: 1, filters: {} }, CONFIG)).toBe("");
  });

  it("키 순서는 config.filters 순서를 따른다(같은 뷰 = 같은 문자열)", () => {
    const a = buildViewQuery({ q: "x", page: 2, filters: { since: "2026-08-01T00:00", action: "user.login" } }, CONFIG);
    const b = buildViewQuery({ q: "x", page: 2, filters: { action: "user.login", since: "2026-08-01T00:00" } }, CONFIG);
    expect(a).toBe(b);
    expect(a.indexOf("action=")).toBeLessThan(a.indexOf("since="));
  });

  it("parse → build 왕복이 안정적이다", () => {
    const query = "q=%EC%8B%A4%ED%8C%A8&action=user.login&status=failed&page=4";
    expect(buildViewQuery(parseView(query, CONFIG), CONFIG)).toBe(query);
  });

  it("모르는 필터는 다시 쓰지 않는다", () => {
    const view = parseView("id=abc&status=failed", CONFIG);
    expect(buildViewQuery(view, CONFIG)).toBe("status=failed");
  });
});

describe("해시 경로/쿼리", () => {
  it("경로와 쿼리를 가른다", () => {
    expect(hashPath("#/audit?status=failed")).toBe("#/audit");
    expect(hashQuery("#/audit?status=failed")).toBe("status=failed");
    expect(hashQuery("#/audit")).toBe("");
  });

  it("경로는 그대로 두고 쿼리만 바꾼다", () => {
    expect(withHashQuery("#/audit?old=1", "status=failed")).toBe("#/audit?status=failed");
    expect(withHashQuery("#/audit?old=1", "")).toBe("#/audit");
    // 해시가 아예 없어도 유효한 값을 낸다(빈 문자열을 그대로 두면 주소가 사라진다).
    expect(withHashQuery("", "")).toBe("#");
  });
});

describe("describeView", () => {
  it("select 필터는 화면에서 고른 표시 문구로 읽어 준다", () => {
    expect(describeView("status=failed", CONFIG)).toBe("결과: 실패");
  });

  it("검색어·필터·페이지를 한 줄로 잇는다", () => {
    expect(describeView("q=x&action=user.login&page=2", CONFIG))
      .toBe('검색 "x", 작업: user.login, 2쪽');
  });

  it("조건이 없으면 빈 문자열 — 화면이 '조건 없음(전체)'로 바꿔 쓴다", () => {
    expect(describeView("", CONFIG)).toBe("");
  });
});
