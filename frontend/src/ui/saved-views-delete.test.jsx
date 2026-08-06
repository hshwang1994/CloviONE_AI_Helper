import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 저장된 뷰 삭제는 되돌릴 수 없다 — 그러니 물어본다 (E2).
 *
 * 메뉴에서 뷰를 고르려다 바로 옆의 휴지통을 누르면 그 뷰가 **한 번의 오조작으로 사라졌다.**
 * 복구 수단이 없다(서버에 휴지통이 없다). 이 저장소의 다른 위험 액션은 전부 확인을 받는다 —
 * 게시글 삭제, 대화 삭제, 채팅방 나가기, 변경 사항 버리기. 같은 관용을 그대로 쓴다
 * (`useConfirm` + `{ danger: true }`).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { SavedViews } from "./SavedViews.jsx";
import { ConfirmProvider, ToastProvider } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

const VIEW = { id: "v-1", screen_key: "audit", name: "실패만", query: "result=failure" };

function renderViews() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockImplementation((path, options) => {
    if (options && options.method === "DELETE") return Promise.resolve({ ok: true });
    return Promise.resolve({ items: [VIEW] });
  });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <SavedViews screenKey="audit" query="result=failure" onApply={() => {}} />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function deleteCalls() {
  return apiMock.mock.calls.filter((c) => c[1] && c[1].method === "DELETE");
}

async function openTrash(user) {
  await user.click(await screen.findByRole("button", { name: /저장된 뷰 \(1\)/ }));
  await user.click(await screen.findByRole("button", { name: "실패만 삭제" }));
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("저장된 뷰 삭제", () => {
  it("휴지통을 눌러도 바로 지우지 않고 먼저 물어본다", async () => {
    const user = userEvent.setup();
    renderViews();

    await openTrash(user);

    // 어느 뷰가 사라지는지 이름으로 말해야 한다 — 목록에서 옆칸을 잘못 눌렀을 때 그것이 유일한 단서다.
    // (메뉴 항목에도 같은 이름이 있으므로 확인 문구 전체로 집는다.)
    expect(await screen.findByText(/실패만.*뷰를 지울까요/)).toBeInTheDocument();
    expect(deleteCalls()).toHaveLength(0);
  });

  it("취소하면 아무 일도 일어나지 않는다", async () => {
    const user = userEvent.setup();
    renderViews();

    await openTrash(user);
    await user.click(await screen.findByRole("button", { name: "취소" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "취소" })).toBeNull());
    expect(deleteCalls()).toHaveLength(0);
  });

  it("확인하면 그때 지운다", async () => {
    const user = userEvent.setup();
    renderViews();

    await openTrash(user);
    await user.click(await screen.findByRole("button", { name: "삭제" }));

    await waitFor(() => expect(deleteCalls()).toHaveLength(1));
    expect(deleteCalls()[0][0]).toBe("/api/me/views/v-1");
  });
});
