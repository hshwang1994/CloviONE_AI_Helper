import { describe, expect, it } from "vitest";
import { ROUTE_ROLES, routePath, routeReachable } from "./routeAccess.js";

/* 서버가 실어 주는 딥링크를 이 역할이 실제로 열 수 있는가 (r23 #68).
 * 일반 사용자는 언제나 사용자 콘솔이라 관리자 콘솔 경로는 「권한이 없습니다」다. 관리자군은 화면이 부르는 API 의 읽기 역할을 본다. */

describe("routeReachable", () => {
  it("일반 사용자는 사용자 콘솔 경로만 연다", () => {
    expect(routeReachable("/tickets/p-1", "user")).toBe(true);
    expect(routeReachable("/my-approvals?id=a-1", "user")).toBe(true);
    expect(routeReachable("/chat-rooms/r-1", "user")).toBe(true);
    expect(routeReachable("/users?id=u-1", "user")).toBe(false);
    expect(routeReachable("/jobs?job_id=j-1", "user")).toBe(false);
    expect(routeReachable("/ai-connection", "user")).toBe(false);
  });

  it("관리자군은 표에 적힌 읽기 역할을 본다", () => {
    expect(routeReachable("/users?id=u-1", "admin")).toBe(true);
    expect(routeReachable("/users?id=u-1", "auditor")).toBe(false);
    expect(routeReachable("/jobs?job_id=j-1", "auditor")).toBe(true);
    expect(routeReachable("/jobs?job_id=j-1", "operator")).toBe(true);
    expect(routeReachable("/tickets/p-1", "operator")).toBe(true);
    for (const roles of Object.values(ROUTE_ROLES)) expect(roles).not.toContain("user");
  });

  it("역할을 모르거나 바깥 주소 · 빈 값이면 열 수 없다", () => {
    expect(routeReachable("/tickets/p-1", null)).toBe(false);
    expect(routeReachable("//evil.example/x", "admin")).toBe(false);
    expect(routeReachable("https://evil.example/x", "admin")).toBe(false);
    expect(routeReachable(null, "admin")).toBe(false);
    expect(routePath("/users?id=1#x")).toBe("/users");
  });
});
