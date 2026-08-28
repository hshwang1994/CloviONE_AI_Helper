/* 프로젝트 상세의 「문서」 탭 (§14.3) — Project → Document 진입.
 *
 * 새 API 를 안 만들고 GET /api/knowledge/documents?project_id= 를 그대로 쓴다(§11.4).
 * 여기서 보는 것은 그 사실 하나다: 화면이 실제로 그 파라미터로 묻고, 빈 목록에서 "이
 * 프로젝트 문서 추가"로 바로 이어지는가(§14.3, 동사는 PA-RC-0002 §3 표준 동사표를 따른다).
 */
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

const toasts = [];
vi.mock("../ui/kit.jsx", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, useToast: () => (m) => toasts.push(m) };
});

import { ProjectDocuments } from "./ProjectDocuments.jsx";

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ProjectDocuments projectId="proj-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProjectDocuments", () => {
  it("project_id 로 문서를 묻는다", async () => {
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/knowledge/documents?")) {
        expect(path).toContain("project_id=proj-1");
        return Promise.resolve({ items: [{ id: "d-1", title: "설계 문서", tags: [], updated_at: "2026-08-20T01:00:00" }] });
      }
      return Promise.resolve({ items: [] });
    });
    renderTab();
    expect(await screen.findByText("설계 문서")).toBeInTheDocument();
  });

  it("🔴 문서가 없으면 「이 프로젝트 문서 추가」로 바로 만들 수 있다(§14.3)", async () => {
    apiMock.mockImplementation((path, options) => {
      if (options?.method === "POST") {
        expect(options.body.project_id).toBe("proj-1");
        expect(options.body.title).toBe("킥오프 회의록");
        return Promise.resolve({ id: "d-new" });
      }
      return Promise.resolve({ items: [] });
    });
    const user = userEvent.setup();
    renderTab();

    const action = await screen.findByRole("button", { name: "이 프로젝트 문서 추가" });
    await user.click(action);
    const dialog = await screen.findByRole("dialog");
    await user.type(screen.getByLabelText(/문서 제목/), "킥오프 회의록");
    await user.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) => p === "/api/knowledge/documents" && o?.method === "POST");
      expect(post, "문서 생성 요청이 안 나갔다").toBeTruthy();
    });
  });
});
