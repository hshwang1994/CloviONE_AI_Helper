import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { Callout, EmptyState } from "./kit.jsx";
import { KO_WORD_BREAK } from "./theme.js";

/* 한국어 도움말이 **단어 중간에서** 줄바꿈되지 않는다 (사용자 지적 #11).
 *
 * CSS 기본값(`word-break: normal`)은 한글을 음절 단위로 끊어도 된다고 본다. 그래서
 * "도와드/려요" 처럼 단어 중간에서 줄이 바뀐다 — 영문에서는 안 일어나는 일이라 개발 중에는
 * 눈에 잘 안 띄고, 좁은 칸에서만 드러난다.
 *
 * 🔴 이 저장소는 그 증상을 **이미 진단해 놓고**(`Mascot.jsx` 주석) 거기 한 곳에만 고쳤다.
 * 정작 **모든 페이지의 도움말**을 그리는 `Callout` 에는 없었다. 사용자가 "휴지통·미할당 티켓
 * 등 여러 페이지" 라고 말한 것이 그것이다.
 *
 * 그래서 값을 화면마다 적지 않고 토큰(`KO_WORD_BREAK`) 한 곳에서 정하고, 여기서 그 토큰이
 * 실제로 **Callout 에 도달하는지**를 본다 — 토큰만 있고 안 쓰이면 아무 일도 안 일어난다
 * (X4 에서 이미 겪었다: 순수 값 테스트는 배선을 증명하지 않는다).
 */

describe("한국어 줄바꿈", () => {
  it("토큰이 keep-all 이다", () => {
    expect(KO_WORD_BREAK.wordBreak).toBe("keep-all");
    // 긴 URL·UUID 가 상자를 밀어내지 않게 하는 짝이다. 하나만 있으면 다른 쪽이 깨진다.
    expect(KO_WORD_BREAK.overflowWrap).toBe("break-word");
  });

  it("Callout 본문에 실제로 적용된다", () => {
    const { container } = render(<Callout>휴지통에서 항목을 되돌릴 수 있습니다</Callout>);
    const message = container.querySelector(".k-callout");
    expect(message, "Callout 구조가 바뀌었다 — 이 검사가 아무것도 안 보고 있다").toBeTruthy();
    expect(getComputedStyle(message).wordBreak).toBe("keep-all");
  });

  it("긴 영문 토큰이 상자를 밀어내지 않는다", () => {
    /* keep-all 만 걸면 UUID 같은 긴 토큰이 안 끊겨 가로 스크롤이 생긴다.
       그래서 overflowWrap 을 짝으로 둔다 — 둘 중 하나만 두면 다른 문제가 생긴다. */
    const { container } = render(
      <Callout>{"요청 번호 a491cf5f-0000-4000-8000-0000000000ff 를 알려 주세요"}</Callout>,
    );
    const message = container.querySelector(".k-callout");
    expect(getComputedStyle(message).overflowWrap).toBe("break-word");
  });

  /* WF1 R1 — Callout(위)엔 이미 있었는데, 정작 **31개 파일**이 빈 상태 안내문을 그리는 데
   * 쓰는 EmptyState 에는 토큰이 안 걸려 있었다. 등록을 잊은 한 곳이 조용히 재발한 사례라
   * title·help·steps 세 자리를 모두 잠근다(help 만 잠그면 title·steps 는 다음에 또 샌다). */
  it("EmptyState 의 제목·도움말·단계 목록에도 적용된다", () => {
    const { container } = render(
      <EmptyState
        title="등록된 항목이없습니다"
        help="여기에서새 항목을 추가하세요"
        steps={["오른쪽위 버튼을 누르세요", "필요한값을 입력하세요"]}
      />,
    );
    const heading = container.querySelector('[role="heading"]');
    const help = screen.getByText("여기에서새 항목을 추가하세요");
    const steps = container.querySelector("ol");
    expect(getComputedStyle(heading).wordBreak).toBe("keep-all");
    expect(getComputedStyle(help).wordBreak).toBe("keep-all");
    expect(getComputedStyle(steps).wordBreak).toBe("keep-all");
  });
});
