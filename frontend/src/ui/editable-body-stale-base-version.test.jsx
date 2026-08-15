import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 본문 편집(EditableBody) — 저장에 실어 보내는 base_version은 "편집을 시작한 시점"의
 * 지문이어야 한다(EditableBody.jsx 상단 주석 3번: "편집을 시작할 때 받은 지문(base_version)을
 * 저장에 실어 보낸다. 안 보내면 그 사이 먼저 저장한 사람의 글을 통째로 지우고 양쪽 다 성공
 * 토스트를 본다.").
 *
 * 그런데 실제 구현은 `bodyVersion`을 **prop 그대로** mutationFn 클로저에서 읽는다. 편집 중에
 * 이 화면이 리렌더되어 `bodyVersion` prop이 새 값으로 바뀌면(예: 같은 티켓의 첨부를 올려서
 * `["ticket", ticketId]` 쿼리가 무효화·재조회되는 동안, 하필 다른 사람이 먼저 본문을 저장해
 * 서버의 body_version이 실제로 바뀐 경우) 저장 버튼을 누르는 순간에는 **편집을 시작할 때의
 * 지문이 아니라 방금 도착한 새 지문**이 실려 나간다. 서버의 충돌 검사(`_ensure_body_not_changed`)
 * 는 "지금 서버 값과 내가 보낸 값이 같냐"만 보므로, 방금 반영된 새 지문을 그대로 돌려보내면
 * 검사를 통과해 버리고 — 이 사용자의 옛 초안이 방금 저장된 남의 글을 조용히 덮어쓴다. 편집
 * 시작 시점의 지문을 얼려 두지 않으면 이 보호 장치는 하필 그것이 필요한 순간에만 무력화된다. */

const apiMock = vi.fn(() => Promise.resolve({ body_markdown: "저장됨", synced: true }));
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { EditableBody } from "./EditableBody.jsx";
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

beforeEach(() => { apiMock.mockClear(); });

describe("본문 편집 — 저장 지문(base_version)은 편집 시작 시점 값을 쓴다", () => {
  it("편집 도중 bodyVersion prop이 바뀌어도, 저장은 편집을 시작할 때의 지문을 보낸다", async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <EditableBody
                editorId="ticket-body-1"
                endpoint="/api/tickets/1/body"
                bodyMarkdown="원본"
                bodyVersion="v1"
                bodyIsLocal
                sourceView={<div>원본</div>}
              />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: "본문 수정" }));

    // 편집 중 다른 동작(예: 같은 티켓의 첨부 변경)이 상세 재조회를 불러, 그 사이 다른 사람이
    // 먼저 저장한 새 지문이 prop으로 도착한다. 이 컴포넌트는 리마운트되지 않는다(같은 자리).
    rerender(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <EditableBody
                editorId="ticket-body-1"
                endpoint="/api/tickets/1/body"
                bodyMarkdown="다른 사람이 먼저 고친 본문"
                bodyVersion="v2"
                bodyIsLocal
                sourceView={<div>원본</div>}
              />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(apiMock).toHaveBeenCalledWith(
      "/api/tickets/1/body",
      expect.objectContaining({
        method: "PUT",
        body: expect.objectContaining({ base_version: "v1" }),
      }),
    );
  });
});
