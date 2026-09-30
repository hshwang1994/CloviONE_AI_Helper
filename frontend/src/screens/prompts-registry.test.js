import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { REGISTRY } from "./registry.js";

/* 프롬프트 화면(계획 3.8, D-518). 런타임이 실제로 읽는 지시문을 다루므로 화면이 지키는 것:
 *
 *  1. 목록 첫머리의 기본 제공 행은 고칠 수 없고 「복제해서 수정」만 있다. 바꿀 수 없는 사용처(연결 확인)는 그것도 없다.
 *  2. 관리자가 쓴 행은 초안에서 곧바로 발행한다(테스트 · 검토 단계는 없다). 발행본은 「사용 중」으로 읽힌다.
 *  3. 기본 제공 행은 같은 사용처에 발행본이 있으면 「대체됨」이다.
 *  4. 만들기와 고치기는 사용처를 고르고, 그 후보는 서버의 사용처 목록에서 온다.
 */

const cfg = REGISTRY.prompts;
const labelsFor = (row) => cfg.actions.filter((a) => !a.when || a.when(row, undefined)).map((a) => a.label);
const statusOf = (row) => renderToStaticMarkup(cfg.columns.find((c) => c.key === "status").render(row));

const builtin = { id: "builtin:answer", source: "builtin", status: "builtin", slot: "answer", in_use: true, editable: true };
const draft = { id: "p-1", source: "admin", status: "draft", slot: "answer", name: "답변 지시", version: 1 };

describe("프롬프트 화면", () => {
  it("기본 제공 행에는 「복제해서 수정」만 있다", () => {
    expect(labelsFor(builtin)).toEqual(["복제해서 수정"]);
    expect(labelsFor({ ...builtin, id: "builtin:connection_test", slot: "connection_test", editable: false })).toEqual([]);
  });

  it("관리자가 쓴 초안은 곧바로 발행하고, 발행본에서는 새 버전을 만든다", () => {
    expect(labelsFor(draft)).toEqual(["발행", "버전 기록", "보관", "감사 로그에서 보기"]);
    expect(labelsFor({ ...draft, status: "published" })).toEqual(["새 버전", "버전 기록", "보관", "감사 로그에서 보기"]);
    expect(cfg.actions.map((a) => a.label)).not.toContain("테스트로");
    expect(cfg.editWhen(draft)).toBe(true);
    expect(cfg.editWhen(builtin)).toBe(false);
  });

  it("상태 배지는 지금 쓰이는가를 말한다", () => {
    expect(statusOf(builtin)).toContain("사용 중");
    expect(statusOf({ ...builtin, in_use: false })).toContain("대체됨");
    expect(statusOf({ ...draft, status: "published" })).toContain("사용 중");
    expect(statusOf(draft)).toContain("초안");
  });

  it("사용처는 서버의 목록에서 고른다", () => {
    expect(cfg.refLists).toEqual([{ key: "promptSlots", endpoint: "/api/admin/prompts/slots", valueKey: "key", labelKey: "label" }]);
    for (const form of [cfg.create, cfg.edit]) {
      const slot = form.fields.find((f) => f.name === "slot");
      expect(slot.optionsFromRefList).toBe("promptSlots");
      expect(slot.required).toBe(true);
    }
    expect(cfg.filters.find((f) => f.key === "slot").optionsFromRefList).toBe("promptSlots");
  });

  it("사용 통계에서 지금 쓰는 지시문으로 건너간다", () => {
    const go = REGISTRY["prompt-usage"].actions.find((a) => a.label === "지금 쓰는 지시문 보기");
    expect(go.navigate({ current_id: "builtin:draft" })).toBe("#/prompts?id=builtin%3Adraft");
  });
});
