/* 휴지통 복원·영구삭제가 **문서 화면의 캐시**까지 무효화하는가 (FN-14 · D-313).
 *
 * qa-contract-change: 문서 축이 S14 에서 정본으로 옮겨 가며 화면의 질의 키가 team-doc 에서 knowledge 로 바뀌었는데 이 시험은 옛 키를 스스로 심고 그 키가 무효화되는지 물었다 — 제품이 실제 문서 캐시를 하나도 안 지우는 동안에도 초록이었다. 이제 화면이 실제로 쓰는 키를 심고 묻는다.
 * qa-contract-replaced-by: frontend/src/screens/teamdocs-bulk-trash-invalidation.test.jsx
 *
 * 왜 이것이 계약인가: `main.jsx` 가 `staleTime:30s` + `refetchOnWindowFocus:false` 다.
 * 무효화가 안 걸리면 복원한 문서는 그 시간 동안 `/knowledge` 목록에 안 나타나고, 영구
 * 삭제한 문서의 상세는 그동안 멀쩡히 열린다. 둘 다 사용자에게는 「내가 누른 것이 안 먹혔다」다.
 * 어느 키가 문서를 그리는지는 `document-views.js` 한 곳이 안다.
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

const DOC_ID = "np-1";
const DOC_ROW = {
  id: "trash-1", item_type: "document", type_label: "문서", title: "인프라 운영 계획",
  url: null, notion_page_id: DOC_ID, deleted_by: "박세찬",
  deleted_at: "2026-08-08T00:00:00Z", purge_after: "2026-08-15T00:00:00Z", can_manage: true,
};

/* 화면이 실제로 쓰는 두 키. `Knowledge.jsx::useDocuments` 와 `KnowledgeDoc.jsx` 를 따른다 —
 * 목록 키에는 조건이 뒤에 붙으므로 여기서도 조건까지 붙여 심는다(접두사 일치를 시험한다). */
const DOC_DETAIL_KEY = ["knowledge", "document", DOC_ID];
const DOC_LIST_KEY = ["knowledge", "documents", "sp-1", null, "", false, "", 1];

function seedDocumentCaches(qc) {
  qc.setQueryData(DOC_DETAIL_KEY, { document: { id: DOC_ID } });
  qc.setQueryData(DOC_LIST_KEY, { items: [], total: 0 });
  expect(qc.getQueryState(DOC_DETAIL_KEY).isInvalidated).toBe(false);
  expect(qc.getQueryState(DOC_LIST_KEY).isInvalidated).toBe(false);
}

async function expectDocumentCachesInvalidated(qc) {
  await waitFor(() => expect(qc.getQueryState(DOC_DETAIL_KEY).isInvalidated, "문서 상세 캐시").toBe(true));
  await waitFor(() => expect(qc.getQueryState(DOC_LIST_KEY).isInvalidated, "문서 목록 캐시").toBe(true));
}

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

describe("휴지통 — 문서 화면 캐시 무효화 (FN-14 · D-313)", () => {
  it("단일 복원이 그 문서의 상세와 목록 캐시를 무효화한다", async () => {
    api.mockImplementation((path) => {
      if (path.startsWith("/api/trash?")) return Promise.resolve({ items: [DOC_ROW], retention_days: 7, total: 1 });
      if (path === "/api/trash/trash-1/restore") return Promise.resolve({ ok: true });
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedDocumentCaches(qc);

    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");
    fireEvent.click(screen.getByRole("button", { name: "복원" }));

    await waitFor(() => {
      const called = api.mock.calls.some(([p, opts]) => p === "/api/trash/trash-1/restore" && opts && opts.method === "POST");
      expect(called, "복원 호출").toBe(true);
    });
    await expectDocumentCachesInvalidated(qc);
  });

  it("단일 영구삭제(확인 포함)도 상세와 목록 캐시를 무효화한다", async () => {
    api.mockImplementation((path) => {
      if (path.startsWith("/api/trash?")) return Promise.resolve({ items: [DOC_ROW], retention_days: 7, total: 1 });
      if (path === "/api/trash/trash-1/purge") return Promise.resolve({ ok: true });
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedDocumentCaches(qc);

    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");
    fireEvent.click(screen.getByRole("button", { name: "영구 삭제" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "영구 삭제" }));

    await waitFor(() => {
      const called = api.mock.calls.some(([p, opts]) => p === "/api/trash/trash-1/purge" && opts && opts.method === "POST");
      expect(called, "영구삭제 호출").toBe(true);
    });
    await expectDocumentCachesInvalidated(qc);
  });

  it("선택 복원(bulk)도 복원된 문서의 상세와 목록 캐시를 무효화한다", async () => {
    api.mockImplementation((path) => {
      if (path.startsWith("/api/trash?")) return Promise.resolve({ items: [DOC_ROW], retention_days: 7, total: 1 });
      if (path === "/api/trash/restore-bulk") {
        return Promise.resolve({ restored: [{ id: "trash-1", title: "인프라 운영 계획", item_type: "document", notion_page_id: DOC_ID }], failed: [] });
      }
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedDocumentCaches(qc);

    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");
    fireEvent.click(screen.getByRole("checkbox", { name: "인프라 운영 계획 선택" }));
    fireEvent.click(await screen.findByRole("button", { name: "선택 복원" }));

    await expectDocumentCachesInvalidated(qc);
  });
});
