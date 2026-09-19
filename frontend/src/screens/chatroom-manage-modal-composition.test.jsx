import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 채팅방 관리 창의 채움 — 입력 영역마다 하나다 (UI 3차 조합 계약 C-4 · D-491).
 *
 * 이 창에는 따로 확정하는 입력이 둘 있다: 방 이름(「저장」)과 초대할 사람 고르기(「초대」). 둘 다 채움이라 창 하나에
 * 채움이 둘로 보였고(조사 부록 「채팅방 관리 모달 채움 둘」), 조합 잣대 `primary_budget` 은 입력 영역 표식
 * (`data-form-scope`)으로 영역마다 제 몫을 센다. 여기서는 두 구획이 각각 표식을 들고 채움을 정확히 하나씩 가지며,
 * 창 발은 닫기(보조) 하나라는 것을 못박는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ManageRoomModal } from "./ChatRoomMembers.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function Providers({ children }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <ConfirmProvider>
          <MemoryRouter>{children}</MemoryRouter>
        </ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

const DIRECTORY = {
  users: [
    { user_id: "u3", display_name: "새 동료", email: "peer@example.com", dept: "ClovirONE팀", title: "", org: "", archived: false },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) =>
    path === "/api/team-chat/directory" ? Promise.resolve(DIRECTORY) : Promise.resolve({}));
});

describe("채팅방 관리 창 — 입력 영역 둘, 채움은 영역마다 하나", () => {
  it("이름 구획과 초대 구획이 각각 입력 영역 표식을 들고 채움을 하나씩 가진다", async () => {
    render(
      <Providers>
        <ManageRoomModal open onClose={() => {}} roomId="r1" title="우리방" members={[]} meId="u1" />
      </Providers>,
    );
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("button", { name: "초대" });
    const scopes = [...dialog.querySelectorAll("[data-form-scope]")];
    expect(scopes).toHaveLength(2);
    const [renameScope, inviteScope] = scopes;
    expect(renameScope.contains(document.getElementById("tc-rename"))).toBe(true);
    expect(within(inviteScope).getByRole("heading", { name: "초대하기" })).toBeInTheDocument();
    for (const [scope, label] of [[renameScope, "저장"], [inviteScope, "초대"]]) {
      const filled = scope.querySelectorAll(".MuiButton-containedPrimary");
      expect(filled).toHaveLength(1);
      expect(filled[0].textContent).toBe(label);
    }
    // 영역 밖에 선 채움은 없다 — 창의 채움은 전부 영역의 몫이다.
    const loose = [...dialog.querySelectorAll(".MuiButton-contained")].filter((b) => !b.closest("[data-form-scope]"));
    expect(loose).toHaveLength(0);
  });

  it("창 발은 닫기(보조) 하나이고 글자 단추가 아니다", async () => {
    render(
      <Providers>
        <ManageRoomModal open onClose={() => {}} roomId="r1" title="우리방" members={[]} meId="u1" />
      </Providers>,
    );
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector('[data-action-footer="modal"]')).not.toBeNull());
    const footer = dialog.querySelector('[data-action-footer="modal"]');
    const buttons = [...footer.querySelectorAll("button")];
    expect(buttons.map((b) => b.textContent)).toEqual(["닫기"]);
    expect(buttons[0].className).toMatch(/MuiButton-outlined/);
    expect(buttons[0].className).not.toMatch(/MuiButton-text/);
  });
});
