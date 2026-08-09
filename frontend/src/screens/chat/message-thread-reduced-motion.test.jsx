import React from "react";
import { describe, it, expect, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { TypingBubble } from "./MessageThread.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* '작동 중' 표시(TypingBubble)의 접근성 계약.
 *
 * screens.css에는 한때 .chat-thinking에 걸린 reduced-motion 예외("동작 줄이기에서도
 * 작동 중 표시는 멈추지 않는다")가 있었다 - 하지만 .chat-thinking은 어떤 JSX에서도
 * 쓰이지 않는 죽은 선택자였고(실제로 쓰는 이 컴포넌트는 인라인 sx로 chat-bounce
 * 애니메이션을 직접 건다), 설령 썼더라도 theme.js의 MuiCssBaseline이 전역
 * `*, *::before, *::after`에 `animation-duration: 0.01ms !important` 를 걸어 두어
 * 그 예외는 애초에 이길 수 없는 규칙이었다(감사에서 확인, 죽은 CSS로 제거).
 *
 * 진짜 접근성 요구는 CSS 애니메이션이 도는지가 아니라 - '작동 중'이라는 사실이
 * 스크린리더에 텍스트로 전달되는지다. 점 세 개(시각 연출)는 aria-hidden으로 숨기고,
 * 별도 sr-only 텍스트 노드로 같은 사실을 전한다 - CSS 상태(reduced-motion 매치 여부)와
 * 무관하게 항상 DOM에 있어야 한다. */

function setMatchMedia(reduce) {
  window.matchMedia = (query) => ({
    matches: /prefers-reduced-motion/.test(query) ? reduce : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

function renderBubble() {
  return render(
    <ThemeModeProvider>
      <TypingBubble />
    </ThemeModeProvider>
  );
}

afterEach(() => {
  delete window.matchMedia;
});

describe("TypingBubble - 동작 줄이기와 무관한 '작동 중' 안내", () => {
  it("OS가 동작 줄이기를 켠 상태에서도 sr-only 안내 텍스트가 그대로 있다", () => {
    setMatchMedia(true);
    renderBubble();

    const notice = screen.getByText("도우미: 답변을 작성하고 있습니다.");
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveClass("sr-only");
  });

  it("동작 줄이기를 끈 기본 상태에서도 같은 sr-only 안내 텍스트가 있다", () => {
    setMatchMedia(false);
    renderBubble();

    const notice = screen.getByText("도우미: 답변을 작성하고 있습니다.");
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveClass("sr-only");
  });

  it("점 세 개 연출은 장식(aria-hidden)이고, 삭제된 .chat-thinking 클래스에 기대지 않는다", () => {
    setMatchMedia(false);
    const { container } = renderBubble();

    const decorative = container.querySelector('[aria-hidden="true"]');
    expect(decorative).toBeInTheDocument();
    expect(decorative.className).not.toMatch(/chat-thinking/);
  });
});
