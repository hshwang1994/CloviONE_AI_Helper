/* 새 문서 폼 → API 페이로드.
 *
 * 서버(app/team_docs/schemas.py::DocumentCreate)가 받는 owner(소유자, 최대 200자)에 예전엔
 * 이 폼에 칸이 없었다 — 문서 상세(TeamDoc.jsx DocMeta)는 owner 값이 있으면 '소유자' 줄을
 * 보여 주는데, 포털에서 만든 문서는 그 값을 채울 방법이 아예 없었다(폼↔API 불일치).
 * 이 테스트는 칸이 있고, 채운 값이 그대로 생성 요청에 실리는지를 확인한다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api.js", () => ({ api: vi.fn() }));
import { api } from "../lib/api.js";
import { ToastProvider } from "../ui/kit.jsx";
import { TeamDocs } from "./TeamDocs.jsx";

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter><TeamDocs /></MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.mockReset();
  api.mockImplementation((path, opts) => {
    if (path.startsWith("/api/team-docs/filters")) {
      return Promise.resolve({ doc_types: ["회의록"], work_fields: ["개발"], tech_tags: [], projects: [] });
    }
    if (path.startsWith("/api/team-docs/projects")) {
      return Promise.resolve({ projects: [] });
    }
    if (path === "/api/team-docs" && opts && opts.method === "POST") {
      return Promise.resolve({ document: { id: "new-doc" } });
    }
    return Promise.resolve({
      items: [], page: 1, page_size: 20, total: 0, sync: { last_success_at: "2026-08-01T00:00:00Z" }, can_sync: true,
    });
  });
});

describe("새 문서 폼", () => {
  it("소유자 칸이 있고, 채운 값이 그대로 생성 요청(POST /api/team-docs)에 실린다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "새 문서" }));

    const dialog = await screen.findByRole("dialog");
    // 필수 칸은 MUI가 라벨에 " *"를 덧붙이므로 정확히 일치하는 문자열 대신 부분 일치로 찾는다.
    await user.type(within(dialog).getByLabelText(/^제목/), "회의록 초안");

    await user.click(within(dialog).getByRole("combobox", { name: /^문서 종류/ }));
    await user.click(await screen.findByRole("option", { name: "회의록" }));

    await user.click(within(dialog).getByRole("combobox", { name: /^업무 분야/ }));
    await user.click(await screen.findByRole("option", { name: "개발" }));

    // 지적 대상: 이 칸이 없으면 아래 getByLabelText가 실패해 여기서 즉시 RED가 된다.
    await user.type(within(dialog).getByLabelText(/^소유자/), "김소유");

    await user.click(within(dialog).getByRole("button", { name: "생성" }));

    const postCall = api.mock.calls.find((c) => c[0] === "/api/team-docs" && c[1] && c[1].method === "POST");
    expect(postCall).toBeTruthy();
    expect(postCall[1].body.owner).toBe("김소유");
    expect(postCall[1].body.title).toBe("회의록 초안");
    expect(postCall[1].body.document_type).toBe("회의록");
    expect(postCall[1].body.work_field).toBe("개발");
  });
});
