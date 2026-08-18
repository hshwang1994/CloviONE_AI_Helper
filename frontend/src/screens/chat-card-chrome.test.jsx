import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { TicketCard } from "./Chat.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* AI 도우미 결과 카드의 겉모습 계약.
 *
 * 사용자 지적: "AI도우미 디자인이 왼쪽 바에 색상 칠해져 있는 거, 이거 안 쓰기로 했잖아."
 *
 * 기준선(폐기한 목업(지시 64))의 카드는 이렇다:
 *     .kanban-card { background: var(--surface); border: 1px solid var(--border);
 *                    border-radius: 12px; padding: 12px; box-shadow: var(--shadow-sm); }
 * 네 변이 같은 1px 중립 테두리다. 상태를 색으로 말하는 자리는 카드 몸통이 아니라
 * 칩(.chip.ok / .warn / .danger / .info)이다. 기준선 전체를 뒤져도 상태를 뜻하는
 * 왼쪽 색 막대(border-left)는 한 군데도 없다 — .ai-drawer 의 border-left 하나뿐인데
 * 그건 패널의 가장자리이지 상태 표시가 아니다.
 *
 * 그래서 이 파일이 지키는 것은 두 가지다:
 *   1) 카드는 네 변이 같은 중립 테두리다(색 막대 없음).
 *   2) 그래도 상태 정보는 사라지지 않는다 — 배지가 그 일을 한다.
 * 2번이 없으면 "색을 지웠더니 상태를 알 수 없게 됐다"로 고칠 수 있어서, 지적 하나를
 * 다른 지적으로 바꾸는 수정이 통과한다.
 */

// "이슈"는 kit.jsx 의 STATUS_KIND 에서 danger 로 매핑된다 — 톤이 붙는 확실한 값이다.
const TICKET = { title: "러너 상태 수집 타임아웃 분리", status: "이슈", assignee: "홍길동" };

function renderCard(t = TICKET) {
  return render(
    <ThemeModeProvider>
      <TicketCard t={t} isTicket />
    </ThemeModeProvider>
  );
}

function cardOf(titleText) {
  return screen.getByText(titleText, { exact: false }).closest(".MuiPaper-root");
}

describe("결과 카드에는 상태를 뜻하는 왼쪽 색 막대가 없다", () => {
  it("왼쪽 테두리의 굵기가 나머지 세 변과 같다", () => {
    renderCard();
    const style = getComputedStyle(cardOf(TICKET.title));

    expect(
      style.borderLeftWidth,
      `왼쪽만 ${style.borderLeftWidth} 다 (나머지는 ${style.borderTopWidth})`
    ).toBe(style.borderTopWidth);
  });

  it("왼쪽 테두리의 색이 나머지 세 변과 같다", () => {
    renderCard();
    const style = getComputedStyle(cardOf(TICKET.title));

    expect(
      style.borderLeftColor,
      `왼쪽만 ${style.borderLeftColor} 로 칠해져 있다 (나머지는 ${style.borderTopColor})`
    ).toBe(style.borderTopColor);
  });

  it("상태가 없는 카드와 있는 카드의 테두리가 같다", () => {
    // 상태가 카드 몸통의 색을 바꾸면 목록이 알록달록해진다 — 기준선의 카드는 언제나 중립이다.
    const { unmount } = renderCard();
    const withStatus = getComputedStyle(cardOf(TICKET.title)).borderColor;
    unmount();

    renderCard({ title: "상태 없는 항목" });
    const withoutStatus = getComputedStyle(cardOf("상태 없는 항목")).borderColor;

    expect(withStatus).toBe(withoutStatus);
  });

  it("색을 뺐어도 상태는 배지로 그대로 읽힌다", () => {
    renderCard();
    expect(screen.getByText("이슈")).toBeInTheDocument();
  });
});
