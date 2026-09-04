import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 휴지통에서 온 문서를 이 화면이 **휴지통 문서로** 다룬다.
 *
 * ## 무엇이 뚫려 있었나
 *
 * 서버는 진작부터 `archived`·`archived_at`·`archiver` 를 상세 응답에 실어 보냈는데
 * (`app/knowledge/router.py::_document_json`) 이 화면 파일에는 `archived` 라는 낱말이
 * **한 번도 안 나왔다.** 그래서 휴지통에서 제목을 눌러 온 사람에게 평범한 살아 있는
 * 문서가 열렸다 — 편집기, 저장 단추, 즐겨찾기, 그리고 **이미 들어 있는 휴지통으로**
 * 「휴지통으로 보내기」 메뉴까지.
 *
 * 그 화면에서 오타를 고치고 저장하면 「저장했습니다」가 떴다. 그런데 그 문서는 여전히
 * 목록에 없고, 보관기간이 지나면 판까지 통째로 하드 삭제된다. 사람은 저장됐다고 들었는데
 * 그 글은 곧 사라진다. 서버 쪽 구멍은
 * `tests/integration/test_trashed_document_is_read_only.py` 가 막고, 이 파일은 **화면이
 * 그 사실을 말하는가**를 본다.
 *
 * 반례를 함께 둔다 — 살아 있는 문서에서는 편집기와 저장이 그대로여야 한다.
 */

vi.mock("../ui/BlockEditor.jsx", () => ({
  BlockEditor: ({ value, readOnly }) => (
    <div data-testid="editor" data-readonly={readOnly ? "true" : "false"}>
      {JSON.stringify(value || {})}
    </div>
  ),
  BlockView: () => <div />,
}));

const toasts = [];
vi.mock("../ui/kit.jsx", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, useToast: () => (m) => toasts.push(m), useConfirm: () => async () => true };
});

const responses = new Map();
const calls = [];
vi.mock("../lib/api.js", () => ({
  api: vi.fn(async (path, options) => {
    const key = `${options?.method || "GET"} ${path}`;
    calls.push(key);
    if (!responses.has(key)) throw new Error(`no stub for ${key}`);
    const value = responses.get(key);
    return typeof value === "function" ? value(options) : value;
  }),
}));

const DOC_ID = "doc-1";

function stubDocument({ archived = false } = {}) {
  responses.set(`GET /api/knowledge/documents/${DOC_ID}`, {
    id: DOC_ID,
    title: "주간 회의록",
    version: 3,
    space_id: "space-1",
    space_name: "우리 공간",
    project: null,
    folder_id: null,
    updated_at: "2026-08-20T01:00:00",
    created_at: "2026-08-01T01:00:00",
    author: { user_id: "u-1", display_name: "김동현" },
    archived,
    archived_at: archived ? "2026-08-26T02:00:00" : null,
    archiver: archived ? { user_id: "u-2", display_name: "이성진" } : null,
    current: { version_no: 2, body: { type: "doc", content: [] } },
    tags: [{ id: "tag-1", name: "회의록", slug: "meeting" }],
    category: { id: "cat-1", name: "회의 기록" },
    relations: [],
    backlinks: [],
    attachments: [],
  });
  responses.set("GET /api/knowledge/spaces/space-1/tree", { folders: [] });
  responses.set("GET /api/knowledge/categories", {
    items: [{ id: "cat-1", name: "회의 기록", slug: "회의 기록", sort_order: 1024, document_count: 1 }],
  });
  responses.set(`GET /api/knowledge/documents/${DOC_ID}/comments`, { ok: true, comments: [], people: {} });
  responses.set(`GET /api/knowledge/documents/${DOC_ID}/versions`, {
    current_version_no: 2,
    items: [{ id: "v2", version_no: 2, change_reason: "오타 수정", source: "USER", ai_used: false }],
  });
  responses.set(`POST /api/knowledge/documents/${DOC_ID}/restore`, { id: DOC_ID, archived: false });
}

