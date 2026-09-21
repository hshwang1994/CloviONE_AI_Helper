import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../lib/api.js", () => ({ api: vi.fn(async () => ({})), setCsrf: () => {} }));

import { KitGallery } from "./KitGallery.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* 부품 갤러리가 **끝까지 그려지는가** (UI 3차 P2 실측).
 *
 * 필터 바 절을 조합 부품으로 바꾸면서 import 에서 뺀 낱개 부품(`FilterConditionLine`)을 다른 절이 계속 쓰고 있었다.
 * 빌드는 초록이었다 — 저장소에 정의되지 않은 이름을 잡는 정적 검사가 없고, 번들러는 JSX 안의 없는 이름을 오류로
 * 보지 않는다. 화면은 브라우저에서 `ReferenceError` 로 오류 경계에 떨어졌고 캡처의 콘솔 검사가 그것을 잡았다.
 * 이 시험은 그 자리를 캡처보다 먼저 막는다: 갤러리 절 전부가 그려지고 오류 경계 문장이 없어야 한다. */

describe("부품 갤러리", () => {
  it("모든 절이 오류 없이 그려진다", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <MemoryRouter><KitGallery /></MemoryRouter>
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>,
    );
    for (const title of ["버튼", "검색과 필터 바", "세그먼티드", "데이터 표", "배지와 태그와 점과 칩", "폼 필드"]) {
      expect(screen.getByRole("heading", { level: 2, name: title })).toBeInTheDocument();
    }
    expect(screen.queryByText("화면을 표시하지 못했습니다")).toBeNull();
    expect(document.querySelector("[data-error-boundary]")).toBeNull();
    // 필터 바 절은 조합 부품 셋이다 — 견본마다 필터 면이 하나다.
    const filterSection = document.getElementById("kit-filter-bar");
    expect(filterSection.querySelectorAll("[data-filter-bar]")).toHaveLength(3);
    expect(filterSection.querySelectorAll("[data-condition-line]")).toHaveLength(1);
    const referenceErrors = errors.mock.calls.filter((args) => String(args[0] && (args[0].stack || args[0])).includes("ReferenceError"));
    expect(referenceErrors).toHaveLength(0);
    errors.mockRestore();
  });
});
