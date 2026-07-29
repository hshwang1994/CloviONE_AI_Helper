import { describe, it, expect } from "vitest";
import { diffFields, roleOptionsFor } from "./Users.jsx";

const ALL_OPTS = ["user", "operator", "admin", "auditor", "system_admin"].map((v) => ({ value: v, label: v }));
const values = (opts) => opts.map((o) => o.value);

describe("diffFields", () => {
  it("omits unchanged fields", () => {
    expect(diffFields({ a: 1, b: 2 }, { a: 1, b: 3 })).toEqual({ b: 2 });
  });
  it("returns empty object when nothing changed", () => {
    expect(diffFields({ a: 1, b: "x" }, { a: 1, b: "x" })).toEqual({});
  });
  it("coerces booleans (true vs truthy 1 is unchanged)", () => {
    expect(diffFields({ active: true }, { active: 1 })).toEqual({});
  });
  it("detects a real boolean change", () => {
    expect(diffFields({ active: false }, { active: true })).toEqual({ active: false });
  });
  it("treats null and empty-string as equal (no spurious diff)", () => {
    expect(diffFields({ x: null }, { x: "" })).toEqual({});
  });
  it("treats a missing initial value as a change", () => {
    expect(diffFields({ a: 1 }, undefined)).toEqual({ a: 1 });
  });
});

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
