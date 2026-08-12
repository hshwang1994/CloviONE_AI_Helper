/* VIS-86 — 본문 편집기의 이모지 버튼 8개가 aria-label="이모지 ✅"처럼 이모지를 그대로
 * 되읽어, 스크린리더 사용자에게 그 버튼이 무엇을 하는지 아무 정보도 주지 않았다.
 * 각 버튼이 실제로 삽입하는 내용의 뜻을 말해야 한다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BodyEditor } from "./BodyEditor.jsx";

describe("본문 편집기 — 이모지 버튼의 접근 이름", () => {
  it("이모지 버튼 8개 모두 이모지 자체가 아니라 뜻을 말하는 aria-label을 갖는다", () => {
    render(<BodyEditor id="b1" value="" onChange={() => {}} />);
    const names = [
      "완료 표시 넣기", "고정 표시 넣기", "주의 표시 넣기", "강조 표시 넣기",
      "가리킴 표시 넣기", "목표 표시 넣기", "축하 표시 넣기", "아이디어 표시 넣기",
    ];
    for (const name of names) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    // 예전 결함의 정확한 모양(aria-label="이모지 " + 글자)이 남아 있지 않은지도 확인한다.
    expect(screen.queryByRole("button", { name: /^이모지 / })).toBeNull();
  });
});
