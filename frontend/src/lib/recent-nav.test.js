import { describe, it, expect, beforeEach } from "vitest";
import { recordNavVisit, readRecentNav, RECENT_LIMIT } from "./recentNav.js";

/* SRCH-04 — 팔레트 빈 질의가 최근 방문만 보여주려면 이 저장소가 정확해야 한다. */

beforeEach(() => {
  window.localStorage.clear();
});

describe("recentNav", () => {
  it("아무것도 방문한 적 없으면 빈 배열이다", () => {
    expect(readRecentNav()).toEqual([]);
  });

  it("방문한 경로를 최근 순으로 기억한다", () => {
    recordNavVisit("/my-tickets");
    recordNavVisit("/team-docs");
    expect(readRecentNav()).toEqual(["/team-docs", "/my-tickets"]);
  });

  it("같은 경로를 다시 방문하면 중복 없이 맨 앞으로 옮긴다", () => {
    recordNavVisit("/my-tickets");
    recordNavVisit("/team-docs");
    recordNavVisit("/my-tickets");
    expect(readRecentNav()).toEqual(["/my-tickets", "/team-docs"]);
  });

  it(`상한(${RECENT_LIMIT}개)을 넘으면 가장 오래된 것부터 잘린다`, () => {
    for (let i = 0; i < RECENT_LIMIT + 2; i++) recordNavVisit("/route-" + i);
    const list = readRecentNav();
    expect(list).toHaveLength(RECENT_LIMIT);
    expect(list[0]).toBe("/route-" + (RECENT_LIMIT + 1));
    expect(list).not.toContain("/route-0");
  });

  it("빈 경로는 무시한다", () => {
    recordNavVisit("");
    recordNavVisit(null);
    expect(readRecentNav()).toEqual([]);
  });

  it("localStorage에 깨진 JSON이 있어도 죽지 않고 빈 배열로 취급한다", () => {
    window.localStorage.setItem("cv.recentNav.v1", "{not json");
    expect(readRecentNav()).toEqual([]);
    // 그 상태에서도 새 방문 기록은 계속 동작해야 한다(깨진 값 위에 정상적으로 다시 쓴다).
    recordNavVisit("/my-tickets");
    expect(readRecentNav()).toEqual(["/my-tickets"]);
  });
});
