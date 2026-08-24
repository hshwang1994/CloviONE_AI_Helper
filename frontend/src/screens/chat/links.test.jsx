import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { linkifyText } from "./links.jsx";

/* AI 도우미의 URL 다듬기가 팀 채팅 말풍선(chat-text.js)과 같은 규칙을 쓰는지 본다
 * (step 10 #1). 예전엔 chat-helpers.js 의 URL_RE(`/(https?:\/\/[^\s]+)/g`)가 공백 전까지
 * 욕심껏 먹어서 "...(https://a.b/c)에서" 같은 문장의 닫는 괄호·조사까지 통째로 URL에
 * 들어갔다 - href 도 그 오염된 문자열로 이뤄져 자신만만하게 틀린 링크를 냈다.
 *
 * 지금은 **어떤 주소도 앵커가 아니다.** 예전에는 notion.so 계열만 진짜 링크로 열어 줬는데
 * 그 호스트를 특별히 믿을 근거가 없어졌다(chat-helpers.js 의 설명 참고). 그래서 아래
 * 시험들이 보는 것은 `<a>` 가 아니라 PlainUrl 복사 버튼이고, 꼬리 다듬기 규칙은 그대로다.
 */

function renderParts(text) {
  return render(<div data-testid="out">{linkifyText(text, "t")}</div>);
}

describe("linkifyText — URL 꼬리 다듬기", () => {
  it("괄호로 감싼 링크는 닫는 괄호가 URL에서 빠진다(chat-text.js와 같은 입력·같은 결과)", () => {
    // chat-text.test.js의 "주소 끝 마침표·괄호는 뺀다" 테스트와 같은 모양의 입력이다 -
    // 괄호 뒤에 공백이 있어야 trimUrlTail이 아는 "닫는 괄호"로 잡힌다(순수 ASCII
    // 문장부호·괄호만 다듬는다 - 공백 없이 바로 붙은 뒷말까지 떼는 것은 이 함수의
    // 책임이 아니다, chat-text.js도 같은 한계를 가진 채로 이미 쓰이고 있다).
    const { container } = renderParts("자세한 내용은 (https://www.notion.so/abc) 에서 확인하세요.");
    expect(container.querySelector("a")).toBeNull();
    const btn = container.querySelector("button");
    expect(btn).not.toBeNull();
    expect(btn.textContent).toBe("https://www.notion.so/abc");
    expect(container.textContent).toContain(") 에서 확인하세요.");
  });

  it("마침표로 끝나는 링크는 마침표가 빠진다", () => {
    const { container } = renderParts("문서 링크: https://www.notion.so/xyz.");
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("button").textContent).toBe("https://www.notion.so/xyz");
    expect(container.textContent.endsWith(".")).toBe(true);
  });

  it("어떤 링크든 같은 규칙으로 꼬리가 빠진다(PlainUrl 복사 버튼)", () => {
    const { container } = renderParts("(https://example.com/page) 참고");
    const btn = container.querySelector("button");
    expect(btn).not.toBeNull();
    expect(btn.textContent).toBe("https://example.com/page");
  });

  it("주소 안의 균형 잡힌 괄호는 그대로 둔다(위키백과 주소 같은 경우)", () => {
    const { container } = renderParts("참고: https://ko.example/wiki/A_(B) 확인");
    const link = container.querySelector("a, button");
    expect(link.textContent).toBe("https://ko.example/wiki/A_(B)");
  });

  it("꼬리가 없는 평범한 링크는 그대로다(회귀 없음)", () => {
    const { container } = renderParts("링크: https://www.notion.so/plain");
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("button").textContent).toBe("https://www.notion.so/plain");
  });
});
