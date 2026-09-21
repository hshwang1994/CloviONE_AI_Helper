import { describe, it, expect } from "vitest";
import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { BlockEditor, EMPTY_DOC, SafeImage, dropUnembeddableImages } from "./BlockEditor.jsx";
import { ToastProvider } from "./kit.jsx";
import { isEmbeddableImageSrc } from "../lib/safeUrl.js";

/* 본문 편집기는 서버가 받는 주소의 그림만 받는다.
 *
 * 🔴 이 파일이 생긴 이유(2026-09-16 운영 로그): 새 티켓 만들기가 다섯 번 연달아 500 이었다. 메일에서 복사해 붙여 넣은
 * 본문의 그림 주소가 `cid:` 였고, 서버의 본문 검증기(`app/knowledge/blocks.py`)가 그 그림을 거절하는 예외를 생성
 * 경로가 처리하지 못했다. 서버 쪽은 422 로 고쳤다(`tests/integration/test_ticket_create_bad_image.py`). 여기서는 편집기가
 * 그런 그림을 애초에 받지 않고, 걷었으면 사용자에게 한 번 알린다는 것을 못박는다.
 */

describe("그림 주소 판정 — 서버 `_safe_href(SAFE_IMAGE_SCHEMES)` 와 같은 규칙", () => {
  it("웹 주소와 상대 주소는 받는다", () => {
    for (const src of ["https://example.com/a.png", "http://example.com/a.png", "/api/knowledge/attachments/abc", "  https://e.com/x.png  ", "HTTPS://E.COM/X.PNG"]) {
      expect(isEmbeddableImageSrc(src), src).toBe(true);
    }
  });

  it("제품 밖에서만 열리는 주소와 스크립트 주소는 받지 않는다", () => {
    for (const src of ["cid:image001.png@01DA", "blob:https://e.com/0f1c", "file:///C:/Users/a/b.png", "data:image/png;base64,AAAA", "javascript:alert(1)", "java\tscript:alert(1)", "", "   ", null, undefined, 42]) {
      expect(isEmbeddableImageSrc(src), String(src)).toBe(false);
    }
  });
});

describe("편집기가 HTML 을 읽을 때", () => {
  it("🔴 받지 않는 주소의 그림은 본문에 들어가지 않는다", () => {
    const editor = new Editor({
      extensions: [StarterKit, SafeImage.configure({ inline: false, allowBase64: false })],
      content: '<p>앞 문단</p><img src="cid:image001.png"><img src="file:///C:/a.png"><img src="https://example.com/ok.png"><p>뒤 문단</p>',
    });
    const images = (editor.getJSON().content || []).filter((n) => n.type === "image");
    expect(images.map((n) => n.attrs.src)).toEqual(["https://example.com/ok.png"]);
    editor.destroy();
  });
});

describe("붙여 넣은 HTML 거르기", () => {
  it("받지 않는 그림만 걷고 그 수를 준다", () => {
    const { html, dropped } = dropUnembeddableImages('<p>안녕</p><img src="cid:a"><img src="/api/x"><img>');
    expect(dropped).toBe(2);
    expect(html).toContain('src="/api/x"');
    expect(html).not.toContain("cid:a");
  });

  it("걷을 것이 없으면 받은 글자를 그대로 돌려준다", () => {
    const raw = '<meta charset="utf-8"><p>그림 없음</p>';
    expect(dropUnembeddableImages(raw)).toEqual({ html: raw, dropped: 0 });
  });

  it("🔴 편집기에 붙여 넣으면 받지 않는 그림을 걷고 한 번 알린다", async () => {
    const { container } = render(
      <ToastProvider>
        <BlockEditor value={EMPTY_DOC} onChange={() => {}} label="본문" />
      </ToastProvider>,
    );
    await waitFor(() => expect(container.querySelector(".ProseMirror")).toBeTruthy());
    const editor = container.querySelector(".ProseMirror").editor;
    /* ProseMirror 의 붙여넣기 경로를 그대로 탄다. jsdom 에는 ClipboardEvent 가 없어 보통 이벤트를 넘긴다. */
    act(() => {
      editor.view.pasteHTML('<p>메일 본문</p><img src="cid:image001.png"><img src="cid:image002.png">', new Event("paste"));
    });
    expect(editor.getText()).toContain("메일 본문");
    expect((editor.getJSON().content || []).some((n) => n.type === "image")).toBe(false);
    expect(await screen.findByText("붙여 넣은 그림 2개는 본문에 넣지 못했습니다. 웹 주소로 열리는 그림만 넣을 수 있습니다.")).toBeInTheDocument();
  });
});
