/* 휴지통 복원·영구삭제가 문서 상세 캐시(["team-doc", notion_page_id])까지 무효화하는가 (FN-14).
 *
 * app/trash/router.py::_item_view 가 notion_page_id 를 안 줘서(2026-08-10 이전) 이 화면은
 * 그 값을 아예 몰랐다 — team-docs 목록의 선택삭제(teamdocs-bulk-trash-invalidation.test.jsx)와
 * 같은 부류의 결함이지만 반대 방향(휴지통→상세)이다. 단일 복원/영구삭제와 선택(bulk) 양쪽을 본다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api.js", () => ({ api: vi.fn() }));
import { api } from "../lib/api.js";
import { Trash } from "./Trash.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const DOC_ROW = {
  id: "trash-1", item_type: "document", type_label: "문서", title: "인프라 운영 계획",
  url: null, notion_page_id: "np-1", deleted_by: "박세찬",
  deleted_at: "2026-08-08T00:00:00Z", purge_after: "2026-08-15T00:00:00Z", can_manage: true,
};

function renderScreen(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><Trash /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.mockReset();
});

describe("휴지통 — 문서 상세 캐시 무효화 (FN-14)", () => {
  it("단일 복원이 그 문서의 team-doc 상세 캐시를 무효화한다", async () => {
    api.mockImplementation((path, opts) => {
      if (path.startsWith("/api/trash?")) return Promise.resolve({ items: [DOC_ROW], retention_days: 7, total: 1 });
      if (path === "/api/trash/trash-1/restore") return Promise.resolve({ ok: true });
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["team-doc", "np-1"], { document: { id: "np-1" } });
    expect(qc.getQueryState(["team-doc", "np-1"]).isInvalidated).toBe(false);

    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");
    fireEvent.click(screen.getByRole("button", { name: "복원" }));

    await waitFor(() => {
      const called = api.mock.calls.some(([p, opts]) => p === "/api/trash/trash-1/restore" && opts && opts.method === "POST");
      expect(called, "복원 호출").toBe(true);
    });
    await waitFor(() => expect(qc.getQueryState(["team-doc", "np-1"]).isInvalidated, "문서 상세 캐시").toBe(true));
  });

  it("단일 영구삭제(확인 포함)도 그 문서의 상세 캐시를 무효화한다", async () => {
    api.mockImplementation((path, opts) => {
      if (path.startsWith("/api/trash?")) return Promise.resolve({ items: [DOC_ROW], retention_days: 7, total: 1 });
      if (path === "/api/trash/trash-1/purge") return Promise.resolve({ ok: true });
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["team-doc", "np-1"], { document: { id: "np-1" } });

    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");
    fireEvent.click(screen.getByRole("button", { name: "영구 삭제" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "영구 삭제" }));

    await waitFor(() => {
      const called = api.mock.calls.some(([p, opts]) => p === "/api/trash/trash-1/purge" && opts && opts.method === "POST");
      expect(called, "영구삭제 호출").toBe(true);
    });
    await waitFor(() => expect(qc.getQueryState(["team-doc", "np-1"]).isInvalidated, "문서 상세 캐시").toBe(true));
  });

  it("선택 복원(bulk)도 복원된 문서들의 상세 캐시를 무효화한다", async () => {
    api.mockImplementation((path, opts) => {
      if (path.startsWith("/api/trash?")) return Promise.resolve({ items: [DOC_ROW], retention_days: 7, total: 1 });
      if (path === "/api/trash/restore-bulk") {
        return Promise.resolve({ restored: [{ id: "trash-1", title: "인프라 운영 계획", item_type: "document", notion_page_id: "np-1" }], failed: [] });
      }
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["team-doc", "np-1"], { document: { id: "np-1" } });

    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");
    fireEvent.click(screen.getByRole("checkbox", { name: "인프라 운영 계획 선택" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택 복원" }));

    await waitFor(() => expect(qc.getQueryState(["team-doc", "np-1"]).isInvalidated, "문서 상세 캐시").toBe(true));
  });
});
