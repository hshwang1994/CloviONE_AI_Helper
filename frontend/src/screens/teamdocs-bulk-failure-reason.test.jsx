/* UA-25 — TeamDocs의 선택 삭제(trash-bulk) 실패 토스트도 Trash.jsx와 같은 뿌리로 항상
 * "권한이 없어 건너뛰었습니다"였다. `team_docs/service.py::trash_documents_bulk`는 이미
 * 건별 실제 사유(failed[].error)를 돌려주므로, 화면이 그 값을 그대로 보여주는지 확인한다.
 * 렌더 하네스는 teamdocs-bulk-trash-invalidation.test.jsx와 같다. */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

vi.mock("../lib/api.js", () => ({ api: vi.fn() }));
import { api } from "../lib/api.js";
import { TeamDocs } from "./TeamDocs.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const DOCS = [
  { id: "d1", title: "인프라 운영 계획", document_type: "작업 계획서", work_field: "인프라",
    tech_tags: ["Ansible"], projects: [], author_names: ["박세찬"], last_edited: "2026-08-01T00:00:00Z",
    is_favorite: false },
];

function renderScreen(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><TeamDocs /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  api.mockReset();
  api.mockImplementation((path, opts) => {
    if (path.startsWith("/api/team-docs/filters")) {
      return Promise.resolve({ doc_types: [], work_fields: [], tech_tags: [], projects: [] });
    }
    if (path === "/api/team-docs/trash-bulk") {
      return Promise.resolve({
        trashed: [],
        failed: [{ id: "d1", error: "이 문서를 삭제할 권한이 없습니다." }],
      });
    }
    return Promise.resolve({
      items: DOCS, page: 1, page_size: 20, total: 1,
      sync: { last_success_at: "2026-08-03T00:00:00Z" }, can_sync: true,
    });
  });
});

describe("문서 선택 삭제 실패 사유 (UA-25)", () => {
  it("실패 사유를 그대로 보여준다(하드코딩된 '권한이 없어' 문구가 아니라 응답의 error)", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");

    fireEvent.click(screen.getByRole("checkbox", { name: "인프라 운영 계획 선택" }));
    fireEvent.click(await screen.findByRole("button", { name: /선택 삭제/ }));

    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "1건 삭제" }));

    await screen.findByText(/이 문서를 삭제할 권한이 없습니다/);
  });
});
