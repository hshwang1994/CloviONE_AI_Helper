import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";

/* 티켓 미리보기의 **히스토리 계약** (D-483).
 *
 *  1) 여는 것은 push 다 — 뒤로가기 한 번이 미리보기를 닫고 화면은 그대로다.
 *  2) 닫기 단추는 밀어 넣은 항목을 되돌린다 — `peek` 없는 주소를 다시 push 하지 않는다
 *     (그러면 뒤로가기가 미리보기를 다시 연다).
 *  3) 「티켓 상세 보기」는 미리보기 항목을 상세로 갈아 끼운다 — 상세에서 뒤로가기 한 번에
 *     미리보기 없는 원래 화면이고, 상세의 「목록」이 돌아올 자리(`from`)를 싣는다.
 *  4) 딥링크로 `?peek=` 채로 들어오면 되돌릴 항목이 없으니 닫기는 replace 다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u-1" } }) }));

import { TicketPeek, useTicketPeek } from "./TicketPeek.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const TICKET = {
  configured: true, ok: true, can_edit: true,
  ticket: { id: "pg-1", key: "ABC-1", title: "확인할 일", status: "진행", project: "포털", sprint_id: "sp-1", due: "2026-08-28", assignee_people: [] },
  body_markdown: "설명 본문입니다.",
};

const SPEC = { team: "", sprint: "", peek: "" };

function Screen() {
  const [state, setState] = useQueryState(SPEC);
  const peek = useTicketPeek(state, setState);
  const loc = useLocation();
  const nav = useNavigate();
  return (
    <div>
      <div data-testid="here">{`${loc.pathname}${loc.search}`}</div>
      <button type="button" onClick={() => peek.open({ page_id: "pg-1" })}>열기</button>
      {/* 브라우저 뒤로가기의 자리 — MemoryRouter 는 window.history 를 안 쓴다. */}
      <button type="button" onClick={() => nav(-1)}>브라우저 뒤로</button>
      <TicketPeek
        pageId={peek.pageId}
        onClose={peek.close}
        onDetail={peek.detail}
        from="/work-board"
        sprints={[{ id: "sp-1", name: "9-2" }]}
      />
    </div>
  );
}

function Detail() {
  const loc = useLocation();
  const nav = useNavigate();
  return (
    <div>
      <div data-testid="detail">{`${loc.pathname} from=${(loc.state && loc.state.from) || ""}`}</div>
      <button type="button" onClick={() => nav(-1)}>뒤로</button>
    </div>
  );
}

function renderAt(entry) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes>
                <Route path="/work-board" element={<Screen />} />
                <Route path="/tickets/:id" element={<Detail />} />
              </Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => (String(path).startsWith("/api/tickets/") ? Promise.resolve(TICKET) : Promise.resolve({})));
});

describe("useTicketPeek + TicketPeek", () => {
  it("🔴 열기는 push, 닫기는 되돌리기 — 닫은 뒤 주소에 peek 이 없고 뒤로가기가 미리보기를 다시 열지 않는다", async () => {
    renderAt("/work-board?team=d-a&sprint=sp-1");
    await userEvent.click(screen.getByRole("button", { name: "열기" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("peek=pg-1"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("설명 본문입니다.")).toBeTruthy();
    // 회차 이름을 말한다.
    expect(within(dialog).getByText("9-2")).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toBe("/work-board?team=d-a&sprint=sp-1"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // 되돌렸으므로 앞으로가기 자리에 미리보기가 남을 뿐, 뒤로가기는 화면을 떠난다(진입 전).
    // 여기서 확인하는 것은 「닫기가 push 가 아니다」 — 열기 전과 같은 주소다.
  });

  it("🔴 뒤로가기 한 번이 미리보기를 닫는다 — 화면을 떠나지 않는다", async () => {
    renderAt("/work-board?team=d-a&sprint=sp-1");
    await userEvent.click(screen.getByRole("button", { name: "열기" }));
    await screen.findByRole("dialog");
    // 모달이 열린 동안 바깥은 aria-hidden 이다 — 브라우저의 뒤로가기는 그 밖에서 온다.
    await userEvent.click(screen.getByRole("button", { name: "브라우저 뒤로", hidden: true }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toBe("/work-board?team=d-a&sprint=sp-1"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("🔴 「티켓 상세 보기」는 미리보기 항목을 상세로 갈아 끼운다 — 뒤로가기 한 번에 미리보기 없는 원래 화면", async () => {
    renderAt("/work-board?team=d-a&sprint=sp-1");
    await userEvent.click(screen.getByRole("button", { name: "열기" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "티켓 상세 보기" }));
    await waitFor(() => expect(screen.getByTestId("detail").textContent).toBe("/tickets/pg-1 from=/work-board"));
    await userEvent.click(screen.getByRole("button", { name: "뒤로" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toBe("/work-board?team=d-a&sprint=sp-1"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("딥링크로 들어온 미리보기는 닫기가 replace 다 — 되돌릴 항목이 없다", async () => {
    renderAt("/work-board?team=d-a&sprint=sp-1&peek=pg-1");
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toBe("/work-board?team=d-a&sprint=sp-1"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("회차 안에서 할 수 있는 일(actions)이 단추로 서고, 없으면 안 선다", async () => {
    const onRemove = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/x"]}>
        <QueryClientProvider client={qc}>
          <ThemeModeProvider>
            <ToastProvider>
              <ConfirmProvider>
                <TicketPeek
                  pageId="pg-1" onClose={() => {}} onDetail={() => {}} from="/work-board"
                  actions={[{ key: "remove", label: "현재 회차에서 빼기", onClick: onRemove }]}
                />
              </ConfirmProvider>
            </ToastProvider>
          </ThemeModeProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "현재 회차에서 빼기" }));
    expect(onRemove).toHaveBeenCalledTimes(1);
    expect(onRemove.mock.calls[0][0].key).toBe("ABC-1");
  });
});
