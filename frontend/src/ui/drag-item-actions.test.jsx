import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/* 카드 안의 단추는 단추다 (D-483).
 *
 * `DragItem` 은 손잡이 속성을 카드 전체에 붙인다 — 포인터 누름은 끌기의 시작이고 스페이스는
 * 「집기」이며, 카드의 클릭은 미리보기다. 카드 안의 작업 단추(빠른 수정 · 현재 회차에서
 * 빼기)가 그 셋을 카드까지 올려 보내면, 단추를 누르는 손짓이 끌기가 되고 메뉴를 고른
 * 클릭이 미리보기를 연다. `DragItemActions` 가 그 사건을 카드 앞에서 멈춘다. */

import { DragItemActions } from "./DragDrop.jsx";

function Harness({ onCardClick, onCardKey, onCardPointer }) {
  return (
    <div onClick={onCardClick} onKeyDown={onCardKey} onPointerDown={onCardPointer} data-testid="card">
      카드
      <DragItemActions>
        <button type="button">작업</button>
      </DragItemActions>
    </div>
  );
}

describe("DragItemActions", () => {
  it("🔴 단추의 클릭·키·포인터가 카드까지 올라가지 않는다", async () => {
    const onCardClick = vi.fn();
    const onCardKey = vi.fn();
    const onCardPointer = vi.fn();
    render(<Harness onCardClick={onCardClick} onCardKey={onCardKey} onCardPointer={onCardPointer} />);
    const button = screen.getByRole("button", { name: "작업" });
    await userEvent.click(button);
    button.focus();
    await userEvent.keyboard(" ");
    expect(onCardClick).not.toHaveBeenCalled();
    expect(onCardKey).not.toHaveBeenCalled();
    expect(onCardPointer).not.toHaveBeenCalled();
    // 반례 — 카드 자신을 누르면 카드가 받는다.
    await userEvent.click(screen.getByTestId("card"));
    expect(onCardClick).toHaveBeenCalledTimes(1);
  });
});
