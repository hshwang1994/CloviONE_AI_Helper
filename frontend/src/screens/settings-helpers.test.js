import { describe, it, expect } from "vitest";
import { fmtDuration, summarizeSetting } from "./Settings.jsx";
import { securityDowngradeWarning } from "./settings/settingsRegistry.js";

describe("fmtDuration", () => {
  it("returns empty string for null", () => {
    expect(fmtDuration(null)).toBe("");
  });
  it("formats exact hours and minutes", () => {
    expect(fmtDuration(3600)).toBe("1시간");
    expect(fmtDuration(28800)).toBe("8시간");
    expect(fmtDuration(1800)).toBe("30분");
  });
  it("formats sub-minute values as seconds", () => {
    expect(fmtDuration(45)).toBe("45초");
  });
  it("formats compound minute/second values without distortion", () => {
    expect(fmtDuration(90)).toBe("1분 30초");
    expect(fmtDuration(1830)).toBe("30분 30초");
  });
  it("prefers a whole-minute form when divisible by 60", () => {
    expect(fmtDuration(3660)).toBe("61분");
  });
});

describe("summarizeSetting", () => {
  it("suffixes retention-day integers with 일", () => {
    expect(summarizeSetting("conversation_retention_days", 90)).toBe("90일");
    expect(summarizeSetting("notification_retention_days", 30)).toBe("30일");
  });
  it("summarizes password_policy", () => {
    expect(summarizeSetting("password_policy", { min_length: 12, min_classes: 3 })).toBe("최소 12자 / 3종류 이상");
  });
  it("summarizes session_policy with durations", () => {
    expect(summarizeSetting("session_policy", { idle_timeout_seconds: 1800, absolute_timeout_seconds: 28800 })).toBe("유휴 30분, 최대 8시간");
  });
  it("summarizes allowed_email_domains (list and empty)", () => {
    expect(summarizeSetting("allowed_email_domains", ["goodmit.co.kr"])).toBe("도메인: goodmit.co.kr");
    expect(summarizeSetting("allowed_email_domains", [])).toBe("제한 없음(모든 도메인 허용)");
  });
  it("summarizes ui_branding", () => {
    expect(summarizeSetting("ui_branding", { product_name: "ClovirONE", support_email: "help@goodmit.co.kr" })).toBe("제품명: ClovirONE, 지원: help@goodmit.co.kr");
  });
  it("summarizes smtp (VIS-54 - 예전엔 요약이 없어 잘린 raw JSON 으로 샜다)", () => {
    expect(summarizeSetting("smtp", { enabled: false })).toBe("비활성");
    expect(summarizeSetting("smtp", {
      enabled: true, host: "smtp.example.com", port: 587, security: "starttls",
      from_address: "portal@example.com",
    })).toBe("활성, smtp.example.com:587, STARTTLS, 발신: portal@example.com");
    // 비밀번호(password_ref)는 파일 이름일 뿐이지만, 그래도 요약에 넣지 않는다 - 화면
    // 관례가 아니고 값 자체를 보여줄 이유가 없다.
    expect(summarizeSetting("smtp", { enabled: true, host: "x", port: 25, password_ref: "smtp_pw" }))
      .not.toMatch(/smtp_pw/);
  });
  it("returns null for non-object / unknown values", () => {
    expect(summarizeSetting("unknown_key", "some string")).toBeNull();
    expect(summarizeSetting("maintenance_mode", true)).toBeNull();
    expect(summarizeSetting("password_policy", null)).toBeNull();
  });
});

describe("securityDowngradeWarning — session_policy", () => {
  const setting = { key: "session_policy", value: { idle_timeout_seconds: 1800, absolute_timeout_seconds: 28800 } };

  it("경고 없음 - 값이 그대로다", () => {
    expect(securityDowngradeWarning(setting, { idle_timeout_seconds: 1800, absolute_timeout_seconds: 28800 })).toBeNull();
  });

  it("늘리면(완화) 경고한다", () => {
    const msg = securityDowngradeWarning(setting, { idle_timeout_seconds: 3600, absolute_timeout_seconds: 28800 });
    expect(msg).toMatch(/완화/);
  });

  it("유휴 제한을 줄이면 - 완화 경고가 아니라 '즉시 적용' 경고를 낸다", () => {
    // 회귀: 늘릴 때만 확인받고 줄일 때는 조용히 저장돼, 이미 로그인된 사용자가(관리자
    // 자신 포함) 예고 없이 로그아웃되는 비대칭이 있었다.
    const msg = securityDowngradeWarning(setting, { idle_timeout_seconds: 60, absolute_timeout_seconds: 28800 });
    expect(msg).not.toBeNull();
    expect(msg).not.toMatch(/완화/);
    expect(msg).toMatch(/즉시/);
    expect(msg).toMatch(/로그아웃/);
  });

  it("최대 세션 길이만 줄이는 것은 경고하지 않는다 - 신규 세션부터만 적용되므로 즉시 로그아웃 위험이 없다", () => {
    const msg = securityDowngradeWarning(setting, { idle_timeout_seconds: 1800, absolute_timeout_seconds: 3600 });
    expect(msg).toBeNull();
  });
});
