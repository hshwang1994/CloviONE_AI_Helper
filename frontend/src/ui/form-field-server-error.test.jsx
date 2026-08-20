import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { FormModal, ToastProvider, ConfirmProvider } from "./kit.jsx";

/* PA-RC-0014 — 서버 422 details[].loc가 실제 폼 필드까지 연결되는가.
 *
 * 예전엔 폼 상단 알림 문구(err) 하나뿐이라 필드가 많은 폼(예: 사용자 생성 8개)에서
 * 어느 칸이 문제인지 표시가 전혀 없었다(aria-invalid 0개, PA-F-054/055). FormModal의
 * catch가 e.body.error.details의 loc 마지막 조각을 필드명과 맞춰 그 칸에 aria-invalid를
 * 걸고, FormField는 도움말 대신 그 오류 문구를 helperText(=aria-describedby 대상)로
 * 보여준다 — 빨간 테두리만으로는 스크린리더가 원인을 못 읽는다.
 */

function wrap(ui) {
  return (
    <ToastProvider>
      <ConfirmProvider>{ui}</ConfirmProvider>
    </ToastProvider>
  );
}

const FIELDS = [
  { name: "name", label: "이름", type: "text", required: true },
  { name: "email", label: "이메일", type: "email", required: true },
];

const MSG = "입력값을 확인해 주세요. 최대 5자까지 입력할 수 있습니다.";

function serverError(message, details) {
  const e = new Error(message);
  e.status = 422;
  e.body = { error: { code: "validation_error", message: "입력값을 확인해 주세요.", details } };
  return e;
}

describe("FormModal — 422 details가 필드에 연결된다", () => {
  it("loc가 가리키는 필드에 aria-invalid + 오류 문구(aria-describedby)가 붙는다", async () => {
    const onSubmit = vi.fn().mockRejectedValue(
      serverError(MSG, [{ loc: ["body", "name"], msg: "최대 5자까지 입력할 수 있습니다." }]),
    );
    const user = userEvent.setup();
    render(wrap(<FormModal open title="시험" fields={FIELDS}
      initial={{ name: "abc", email: "a@b.com" }} onSubmit={onSubmit} onClose={vi.fn()} />));
    await user.click(screen.getByRole("button", { name: /저장/ }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());

    const nameInput = await screen.findByLabelText(/이름/);
    await waitFor(() => expect(nameInput).toHaveAttribute("aria-invalid", "true"));
    const describedBy = nameInput.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const helper = document.getElementById(describedBy);
    expect(helper).toHaveTextContent(MSG);

    // 문제 없는 필드는 건드리지 않는다 — 오검출 방지.
    expect(screen.getByLabelText(/이메일/)).not.toHaveAttribute("aria-invalid", "true");
  });

  it("details가 없으면(또는 필드와 안 맞으면) 상단 알림만 뜨고 필드는 건드리지 않는다", async () => {
    const onSubmit = vi.fn().mockRejectedValue(serverError("서버 오류가 발생했습니다.", null));
    const user = userEvent.setup();
    render(wrap(<FormModal open title="시험" fields={FIELDS}
      initial={{ name: "abc", email: "a@b.com" }} onSubmit={onSubmit} onClose={vi.fn()} />));
    await user.click(screen.getByRole("button", { name: /저장/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("서버 오류가 발생했습니다."));

    expect(screen.getByLabelText(/이름/)).not.toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/이메일/)).not.toHaveAttribute("aria-invalid", "true");
  });
});

/* W5 — **한 오류에 표현 하나** (PLAN C5 «Feedback 위계»).
 *
 * 예전에는 필드 하나가 틀렸을 때 전폭 테두리 상자와 그 칸 아래 인라인 문구가 **같은
 * 문자열로 동시에** 떴다. C5 는 전폭 상자를 「행동이 있는 것」에만 허용하고, 어느 칸을
 * 고치면 되는지는 그 칸 옆에서 말하는 것이 가장 짧은 경로다(이미 그 칸으로 스크롤·포커스한다).
 * 전폭 상자는 **필드를 지목하지 못한 오류**(서버 거절·네트워크)에만 남는다 — 그때는 인라인으로
 * 붙일 자리가 없다. */
describe("한 오류에 표현 하나 (C5)", () => {
  it("🔴 필드를 지목한 오류는 인라인만 쓴다 — 전폭 상자를 함께 띄우지 않는다", async () => {
    const user = userEvent.setup();
    render(wrap(
        <FormModal
          open
          title="사용자 추가"
          fields={[{ name: "email", label: "이메일", type: "text", required: true }]}
          initial={{}}
          onSubmit={async () => {}}
          onClose={() => {}}
        />
    ));
    await user.click(screen.getByRole("button", { name: "저장" }));
    // 인라인은 있다.
    expect(await screen.findByText(/이메일을\(를\) 입력하세요\./)).toBeInTheDocument();
    // 전폭 상자는 없다.
    expect(document.querySelector(".k-form-err")).toBeNull();
  });

  it("필드를 지목하지 못한 오류는 전폭 상자로 남는다 — 붙일 칸이 없다", async () => {
    const user = userEvent.setup();
    render(wrap(
        <FormModal
          open
          title="사용자 추가"
          fields={[{ name: "email", label: "이메일", type: "text" }]}
          initial={{ email: "a@b.c" }}
          onSubmit={async () => { throw new Error("서버가 거절했습니다."); }}
          onClose={() => {}}
        />
    ));
    await user.click(screen.getByRole("button", { name: "저장" }));
    const box = await screen.findByText("서버가 거절했습니다.");
    expect(box.closest(".k-form-err")).not.toBeNull();
  });
});
