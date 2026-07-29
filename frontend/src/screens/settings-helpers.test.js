import { describe, it, expect } from "vitest";
import { fmtDuration, summarizeSetting } from "./Settings.jsx";

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
  it("returns null for non-object / unknown values", () => {
    expect(summarizeSetting("unknown_key", "some string")).toBeNull();
    expect(summarizeSetting("maintenance_mode", true)).toBeNull();
    expect(summarizeSetting("password_policy", null)).toBeNull();
  });
});
