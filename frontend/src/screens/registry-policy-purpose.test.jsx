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
 * qa-contract-change: 정책 목록의 「용도」 열은 계획 3.12 대로 「종류」와 「적용할 기능」 열이 대신한다(D-519). 정책이 무엇을 하는지는 이제 종류와 대상이 말하고, 사람이 적는 설명은 라벨을 「설명」으로 바꿔 상세와 두 폼에 남는다. 그래서 「용도 열이 목록에 있다」 세 단언은 「종류와 적용할 기능이 목록에 있다」로 바뀌었다.
 */
function findCol(key) {
  return REGISTRY.policies.columns.find((c) => c.key === key);
}

function renderCol(col, row) {
  return render(<div>{col.render(row)}</div>);
}

describe("정책 목록 — 종류와 적용할 기능, 폼의 설명 (D-519)", () => {
  it("「종류」 열이 서버가 준 이름을 보인다", () => {
    const col = findCol("kind");
    expect(col.label).toBe("종류");
    const { container } = renderCol(col, { kind: "data_protection", kind_label: "개인정보 가리기" });
    expect(container).toHaveTextContent("개인정보 가리기");
  });

  it("「적용할 기능」 열이 기능 이름을 쉼표로 잇고, 없으면 '-' 를 보인다", () => {
    const col = findCol("applies_to_labels");
    expect(renderCol(col, { applies_to_labels: ["채팅 답변", "작업 공간 질문"] }).container)
      .toHaveTextContent("채팅 답변, 작업 공간 질문");
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
