import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { REGISTRY } from "./registry.js";

/* WF1 단독 결함 — 자매 엔티티 Prompt에는 있는 purpose(무엇을 강제하는 규칙인지)가 Policy에는
 * 컬럼 자체가 없어 목록에서 "이 정책이 왜 있는지" 알 방법이 없었다(app/prompts/models.py::Policy,
 * 마이그레이션 0058). 백엔드는 이미 저장/반환/PATCH/새 버전 이어짐을 프롬프트와 동일하게 지원한다
 * (tests/integration/test_prompts_api.py). 여기서는 화면(registry/authoring.js)이 프롬프트의
 * 기존 배선(목록 열 + create/edit textarea)을 그대로 따라가는지 고정한다.
 */
function findCol(key) {
  return REGISTRY.policies.columns.find((c) => c.key === key);
}

function renderCol(col, row) {
  return render(<div>{col.render(row)}</div>);
}

describe("정책 목록 — '용도' 열과 create/edit 폼 (WF1 단독 결함)", () => {
  it("'용도' 열이 목록에 존재하고 짧은 값은 그대로 보여준다", () => {
    const col = findCol("purpose");
    expect(col).toBeTruthy();
    expect(col.label).toBe("용도");
    const { container } = renderCol(col, { purpose: "3일 이상 휴가는 팀장 승인이 필요합니다." });
    expect(container).toHaveTextContent("3일 이상 휴가는 팀장 승인이 필요합니다.");
  });

  it("purpose가 없으면(null) '-'로 보여준다 — 미기재와 빈 문자열을 구분한다", () => {
    const col = findCol("purpose");
    const { container } = renderCol(col, { purpose: null });
    expect(container).toHaveTextContent("-");
  });

  it("60자를 넘으면 말줄임(…)으로 자르고 title 속성에 전체 텍스트를 남긴다", () => {
    const col = findCol("purpose");
    const long = "가".repeat(80);
    const { container } = renderCol(col, { purpose: long });
    const span = container.querySelector("span[title]");
    expect(span).toBeTruthy();
    expect(span.getAttribute("title")).toBe(long);
    expect(span.textContent.endsWith("…")).toBe(true);
    expect(span.textContent.length).toBeLessThan(long.length);
  });

  it("생성 폼에 '용도' textarea가 있다", () => {
    const field = REGISTRY.policies.create.fields.find((f) => f.name === "purpose");
    expect(field).toBeTruthy();
    expect(field.type).toBe("textarea");
  });

  it("수정 폼에 '용도' textarea가 있다", () => {
    const field = REGISTRY.policies.edit.fields.find((f) => f.name === "purpose");
    expect(field).toBeTruthy();
    expect(field.type).toBe("textarea");
  });
});
