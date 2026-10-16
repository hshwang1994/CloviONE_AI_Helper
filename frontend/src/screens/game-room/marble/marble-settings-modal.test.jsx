import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { MarbleSettingsModal } from "./MarbleSettingsModal.jsx";
import { ConfirmProvider, ToastProvider } from "../../../ui/kit.jsx";
import { ThemeModeProvider } from "../../../ui/ThemeModeProvider.jsx";

/* 경주 설정 창은 바뀐 쪽만 보낸다 (r23 D-593).
 *
 * 예전에는 저장할 때마다 참가자를 먼저 보냈다. 방 구성원을 참가자로 쓰는 방(참가자 목록이 빈 방)은 그 요청이 2명 미만이라며 막혀
 * 뒤의 설정 요청이 돌지 않았고, 그래서 맵을 바꿀 수 없었다. 이제 참가자 칸이 그대로면 참가자 요청을 보내지 않는다. */

function mutations() {
  return {
    marbleParticipants: { mutateAsync: vi.fn(() => Promise.resolve({})), isPending: false },
    marbleConfig: { mutateAsync: vi.fn(() => Promise.resolve({})), isPending: false },
  };
}

function renderModal(config, m) {
  const onClose = vi.fn();
  render(
    <ThemeModeProvider><ToastProvider><ConfirmProvider>
      <MarbleSettingsModal open onClose={onClose} config={config} members={[{ user_id: "u1", name: "가", role: "host" }, { user_id: "u2", name: "나", role: "player" }]} mutations={m} />
    </ConfirmProvider></ToastProvider></ThemeModeProvider>,
  );
  return onClose;
}

async function pickMap(user, label) {
  await user.click(screen.getByRole("combobox", { name: "맵 선택" }));
  await user.click(await screen.findByRole("option", { name: label }));
}

describe("경주 설정 — 바뀐 쪽만 보낸다 (D-593)", () => {
  it("🔴 구성원을 참가자로 쓰는 방에서 맵만 바꾸면 설정 요청 하나만 간다", async () => {
    const m = mutations();
    const user = userEvent.setup();
    const onClose = renderModal({ participants: [], winners: 1, pick_last: false, speed: 1, map: "wheel" }, m);
    await pickMap(user, "탐욕의 항아리");
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(m.marbleParticipants.mutateAsync).not.toHaveBeenCalled();
    expect(m.marbleConfig.mutateAsync).toHaveBeenCalledWith({ winners: 1, pick_last: false, speed: 1, map: "pot" });
    expect(onClose).toHaveBeenCalled();
  });

  it("참가자 칸만 고치면 참가자 요청만 간다", async () => {
    const m = mutations();
    const user = userEvent.setup();
    renderModal({ participants: [], winners: 1, pick_last: false, speed: 1, map: "wheel" }, m);
    await user.type(screen.getByRole("textbox", { name: "참가자" }), "하나{enter}둘");
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(m.marbleParticipants.mutateAsync).toHaveBeenCalledWith({ participants: [{ name: "하나" }, { name: "둘" }] });
    expect(m.marbleConfig.mutateAsync).not.toHaveBeenCalled();
  });

  it("둘 다 바꾸면 참가자 다음 설정 순서로 둘 다 간다", async () => {
    const m = mutations();
    const user = userEvent.setup();
    renderModal({ participants: [], winners: 1, pick_last: false, speed: 1, map: "wheel" }, m);
    await user.type(screen.getByRole("textbox", { name: "참가자" }), "하나{enter}둘");
    await pickMap(user, "밤을 달리다");
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(m.marbleParticipants.mutateAsync).toHaveBeenCalledTimes(1);
    expect(m.marbleConfig.mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ map: "yoru" }));
    expect(m.marbleParticipants.mutateAsync.mock.invocationCallOrder[0]).toBeLessThan(m.marbleConfig.mutateAsync.mock.invocationCallOrder[0]);
  });
});
