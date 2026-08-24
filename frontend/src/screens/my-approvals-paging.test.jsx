/* 결재함이 **20건에서 조용히 잘리지 않는다** (S15 · C7).
 *
 * `/api/approvals/mine` 은 처음부터 20건에서 자르고 `total` 을 함께 줬는데, 화면은 그 둘을
 * 다 무시하고 첫 20건만 그렸다 — 21번째 결재 건은 있다는 사실조차 화면에 없었다.
 * 결재는 **놓치면 남이 대신 못 하는** 일이라 그 침묵이 그대로 지연이 된다.
 *
 * 고른 칸과 쪽은 주소에 둔다. 그래야 「이 건 좀 봐 달라」고 링크를 건넬 수 있고, 상세를
 * 보고 돌아왔을 때 있던 자리가 유지된다(다른 목록 화면과 같은 규칙).
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { MyApprovals } from "./MyApprovals.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

let calls = [];

function page(n, total) {
  const size = Math.min(20, total - (n - 1) * 20);
  return {
    items: Array.from({ length: size }, (_, i) => ({
      id: `a${(n - 1) * 20 + i}`,
      request_type: "user.role_change",
      status: "pending",
      requested_at: "2026-08-01T01:00:00",
      requester_name: `요청자 ${(n - 1) * 20 + i}`,
      summary: `건 ${(n - 1) * 20 + i}`,
    })),
    total, page: n, page_size: 20, can_decide: true,
  };
}

beforeEach(() => {
  calls = [];
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    calls.push(p);
    const q = new URLSearchParams(p.includes("?") ? p.slice(p.indexOf("?") + 1) : "");
    return Promise.resolve(page(Number(q.get("page") || 1), 45));
  });
});

function AddressProbe() {
  const loc = useLocation();
  return <div data-testid="addr">{loc.pathname + loc.search}</div>;
}

function renderApprovals() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/my-approvals"]}>
          <AddressProbe />
          <Routes><Route path="/my-approvals" element={<MyApprovals />} /></Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const addr = () => screen.getByTestId("addr").textContent;

describe("내 결재함 — 쪽 넘기기", () => {
  it("총 건수를 말하고 다음 쪽을 실제로 요청한다", async () => {
    renderApprovals();
    expect(await screen.findByText("요청자 0")).toBeInTheDocument();
    expect(screen.getByText("1 / 3, 총 45건")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(calls.some((u) => u.includes("page=2"))).toBe(true));
    expect(await screen.findByText("요청자 20")).toBeInTheDocument();
    // 쪽은 주소에 남는다 — 링크를 건네면 상대가 같은 자리를 본다.
    expect(addr()).toContain("page=2");
  });

  it("칸을 바꾸면 첫 쪽으로 돌아온다", async () => {
    renderApprovals();
    expect(await screen.findByText("요청자 0")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(calls.some((u) => u.includes("page=2"))).toBe(true));

    await userEvent.click(screen.getByRole("tab", { name: "내가 올린 요청" }));

    await waitFor(() => expect(addr()).toContain("box=requested"));
    expect(addr()).not.toContain("page=2");
    const last = calls[calls.length - 1];
    expect(last).toContain("box=requested");
    expect(last).not.toContain("page=2");
  });
});
