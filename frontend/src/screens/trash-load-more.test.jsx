import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* UA-10 확증 — /api/trash에 상한도 total도 없어 "더 보기" 자체가 불가능했다(?limit=1을 줘도
 * 조용히 무시됐다). AI-18(대화 목록)과 같은 모양의 결함을 같은 관용(더 보기 → limit을 늘려
 * 처음부터 다시 받는다, keepPreviousData로 깜빡임 방지)으로 고쳤다 — 그 배선만 화면 통째로 본다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Trash } from "./Trash.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderTrash() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Trash />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

function item(id) {
  return {
    id, item_type: "document", type_label: "문서", title: "문서 " + id,
    deleted_by: "김운영", deleted_at: "2026-08-01T01:00:00", purge_after: "2026-08-08T01:00:00",
    can_manage: true, url: null,
  };
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("휴지통 '더 보기' (UA-10 확증)", () => {
  it("total이 받은 개수와 같으면(상한 이하 — 절대다수) 버튼이 없다", async () => {
    apiMock.mockImplementation((url, opts) => {
      if (url.startsWith("/api/trash?") && !opts) {
        return Promise.resolve({ items: [item("t1")], retention_days: 7, total: 1 });
      }
      return Promise.resolve({ ok: true });
    });
    renderTrash();
    await screen.findByText("문서 t1");
    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
  });

  it("total이 받은 개수보다 크면 버튼이 보이고, 누르면 늘어난 limit으로 다시 받는다", async () => {
    const calls = [];
    apiMock.mockImplementation((url, opts) => {
      if (url.startsWith("/api/trash?") && !opts) {
        calls.push(url);
        return Promise.resolve({ items: [item("t1")], retention_days: 7, total: 150 });
      }
      return Promise.resolve({ ok: true });
    });
    const user = userEvent.setup();
    renderTrash();
    await screen.findByText("문서 t1");

    const btn = screen.getByRole("button", { name: "휴지통 더 보기" });
    await user.click(btn);

    await waitFor(() => {
      expect(calls.some((u) => u.includes("limit=200"))).toBe(true);
    });
  });

  it("다음 페이지를 받는 동안(isFetching) 버튼이 비활성화되고 문구가 바뀐다", async () => {
    let resolveSecond;
    let callCount = 0;
    apiMock.mockImplementation((url, opts) => {
      if (url.startsWith("/api/trash?") && !opts) {
        callCount += 1;
        if (callCount === 1) {
          return Promise.resolve({ items: [item("t1")], retention_days: 7, total: 150 });
        }
        return new Promise((resolve) => { resolveSecond = resolve; });
      }
      return Promise.resolve({ ok: true });
    });
    const user = userEvent.setup();
    renderTrash();
    await screen.findByText("문서 t1");

    await user.click(screen.getByRole("button", { name: "휴지통 더 보기" }));

    const btn = await screen.findByRole("button", { name: "불러오는 중…" });
    expect(btn).toBeDisabled();
    // keepPreviousData 덕분에 이전 페이지가 사라지지 않고 그대로 남아 있어야 한다(스켈레톤 금지).
    expect(screen.getByText("문서 t1")).toBeInTheDocument();

    resolveSecond({ items: [item("t1"), item("t2")], retention_days: 7, total: 150 });
    await screen.findByText("문서 t2");
  });
});
