import { describe, it, expect } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { BlockView } from "./BlockEditor.jsx";

/* 본문의 이미지와 표가 **읽기 전용 화면에 실제로 그려지는지** (S14 · D3).
 *
 * ## 왜 소스 검사가 아니라 렌더인가
 *
 * "확장을 import 했다"는 아무것도 증명하지 않는다. `extensions` 배열에 안 넣으면
 * ProseMirror 는 모르는 노드를 만난 자리를 **통째로 버리고**, 화면에는 오류가 아니라
 * 빈 자리가 뜬다. 그 상태로 저장하면 본문에서 그림과 표가 진짜로 사라진다 — 아무도
 * 신고하지 않는 손실이라 시험이 실제 DOM 을 봐야 한다.
 *
 * 서버가 같은 모양을 거절하지 않는지는 `tests/unit/test_knowledge_blocks.py` 가 본다.
 * 두 쪽이 같은 노드 이름을 쓰는 것이 계약이다(D3).
 */

const CELLS = ["담당자", "마감일", "김철수", "2026-08-24"];

function cell(text, kind) {
  return {
    type: kind,
    attrs: { colspan: 1, rowspan: 1, colwidth: null },
    content: [{ type: "paragraph", content: [{ type: "text", text }] }],
  };
}

const DOC = {
  type: "doc",
  content: [
    {
      type: "image",
      attrs: { src: "/api/knowledge/attachments/abc", alt: "구성도", blockId: "img-1" },
    },
    {
      type: "table",
      attrs: { blockId: "tbl-1" },
      content: [
        { type: "tableRow", content: [cell(CELLS[0], "tableHeader"), cell(CELLS[1], "tableHeader")] },
        { type: "tableRow", content: [cell(CELLS[2], "tableCell"), cell(CELLS[3], "tableCell")] },
      ],
    },
  ],
};

async function renderBody() {
  const { container } = render(<BlockView value={DOC} />);
  await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
  return container;
}

describe("읽기 전용 본문이 이미지와 표를 그린다", () => {
  it("이미지가 src 와 alt 를 그대로 들고 나온다", async () => {
    const container = await renderBody();
    const img = container.querySelector("img");
    expect(img, "이미지 노드가 사라졌다 — 확장이 등록되지 않았다").toBeTruthy();
    expect(img.getAttribute("src")).toBe("/api/knowledge/attachments/abc");
    expect(img.getAttribute("alt")).toBe("구성도");
  });

  it("표가 머리줄과 본문 줄을 갖춘 표로 나온다", async () => {
    const container = await renderBody();
    const table = container.querySelector("table");
    expect(table, "표 노드가 사라졌다 — 확장이 등록되지 않았다").toBeTruthy();
    expect(table.querySelectorAll("tr")).toHaveLength(2);
    expect(table.querySelectorAll("th")).toHaveLength(2);
    expect(table.querySelectorAll("td")).toHaveLength(2);
  });

  it("셀 글자가 한 칸도 빠지지 않는다", async () => {
    await renderBody();
    for (const text of CELLS) {
      expect(screen.getByText(text), `셀 글자가 사라졌다: ${text}`).toBeInTheDocument();
    }
  });

  it("서버가 준 블록 앵커를 이미지와 표도 들고 있는다", async () => {
    /* 앵커를 안 돌려주면 서버가 새 id 를 발급하고, 그러면 그 그림·표를 가리키던 인용이
     * 끊긴다(app/knowledge/blocks.py 의 `carry_from` 설명). */
    const container = await renderBody();
    expect(container.querySelector("img").getAttribute("data-block-id")).toBe("img-1");
    expect(container.querySelector("table").getAttribute("data-block-id")).toBe("tbl-1");
  });

  it("이미지가 칸을 안 넘는다", async () => {
    const container = await renderBody();
    // `max-width` 가 없으면 원본 폭 그대로 나와서 화면 전체가 가로로 밀린다.
    expect(getComputedStyle(container.querySelector("img")).maxWidth).toBe("100%");
  });

  it("옛 노드가 밀려나지 않는다 — 반대편", async () => {
    /* 새 노드를 들이면서 문단이 안 나오면 위 시험들은 「표만 그리는 편집기」도 통과시킨다. */
    const { container } = render(
      <BlockView value={{
        type: "doc",
        content: [{
          type: "paragraph",
          attrs: { blockId: "p-1" },
          content: [{ type: "text", text: "본문 한 줄." }],
        }],
      }} />,
    );
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    expect(screen.getByText("본문 한 줄.")).toBeInTheDocument();
  });
});
