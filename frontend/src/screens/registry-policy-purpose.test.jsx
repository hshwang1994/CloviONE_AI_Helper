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
 *
 * qa-contract-change: 정책 목록의 「종류」 열은 종류별 구획의 머리행이 대신한다(D-542) — 같은 표 안에 종류마다 머리행이 서고 그 종류가
 * 하는 일을 한 문장으로 말한다. 그래서 「종류 열이 서버가 준 이름을 보인다」 단언은 「행이 종류의 구획으로 묶이고 구획 머리가 이름과
 * 할 일을 말한다」로 바뀌었다. 열 이름 「적용할 기능」은 「적용 기능」이다.
 * qa-contract-change: 정책 목록의 「용도」 열은 계획 3.12 대로 「종류」와 「적용할 기능」 열이 대신한다(D-519). 정책이 무엇을 하는지는 이제 종류와 대상이 말하고, 사람이 적는 설명은 라벨을 「설명」으로 바꿔 상세와 두 폼에 남는다. 그래서 「용도 열이 목록에 있다」 세 단언은 「종류와 적용할 기능이 목록에 있다」로 바뀌었다.
 */
function findCol(key) {
  return REGISTRY.policies.columns.find((c) => c.key === key);
}

function renderCol(col, row) {
  return render(<div>{col.render(row)}</div>);
}

describe("정책 목록 — 종류와 적용할 기능, 폼의 설명 (D-519)", () => {
  it("행은 종류의 구획으로 묶이고, 구획 머리가 종류 이름과 그 종류가 하는 일을 말한다", () => {
    const groupOf = REGISTRY.policies.groupRows;
    expect(REGISTRY.policies.groupOrder).toEqual(["approval", "data_protection", "content"]);
    // 규칙이 없는 종류도 머리와 한 줄로 선다(D-542) — 갈래 셋이 순서대로, 빈 줄 문장을 함께 든다.
    expect(REGISTRY.policies.groupSlots.map((s) => s.key)).toEqual(["approval", "data_protection", "content"]);
    expect(REGISTRY.policies.groupSlots.every((s) => s.emptyText === "이 종류의 규칙이 없습니다.")).toBe(true);
    expect(groupOf({ kind: "data_protection" })).toEqual({ key: "data_protection", label: "개인정보 가리기", note: "모델에 보내기 전에 개인정보를 가립니다." });
    expect(groupOf({ kind: "approval" }).label).toBe("쓰기 승인");
    expect(groupOf({ kind: "content" }).note).toContain("응답");
    expect(findCol("kind")).toBeUndefined();
  });

  it("「적용할 기능」 열이 기능 이름을 쉼표로 잇고, 없으면 '-' 를 보인다", () => {
    const col = findCol("applies_to_labels");
    expect(col.label).toBe("적용 기능");
    expect(renderCol(col, { applies_to_labels: ["AI 도우미", "작업 공간 문서 초안"] }).container)
      .toHaveTextContent("AI 도우미, 작업 공간 문서 초안");
    expect(renderCol(col, { applies_to_labels: [] }).container).toHaveTextContent("-");
  });

  it("상세에 사람이 적은 설명이 남는다", () => {
    const detail = REGISTRY.policies.detailFields.find((f) => f.key === "purpose");
    expect(detail.label).toBe("설명");
  });

  it("생성 폼에 '설명' textarea가 있다", () => {
    const field = REGISTRY.policies.create.fields.find((f) => f.name === "purpose");
    expect(field).toBeTruthy();
    expect(field.type).toBe("textarea");
    expect(field.label).toBe("설명");
  });

  it("수정 폼에 '설명' textarea가 있다(정책 종류마다 같은 자리)", () => {
    for (const kind of ["approval", "data_protection", "content"]) {
      const field = REGISTRY.policies.edit.fields("system_admin", { kind }).find((f) => f.name === "purpose");
      expect(field).toBeTruthy();
      expect(field.type).toBe("textarea");
    }
  });
});
