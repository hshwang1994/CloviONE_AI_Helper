/* 스코프 바 — 지금 보는 범위를 화면이 말한다 (S4 / A8).
 *
 * 범위를 실제로 걸기 시작하면 목록이 좁아지는데, **왜 좁아졌는지 화면이 말하지 않으면**
 * 사용자는 "왜 이것만 보이지" 를 알 수 없고 그건 결함으로 신고된다.
 */
import { describe, it, expect } from "vitest";
import { scopeSummary } from "./ScopeBar.jsx";

describe("범위 요약", () => {
  it("일반 사용자는 자기 팀을 이름으로 말한다", () => {
    expect(scopeSummary({ role: "user", department: "ClovirONE팀" }))
      .toEqual({ label: "내 팀", detail: "ClovirONE팀" });
  });

  it("부서가 없는 일반 사용자에게는 **띄우지 않는다** — 실제로 안 좁혀지기 때문이다", () => {
    // `build_scope` 의 폴백과 같은 규칙. 안 좁혀졌는데 좁혔다고 하면 거짓말이다.
    expect(scopeSummary({ role: "user", department: null })).toBeNull();
  });

  it("전체 범위 관리자에게도 띄우지 않는다 — 모든 화면 위의 '전체 포털'은 소음이다", () => {
    expect(scopeSummary({ role: "admin", admin_scope: "global" })).toBeNull();
    expect(scopeSummary({ role: "system_admin" })).toBeNull();
  });

  it("부서 관리자는 어느 부서인지 말한다", () => {
    expect(scopeSummary({ role: "admin", admin_scope: "dept", department: "브로드컴사업본부" }))
      .toEqual({ label: "관리 범위", detail: "브로드컴사업본부" });
  });

  it("대상 부서가 없으면 그 사실을 말한다 — 그 계정은 아무것도 못 본다", () => {
    expect(scopeSummary({ role: "admin", admin_scope: "dept", department: null }).detail)
      .toBe("지정된 부서 없음");
  });

  it("조직 관리자", () => {
    expect(scopeSummary({ role: "admin", admin_scope: "org" }))
      .toEqual({ label: "관리 범위", detail: "내 조직" });
  });
});
