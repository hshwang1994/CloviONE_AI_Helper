import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";
import { COPY_LIMIT } from "../ui/theme.js";

const ROLES = ["admin", "system_admin", "operator", "auditor", "user"];
const FIELDS = ["emptyHelp", "emptySituation", "emptyPrerequisite", "emptyExpected", "emptySteps"];

function collect(value, bag) {
  if (value == null || value === false) return;
  if (typeof value === "function") {
    for (const role of ROLES) {
      try { collect(value(role), bag); } catch { /* arity */ }
    }
    try { collect(value(), bag); } catch { /* arity */ }
    return;
  }
  if (typeof value === "string" && value) bag.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collect(item, bag));
}

describe("registry 빈 상태 문구는 칸 폭에서 온 한도를 지킨다", () => {
  it("emptyHelp·상황·준비물·단계·기대 결과가 COPY_LIMIT.emptyHelp 이하다", () => {
    const over = [];
    for (const [key, cfg] of Object.entries(REGISTRY)) {
      const bag = [];
      for (const field of FIELDS) collect(cfg[field], bag);
      for (const text of bag) {
        const n = [...text].length;
        if (n > COPY_LIMIT.emptyHelp) over.push(`${key} (${n}자): ${text}`);
      }
    }
    expect(over, over.join("\n")).toEqual([]);
  });
});
