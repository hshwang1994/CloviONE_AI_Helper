/* 일괄 삭제는 **확인을 받고, 몇 건인지 숫자로 말한다** (E1).
 *
 * qa-contract-replaced-by: frontend/src/screens/bulk-delete-confirm.test.jsx
 *
 * 원래 이 계약은 옛 문서 화면(`TeamDocs.jsx`)에서 못박혀 있었다. 그 화면은 S14 에서
 * 사라졌지만 **계약은 안 사라졌다** — 지금 이 규칙을 지고 있는 것은 「내 티켓」의 선택
 * 삭제다(`MyTickets.jsx::MyTicketsScreen`). 화면이 옮겨 갔다고 계약을 지우면, 다음에 같은
 * 자리를 만드는 사람은 확인 없이 지우는 코드를 아무 저항 없이 쓴다.
 *
 * 못박는 것은 둘이다. 둘 다 실제로 한 번씩 어겼던 자리다.
 *
 *   1. **확인 전에는 요청을 안 보낸다.** 예전에는 「선택 삭제」를 누르는 순간 선택 전부가
 *      휴지통으로 갔다. 같은 화면군의 `Trash.jsx` 는 확인을 받는데 여기만 규칙이 갈렸다.
 *   2. **확인 문구가 몇 건인지 숫자로 말한다.** 「선택한 항목」은 개수를 안 알려 준다 —
 *      화면 밖(다른 쪽)의 선택까지 지워질 때 사용자는 그 사실을 여기서만 알 수 있다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "me-1" } }) }));

import { MyTickets } from "./MyTickets.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const META = { configured: true, ok: true, statuses: ["진행"], priorities: ["High"], difficulties: ["중"] };
const ROWS = {
  configured: true, ok: true, total: 2, page: 1, page_size: 20,
  items: [
    { id: "t-1", tid: 4101, title: "로그인 실패 조사", status: "진행", priority: "High", project: "인프라" },
    { id: "t-2", tid: 4102, title: "배포 스크립트 정리", status: "진행", priority: "High", project: "인프라" },
  ],
};

function trashCalls() {
  return apiMock.mock.calls.filter(([p]) => String(p) === "/api/tickets/trash-bulk");
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/tickets/meta")) return Promise.resolve(META);
    if (p.startsWith("/api/tickets/projects")) return Promise.resolve({ configured: true, ok: true, projects: [] });
    if (p.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (p.startsWith("/api/tickets/mine")) return Promise.resolve(ROWS);
    if (p === "/api/tickets/trash-bulk") return Promise.resolve({ trashed: ["t-1"], failed: [] });
    return Promise.resolve({});
  });
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/my-tickets"]}><MyTickets /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

async function selectOneAndPressDelete() {
  renderScreen();
  await screen.findByText("로그인 실패 조사");
  fireEvent.click(screen.getByRole("checkbox", { name: "로그인 실패 조사 선택" }));
  fireEvent.click(await screen.findByRole("button", { name: "선택 삭제" }));
  return screen.findByRole("dialog");
}

describe("선택 삭제 (E1)", () => {
  it("확인을 받기 전에는 삭제 요청을 보내지 않는다", async () => {
    const dialog = await selectOneAndPressDelete();
    expect(trashCalls(), "확인 창이 떠 있는데 이미 지웠다").toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(trashCalls(), "취소했는데 지웠다").toHaveLength(0);
  });

  it("확인 문구가 몇 건인지 숫자로 말한다 — 「선택한 항목」은 개수를 안 알려 준다", async () => {
    const dialog = await selectOneAndPressDelete();
    expect(dialog).toHaveTextContent("1건");
    expect(dialog.textContent).not.toContain("선택한 항목");
  });

  it("확인하면 고른 것만 삭제 요청에 실린다", async () => {
    const dialog = await selectOneAndPressDelete();
    fireEvent.click(within(dialog).getByRole("button", { name: "1건 삭제" }));

    await waitFor(() => expect(trashCalls()).toHaveLength(1));
    const [, opts] = trashCalls()[0];
    expect(opts.method).toBe("POST");
    expect(opts.body.page_ids).toEqual(["t-1"]);
  });
});
