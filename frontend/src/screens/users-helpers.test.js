import { describe, it, expect } from "vitest";
import { roleOptionsFor } from "./Users.jsx";

const ALL_OPTS = ["user", "operator", "admin", "auditor", "system_admin"].map((v) => ({ value: v, label: v }));
const values = (opts) => opts.map((o) => o.value);

describe("roleOptionsFor", () => {
  it("gives system_admin every option", () => {
    expect(roleOptionsFor("system_admin", "create", ALL_OPTS)).toBe(ALL_OPTS);
    expect(roleOptionsFor("system_admin", "edit", ALL_OPTS)).toBe(ALL_OPTS);
  });
  it("restricts non-system_admin create to user/operator/auditor", () => {
    expect(values(roleOptionsFor("admin", "create", ALL_OPTS))).toEqual(["user", "operator", "auditor"]);
    expect(values(roleOptionsFor("operator", "create", ALL_OPTS))).toEqual(["user", "operator", "auditor"]);
  });
  it("allows non-system_admin edit up to admin (approval flow)", () => {
    expect(values(roleOptionsFor("admin", "edit", ALL_OPTS))).toEqual(["user", "operator", "admin", "auditor"]);
  });
  it("never exposes system_admin to a non-system_admin actor", () => {
    expect(values(roleOptionsFor("admin", "edit", ALL_OPTS))).not.toContain("system_admin");
    expect(values(roleOptionsFor("admin", "create", ALL_OPTS))).not.toContain("system_admin");
  });
});
