import { describe, it, expect } from "vitest";
import { diffFields } from "./diffFields.js";

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

  /* CONC-01: DataScreen.jsx의 toApiBody가 만드는 값(templates의 approval_policy 등)은 객체다.
   * 옛 구현은 String(obj)로 비교해 내용이 달라도 항상 "[object Object]" === "[object Object]"로
   * "같음"이라고 오판했다 — 실제로 바뀐 객체 필드가 조용히 diff에서 빠져 저장되지 않는 결함. */
  it("객체 필드는 내용으로 비교한다(참조가 달라도 내용이 같으면 변경 없음)", () => {
    expect(diffFields({ policy: { required: true } }, { policy: { required: true } })).toEqual({});
  });
  it("객체 필드의 내용이 실제로 다르면 변경으로 잡는다(옛 String(obj) 비교의 회귀)", () => {
    expect(diffFields({ policy: { required: true } }, { policy: { required: false } }))
      .toEqual({ policy: { required: true } });
  });
  it("배열 필드도 내용으로 비교한다", () => {
    expect(diffFields({ tags: ["a", "b"] }, { tags: ["a", "b"] })).toEqual({});
    expect(diffFields({ tags: ["a", "b"] }, { tags: ["a", "c"] })).toEqual({ tags: ["a", "b"] });
  });
});
