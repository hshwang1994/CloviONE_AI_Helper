import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { RichText } from "./RichText.jsx";

/* 머리글 줄의 URL도 목록·표·문단과 같이 링크가 된다(step 10 #2).
 *
 * parseBlocks가 만드는 네 블록(head·list·kv·para) 중 목록·표·문단 셋은 이미
 * linkifyText를 거치는데 머리글만 `{b.text}`를 그대로 그렸다 - "■ https://…" 처럼
 * 답변이 URL로 시작하는 줄(가장 흔한 트리거는 AI-33이지만, 그걸 고쳐도 이 경로 자체는
 * 남는다)에서 그 줄의 URL이 링크도 복사 버튼도 아닌 죽은 글자로 남았다.
 */

describe("RichText — 머리글 줄의 URL", () => {
  it("[제목] 형태 머리글 안의 URL이 링크가 된다", () => {
    const { container } = render(<RichText text="[참고] https://www.notion.so/abc 확인" />);
    const link = container.querySelector("a, button");
    expect(link).not.toBeNull();
    // NotionLink는 새 탭 고지를 sr-only 텍스트로도 덧붙인다 - 주소 자체가 들어 있는지만 본다.
    expect(link.textContent).toContain("https://www.notion.so/abc");
  });

  it("■ 불릿 머리글 안의 URL도 링크가 된다", () => {
    const { container } = render(<RichText text="■ https://www.notion.so/xyz" />);
    const link = container.querySelector("a, button");
    expect(link).not.toBeNull();
    expect(link.textContent).toContain("https://www.notion.so/xyz");
  });

  it("URL이 없는 평범한 머리글은 그대로 글자로 남는다(회귀 없음)", () => {
    const { getByText } = render(<RichText text="[요약] 이번 주 진행 상황" />);
    expect(getByText("요약", { exact: false })).toBeInTheDocument();
  });
});
