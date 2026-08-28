import { describe, it, expect } from "vitest";
import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";
import { BlockView, BlockEditor, EMPTY_DOC } from "./BlockEditor.jsx";
import { createClovirTheme } from "./theme.js";

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
 *
 * ## REAUDIT §15.4/§18.2 — 밑줄·체크 목록·새 도구모음
 *
 * 이 파일 아래쪽은 새 아이콘 도구모음(REAUDIT §15.4)과 그 도구모음이 만드는 두 새 노드
 * (`underline` 마크 · `taskList`/`taskItem`)를 겨눈다. 특히 마지막 `describe` 는 §18.2 가
 * 이름으로 요구한 왕복 시험이다 — 밑줄·체크 목록이 든 문서를 "저장"(`onChange` 가 낸
 * JSON) 하고 그 JSON 을 새 편집기 인스턴스로 "다시 열어" 같은 노드가 살아 있는지 본다.
 * 이미지·표가 겪은 것과 같은 위험이다: 확장을 안 넣으면 ProseMirror 가 모르는 노드를
 * 조용히 버리고, 그 손실은 저장 시점이 아니라 다시 열었을 때만 드러난다. */

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

// ── 밑줄과 체크 목록 (REAUDIT §15.4) ────────────────────────────────────────

const CHECK_DOC = {
  type: "doc",
  content: [
    {
      type: "paragraph",
      attrs: { blockId: "p-underline" },
      content: [{ type: "text", text: "밑줄 문장", marks: [{ type: "underline" }] }],
    },
    {
      type: "taskList",
      attrs: { blockId: "tl-1" },
      content: [
        {
          type: "taskItem", attrs: { checked: false },
          content: [{ type: "paragraph", content: [{ type: "text", text: "할 일" }] }],
        },
        {
          type: "taskItem", attrs: { checked: true },
          content: [{ type: "paragraph", content: [{ type: "text", text: "완료" }] }],
        },
      ],
    },
  ],
};

/* 편집 가능한 `BlockEditor` 는 눌린 도구의 색을 `theme.palette.brand.core` 로 낸다
 * (`toolButtonSx`, REAUDIT §15.4 — D-289 잉크·레일 관례). 실제 화면은 앱 루트의
 * `ThemeProvider` 가 항상 감싸 주지만 이 시험은 컴포넌트 하나만 그려서 그 자리가 없다 —
 * `body-editor-toolbar-contrast.test.jsx` 와 같은 이유로 여기서 직접 씌운다. 읽기 전용
 * `BlockView` 는 도구모음 자체가 안 그려지므로(`{!readOnly && …}`) 이 값을 안 쓴다. */
function renderEditable(node) {
  return render(<ThemeProvider theme={createClovirTheme()}>{node}</ThemeProvider>);
}

describe("읽기 전용 본문이 밑줄과 체크 목록을 그린다", () => {
  it("체크박스 둘이 각자의 checked 상태로 그려진다", async () => {
    const { container } = render(<BlockView value={CHECK_DOC} />);
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    const boxes = container.querySelectorAll('input[type="checkbox"]');
    expect(boxes, "체크박스가 사라졌다 — taskItem 확장이 등록되지 않았다").toHaveLength(2);
    expect(boxes[0].checked).toBe(false);
    expect(boxes[1].checked).toBe(true);
    expect(screen.getByText("할 일")).toBeInTheDocument();
    expect(screen.getByText("완료")).toBeInTheDocument();
  });

  it("밑줄 마크가 실제 <u> 태그로 그려진다", async () => {
    const { container } = render(<BlockView value={CHECK_DOC} />);
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    const u = container.querySelector("u");
    expect(u, "밑줄 태그가 사라졌다 — Underline 확장이 등록되지 않았다").toBeTruthy();
    expect(u.textContent).toBe("밑줄 문장");
  });

  it("체크 목록도 서버가 준 블록 앵커를 그대로 들고 있는다", async () => {
    const { container } = render(<BlockView value={CHECK_DOC} />);
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    expect(container.querySelector('ul[data-type="taskList"]').getAttribute("data-block-id")).toBe("tl-1");
  });
});

describe("체크박스는 장식이 아니라 실제 입력이다 — 편집 가능한 편집기", () => {
  it("체크박스를 누르면 checked 가 바뀌고 onChange 가 그 상태를 낸 문서를 낸다", async () => {
    let latest = null;
    const { container } = renderEditable(
      <BlockEditor value={CHECK_DOC} onChange={(doc) => { latest = doc; }} />,
    );
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    const boxes = container.querySelectorAll('input[type="checkbox"]');
    expect(boxes[0].checked).toBe(false);

    fireEvent.click(boxes[0]);

    await waitFor(() => expect(boxes[0].checked).toBe(true));
    await waitFor(() => expect(latest).toBeTruthy());
    const taskList = latest.content.find((b) => b.type === "taskList");
    expect(taskList, "onChange 가 낸 문서에서 taskList 가 사라졌다").toBeTruthy();
    expect(taskList.content.map((i) => i.attrs.checked)).toEqual([true, true]);
  });
});

