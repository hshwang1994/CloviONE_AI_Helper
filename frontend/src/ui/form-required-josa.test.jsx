import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { FormModal, ToastProvider, ConfirmProvider } from "./kit.jsx";

/* 필수 칸 오류가 한국어 문장으로 끝난다 — 조사를 칸 이름의 받침으로 고른다.
 *
 * 2026-09-06 배포 환경(clovirassist.gooddi.lab)의 공지 추가 폼에서 실측한 것:
 * 빈 채로 저장하면 「제목을(를) 입력하세요.」가 떴다. 칸 이름은 registry 가 정하는
 * 데이터라 문장을 손으로 적어 둘 수 없고, 그래서 지금까지 두 조사를 나란히 적었다.
 * 그것은 결정을 화면에 미룬 것이고 관리자는 그 괄호를 읽는다.
 *
 * 반례를 같은 폼에서 함께 잰다 — 받침 있는 칸과 없는 칸이 **다른** 조사를 받아야 한다.
 * 하나만 재면 「항상 을」도 통과하고, 그러면 「대상자을 고르세요」가 다시 살아난다.
 * 그리고 옛 문구가 어디에도 안 남는 것을 따로 못박는다.
 */

function wrap(ui) {
  return (
    <ToastProvider>
      <ConfirmProvider>{ui}</ConfirmProvider>
    </ToastProvider>
  );
}

describe("FormModal 필수 칸 — 조사를 받침으로 고른다", () => {
  it("받침이 있는 칸은 '을', 없는 칸은 '를'이다", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(wrap(<FormModal open title="시험"
      fields={[
        { name: "title", label: "제목", type: "text", required: true },
        { name: "owner", label: "대상자", type: "text", required: true },
      ]}
      initial={{ title: "", owner: "" }} onSubmit={onSubmit} onClose={vi.fn()} />));

    await user.click(screen.getByRole("button", { name: /저장/ }));

    await waitFor(() => expect(screen.getByText("제목을 입력하세요.")).toBeInTheDocument());
    expect(screen.queryByText(/제목을\(를\)/)).toBeNull();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("받침 없는 칸만 비면 '를'이 붙는다 — 반례", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(wrap(<FormModal open title="시험"
      fields={[
        { name: "title", label: "제목", type: "text", required: true },
        { name: "owner", label: "대상자", type: "text", required: true },
      ]}
      initial={{ title: "채운 값", owner: "" }} onSubmit={onSubmit} onClose={vi.fn()} />));

    await user.click(screen.getByRole("button", { name: /저장/ }));

    await waitFor(() => expect(screen.getByText("대상자를 입력하세요.")).toBeInTheDocument());
    expect(screen.queryByText("대상자을 입력하세요.")).toBeNull();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
