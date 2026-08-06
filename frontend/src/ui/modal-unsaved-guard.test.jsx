/**
 * 저수준 `Modal` 의 미저장 보호 (E11).
 *
 * `FormModal` 은 값 스냅샷으로 더티를 스스로 판정하는데, 저수준 `Modal` 은 내용을 모르므로
 * 아무 보호가 없었다. 그 모달을 쓰는 자리 중 하나가 **퀴즈 방 만들기(최대 20문항)** 다.
 * 다 쓰고 Esc 나 바깥을 한 번 누르면 전부 사라졌고, 되돌릴 방법이 없었다.
 *
 * 두 방향을 다 본다. 확인을 **안 물어보면** 데이터가 사라지고, **늘 물어보면** 아무것도
 * 안 쓴 사람까지 성가시게 해서 결국 사람들이 확인창을 안 읽고 누르게 된다.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmProvider, Modal, ToastProvider } from "./kit.jsx";

function Wrap({ children }) {
  return (
    <ToastProvider>
      <ConfirmProvider>{children}</ConfirmProvider>
    </ToastProvider>
  );
}

function open(props) {
  const onClose = vi.fn();
  render(
    <Wrap>
      <Modal open title="게임방 만들기" onClose={onClose} {...props}>
        <div>내용</div>
      </Modal>
    </Wrap>,
  );
  return onClose;
}

describe("미저장 내용 보호", () => {
  it("아무것도 안 썼으면 그냥 닫힌다", async () => {
    const onClose = open({ dirty: false });
    await userEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("🔴 쓴 내용이 있으면 바로 닫지 않고 먼저 물어본다", async () => {
    const onClose = open({ dirty: true });
    await userEvent.click(screen.getByRole("button", { name: "닫기" }));
    await screen.findByText(/저장되지 않았습니다/);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("확인하면 닫힌다", async () => {
    const onClose = open({ dirty: true });
    await userEvent.click(screen.getByRole("button", { name: "닫기" }));
    const dialog = await screen.findByText(/저장되지 않았습니다/);
    expect(dialog).toBeTruthy();
    const buttons = screen.getAllByRole("button").filter((b) => b.textContent === "닫기");
    // 마지막 '닫기' 가 확인창의 확인 버튼이다(모달 헤더의 것보다 나중에 그려진다).
    await userEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("Esc 로도 그냥 사라지지 않는다", async () => {
    const onClose = open({ dirty: true });
    await userEvent.keyboard("{Escape}");
    await screen.findByText(/저장되지 않았습니다/);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("dirty 를 안 주면 예전과 똑같이 동작한다", async () => {
    // 기존 호출부를 깨지 않는다는 계약. 이게 깨지면 여러 화면이 한꺼번에 성가셔진다.
    const onClose = open({});
    await userEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalled();
  });
});