describe("새 도구모음 — 아이콘 단추마다 접근 가능한 이름이 있다 (REAUDIT §15.4)", () => {
  it("서식·문단·목록·삽입·실행 다섯 묶음의 단추가 모두 있다", async () => {
    renderEditable(<BlockEditor value={EMPTY_DOC} onChange={() => {}} />);
    await screen.findByRole("toolbar");
    const names = [
      "굵게", "기울임", "밑줄", "취소선", "코드",
      "제목1", "제목2", "제목3", "인용", "코드 블록", "구분선",
      "글머리", "번호", "체크 목록",
      "표", "링크", "이모지",
      "되돌리기", "다시 실행",
    ];
    for (const name of names) {
      expect(screen.getByRole("button", { name }), `${name} 단추가 없다`).toBeInTheDocument();
    }
  });

  it("도구모음이 role=toolbar 로 스크린리더에 식별된다", async () => {
    renderEditable(<BlockEditor value={EMPTY_DOC} onChange={() => {}} label="본문" />);
    expect(await screen.findByRole("toolbar", { name: "본문 서식" })).toBeInTheDocument();
  });

  it("이미지 단추는 onPickImage 를 준 자리에서만 선다", async () => {
    renderEditable(<BlockEditor value={EMPTY_DOC} onChange={() => {}} />);
    await screen.findByRole("toolbar");
    expect(screen.queryByRole("button", { name: "이미지" })).toBeNull();
  });

  it("멘션 단추는 없다 — 자동완성 없이 버튼만 두면 눌러도 아무 일이 안 난다(범위 밖)", async () => {
    renderEditable(<BlockEditor value={EMPTY_DOC} onChange={() => {}} />);
    await screen.findByRole("toolbar");
    expect(screen.queryByRole("button", { name: "멘션" })).toBeNull();
  });
});

describe("체크 목록 단추 — 커서만 있어도 현재 문단을 바꾼다", () => {
  it("누르면 onChange 가 taskList 를 담은 문서를 낸다", async () => {
    const user = userEvent.setup();
    let latest = null;
    const oneParagraph = {
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "할 일" }] }],
    };
    renderEditable(<BlockEditor value={oneParagraph} onChange={(doc) => { latest = doc; }} />);
    await user.click(await screen.findByRole("button", { name: "체크 목록" }));
    await waitFor(() => expect(latest).toBeTruthy());
    expect(latest.content.some((b) => b.type === "taskList")).toBe(true);
  });
});

describe("링크 도구 — 팝오버로 주소를 받는다(window.prompt 를 안 쓴다)", () => {
  it("링크 단추를 누르고 주소를 넣으면 링크 글이 들어간다", async () => {
    const user = userEvent.setup();
    let latest = null;
    renderEditable(<BlockEditor value={EMPTY_DOC} onChange={(doc) => { latest = doc; }} />);
    await user.click(await screen.findByRole("button", { name: "링크" }));
    const field = await screen.findByLabelText("링크 주소");
    await user.type(field, "https://example.test");
    await user.click(screen.getByRole("button", { name: "적용" }));

    await waitFor(() => expect(latest).toBeTruthy());
    // 빈 문서는 문단이 하나 자동으로 채워져 있어(TipTap 자체 동작), 새 링크 글이 그
    // 문단 안이 아니라 새 문단으로 들어갈 수 있다 — 어느 문단이든 찾는다.
    const text = latest.content.flatMap((b) => b.content || []).find((n) => n.type === "text");
    expect(text, "선택 없이 링크를 눌렀는데 아무 글도 안 들어갔다").toBeTruthy();
    expect(text.text).toBe("https://example.test");
    expect((text.marks || []).map((m) => m.type)).toContain("link");
  });
});

describe("저장 → 다시 열기 — 같은 노드가 살아 있다 (REAUDIT §18.2 왕복 시험)", () => {
  it("onChange 가 낸 문서를 새 편집기 인스턴스에 그대로 넣어도 밑줄과 체크 목록이 남는다", async () => {
    let saved = null;
    const first = renderEditable(
      <BlockEditor value={CHECK_DOC} onChange={(doc) => { saved = doc; }} />,
    );
    await waitFor(() => expect(first.container.querySelector(".ProseMirror")).toBeTruthy());

    // "저장" — 체크박스 하나를 눌러 실제로 onChange 를 한 번 태운다. 이 문서가 서버에
    // 저장될 모양이다(BlockEditor 는 스스로 저장을 부르지 않는다 — 부르는 쪽의 몫이다).
    const boxes = first.container.querySelectorAll('input[type="checkbox"]');
    fireEvent.click(boxes[0]);
    await waitFor(() => expect(saved).toBeTruthy());
    const savedParagraph = saved.content.find((b) => b.type === "paragraph");
    expect((savedParagraph.content[0].marks || []).map((m) => m.type)).toContain("underline");
    first.unmount();

    // "다시 열기" — 저장된 그 문서를 새 편집기 인스턴스에 넣는다. 다른 문서를 열었다가
    // 이 문서로 돌아온 것과 같은 모양이다 — 앞 인스턴스의 어떤 내부 상태도 재사용하지
    // 않는다.
    const reopened = render(<BlockView value={saved} />);
    await waitFor(() => expect(reopened.container.querySelector(".ProseMirror")).toBeTruthy());

    const reopenedBoxes = reopened.container.querySelectorAll('input[type="checkbox"]');
    expect(reopenedBoxes, "다시 열었더니 체크 목록이 사라졌다").toHaveLength(2);
    expect(reopenedBoxes[0].checked).toBe(true); // 저장 전에 눌러서 체크됐다
    expect(reopenedBoxes[1].checked).toBe(true);
    expect(reopened.container.querySelector("u")?.textContent).toBe("밑줄 문장");
  });
});
