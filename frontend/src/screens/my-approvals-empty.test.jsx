import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 승인 화면의 0건 · 권한 없음은 목록 판 안(표 머리 아래 띠)에 선다 (D-588, r23 화면 대장 06).
 *
 * 예전에는 판 없이 화면 가운데 큰 클로비와 두 줄만 남아, 세 칸(처리할 · 올린 · 처리한)을 오갈 때마다 화면 모양이 바뀌었다.
 * 이제 0건은 다건과 같은 셸이고, 권한 없음은 그 셸 안에서 다른 아이콘(자물쇠)으로 말한다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { MyApprovals } from "./MyApprovals.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderApprovals() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/my-approvals"]}><MyApprovals /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("승인 — 0건과 권한 없음은 목록 판 안이다", () => {
  it("처리할 승인 요청 0건은 표 머리 아래 띠에 선다 — 화면 전체 그림이 아니다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, can_decide: true });
    const { container } = renderApprovals();
    const title = await screen.findByText("처리할 승인 요청이 없습니다.");
    expect(title.closest("[data-empty-layout='band']")).not.toBeNull();
    expect(screen.getAllByRole("columnheader").length).toBeGreaterThan(0);
    expect(container.querySelector("[data-empty-layout='page']")).toBeNull();
  });

  it("처리 권한이 없으면 같은 셸 안에서 권한 없음을 말한다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, can_decide: false });
    const { container } = renderApprovals();
    const title = await screen.findByText("승인 요청을 처리할 권한이 없습니다.");
    expect(title.closest("[data-empty-layout='band']")).not.toBeNull();
    expect(container.querySelector("[data-empty-layout='page']")).toBeNull();
  });
});
