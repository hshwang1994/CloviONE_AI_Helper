/* qa-contract-change: 확인 문구가 「요청자: 이름」 꼴의 조각 나열에서 완전한 한 문장으로 바뀌었다(CLAUDE.md §10 은 UI 문구에 `\n` 을 금지한다) — 재는 사실(창이 요청자와 대상을 말한다)은 그대로 두고 문장 모양만 새 문구에 맞춘다. */

/* 개인 결재함의 승인·거절은 **확인 한 단계**를 지나고, 결재한 줄은 **자리를 지킨다** (perm-10).
 *
 * 실측으로 일어난 일: 1행의 「승인」을 한 번 누르자 그 줄이 목록에서 빠지고 2행이 그 자리로
 * 올라왔다. 같은 좌표를 1.4초 뒤에 한 번 더 누르니 **열어 본 적 없는 다른 사람의 승격**이
 * 승인됐고, 계정 둘이 연속으로 admin 이 됐다. 결재는 되돌릴 수 없어서 그 사고는 사과로
 * 끝나지 않는다.
 *
 * 그래서 이 파일은 둘을 함께 못박는다:
 *   1. 확인 창이 먼저 뜨고, 그 창이 **누구의 무엇을 결재하는지** 말한다.
 *   2. 결재가 끝난 줄은 자리를 지킨 채 결과만 바뀐다 — 아래 줄이 커서 밑으로 올라오지 않는다.
 *
 * 반례(좋은 경우가 그대로 초록이어야 한다): 확인 창에서 「확인」을 누르면 그 요청 하나가
 * 실제로 결재되고, 취소하면 아무 요청도 안 나간다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
// 축포는 캔버스를 만든다 — jsdom 에서 부를 일이 없게 막는다(이 시험의 관심사가 아니다).
vi.mock("../ui/celebrate.js", () => ({ celebrateIfCleared: () => {}, celebrateIfCompleted: () => {} }));

import { MyApprovals } from "./MyApprovals.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function row(id, requester, targetName) {
  return {
    id,
    request_type: "user.role_change",
    status: "pending",
    object_type: "user",
    object_id: "u-" + id,
    requested_at: "2026-08-01T01:00:00",
    requester_name: requester,
    request_payload: { role: "admin", previous_role: "operator", target_name: targetName },
  };
}

/** 서버 대역 — 결재된 id 는 다음 목록 응답에서 빠진다(실서버와 같은 계약). */
let decided = [];
const ROWS = [row("A1", "박민준", "첫째 대상"), row("A2", "김지훈", "둘째 대상")];

beforeEach(() => {
  decided = [];
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    if (opts && opts.method === "POST") {
      const id = p.split("/approvals/")[1].split("/")[0];
      decided.push({ id, verb: p.endsWith("/approve") ? "approve" : "reject" });
      return Promise.resolve({ ok: true });
    }
    const items = ROWS.filter((r) => !decided.some((d) => d.id === r.id));
    return Promise.resolve({ items, total: items.length, page: 1, page_size: 20, can_decide: true });
  });
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/my-approvals"]}>
          <Routes><Route path="/my-approvals" element={<MyApprovals />} /></Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const dataRows = () => screen.getAllByRole("row").slice(1);   // 첫 줄은 열 제목이다

describe("개인 결재함 — 되돌릴 수 없는 결재를 한 번의 클릭으로 실행하지 않는다", () => {
  it("「승인」은 곧바로 POST 하지 않고 확인 창을 먼저 띄우며, 그 창이 요청자와 대상을 말한다", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findAllByRole("button", { name: "승인" });

    await user.click(screen.getAllByRole("button", { name: "승인" })[0]);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/되돌릴 수 없습니다/)).toBeInTheDocument();
    expect(within(dialog).getByText(/박민준님이 올린/)).toBeInTheDocument();
    expect(within(dialog).getByText(/대상은 첫째 대상입니다/)).toBeInTheDocument();
    // 확인 전에는 아무 요청도 안 나간다.
    expect(decided.length).toBe(0);
  });

  it("확인 창에서 취소하면 아무것도 결재되지 않는다(반례)", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findAllByRole("button", { name: "승인" });
    await user.click(screen.getAllByRole("button", { name: "승인" })[0]);
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "취소" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(decided.length).toBe(0);
    expect(dataRows().length).toBe(2);
  });

  it("확인하면 그 한 건만 결재되고, 그 줄은 자리를 지킨 채 결과만 바뀐다", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findAllByRole("button", { name: "승인" });
    const before = dataRows().length;
    expect(before).toBe(2);

    await user.click(screen.getAllByRole("button", { name: "승인" })[0]);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getAllByRole("button", { name: "승인" })[0]);

    await waitFor(() => expect(decided.length).toBe(1));
    expect(decided[0]).toEqual({ id: "A1", verb: "approve" });

    // 줄 수가 그대로다 = 아래 줄이 커서 밑으로 올라오지 않았다.
    await waitFor(() => expect(within(dataRows()[0]).getByText("승인했습니다.")).toBeInTheDocument());
    expect(dataRows().length).toBe(before);
    expect(within(dataRows()[0]).getByText("박민준")).toBeInTheDocument();
    // 결재가 끝난 줄에는 단추가 없다 — 같은 자리를 다시 눌러도 두 번째 요청이 안 나간다.
    expect(within(dataRows()[0]).queryByRole("button", { name: "승인" })).toBeNull();
    expect(within(dataRows()[0]).queryByRole("button", { name: "거절" })).toBeNull();
  });

  it("결재 직후 같은 자리를 다시 눌러도 다른 사람의 요청이 결재되지 않는다", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findAllByRole("button", { name: "승인" });

    // 1행 승인 → 확인 → 성공.
    await user.click(screen.getAllByRole("button", { name: "승인" })[0]);
    let dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getAllByRole("button", { name: "승인" })[0]);
    await waitFor(() => expect(decided.length).toBe(1));

    // 남아 있는 「승인」 단추는 2행의 것뿐이고, 그것을 눌러도 확인 창이 먼저 뜬다.
    const stillThere = screen.getAllByRole("button", { name: "승인" });
    expect(stillThere.length).toBe(1);
    await user.click(stillThere[0]);
    dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/김지훈님이 올린/)).toBeInTheDocument();
    expect(decided.length).toBe(1);
  });

  it("「거절」도 같은 확인을 지나고, 확인 문구가 다시 요청할 수밖에 없다는 사실을 말한다", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findAllByRole("button", { name: "거절" });

    await user.click(screen.getAllByRole("button", { name: "거절" })[0]);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/요청자가 새로 요청해야 합니다/)).toBeInTheDocument();

    await user.click(within(dialog).getAllByRole("button", { name: "거절" })[0]);
    await waitFor(() => expect(decided.length).toBe(1));
    expect(decided[0]).toEqual({ id: "A1", verb: "reject" });
  });
});
