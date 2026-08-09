import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { FormModal } from "./kit.jsx";

/* FormModal의 검증 실패 스크롤이 '동작 최소화'를 지킨다.
 *
 * scrollIntoView({ behavior: "smooth" })처럼 JS에서 behavior를 명시하면 theme.js의 전역
 * CSS scroll-behavior 규칙은 이 호출에 닿지 않는다 — CSS 규칙은 behavior를 명시하지 않은
 * 호출에만 적용된다. 그래서 이 화면 코드가 직접 prefersReducedMotion()을 판정해서
 * behavior를 골라야 한다(gameroom.test.jsx의 축포 규약과 같은 이유).
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

describe("검증 실패 스크롤은 동작 최소화 설정을 따른다", () => {
  it("동작 최소화를 켠 사용자에게는 behavior: auto로 스크롤한다", async () => {
    setMatchMedia(true);
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;

    await submitEmptyRequiredField();

    expect(scrollSpy).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
  });

  it("동작 최소화를 끈 사용자에게는 behavior: smooth로 스크롤한다", async () => {
    setMatchMedia(false);
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;

    await submitEmptyRequiredField();

    expect(scrollSpy).toHaveBeenCalledWith(expect.objectContaining({ behavior: "smooth" }));
  });
});
