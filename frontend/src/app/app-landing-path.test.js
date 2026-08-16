import { describe, it, expect } from "vitest";
import { initialLandingPath } from "./App.jsx";

/* PA-RC-0018 acceptance criteria 11 — 관리자 로그인 착지가 /dashboard다.
 *
 * login.js는 next가 없으면 항상 물리 경로 "/"로 보낸다(next는 세션 만료 bounce-back에서만
 * 채워진다) — 이전엔 여기서 물리 경로만 봐서 "/"로 들어오는 모든 역할이 /me에 떨어졌다.
 * 관리자도 예외가 아니었다. 이제는 역할로 정한다. */
describe("initialLandingPath — 최초 진입 기본 화면", () => {
  it("일반 사용자(role=user)는 물리 경로가 무엇이든 /me로 간다", () => {
    expect(initialLandingPath("/", "user")).toBe("/me");
    expect(initialLandingPath("/login", "user")).toBe("/me");
  });

  it("관리 콘솔 역할(operator/auditor/admin/system_admin)은 물리 경로 '/'(로그인 직후)에서도 /dashboard로 간다", () => {
    for (const role of ["operator", "auditor", "admin", "system_admin"]) {
      expect(initialLandingPath("/", role)).toBe("/dashboard");
    }
  });

  it("/admin 경로로 직접 들어오면 역할과 무관하게 /dashboard로 간다(서버가 이미 게이팅한다)", () => {
    expect(initialLandingPath("/admin", "user")).toBe("/dashboard");
    expect(initialLandingPath("/admin", "admin")).toBe("/dashboard");
  });

  it("역할을 아직 모르면(인증 오류 등) /me로 간다 — 이전 기본값과 같다", () => {
    expect(initialLandingPath("/", null)).toBe("/me");
    expect(initialLandingPath("/", undefined)).toBe("/me");
  });
});
