import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { Card, Modal } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 카드 규율 (F7 · D-553). 카드는 독립 상태 · 독립 설정 묶음 · 요약 · 꼭 필요한 경계에만 쓰고, **카드 안에 카드를 두지 않는다.**
 * 시각 프로브(`nested_card`)는 `Surface` 가 다는 `data-surface="plate"` 로 DOM 에서 중첩을 센다 — 판 안의 판은 저절로
 * `plate>none`(테두리 · 여백 없음)으로 눕으므로, 프로브가 세는 것은 그 규칙을 비껴간 진짜 겹판이다. */

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("Card surface 표지", () => {
  it("캔버스 위의 카드는 plate 이고, 판 안의 카드는 plate>none 으로 눕는다", () => {
    const { container } = ui(<Card className="outer"><Card className="inner">안</Card></Card>);
    expect(container.querySelector(".outer")).toHaveAttribute("data-surface", "plate");
    expect(container.querySelector(".inner")).toHaveAttribute("data-surface", "plate>none");
    // 프로브가 세는 겹판(plate 안의 plate)은 없다.
    expect(container.querySelectorAll('[data-surface="plate"] [data-surface="plate"]')).toHaveLength(0);
  });

  it("padding 단계는 화면이 sx 로 덮지 않고 속성으로 말한다(normal 20 · compact 10 · none 0)", () => {
    const { container } = ui(
      <>
        <Card className="n">기본</Card>
        <Card className="c" padding="compact">칸반</Card>
        <Card className="z" padding="none">대화</Card>
      </>,
    );
    expect(getComputedStyle(container.querySelector(".n")).paddingTop).toBe("1.25rem");
    expect(getComputedStyle(container.querySelector(".c")).paddingTop).toBe("0.625rem");
    expect(getComputedStyle(container.querySelector(".z")).paddingTop).toMatch(/^0(px|rem)?$/);
  });

  it("모달 안의 카드는 다시 판이다 — 떠 있는 것은 깊이를 0 으로 되돌린다", () => {
    ui(<Card><Modal open title="상세" onClose={() => {}}><Card className="in-modal">몸</Card></Modal></Card>);
    expect(document.querySelector(".in-modal")).toHaveAttribute("data-surface", "plate");
  });
});
