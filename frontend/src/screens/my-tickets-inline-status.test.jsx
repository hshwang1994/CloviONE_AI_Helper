import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 목록에서 **상세로 들어가지 않고** 상태를 바꾼다 (지시 18).
 *
 * 여기서 지키는 것은 넷이다.
 *
 * 1. 상태 칸이 눌리고, 열리는 목록이 **서버 어휘**다(화면이 상태 이름을 안 적는다).
 * 2. 고르면 그 티켓 하나만 PATCH 한다.
 * 3. **서버가 돌려준 값**이 화면의 새 값이다 — 넘긴 값이 아니라.
 * 4. 실패하면 **이전 값으로 되돌아가고** 사유가 그 자리에 붙는다. 토스트로만 말하면
 *    어느 행이 실패했는지가 사라진다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args) }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { user: { id: "u1", display_name: "나", role: "user" } } }),
}));

import { ticketColumns } from "./MyTickets.jsx";
import { DataTable } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROW = { id: "t-1", uid: "t-1", key: "ABC-1", title: "서버 등록 IP 중복 방지", status: "계획" };

const STATUS_OPTIONS = [
  { value: "계획", label: "계획" },
  // 저장값과 표시값이 다른 것이 하나 있다 — 서버가 준 라벨을 그대로 쓴다(D-349).
  { value: "진행", label: "진행 중" },
  { value: "완료", label: "완료" },
];

function draw(statusEdit) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <DataTable
            columns={ticketColumns({ statusEdit })}
            rows={[ROW]}
            rowKey={(r) => r.id}
          />
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("내 티켓 — 그 자리에서 상태 바꾸기", () => {
  it("🔴 상태 칸이 눌리고, 열리는 목록이 서버 어휘다", async () => {
    const user = userEvent.setup();
    draw({ options: STATUS_OPTIONS, save: vi.fn() });
    await user.click(screen.getByRole("button", { name: /상태 바꾸기/ }));
    // 「진행 중」은 서버가 준 라벨이다. 화면이 상태 이름을 적으면 어휘가 바뀐 날 여기만 남는다.
    expect(await screen.findByRole("option", { name: "진행 중" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "완료" })).toBeInTheDocument();
  });

  it("고르면 **서버가 돌려준 값**이 새 값이 된다", async () => {
    const user = userEvent.setup();
    const save = vi.fn().mockResolvedValue("진행");
    draw({ options: STATUS_OPTIONS, save });
    await user.click(screen.getByRole("button", { name: /상태 바꾸기/ }));
    await user.click(await screen.findByRole("option", { name: "진행 중" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ id: "t-1" }), "진행"));
    // 저장값 `진행` 이 표시값 `진행 중` 으로 그려진다.
    expect(await screen.findByText("진행 중")).toBeInTheDocument();
  });

  it("🔴 실패하면 이전 값으로 되돌아가고 사유가 그 자리에 붙는다", async () => {
    const user = userEvent.setup();
    const save = vi.fn().mockRejectedValue(new Error("이 티켓을 편집할 권한이 없습니다."));
    draw({ options: STATUS_OPTIONS, save });
    await user.click(screen.getByRole("button", { name: /상태 바꾸기/ }));
    await user.click(await screen.findByRole("option", { name: "완료" }));
    expect(await screen.findByText(/편집할 권한이 없습니다/)).toBeInTheDocument();
    // 값은 그대로다 — 실패한 저장이 화면에 남으면 사용자는 바뀐 줄 안다.
    expect(screen.getByText("계획")).toBeInTheDocument();
  });

  it("바꿀 수 없는 표에는 **눌리는 컨트롤을 두지 않는다**", () => {
    // 열 수 없는 것을 눌러 보게 하지 않는다(`ui/InlineEdit.jsx` 의 `locked` 규칙).
    draw(undefined);
    expect(screen.queryByRole("button", { name: /상태 바꾸기/ })).toBeNull();
    expect(screen.getByText("계획")).toBeInTheDocument();
  });
});
