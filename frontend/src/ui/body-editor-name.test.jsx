import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 본문 편집기의 접근 이름 (접근성 감사 2).
 *
 * qa-contract-change: 편집기가 textarea 에서 TipTap contenteditable 로 바뀌어 label htmlFor 의 대상이 될 수 없다 — 「바깥 라벨을 안 덮어쓴다」는 단정이 잴 대상을 잃었고 편집기가 자기 이름을 드는 계약이 그 자리를 대신한다.
 *
 * 티켓 본문과 문서 본문은 이 앱에서 가장 많이 쓰는 편집 표면인데, 입력 상자에 이름이 없어
 * 스크린리더가 "편집" 이라고만 읽었다. 무엇을 편집하는 칸인지 알 수 없다.
 *
 * 이름은 화면이 이미 쓰고 있는 제목(heading)에서 나와야 한다 - 별도 문자열을 손으로 적으면
 * 티켓과 문서 중 한쪽만 고쳐진다(이 패널이 두 화면 공용인 이유와 같은 이유다).
 */

vi.mock("../lib/api.js", () => ({ api: vi.fn(() => Promise.resolve({})), setCsrf: () => {} }));

import { EditableBody } from "./EditableBody.jsx";
import { BodyEditor } from "./BodyEditor.jsx";
import { ConfirmProvider, ToastProvider } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

function wrap(node) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>{node}</ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("본문 편집기 이름", () => {
  it("수정을 열면 입력 상자가 무엇을 수정하는지 낭독한다", async () => {
    wrap(
      <EditableBody
        editorId="ticket-body-1"
        endpoint="/api/tickets/1/body"
        bodyDoc={{ type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "원래 본문" }] }] }}
        bodyVersion="v1"
        bodyIsLocal
        sourceView={<div>원래 본문</div>}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "본문 수정" }));
    expect(await screen.findByRole("textbox", { name: "본문 수정" })).toBeInTheDocument();
  });

  it("heading 을 바꾸면 입력 상자 이름도 따라간다", async () => {
    wrap(
      <EditableBody
        editorId="doc-body-1"
        endpoint="/api/team-docs/1/body"
        heading="문서 본문"
        bodyDoc={{ type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "원래 본문" }] }] }}
        bodyVersion="v1"
        bodyIsLocal
        sourceView={<div>원래 본문</div>}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "문서 본문 수정" }));
    expect(await screen.findByRole("textbox", { name: "문서 본문 수정" })).toBeInTheDocument();
  });

  /* 🔴 여기 「바깥에서 `<label>` 로 이름을 준 자리는 그 이름을 덮어쓰지 않는다」가 있었다.
     그 시험이 지키던 것은 `<textarea id>` 와 `<label htmlFor>` 의 짝이었고, 그 짝은
     본문 편집기가 TipTap 으로 바뀌면서 없어졌다 — `contenteditable` 은 `<label htmlFor>`
     의 대상이 될 수 없다(레이블 가능한 요소가 아니다). 그래서 지금은 **편집기가 자기 이름을
     스스로 든다**(`ariaLabel`). 보이는 라벨과 낭독되는 이름이 갈리지 않게 하는 규칙 자체는
     그대로다 — 부르는 쪽이 화면에 적은 말과 같은 말을 넘긴다. */
});
