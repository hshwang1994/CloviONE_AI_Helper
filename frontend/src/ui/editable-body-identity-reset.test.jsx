import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 본문 편집(EditableBody) — 편집 중에 **다른 문서로 자리가 바뀌면** 남아 있던 초안을 버려야 한다.
 *
 * `editable-body-stale-base-version.test.jsx` 가 이미 확정한 전제: 이 컴포넌트는 같은 티켓/문서를
 * 계속 보는 동안(예: 첨부 업로드가 상세를 재조회하는 사이) **리마운트되지 않는다** — 그래서 그
 * 테스트는 편집 시작 시점의 base_version 을 얼려 둔다.
 *
 * 그런데 리마운트되지 않는 것은 "같은 티켓을 보는 동안"만이 아니다. `screens/Ticket.jsx` 는
 * `<Route path="/tickets/:id" element={<Ticket/>}/>` 로 붙어 있고, react-router 는 경로 패턴이
 * 같으면 `:id` 만 바뀌어도 컴포넌트를 다시 만들지 않는다 — 그 자식인 TicketBody→EditableBody도
 * 같은 인스턴스로 남는다. 그 새 티켓이 이미 캐시돼 있으면(예: 알림 벨·검색 결과·뒤로가기로 예전에
 * 열어 본 티켓으로 바로 이동) react-query 는 로딩 화면 없이 바로 새 데이터를 준다 — 그 사이
 * EditableBody 는 한 번도 언마운트되지 않는다.
 *
 * 이때 사용자가 이전 티켓의 본문을 편집하던 중이었다면(저장하지 않은 초안이 남아 있다면),
 * `editing`/`draft`/`editBaseVersion` 은 전부 컴포넌트 state 라 새 티켓으로 넘어와도 그대로
 * 남는다. 이 상태에서 '저장'을 누르면 **이전 티켓에서 쓰던 글이 새 티켓의 엔드포인트로** 나간다
 * — 남의(또는 엉뚱한) 문서 본문을 조용히 덮어쓰는 데이터 손상이다. `editorId` 는 호출부가 항상
 * "티켓-body-<id>"/"doc-body-<id>" 처럼 문서 정체성을 그대로 실어 보내므로, 그 값이 바뀌면
 * "다른 문서로 자리가 바뀌었다"는 뜻이다 — 그 순간 남아 있던 편집 상태를 버려야 한다. */

const apiMock = vi.fn(() => Promise.resolve({ body_markdown: "저장됨", synced: true }));
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { EditableBody } from "./EditableBody.jsx";
import { ConfirmProvider, ToastProvider } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

function wrapNode(node, qc) {
  return (
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>{node}</ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => { apiMock.mockClear(); });

describe("본문 편집 — 다른 문서로 자리가 바뀌면 남은 초안을 버린다", () => {
  it("편집 중 editorId/endpoint가 다른 문서로 바뀌면 이전 초안이 새 문서로 저장되지 않는다", async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { rerender } = render(
      wrapNode(
        <EditableBody
          editorId="ticket-body-1"
          endpoint="/api/tickets/1/body"
          bodyMarkdown="티켓1 원본"
          bodyVersion="v1"
          bodyIsLocal
          sourceView={<div>티켓1 원본</div>}
        />,
        qc,
      ),
    );

    await user.click(screen.getByRole("button", { name: "본문 편집" }));
    const textbox = screen.getByRole("textbox", { name: "본문 편집" });
    await user.clear(textbox);
    await user.type(textbox, "저장 안 한 티켓1 초안");

    // 알림 벨 등 다른 경로로, 이미 캐시된 다른 티켓으로 리마운트 없이 넘어간 상황을 흉내낸다.
    rerender(
      wrapNode(
        <EditableBody
          editorId="ticket-body-2"
          endpoint="/api/tickets/2/body"
          bodyMarkdown="티켓2 원본"
          bodyVersion="v9"
          bodyIsLocal
          sourceView={<div>티켓2 원본</div>}
        />,
        qc,
      ),
    );

    // 새 문서로 넘어온 순간 이전 초안은 화면에 남아 있으면 안 된다.
    expect(screen.queryByDisplayValue(/저장 안 한 티켓1 초안/)).not.toBeInTheDocument();
    expect(screen.getByText("티켓2 원본")).toBeInTheDocument();

    // 혹시 저장 버튼이 여전히 눌린다 해도, 티켓1의 초안이 티켓2의 엔드포인트로 나가면 안 된다.
    const saveBtn = screen.queryByRole("button", { name: "저장" });
    if (saveBtn) await user.click(saveBtn);
    for (const call of apiMock.mock.calls) {
      const [url, opts] = call;
      if (url === "/api/tickets/2/body") {
        expect(opts.body.body_markdown).not.toMatch(/저장 안 한 티켓1 초안/);
      }
    }
  });
});
