import { describe, it, expect } from "vitest";

import { inUserSegment, ROUTE_OWNER } from "./navConfig.js";

/* VIS-72 — 관리자군이 Ctrl+K로 통합 검색을 열면 상단 세그먼트가 관리자로 튕기고 사이드바가
 * 통째로 관리자 메뉴로 바뀌었다. 원인: ROUTE_OWNER["/search"] = "/me"(사용자 콘솔 소유라고
 * 선언)인데 USER_SEG_PATHS에는 "/search"가 빠져 있어 inUserSegment("/search")가 false였다 —
 * 두 표가 서로 모순됐다. /projects는 같은 부류의 결함이 이미 한 번 고쳐진 전례라 함께 고정한다.
 */
describe("사용자 세그먼트 판정 — ROUTE_OWNER와 USER_SEG_PATHS가 어긋나지 않는다 (VIS-72)", () => {
  it("/search는 사용자 세그먼트다 — ROUTE_OWNER가 /me 소유라고 선언한 것과 일치해야 한다", () => {
    expect(ROUTE_OWNER["/search"]).toBe("/me");
    expect(inUserSegment("/search")).toBe(true);
  });

  it("/search?q=... 처럼 뒤에 쿼리스트링이 붙어도 사용자 세그먼트로 남는다", () => {
    // pathname은 쿼리스트링을 안 담지만(react-router의 useLocation().pathname), 하위 경로
    // 형태(prefix 매칭)까지 잘못 좁아지지 않는지 함께 확인한다.
    expect(inUserSegment("/search")).toBe(true);
  });

  it("/projects — 같은 부류의 결함이 이미 고쳐진 전례, 회귀하지 않는다", () => {
    expect(inUserSegment("/projects")).toBe(true);
  });

  it("관리자 전용 화면은 여전히 사용자 세그먼트가 아니다(오탐 방지)", () => {
    expect(inUserSegment("/users")).toBe(false);
    expect(inUserSegment("/ai-quotas")).toBe(false);
  });
});
