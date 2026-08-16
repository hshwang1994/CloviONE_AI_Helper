import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAssistantHotkey } from "./AssistantDrawer.jsx";

/* PA-RC-0020: 사이드바 카드·우하단 FAB을 없애면서 그 두 자리를 대신할 전역 단축키
 * (Ctrl/Cmd+/)가 필요했다 — CommandPalette.jsx의 useCommandPaletteHotkey(Ctrl/Cmd+K)와
 * 같은 모양이다. 이 시험은 그 훅 하나만 격리해서 본다(AppShell 전체를 그리면 훅이 실제로
 * 동작하는지와 셸이 그것을 부르는지가 한 시험에 섞인다).
 */

function Probe({ setOpen }) {
  useAssistantHotkey(setOpen);
  return null;
}

function renderProbe() {
  const setOpen = vi.fn();
  render(<Probe setOpen={setOpen} />);
  return setOpen;
}

describe("useAssistantHotkey", () => {
  it("Ctrl+/ 를 누르면 setOpen을 토글 함수로 부른다", async () => {
    const user = userEvent.setup();
    const setOpen = renderProbe();

    await user.keyboard("{Control>}/{/Control}");

    expect(setOpen).toHaveBeenCalledTimes(1);
    // setOpen(v => !v) 형태(함수형 업데이트)로 불렀는지 — 실제로 넘긴 함수를 실행해 확인한다.
    const updater = setOpen.mock.calls[0][0];
    expect(typeof updater).toBe("function");
    expect(updater(false)).toBe(true);
    expect(updater(true)).toBe(false);
  });

  it("/ 단독(모디파이어 없음)으로는 안 열린다 — 입력창에 슬래시를 치는 것과 구별해야 한다", async () => {
    const user = userEvent.setup();
    const setOpen = renderProbe();

    await user.keyboard("/");

    expect(setOpen).not.toHaveBeenCalled();
  });

  it("Ctrl+K(팔레트 단축키)로는 안 열린다 — 서로 다른 단축키다", async () => {
    const user = userEvent.setup();
    const setOpen = renderProbe();

    await user.keyboard("{Control>}k{/Control}");

    expect(setOpen).not.toHaveBeenCalled();
  });
});
