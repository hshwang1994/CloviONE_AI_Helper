import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

/* 셸의 본문 경계 — 화면이 예외를 던져도 사용자가 할 수 있는 일이 새로고침 하나가 아니다.
 *
 * 예전 폴백은 「500」 팻말 그림과 새로고침 단추뿐이었고, 무엇이 던져졌는지 화면 어디에도 안 남았다.
 * 서버와 무관한 화면 예외가 사용자에게 서버 오류로 보였다(2026-09-21 더블클릭 조사). 지금은
 * 다시 시도(경계를 되감는다) · 새로고침 · 옮겨 적을 기술 정보이고, 화면 파일을 못 받은 것(새 버전
 * 배포)은 새로고침만 준다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: null, isLoading: false }), AuthProvider: ({ children }) => children }));

import { ErrorBoundary } from "./App.jsx";
import { crashDetail, isChunkLoadError } from "./AppShell.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

let shouldThrow = true;
function Flaky() {
  if (shouldThrow) throw new TypeError("Cannot read properties of undefined (reading 'items')");
  return <div>다시 그려졌다</div>;
}

let errorSpy;
beforeEach(() => {
  shouldThrow = true;
  // 경계가 남기는 `[ErrorBoundary]` 줄과 React 의 경고를 시험 출력에서 걷는다(내용은 아래에서 단언한다).
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => { errorSpy.mockRestore(); });

describe("본문 경계", () => {
  it("예외를 남기고, 다시 시도하면 같은 화면을 다시 그린다", async () => {
    const user = userEvent.setup();
    render(<ThemeModeProvider><ErrorBoundary resettable><Flaky /></ErrorBoundary></ThemeModeProvider>);
    expect(screen.getByRole("heading", { name: "화면을 표시하지 못했습니다." })).toBeInTheDocument();
    expect(document.querySelector("[data-error-boundary='render']")).not.toBeNull();
    // 원인은 콘솔과 화면의 기술 정보 둘 다에 남는다 — 사용자가 옮겨 적어 줄 수 있어야 한다.
    expect(errorSpy.mock.calls.some((args) => args[0] === "[ErrorBoundary]")).toBe(true);
    expect(document.querySelector("[data-error-detail]").textContent).toContain("reading 'items'");
    expect(screen.getByRole("button", { name: "새로고침" })).toBeInTheDocument();

    shouldThrow = false;
    await user.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(screen.getByText("다시 그려졌다")).toBeInTheDocument();
  });

  it("되감을 수 없는 바깥 경계는 새로고침만 준다", () => {
    render(<ThemeModeProvider><ErrorBoundary><Flaky /></ErrorBoundary></ThemeModeProvider>);
    // 셸 전체가 죽은 자리라 다시 그릴 것이 없다 — 주 동작 하나가 새로고침이다.
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["새로고침"]);
  });
});

describe("화면 파일을 못 받은 것은 새 버전 배포다", () => {
  it.each([
    "Failed to fetch dynamically imported module: https://x/static/react/assets/WorkBoard.abc.js",
    "error loading dynamically imported module: https://x/static/react/assets/WorkBoard.abc.js",
    "Importing a module script failed.",
    "Unable to preload CSS for /static/react/assets/style.css",
  ])("%s", (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true);
  });

  it("평범한 렌더 예외는 새 버전 배포가 아니다", () => {
    expect(isChunkLoadError(new TypeError("Cannot read properties of undefined"))).toBe(false);
  });

  it("기술 정보는 예외 · 부품 경로 · 주소 · 빌드 · 시각을 한 번에 옮겨 적게 한다", () => {
    const text = crashDetail(new TypeError("boom"), "\n    at Board\n    at WorkBoard\n    at Suspense");
    expect(text).toContain("TypeError: boom");
    expect(text).toContain("부품: at Board < at WorkBoard < at Suspense");
    expect(text).toMatch(/주소: /);
    expect(text).toMatch(/빌드: /);
    expect(text).toMatch(/시각: \d{4}-\d{2}-\d{2}T/);
  });
});
