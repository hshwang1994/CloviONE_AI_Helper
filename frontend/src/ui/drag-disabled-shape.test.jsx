import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/* 끌어 옮기기 부품의 `disabled` 는 어떤 식을 넘겨도 화면을 죽이지 않는다.
 *
 * 🔴 이 파일이 생긴 이유(2026-09-21): dnd-kit 의 `SortableContext` 는 참/거짓이 아닌 `disabled` 를
 * `{ draggable, droppable }` 객체로 읽는다. 작업 보드가 `moveBusy || (sprint && …)` 를 넘겼고, 회차 없는 판에서
 * 그 값이 `null` 이라 `null.draggable` 을 읽다 렌더 중에 죽었다. 같은 메뉴를 두 번 누른 사용자가 본 「500」
 * 화면이 이것이다(`scripts/ui_qa/reactivate_e2e.py` 가 Chromium · Firefox 둘 다에서 재현).
 *
 * 여기서 못박는 것:
 *   · 판(`DragBoard`)과 목록(`SortableList`)은 `null` · `undefined` · `0` · 빈 글자를 받아도 선다.
 *   · 켬/끔의 뜻은 그대로다 — 참이면 카드가 끌리지 않는다고 말한다(손잡이 커서), 거짓이면 끌린다.
 */

import { DragBoard, DragItem, SortableList } from "./DragDrop.jsx";

const CARDS = [{ id: "c-1", title: "첫 카드" }, { id: "c-2", title: "둘째 카드" }];

function Board({ disabled }) {
  return (
    <DragBoard
      columns={[{ id: "todo", title: "할 일", items: CARDS }]}
      labelOf={(id) => id}
      onMove={() => {}}
      disabled={disabled}
    >
      {(card) => (
        <DragItem key={card.id} id={card.id} label={card.title}>
          {card.title}
        </DragItem>
      )}
    </DragBoard>
  );
}

function List({ disabled }) {
  return (
    <SortableList items={CARDS} labelOf={(id) => id} onReorder={() => {}} disabled={disabled}>
      {(card) => (
        <DragItem key={card.id} id={card.id} label={card.title}>
          {card.title}
        </DragItem>
      )}
    </SortableList>
  );
}

describe("끌어 옮기기 부품의 disabled 모양", () => {
  for (const [name, value] of [["null", null], ["undefined", undefined], ["0", 0], ["빈 글자", ""]]) {
    it(`🔴 판은 disabled=${name} 를 받아도 선다`, () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      expect(() => render(<Board disabled={value} />)).not.toThrow();
      expect(screen.getByText("첫 카드")).toBeInTheDocument();
      spy.mockRestore();
    });

    it(`🔴 목록은 disabled=${name} 를 받아도 선다`, () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      expect(() => render(<List disabled={value} />)).not.toThrow();
      expect(screen.getByText("둘째 카드")).toBeInTheDocument();
      spy.mockRestore();
    });
  }

  it("켬/끔의 뜻은 그대로다 — 막힌 판의 카드는 끌 수 없다고 말하고, 열린 판의 카드는 끌 수 있다", () => {
    /* 카드는 dnd-kit 의 손잡이 속성을 달아 `aria-roledescription="sortable"` 이다(역할은 dnd-kit 이 단추로 덮는다). */
    const cards = () => [...document.querySelectorAll('[aria-roledescription="sortable"]')];
    const { unmount } = render(<Board disabled />);
    expect(cards()).toHaveLength(2);
    for (const item of cards()) expect(item.getAttribute("aria-disabled")).toBe("true");
    unmount();
    render(<Board disabled={false} />);
    expect(cards()).toHaveLength(2);
    for (const item of cards()) expect(item.getAttribute("aria-disabled")).toBe("false");
  });
});
