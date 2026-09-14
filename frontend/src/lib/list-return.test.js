import { describe, it, expect, beforeEach } from "vitest";

/* 목록 → 상세 → 뒤로 에서 목록이 있던 그대로 돌아온다 (지시 19).
 *
 * 이 파일이 지키는 것은 셋이다:
 *   1) 「목록」은 경로가 아니라 **주소**로 돌아간다 — 조건·정렬·페이지가 질의 문자열에 있다.
 *   2) 조건을 바꾸면 스크롤 기억은 버린다 — 다른 목록의 위치다.
 *   3) 기억이 없으면 조용히 예전처럼 동작한다(`fallback`).
 */

import { listReturnUrl, rememberList, rememberScroll, stripQueryKeys } from "./listReturn.js";

beforeEach(() => {
  window.sessionStorage.clear();
});

describe("돌아갈 주소", () => {
  it("질의 문자열까지 기억한다 — 조건·정렬·페이지가 거기 있다", () => {
    rememberList("/my-tickets", "/my-tickets?status=%EC%A7%84%ED%96%89&page=3");
    expect(listReturnUrl("/my-tickets", "/my-tickets")).toBe(
      "/my-tickets?status=%EC%A7%84%ED%96%89&page=3",
    );
  });

  it("🔴 기억이 없으면 fallback 이다 — 딥링크로 바로 들어온 경우", () => {
    expect(listReturnUrl("/team-tickets", "/my-tickets")).toBe("/my-tickets");
  });

  it("목록마다 따로 기억한다 — 팀 티켓에서 들어온 사람이 내 티켓으로 안 떨어진다", () => {
    rememberList("/my-tickets", "/my-tickets?page=2");
    rememberList("/team-tickets", "/team-tickets?q=%EB%B0%B0%ED%8F%AC");
    expect(listReturnUrl("/team-tickets", "/my-tickets")).toBe("/team-tickets?q=%EB%B0%B0%ED%8F%AC");
  });
});

describe("스크롤", () => {
  it("같은 주소로 다시 적으면 스크롤 기억이 남는다", () => {
    rememberList("/board", "/board?page=1");
    rememberScroll("/board", 1240);
    rememberList("/board", "/board?page=1");
    const raw = JSON.parse(window.sessionStorage.getItem("cv.listReturn.v1"));
    expect(raw["/board"].scrollY).toBe(1240);
  });

  it("🔴 조건이 바뀌면 스크롤 기억을 버린다 — 다른 목록의 위치다", () => {
    rememberList("/board", "/board?page=1");
    rememberScroll("/board", 1240);
    rememberList("/board", "/board?page=2");
    const raw = JSON.parse(window.sessionStorage.getItem("cv.listReturn.v1"));
    expect(raw["/board"].scrollY).toBe(0);
  });

  it("기억한 적 없는 목록의 스크롤은 안 적는다", () => {
    rememberScroll("/knowledge", 500);
    expect(window.sessionStorage.getItem("cv.listReturn.v1")).toBeNull();
  });
});

describe("기억에서 빼는 키 (D-483)", () => {
  it("🔴 미리보기 키를 걷어 낸 주소를 기억한다 — 돌아왔을 때 미리보기가 다시 열리면 안 된다", () => {
    expect(stripQueryKeys("?team=a&sprint=s&peek=pg-1", ["peek"])).toBe("?team=a&sprint=s");
    // 걷어 낼 키뿐이면 빈 주소다 — `?` 만 남기지 않는다.
    expect(stripQueryKeys("?peek=pg-1", ["peek"])).toBe("");
    expect(stripQueryKeys("", ["peek"])).toBe("");
  });

  it("뺄 키가 없으면 주소를 그대로 둔다", () => {
    expect(stripQueryKeys("?team=a&peek=x", null)).toBe("?team=a&peek=x");
    expect(stripQueryKeys("?team=a&peek=x", [])).toBe("?team=a&peek=x");
  });
});

describe("무한히 쌓이지 않는다", () => {
  it("🔴 최근 여덟 개만 남고, 버리는 것은 **가장 오래된 쪽**이다", () => {
    /* 이 단언이 실제 결함을 잡았다. 순서를 `Date.now()` 로 매기면 같은 밀리초에 적힌
       항목이 전부 동점이 되고, 그때 정렬은 원래 순서(가장 오래된 것부터)를 그대로 둔다 —
       뒤를 잘라내면 **방금 본 목록**의 기억이 지워진다. 오류는 안 난다. */
    for (let i = 0; i < 12; i++) rememberList(`/list-${i}`, `/list-${i}?page=1`);
    const raw = JSON.parse(window.sessionStorage.getItem("cv.listReturn.v1"));
    expect(Object.keys(raw).length).toBe(8);
    expect(raw["/list-11"]).toBeTruthy();
    expect(raw["/list-0"]).toBeUndefined();
  });
});
