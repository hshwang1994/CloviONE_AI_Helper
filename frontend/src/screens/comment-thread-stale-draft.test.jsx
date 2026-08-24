import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 댓글 초안이 다른 자원(다른 문서·다른 티켓)으로 넘어가도 남아 있던 버그.
 *
 * KnowledgeDoc.jsx/Ticket.jsx는 같은 라우트("/knowledge/:id", "/tickets/:id")를 쓰므로, 알림
 * 딥링크 등으로 id만 바뀌는 인앱 이동을 하면 화면 컴포넌트는 리마운트되지 않는다(react-router
 * 는 같은 자리의 같은 엘리먼트를 재사용한다) — MEMORY.md의 "컴포넌트가 라우트 파라미터
 * 변경에 걸쳐 마운트된 채로 남으면 id별 상태를 리셋해야 한다" 규칙이 정확히 이 자리다.
 *
 * DocComments/TicketComments는 documentId/ticketId prop만 새로 받고 그 안의 CommentThread
 * 인스턴스는 그대로 남아, 문서(티켓) A에 쓰던 댓글 초안이 지워지지 않은 채 문서(티켓) B의
 * 댓글창에 남는다 — 그대로 "등록"을 누르면 B에 대한 댓글로 잘못 올라간다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { DocComments } from "./DocComments.jsx";
import { TicketComments } from "./TicketComments.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

// KnowledgeDoc.jsx/Ticket.jsx가 id 파라미터만 바뀌어도 리마운트되지 않는 상황을 흉내낸다 —
// Comp 자체는 계속 마운트된 채, prop(id)만 바뀐다.
function Harness({ Comp, propName, first, second }) {
  const [id, setId] = React.useState(first);
  return (
    <>
      <button onClick={() => setId(second)}>다른 자원으로 이동</button>
      <Comp {...{ [propName]: id }} />
    </>
  );
}

function wrap(children) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>{children}</ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ comments: [], people: {} });
});

describe("댓글 초안은 다른 자원으로 이동하면 비워진다", () => {
  it("문서 댓글 — 다른 문서로 이동하면 이전 문서용 초안이 남지 않는다", async () => {
    const user = userEvent.setup();
    wrap(<Harness Comp={DocComments} propName="documentId" first="doc-1" second="doc-2" />);

    const box = await screen.findByLabelText("댓글 입력");
    await user.type(box, "doc-1에 쓰던 초안");
    expect(box).toHaveValue("doc-1에 쓰던 초안");

    await user.click(screen.getByRole("button", { name: "다른 자원으로 이동" }));

    const boxAfter = await screen.findByLabelText("댓글 입력");
    expect(boxAfter).toHaveValue("");
  });

  it("티켓 댓글 — 다른 티켓으로 이동하면 이전 티켓용 초안이 남지 않는다", async () => {
    const user = userEvent.setup();
    wrap(<Harness Comp={TicketComments} propName="ticketId" first="t-1" second="t-2" />);

    const box = await screen.findByLabelText("댓글 입력");
    await user.type(box, "t-1에 쓰던 초안");
    expect(box).toHaveValue("t-1에 쓰던 초안");

    await user.click(screen.getByRole("button", { name: "다른 자원으로 이동" }));

    const boxAfter = await screen.findByLabelText("댓글 입력");
    expect(boxAfter).toHaveValue("");
  });
});
