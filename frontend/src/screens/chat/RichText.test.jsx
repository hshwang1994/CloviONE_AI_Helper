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

// AI-34: 펜스 코드블록이 <pre><code>로 렌더되고, 원문이 linkifyText/블록 재분류를
// 거치지 않고 그대로 보존된다.
describe("RichText — 펜스 코드블록", () => {
  it("```로 감싼 내용이 <pre><code>에 원문 그대로 렌더된다(불릿/URL로 오분류되지 않는다)", () => {
    const { container } = render(
      <RichText text={"```\ndef f(x):\n- https://example.com 아님\n```"} />,
    );
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    const code = pre.querySelector("code");
    expect(code).not.toBeNull();
    expect(code.textContent).toBe("def f(x):\n- https://example.com 아님");
    // 코드 안의 URL은 링크화되지 않는다 - 코드는 코드 그대로다.
    expect(pre.querySelector("a")).toBeNull();
  });

  it("펜스 앞뒤의 일반 텍스트는 그대로 문단으로 렌더된다", () => {
    const { getByText, container } = render(
      <RichText text={"앞 문단\n```\ncode\n```\n뒤 문단"} />,
    );
    expect(getByText("앞 문단")).toBeInTheDocument();
    expect(getByText("뒤 문단")).toBeInTheDocument();
    expect(container.querySelector("pre code").textContent).toBe("code");
  });
});
