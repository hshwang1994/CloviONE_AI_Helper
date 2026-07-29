import { describe, it, expect } from "vitest";
import { fmtCertDays, canGo } from "./Dashboard.jsx";

describe("fmtCertDays", () => {
  it("returns em-dash for null/undefined", () => {
    expect(fmtCertDays(null)).toBe("-");
    expect(fmtCertDays(undefined)).toBe("-");
  });
  it("returns 만료됨 for negative days", () => {
    expect(fmtCertDays(-5)).toBe("만료됨");
  });
  it("returns 오늘 만료 for exactly 0 days", () => {
    expect(fmtCertDays(0)).toBe("오늘 만료");
  });
  it("returns D-N for positive days", () => {
    expect(fmtCertDays(10)).toBe("D-10");
    expect(fmtCertDays(1)).toBe("D-1");
  });
});

describe("canGo (NAV role gating)", () => {
  it("allows operator into /jobs but blocks auditor", () => {
    expect(canGo("/jobs", "operator")).toBe(true);
    expect(canGo("/jobs", "auditor")).toBe(false);
  });
  it("allows auditor into /audit", () => {
    expect(canGo("/audit", "auditor")).toBe(true);
  });
  it("restricts /diagnostics to admin/system_admin", () => {
    expect(canGo("/diagnostics", "admin")).toBe(true);
    expect(canGo("/diagnostics", "operator")).toBe(false);
  });
  it("treats an unlisted path as unrestricted", () => {
    expect(canGo("/anything", "user")).toBe(true);
  });
  it("blocks a null role on a gated path", () => {
    expect(canGo("/diagnostics", null)).toBe(false);
  });
  it("opens /backup and /integrations to read roles including auditor", () => {
    expect(canGo("/backup", "auditor")).toBe(true);
    expect(canGo("/integrations", "auditor")).toBe(true);
  });
});
