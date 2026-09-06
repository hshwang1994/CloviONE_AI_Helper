import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 결재 확인 문구는 **줄바꿈 문자가 아니라 문장**으로 쓴다 (R1-05 · CLAUDE.md §10).
 *
 * 새로 들어온 확인 문구가 `"…확인해 주세요.\n\n" + 요약 + "\n\n계속 승인할까요?"` 였다.
 * 저장소 규칙은 「UI 문구에 `\n`/`<br>`를 넣지 않는다」이고, 그 배치는 확인 대화가 쓰는
 * `whiteSpace: "pre-line"` 한 줄에 기대고 있었다 — 그 CSS 가 바뀌면 문구가 한 줄로 뭉개진다.
 * 게다가 「요청자: 박민준」처럼 이름표와 값을 콜론으로 나열한 조각은 완전한 문장이 아니다.
 *
 * 여기서 못박는 것: 문구에 `\n` 이 없고, 그러면서도 **누구의 무엇을 결재하는지**는 그대로
 * 말한다. 반례는 대상을 실을 수 없는 요청 — 그때도 문장이 문장으로 끝나야 한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../ui/celebrate.js", () => ({ celebrateIfCleared: () => {}, celebrateIfCompleted: () => {} }));

import { MyApprovals } from "./MyApprovals.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function mount(rows) {
  apiMock.mockImplementation((path, opts) => {
    if (opts && opts.method === "POST") return Promise.resolve({ ok: true });
    return Promise.resolve({ items: rows, total: rows.length, page: 1, page_size: 20, can_decide: true });
  });
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

const WITH_TARGET = {
  id: "A1", request_type: "user.role_change", status: "pending",
  object_type: "user", object_id: "u-1", requested_at: "2026-08-24T01:00:00",
  requester_name: "박민준",
  request_payload: { role: "admin", previous_role: "operator", target_name: "김지훈" },
};
// 대상을 실을 수 없는 요청 — payload 에 이름이 없고 object_type 도 비어 있다.
const WITHOUT_TARGET = {
  id: "A2", request_type: "setting.change_config", status: "pending",
  object_type: null, object_id: null, requested_at: "2026-08-24T01:00:00",
  requester_email: "ops@goodmit.co.kr", request_payload: {},
};

async function openConfirm(user, label) {
  const buttons = await screen.findAllByRole("button", { name: label });
  await user.click(buttons[0]);
  return screen.findByRole("dialog");
}

beforeEach(() => { apiMock.mockReset(); });

describe("결재 확인 문구 — 줄바꿈 문자를 쓰지 않는다", () => {
  it("승인 확인 문구에 `\\n` 이 없고, 요청자와 대상을 한 문장으로 말한다", async () => {
    const user = userEvent.setup();
    mount([WITH_TARGET]);
    const dialog = await openConfirm(user, "승인");

    const text = dialog.textContent;
    expect(text).not.toContain("\n");
    expect(text).toContain("박민준님이 올린");
    expect(text).toContain("대상은 김지훈입니다.");
    expect(text).toContain("되돌릴 수 없습니다");
    expect(text).toContain("계속 승인할까요?");
  });

  it("거절 확인 문구도 마찬가지이고, 다시 승인할 수 없다는 사실을 유지한다", async () => {
    const user = userEvent.setup();
    mount([WITH_TARGET]);
    const dialog = await openConfirm(user, "거절");

    const text = dialog.textContent;
    expect(text).not.toContain("\n");
    expect(text).toContain("같은 건을 다시 승인할 방법이 없고 요청자가 새로 요청해야 합니다.");
    expect(text).toContain("계속 거절할까요?");
  });

  it("반례 — 대상을 실을 수 없는 요청도 문장으로 끝난다(조각으로 끊기지 않는다)", async () => {
    const user = userEvent.setup();
    mount([WITHOUT_TARGET]);
    const dialog = await openConfirm(user, "승인");

    const text = dialog.textContent;
    expect(text).not.toContain("\n");
    expect(text).toContain("ops@goodmit.co.kr님이 올린");
    expect(text).toContain("요청입니다.");
    expect(text).not.toContain("대상은");
  });

  it("확인 창은 여전히 결재 앞에 선다 — 「취소」를 누르면 아무 요청도 안 나간다", async () => {
    const user = userEvent.setup();
    mount([WITH_TARGET]);
    const dialog = await openConfirm(user, "승인");

    await user.click(within(dialog).getByRole("button", { name: "취소" }));
    expect(apiMock.mock.calls.some((c) => c[1] && c[1].method === "POST")).toBe(false);
  });
});
