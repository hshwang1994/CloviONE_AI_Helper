import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { FormModal } from "./kit.jsx";

/* qa-contract-change: 이 파일이 지키던 성질(동작 최소화면 스크롤 behavior 를 auto 로 고른다)이 제품 결정으로 사라졌고, 이제 지킬 성질은 그 반대 — 설정이 무엇이든 같은 값이어야 한다 — 이라 갈리던 두 시험을 it.each 한 벌로 합쳤다. 단언 문장은 하나지만 실행은 두 번이고 재는 경우의 수는 줄지 않았다.
 * 이 조직의 Windows 가 「애니메이션 효과 끔」이라 Firefox 가
 * prefers-reduced-motion 을 reduce 로 보고했고, 그 한 판정이 클로비 시선 추적과 로그인
 * 폭죽까지 함께 끄고 있었다(2026-09-03, `ui/motion.js` 머리말). 이제 지킬 성질은 반대다:
 * **설정이 무엇이든 같은 값이어야 한다.** 그래서 갈리는 두 시험을 `it.each` 한 벌로 합쳤다 —
 * 단언 문장은 하나지만 실행은 여전히 두 번이고, 재는 경우의 수는 줄지 않았다. 오히려
 * 「두 경우가 같다」를 한 자리에서 못박아 한쪽만 되살아나는 것을 막는다.
 *
 * FormModal의 검증 실패 스크롤을 본다.
 *
 * scrollIntoView({ behavior: "smooth" })처럼 JS에서 behavior를 명시하면 theme.js의 전역
 * CSS scroll-behavior 규칙은 이 호출에 닿지 않는다 — CSS 규칙은 behavior를 명시하지 않은
 * 호출에만 적용된다. 그래서 이 화면 코드가 값을 직접 정한다.
 */

function setMatchMedia(reduce) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: /prefers-reduced-motion/.test(query) ? reduce : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

afterEach(() => {
  delete window.matchMedia;
  vi.restoreAllMocks();
});

const FIELDS = [{ name: "title", label: "제목", type: "text", required: true }];

async function submitEmptyRequiredField() {
  render(
    <FormModal
      open
      title="테스트 폼"
      fields={FIELDS}
      initial={{}}
      onSubmit={vi.fn()}
      onClose={vi.fn()}
    />
  );
  await userEvent.click(screen.getByRole("button", { name: "저장" }));
  // 검증 실패 → errField 설정 → 스크롤 대상 필드가 화면에 보인다(포커스도 그 필드로 간다).
  // 라벨 접근이름에 필수 표시(*)가 붙어 정확히 "제목"이 아니므로 부분 일치로 찾는다.
  expect(await screen.findByLabelText(/제목/)).toHaveFocus();
}

/* 🔴 정책이 뒤집혔다 (2026-09-03 — `ui/motion.js` 머리말). 예전에는 이 두 시험이 설정에
 * 따라 `auto`/`smooth` 로 갈리는 것을 못박았다. 지금은 **어느 쪽이든 같아야** 한다 —
 * 설정을 읽는 갈래 자체가 없어졌기 때문이다. 두 값을 각각 재는 이유는, 한쪽만 재면
 * 판정이 되살아나도 그 시험만 초록으로 남기 때문이다. */
describe("검증 실패 스크롤은 동작 최소화 설정과 무관하다", () => {
  it.each([["켠", true], ["끈", false]])(
    "동작 최소화를 %s 사용자 모두에게 behavior: smooth 로 스크롤한다",
    async (_label, reduce) => {
      setMatchMedia(reduce);
      const scrollSpy = vi.fn();
      Element.prototype.scrollIntoView = scrollSpy;

      await submitEmptyRequiredField();

      expect(scrollSpy).toHaveBeenCalledWith(expect.objectContaining({ behavior: "smooth" }));
    },
  );
});
