/* 지시 28 — 본문 편집기가 이모지를 **권하지 않는다.**
 *
 * 예전에는 서식 도구 옆에 ✅📌⚠️🔹👉🎯🎉💡 여덟 개가 있었다. 지시 28 은 이모지와 장식
 * 문자를 화면에서 전수 제거하라고 했는데, 이 여덟 개는 그것을 **화면이 스스로 권하는**
 * 자리였다 — 없애는 것으로 끝나지 않고 넣으라고 버튼까지 줬다.
 *
 * 이 파일은 그 전 결함(VIS-86: `aria-label="이모지 ✅"` 처럼 이모지를 되읽던 것)을 지키던
 * 시험을 대신한다. 그 결함은 버튼이 사라지면서 함께 사라졌다 — 시험이 지키던 것이
 * 없어졌으면 시험도 그 사실을 말해야 한다(초록불이 근거가 못 되는 자리를 남기지 않는다).
 *
 * 본문에 이모지를 못 쓰게 막지는 않는다. 사용자가 직접 치면 그대로 저장된다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { BodyEditor } from "./BodyEditor.jsx";

describe("본문 편집기 — 이모지를 권하지 않는다 (지시 28)", () => {
  it("서식 도구에 이모지 버튼이 없다", () => {
    render(<BodyEditor id="b1" value="" onChange={() => {}} />);
    const toolbar = screen.getByRole("group", { name: /서식/ });
    for (const glyph of ["✅", "📌", "⚠️", "🔹", "👉", "🎯", "🎉", "💡"]) {
      expect(toolbar.textContent, `이모지 버튼이 남아 있다: ${glyph}`).not.toContain(glyph);
    }
    // 예전 버튼들의 접근 이름도 함께 사라졌는지 본다(숨겨 두고 남기지 않았다는 확인).
    expect(screen.queryByRole("button", { name: /표시 넣기$/ })).toBeNull();
  });

  it("글의 구조를 만드는 도구는 그대로 있다 — 강조는 이것들이 한다", () => {
    render(<BodyEditor id="b1" value="" onChange={() => {}} />);
    for (const name of ["제목", "글머리", "번호", "구분선"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
  });

  it("사용자가 직접 친 이모지는 그대로 남는다 — 막는 것이 아니라 권하지 않는 것이다", () => {
    render(<BodyEditor id="b1" value="회의 결과 ✅ 완료" onChange={() => {}} />);
    expect(screen.getByDisplayValue("회의 결과 ✅ 완료")).toBeInTheDocument();
  });
});
