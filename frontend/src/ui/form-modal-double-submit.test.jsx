import React from "react";
import { describe, it, expect, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { FormModal, ToastProvider, ConfirmProvider } from "./kit.jsx";

/* FormModal — Enter 를 두 번 쳐도 저장은 한 번이다 (P4 · 중복 제출).
 *
 * 발의 「저장」 단추는 제출 중에 꺼지지만, Enter 는 그 단추가 아니라 폼 안의 **숨은 제출 단추**를
 * 누른다(단일 입력 칸에서도 Enter 가 제출되도록 둔 `sr-only` 단추). 그 단추는 꺼지지 않으므로
 * 예전에는 Enter 두 번이 `onSubmit` 두 번이었다 — 관리자 화면의 추가 폼에서 같은 행이 둘 생기거나
 * 둘째가 「이미 있습니다」로 실패했다. 모든 관리자 추가 · 수정 폼이 이 부품 하나를 쓴다. */

function wrap(ui) {
  return (
    <ToastProvider>
      <ConfirmProvider>{ui}</ConfirmProvider>
    </ToastProvider>
  );
}

const FIELDS = [{ name: "name", label: "이름", type: "text", required: true }];

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function renderForm(onSubmit) {
  return render(wrap(
    <FormModal open title="부서 추가" fields={FIELDS} initial={{ name: "" }} onSubmit={onSubmit} onClose={vi.fn()} />,
  ));
}

describe("FormModal — 진행 중인 제출은 다시 보내지 않는다", () => {
  it("Enter 를 두 번 치면 onSubmit 은 한 번이다", async () => {
    const gate = deferred();
    const onSubmit = vi.fn(() => gate.promise);
    const user = userEvent.setup();
    renderForm(onSubmit);

    const input = screen.getByLabelText(/이름/);
    await user.type(input, "플랫폼팀");
    await user.keyboard("{Enter}{Enter}");
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith({ name: "플랫폼팀" });
    await act(async () => { gate.resolve(); });
  });

  it("같은 틱에 제출이 두 번 와도 onSubmit 은 한 번이다", async () => {
    const gate = deferred();
    const onSubmit = vi.fn(() => gate.promise);
    renderForm(onSubmit);

    fireEvent.change(screen.getByLabelText(/이름/), { target: { value: "플랫폼팀" } });
    const form = screen.getByLabelText(/이름/).closest("form");
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    expect(onSubmit).toHaveBeenCalledTimes(1);
    await act(async () => { gate.resolve(); });
  });

  it("저장이 끝나면 다시 제출할 수 있다", async () => {
    const onSubmit = vi.fn(async () => {});
    const user = userEvent.setup();
    renderForm(onSubmit);

    const input = screen.getByLabelText(/이름/);
    await user.type(input, "플랫폼팀{Enter}");
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "저장" })).toBeEnabled());
    await user.type(input, "{Enter}");
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
  });

  it("저장이 실패해도 다시 제출할 수 있다 — 실패 문구는 그대로 선다", async () => {
    const onSubmit = vi.fn()
      .mockRejectedValueOnce(Object.assign(new Error("같은 이름의 부서가 이미 있습니다."), { status: 409 }))
      .mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    renderForm(onSubmit);

    const input = screen.getByLabelText(/이름/);
    await user.type(input, "플랫폼팀{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("같은 이름의 부서가 이미 있습니다.");
    await user.type(input, "{Enter}");
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
  });
});
