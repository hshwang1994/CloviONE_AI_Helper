import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { FormField } from "./kit.jsx";

/* 지시 17 · Taste §4.6 — **라벨은 입력 위에 있다.**
 *
 * MUI 기본은 떠 있는 라벨이다: 값이 없으면 입력 칸 안에 있다가 포커스하면 위로 올라가
 * 테두리에 걸친다. 그 방식이 잃는 것 셋.
 *   · 훑을 수 없다 — 값이 든 칸과 빈 칸의 라벨 위치가 달라 세로로 라벨을 따라 읽지 못한다.
 *   · 한국어에서 자주 잘린다 — 떠 있는 라벨은 테두리 노치 폭 안에 들어가야 한다.
 *   · 필수 표시가 `*` 하나뿐이고, 그것이 무엇을 뜻하는지 화면 어디에도 없다.
 *
 * 여기서 고정하는 것은 넷이다.
 *   1) 라벨이 입력보다 **앞선다**(DOM 순서 = 읽는 순서 = 보는 순서).
 *   2) 라벨과 입력이 실제로 **연결된다**(라벨을 눌러 포커스가 가고, 이름으로 찾을 수 있다).
 *   3) 필수는 **글자로** 보이되 접근성 이름에는 안 들어간다 — `aria-required` 가 그 몫이다.
 *   4) `select` 는 MUI 가 `id` 를 `<div>` 에 걸어 `<label htmlFor>` 이 끊긴다 — 그때는
 *      `aria-labelledby` 로 잇는다.
 */

function renderField(field, value = "") {
  return render(<FormField field={field} value={value} onChange={() => {}} />);
}

describe("입력 라벨은 위에 있다", () => {
  it("라벨 요소가 입력보다 DOM 에서 앞선다", () => {
    const { container } = renderField({ name: "title", label: "제목", type: "text" });
    const label = container.querySelector("label");
    const input = container.querySelector("input");
    expect(label, "라벨 요소가 없다").toBeTruthy();
    expect(input).toBeTruthy();
    // compareDocumentPosition: 4 = label 이 input 보다 앞선다.
    expect(label.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("라벨과 입력이 연결돼 이름으로 찾을 수 있다", () => {
    renderField({ name: "title", label: "제목", type: "text" });
    expect(screen.getByLabelText(/^제목/)).toBeTruthy();
  });

  it("MUI 의 떠 있는 라벨을 함께 그리지 않는다 — 같은 글자가 두 번 보이면 안 된다", () => {
    const { container } = renderField({ name: "title", label: "제목", type: "text" });
    expect(container.querySelectorAll(".MuiInputLabel-root").length).toBe(0);
    // 라벨 글자는 화면에 한 번만 있다.
    expect(screen.getAllByText(/제목/).length).toBe(1);
  });
});

describe("필수 표기", () => {
  it("필수는 글자로 보인다", () => {
    renderField({ name: "title", label: "제목", type: "text", required: true });
    expect(screen.getByText(/필수/)).toBeInTheDocument();
  });

  it("필수 표기가 접근성 이름을 오염시키지 않는다", () => {
    renderField({ name: "title", label: "제목", type: "text", required: true });
    // 이름은 "제목"이다 — "제목 필수"가 아니다. 필수 여부는 aria-required 가 말한다.
    const input = screen.getByRole("textbox", { name: "제목" });
    expect(input).toHaveAttribute("required");
  });

  it("필수가 아니면 표기가 없다", () => {
    renderField({ name: "title", label: "제목", type: "text" });
    expect(screen.queryByText(/필수/)).toBeNull();
  });
});

describe("select 도 같은 규칙을 따른다", () => {
  it("라벨이 앞서고, 이름으로 찾을 수 있다", () => {
    const { container } = renderField(
      { name: "state", label: "점검 상태", type: "select", options: [{ value: "a", label: "A" }] },
      "a",
    );
    const label = container.querySelector("#ff-state-label");
    expect(label, "select 의 라벨이 없다").toBeTruthy();
    const combo = screen.getByRole("combobox", { name: "점검 상태" });
    expect(combo.getAttribute("aria-labelledby")).toContain("ff-state-label");
    expect(label.compareDocumentPosition(combo) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("라벨을 붙일 수 없는 요소에 <label htmlFor> 를 걸지 않는다", () => {
    const { container } = renderField(
      { name: "state", label: "점검 상태", type: "select", options: [{ value: "a", label: "A" }] },
      "a",
    );
    // 이 자리는 `<span id>` + aria-labelledby 다 — `<label for>` 이 div 를 가리키면
    // 접근성 트리에서 조용히 끊긴다(HTML 명세: non-labellable).
    expect(container.querySelector('label[for="ff-state"]')).toBeNull();
  });
});
