import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 실패는 **그 자리의 메시지 박스**이고, 서는 때와 걷히는 때가 정해져 있다 (핸드오프 RULES §1 · 계획 표 6).
 *
 * 토스트는 몇 초 뒤 저절로 사라졌다. 자리로 옮기면 「언제 걷히는가」가 새로 생기는데, 새 상태를 멋대로 만들면
 * 지난 실패가 다음 동작 위에 붙어 남는다. 여기서 대표 자리 셋의 수명을 못 박는다:
 *   ① 칸 오류는 그 칸을 고치면 걷힌다(티켓 수정 모달)
 *   ② 모달을 닫고 다시 열면 지난 저장 실패가 남지 않는다(티켓 수정 모달)
 *   ③ 판의 실패는 다시 시도해서 성공하면 걷힌다(티켓 첨부)
 * 그리고 문구는 토스트 때와 같다 — 오류 토스트는 더는 뜨지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1" } }),
}));

import { TicketEditModal } from "./MyTickets.jsx";
import { TicketAttachments } from "./TicketAttachments.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function ticket(extra) {
  return {
    id: "p1", tid: 1, key: "ABC-1", title: "티켓 하나", status: "진행",
    due: "2026-08-03", start: "", est_wd: 1, act_wd: null,
    priority: null, difficulty: null, category: "",
    project_ids: [], project_names: [],
    assignee_names: [], assignee_user_ids: [],
    issue: false, blocked: false, blocked_reason: null,
    ...extra,
  };
}

function Providers({ children }) {
  const [qc] = React.useState(() => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }));
  return (
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>{children}</MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

function metaApi(patchImpl) {
  apiMock.mockImplementation((path, options) => {
    if (path === "/api/tickets/p1" && options && options.method === "PATCH") return patchImpl(options);
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ statuses: ["진행", "완료"], priorities: [], difficulties: [] });
    if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
    if (path.startsWith("/api/work-statuses")) return Promise.resolve({ statuses: [] });
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("① 칸 오류 — 그 칸 아래에 서고, 그 칸을 고치면 걷힌다", () => {
  it("제목을 비우고 저장하면 제목 칸이 오류를 말하고, 다시 적으면 오류가 사라진다", async () => {
    metaApi(() => Promise.resolve({ ok: true, ticket: ticket() }));
    const user = userEvent.setup();
    render(<Providers><TicketEditModal ticket={ticket()} open onClose={() => {}} /></Providers>);

    const title = await screen.findByLabelText(/제목/);
    await user.clear(title);
    await user.click(screen.getByRole("button", { name: "저장" }));

    // 칸 오류는 그 칸의 설명(aria-describedby)이다 — 어느 칸인지 말한다.
    await waitFor(() => expect(title).toHaveAccessibleDescription("제목은 비울 수 없습니다."));
    expect(title).toHaveAttribute("aria-invalid", "true");
    // 요청은 나가지 않았다(검증이 먼저다).
    expect(apiMock.mock.calls.some(([p, o]) => p === "/api/tickets/p1" && o && o.method === "PATCH")).toBe(false);

    await user.type(title, "고친 제목");
    await waitFor(() => expect(screen.queryByText("제목은 비울 수 없습니다.")).toBeNull());
    expect(title).not.toHaveAttribute("aria-invalid", "true");
  });
});

describe("② 모달 저장 실패 — 모달 안에 서고, 닫았다 다시 열면 남지 않는다", () => {
  it("저장이 실패하면 발 위에 서버 문장이 서고, 모달을 다시 열면 그 문장이 없다", async () => {
    metaApi(() => Promise.reject(new Error("다른 사람이 먼저 고쳤습니다. 새로고침한 뒤 다시 저장하세요.")));
    const user = userEvent.setup();

    function Harness() {
      const [open, setOpen] = React.useState(true);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>다시 열기</button>
          <TicketEditModal ticket={ticket()} open={open} onClose={() => setOpen(false)} />
        </>
      );
    }
    render(<Providers><Harness /></Providers>);

    const title = await screen.findByLabelText(/제목/);
    await user.type(title, " 수정");
    await user.click(screen.getByRole("button", { name: "저장" }));

    const dialog = await screen.findByRole("dialog");
    const failure = await within(dialog).findByText("다른 사람이 먼저 고쳤습니다. 새로고침한 뒤 다시 저장하세요.");
    expect(failure.closest(".k-callout")).toHaveAttribute("data-tone", "danger");

    // 닫는다(바꾼 값이 있어 확인을 받는다) → 다시 연다.
    await user.click(within(dialog).getByRole("button", { name: "취소" }));
    const confirmBox = await screen.findByRole("dialog", { name: "변경 사항 버리기" });
    // 확인 창에는 머리의 닫기 단추(×)와 확정 단추 「닫기」가 함께 있다 — 글자를 가진 확정 단추를 누른다.
    const confirmClose = within(confirmBox).getAllByRole("button", { name: "닫기" }).find((b) => b.textContent === "닫기");
    await user.click(confirmClose);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /티켓 수정/ })).toBeNull());

    await user.click(screen.getByRole("button", { name: "다시 열기" }));
    await screen.findByRole("dialog", { name: /티켓 수정/ });
    expect(screen.queryByText("다른 사람이 먼저 고쳤습니다. 새로고침한 뒤 다시 저장하세요.")).toBeNull();
  });
});

describe("③ 판 실패 — 판 안에 서고, 다시 시도해서 성공하면 걷힌다", () => {
  function fileInput(container) {
    return container.querySelector('input[type="file"]');
  }
  function pick(input, name) {
    const file = new File(["x"], name, { type: "image/png" });
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  it("첨부 올리기가 통째로 실패하면 첨부 판에 서고, 다음 올리기가 성공하면 사라진다", async () => {
    let fail = true;
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/tickets/page-1/attachments" && opts && opts.method === "POST") {
        return fail ? Promise.reject(new Error("저장 공간이 모자랍니다.")) : Promise.resolve({ ok: true });
      }
      return Promise.resolve({ ok: true });
    });
    const { container } = render(
      <Providers>
        <TicketAttachments ticketId="page-1" attachments={[]} canEdit onChanged={() => {}} />
      </Providers>,
    );

    pick(fileInput(container), "one.png");
    // 파일별 실패는 「일부를 못 올렸다」로 모인다 — 문구는 토스트 때와 같다.
    const notice = await screen.findByText("첨부 1개를 올리지 못했습니다: one.png");
    expect(notice.closest(".k-callout")).toHaveAttribute("data-tone", "danger");

    fail = false;
    pick(fileInput(container), "two.png");
    await waitFor(() => expect(screen.queryByText(/올리지 못했습니다/)).toBeNull());
  });
});
