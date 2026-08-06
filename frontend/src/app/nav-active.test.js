import { describe, it, expect } from "vitest";

import { activeNavPath, bestNavMatch, ROUTE_OWNER, USER_NAV } from "./navConfig.js";

/* 상세 화면에서도 **선택된 메뉴가 남아 있다** (사용자 지적 #14).
 *
 * `bestNavMatch` 는 nav 항목 경로의 접두사만 본다. 그런데 상세는 목록과 **다른 접두사**를
 * 쓴다 — 목록은 `/my-tickets`·`/unassigned`·`/team-tickets` 인데 상세는 `/tickets/:id` 다.
 * 그래서 티켓을 여는 순간 어느 메뉴에도 안 걸려 **선택 표시가 통째로 사라졌다.**
 *
 * 두 단계로 고친다. 순서가 중요하다:
 *   1. 목록에서 들어왔으면 **그 목록**이 켜진다(`location.state.from`) — 사용자가 방금 누른 것
 *   2. 출처를 모르면(새로고침·딥링크·북마크) `ROUTE_OWNER` 의 기본 소속
 *
 * 2번만 두면 미할당에서 연 티켓인데 '내 티켓' 이 켜져 사용자가 자기 위치를 오해한다.
 * 1번만 두면 새로고침 한 번에 다시 사라진다.
 */

const PATHS = USER_NAV.flatMap((g) => g.items || []).map((i) => i.to);

describe("사이드바 선택 유지", () => {
  it("직접 맞는 항목이 있으면 그것이 이긴다", () => {
    expect(activeNavPath("/my-tickets", PATHS)).toBe("/my-tickets");
    // 접두 매칭으로 두 개가 동시에 켜지던 예전 버그도 함께 지킨다.
    expect(activeNavPath("/team-docs/trash", PATHS)).toBe("/team-docs/trash");
  });

  it("티켓 상세는 예전에 아무 메뉴에도 안 걸렸다", () => {
    expect(bestNavMatch("/tickets/abc", PATHS), "이 값이 null 이라 표시가 사라졌다").toBeNull();
    expect(activeNavPath("/tickets/abc", PATHS)).toBe("/my-tickets");
  });

  it("어디서 왔는지가 있으면 그 메뉴가 켜진다", () => {
    expect(activeNavPath("/tickets/abc", PATHS, "/unassigned")).toBe("/unassigned");
    expect(activeNavPath("/tickets/abc", PATHS, "/sprint")).toBe("/sprint");
  });

  it("출처가 실제 메뉴가 아니면 무시한다", () => {
    /* 신뢰하지 않는 값이 그대로 켜지면 없는 메뉴가 활성으로 표시된다. */
    expect(activeNavPath("/tickets/abc", PATHS, "/nope")).toBe("/my-tickets");
  });

  it("검색은 소속이 있고, 자기 메뉴가 있는 화면은 자기 것이 이긴다", () => {
    expect(activeNavPath("/search", PATHS)).toBe("/me");
    // `/profile` 은 **자기 메뉴 항목이 있다** — ROUTE_OWNER 에 넣으면 홈이 켜져 버린다.
    expect(activeNavPath("/profile", PATHS)).toBe("/profile");
  });

  it("ROUTE_OWNER 의 목적지는 실제로 존재하는 메뉴다", () => {
    /* 오타 하나면 그 화면에서 영원히 표시가 안 켜지는데, 증상이 조용해서 안 보인다. */
    for (const [from, to] of Object.entries(ROUTE_OWNER)) {
      expect(PATHS, `${from} → ${to} 의 목적지가 메뉴에 없다`).toContain(to);
    }
  });
});