async function renderDoc() {
  const { KnowledgeDoc } = await import("./KnowledgeDoc.jsx");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/knowledge/${DOC_ID}`]}>
        <Routes><Route path="/knowledge/:id" element={<KnowledgeDoc />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText("주간 회의록");
}

beforeEach(() => {
  responses.clear();
  calls.length = 0;
  toasts.length = 0;
});

describe("휴지통에 있는 문서", () => {
  it("🔴 휴지통에 있다고 말한다 — 누가 언제 버렸는지까지", async () => {
    stubDocument({ archived: true });
    await renderDoc();
    expect(screen.getByText("이 문서는 휴지통에 있습니다")).toBeInTheDocument();
    expect(screen.getByText(/이성진님이 .*에 버렸습니다/)).toBeInTheDocument();
    expect(screen.getByText(/영구 삭제됩니다/)).toBeInTheDocument();
  });

  it("🔴 본문이 읽기 전용이고 저장 단추가 없다 — 여기서 친 글은 아무 데도 안 남는다", async () => {
    stubDocument({ archived: true });
    await renderDoc();
    expect(screen.getByTestId("editor")).toHaveAttribute("data-readonly", "true");
    expect(screen.queryByRole("button", { name: "저장" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "문서 제목" })).toBeNull();
  });

  it("🔴 이미 들어 있는 휴지통으로 「휴지통으로 보내기」를 권하지 않는다", async () => {
    stubDocument({ archived: true });
    await renderDoc();
    expect(screen.queryByRole("button", { name: "문서 작업" })).toBeNull();
    expect(screen.queryByText("휴지통으로 보내기")).toBeNull();
    expect(screen.queryByRole("button", { name: /즐겨찾기/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "이동" })).toBeNull();
  });

  it("🔴 복원이 여기 있다 — 휴지통에서 온 사람에게는 여기 말고 갈 곳이 없다", async () => {
    stubDocument({ archived: true });
    await renderDoc();
    await userEvent.click(screen.getAllByRole("button", { name: "복원" })[0]);
    await waitFor(() =>
      expect(calls).toContain(`POST /api/knowledge/documents/${DOC_ID}/restore`));
  });

  it("이력은 그대로 볼 수 있다 — 무엇을 잃는지가 되살릴지의 근거다", async () => {
    stubDocument({ archived: true });
    await renderDoc();
    expect(screen.getByRole("button", { name: /이력/ })).toBeInTheDocument();
  });

  /* 🔴 곁열도 함께 봐야 한다. 본문만 읽기 전용으로 만들고 곁열을 그대로 두면 **더 나쁜
     상태**가 된다: 분류·태그 고르개는 저장 단추가 없어져서 **아무 데도 안 가고**(오류조차
     안 난다), 첨부·관계·댓글의 쓰기 단추는 서버가 404 로 막으므로 **언제나 실패한다.**
     못 하는 일은 실패하게 두는 것보다 자리를 안 만드는 것이 낫다. */
  it("🔴 분류·태그가 고르개가 아니라 글자다 — 저장할 곳이 없는 고르개는 조용히 죽는다", async () => {
    stubDocument({ archived: true });
    await renderDoc();
    expect(screen.queryByRole("combobox", { name: "분류" })).toBeNull();
    // 분류 값은 맥락 줄이 이미 말한다 — 곁열은 태그만 글자로 남긴다.
    expect(screen.getByText("회의 기록")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "태그" })).toBeInTheDocument();
    expect(screen.getByText("회의록")).toBeInTheDocument();
  });

  it("🔴 첨부·관계·댓글에 쓰는 자리를 안 만든다 — 서버가 어차피 404 로 막는다", async () => {
    stubDocument({ archived: true });
    await renderDoc();
    expect(screen.queryByRole("button", { name: "파일 올리기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "문서 잇기" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "댓글 입력" })).toBeNull();
    expect(screen.queryByRole("button", { name: /댓글 추가/ })).toBeNull();
  });
});

describe("반례 — 살아 있는 문서", () => {
  it("안내판이 없고 편집기와 저장이 그대로다", async () => {
    stubDocument({ archived: false });
    await renderDoc();
    expect(screen.queryByText("이 문서는 휴지통에 있습니다")).toBeNull();
    expect(screen.getByTestId("editor")).toHaveAttribute("data-readonly", "false");
    expect(screen.getByRole("button", { name: "저장" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "이동" })).toBeInTheDocument();
  });

  it("복원 단추는 살아 있는 문서에 없다", async () => {
    stubDocument({ archived: false });
    await renderDoc();
    expect(screen.queryByRole("button", { name: "복원" })).toBeNull();
  });

  it("곁열의 쓰는 자리가 전부 그대로다 — 읽기 전용을 아무 데나 걸면 화면이 죽는다", async () => {
    stubDocument({ archived: false });
    await renderDoc();
    expect(screen.getByRole("combobox", { name: "분류" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "파일 올리기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "문서 잇기" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "댓글 입력" })).toBeInTheDocument();
  });
});
