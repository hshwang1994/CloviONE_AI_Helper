import { describe, it, expect } from "vitest";
import { initialLandingPath, hasDestination } from "./App.jsx";

/* **사람은 누구나 먼저 사용자다** (0060 §3).
 *
 * PA-RC-0018 은 "관리자 로그인 착지가 /dashboard" 를 요구했고 그때는 그것이 맞았다 —
 * 로그인이 항상 물리 경로 "/"로 보내는 탓에 관리자도 개인 홈에 떨어졌고, 관리 콘솔로
 * 가려면 매번 한 번 더 눌러야 했기 때문이다.
 *
 * 0060 에서 그 판단을 뒤집는다. 관리자도 자기 티켓과 자기 승인이 있는 **한 사람**이고,
 * 관리 기능은 필요할 때 상단 전환으로 들어가는 별도 평면(Control Plane)이다. 로그인할
 * 때마다 운영 지표부터 보고 자기 업무는 찾아 들어가야 하는 것은 순서가 뒤집힌 것이다.
 *
 * `/admin` 물리 경로만 예외로 남는다 — 그 주소 자체가 관리 콘솔 진입 의도다.
 */
describe("initialLandingPath — 최초 진입 기본 화면", () => {
  it("일반 사용자(role=user)는 물리 경로가 무엇이든 /me로 간다", () => {
    expect(initialLandingPath("/", "user")).toBe("/me");
    expect(initialLandingPath("/login", "user")).toBe("/me");
  });

  it("관리 콘솔 역할도 로그인 직후에는 /me로 간다 — 사람은 누구나 먼저 사용자다", () => {
    for (const role of ["operator", "auditor", "admin", "system_admin"]) {
      expect(initialLandingPath("/", role)).toBe("/me");
    }
  });

  it("/admin 경로로 직접 들어오면 역할과 무관하게 /dashboard로 간다(서버가 이미 게이팅한다)", () => {
    expect(initialLandingPath("/admin", "user")).toBe("/dashboard");
    expect(initialLandingPath("/admin", "admin")).toBe("/dashboard");
  });

  it("역할을 아직 모르면(인증 오류 등) /me로 간다", () => {
    expect(initialLandingPath("/", null)).toBe("/me");
    expect(initialLandingPath("/", undefined)).toBe("/me");
  });
});

/* 🔴 `#/` 는 갈 곳이 아니다.
 *
 * 이 앱에는 `href="#/"` 로 보내는 자리가 셋 있다(`kit.jsx` 의 ErrorState 「홈으로」,
 * 관리 콘솔과 설정 화면의 권한 벽 「대시보드로 이동」). 그런데 **두 라우트 표 어디에도
 * `path="/"` 가 없어서** 그 단추를 누르면 「찾을 수 없습니다」로 갔다 — 막다른 길에서
 * 막다른 길로 보냈다. 예전 조건은 `!h` 였고 `"#/"` 는 `"/"` 가 되어 그냥 통과했다.
 */
describe("hasDestination — 이 해시가 갈 곳을 말하고 있나", () => {
  it("🔴 빈 해시와 `#/` 는 둘 다 갈 곳이 아니다", () => {
    expect(hasDestination("")).toBe(false);
    expect(hasDestination("#")).toBe(false);
    expect(hasDestination("#/")).toBe(false);
    expect(hasDestination(null)).toBe(false);
    expect(hasDestination(undefined)).toBe(false);
  });

  it("반례 — 진짜 목적지는 그대로 둔다(전부 착지로 덮으면 딥링크가 죽는다)", () => {
    expect(hasDestination("#/me")).toBe(true);
    expect(hasDestination("#/tickets/T-123")).toBe(true);
    expect(hasDestination("#/team-docs/trash?kind=document")).toBe(true);
    // 앞자리가 `/` 인 것만으로 갈 곳이 없다고 보지 않는다.
    expect(hasDestination("#//")).toBe(true);
  });
});
