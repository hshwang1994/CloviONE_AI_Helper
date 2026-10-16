/* 프로젝트 상세의 「문서」 탭 (§14.3) — Project → Document 진입.
 *
 * 새 API 를 안 만들고 GET /api/knowledge/documents?project_id= 를 그대로 쓴다(§11.4).
 * 여기서 보는 것은 그 사실 하나다: 화면이 실제로 그 파라미터로 묻고, 빈 목록에서 "이
 * 프로젝트 문서 추가"로 바로 이어지는가(§14.3, 동사는 PA-RC-0002 §3 표준 동사표를 따른다).

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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
      /* qa-contract-change: 분류와 태그가 필수가 됐으므로(문서 개편 3번) 대역이 그 둘의
         후보를 실제로 줘야 한다. 빈 목록을 주면 고를 것이 없어 「만들기」가 영원히
         비활성이고, 그 상태는 「기능이 깨졌다」와 구별되지 않는다. */
      const text = String(path);
      if (text.startsWith("/api/knowledge/categories")) {
        return Promise.resolve({ items: [{ id: "cat-1", name: "회의 기록", document_count: 0 }] });
      }
      if (text.startsWith("/api/knowledge/tags")) {
        return Promise.resolve({ items: [{ id: "tag-1", name: "인프라", document_count: 0 }] });
      }
      return Promise.resolve({ items: [] });
    });
    const user = userEvent.setup();
    renderTab();

    const action = await screen.findByRole("button", { name: "이 프로젝트 문서 추가" });
    await user.click(action);
    const dialog = await screen.findByRole("dialog");
    /* 문서 화면과 **같은 모달**이다(`knowledge/NewDocumentModal.jsx` · lockedProject) —
       프로젝트 칸은 고정 표기이고 제출 단추도 같은 낱말(「만들기」)을 쓴다. */
    await user.type(screen.getByLabelText(/문서 제목/), "킥오프 회의록");
    await user.click(within(dialog).getByLabelText(/^분류/));
    await user.click(await screen.findByRole("option", { name: "회의 기록" }));
    await user.click(within(dialog).getByLabelText(/^태그/));
    await user.click(await screen.findByRole("option", { name: /^인프라/ }));
    await user.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) => p === "/api/knowledge/documents" && o?.method === "POST");
      expect(post, "문서 생성 요청이 안 나갔다").toBeTruthy();
    });
  });

  /* 이 탭은 쪽을 안 넘긴다 — 받은 만큼이 곧 보이는 전부다. 서버가 `total` 을 함께 주는
     이유가 바로 그것이다(app/knowledge/router.py::list_documents 의 docstring). 그 값을
     안 읽으면 상한을 넘긴 문서가 **오류도 빈자리도 없이** 화면에서 사라진다. */
  it("받은 것보다 문서가 더 있으면 그 사실을 말한다", async () => {
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/knowledge/documents?")) {
        return Promise.resolve({
          items: [{ id: "d-1", title: "설계 문서", tags: [], updated_at: "2026-08-20T01:00:00" }],
          total: 137,
        });
      }
      return Promise.resolve({ items: [] });
    });
    renderTab();

    expect(await screen.findByText(/전체 137건 중 1건만 표시합니다/)).toBeInTheDocument();
  });

  it("다 보여 준 때는 건수만 말한다 (없는 잘림을 있다고 하지 않는다)", async () => {
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/knowledge/documents?")) {
        return Promise.resolve({
          items: [{ id: "d-1", title: "설계 문서", tags: [], updated_at: "2026-08-20T01:00:00" }],
          total: 1,
        });
      }
      return Promise.resolve({ items: [] });
    });
    renderTab();

    expect(await screen.findByText("전체 1건")).toBeInTheDocument();
    expect(screen.queryByText(/가운데/)).toBeNull();
  });
});
