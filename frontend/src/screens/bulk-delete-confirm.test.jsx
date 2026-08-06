/* 일괄 삭제는 **확인을 받는다** (E1).
 *
 * 예전에는 '선택 삭제' 를 누르는 순간 선택 전부가 휴지통으로 갔다. 같은 화면군의
 * `Trash.jsx` 는 확인을 받는데 여기만 규칙이 갈려 있었다.
 * 문서는 특히 **Notion 원본이 보관기간 뒤 삭제되는** 작업인데도 확인이 없었다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { TeamDocs } from "./TeamDocs.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const DOCS = [
  { id: "d1", title: "첫 문서", document_type: "참고자료", work_field: "인프라",
    tech_tags: [], projects: [], author_names: [], last_edited: "2026-08-01T00:00:00Z" },
];

beforeEach(() => {
  window.localStorage.clear();
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (String(path).includes("/filters")) {
      return Promise.resolve({ doc_types: [], work_fields: [], tech_tags: [], projects: [] });
    }
    return Promise.resolve({
      items: DOCS, page: 1, page_size: 20, total: 1,
      sync: { last_success_at: "2026-08-03T00:00:00Z" }, can_sync: true,
    });
  });
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><TeamDocs /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("문서 일괄 삭제", () => {
  it("확인을 받기 전에는 삭제 요청을 보내지 않는다", async () => {
    renderScreen();
    await screen.findByText("첫 문서");

    fireEvent.click(screen.getByRole("checkbox", { name: /첫 문서 선택/ }));
    fireEvent.click(await screen.findByRole("button", { name: "선택 삭제" }));

    // 확인 대화상자가 떠야 하고, 그 사이 삭제 API 는 안 나가야 한다.
    await waitFor(() => expect(screen.getByText(/보관기간이 지나면/)).toBeTruthy());
    expect(apiMock.mock.calls.some(([p]) => String(p).includes("trash-bulk"))).toBe(false);
  });

  it("확인 문구가 **몇 건인지 숫자로** 말한다 — '선택한 항목' 은 개수를 안 알려 준다", async () => {
    renderScreen();
    await screen.findByText("첫 문서");
    fireEvent.click(screen.getByRole("checkbox", { name: /첫 문서 선택/ }));
    fireEvent.click(await screen.findByRole("button", { name: "선택 삭제" }));

    await waitFor(() => expect(screen.getByText(/문서 1건을 휴지통으로/)).toBeTruthy());
    expect(screen.getByRole("button", { name: "1건 삭제" })).toBeTruthy();
  });
});
