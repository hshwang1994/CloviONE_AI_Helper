import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/* 문서 화면이 **판·차이·되돌리기를 사람에게 정확히 말하는가** (S7 Exit).
 *
 * 서버 쪽 동작은 `tests/integration/test_knowledge_versions.py` 가 실제 요청으로 본다.
 * 여기서 보는 것은 화면이 그 답을 어떻게 옮기는가다 — 특히 **구별해서 말하는지**:
 *
 *   * 「저장했습니다」와 「저장했고 이력에 남겼습니다」는 다른 일이다.
 *   * 되돌리기는 **지우는 것이 아니라 쌓는 것**이고, 확인 문구가 그렇게 말해야 한다.
 *   * 차이는 문단 단위이고, 화면도 문단 단위로 보여야 한다.
 *
 * 편집기(TipTap)는 여기서 안 띄운다 — `React.lazy` 라 jsdom 에서 뜨는 데 시간이 걸리고,
 * 그것을 확인하는 것은 `block-editor-lazy.test.jsx` 의 일이다.
 */

vi.mock("../ui/BlockEditor.jsx", () => ({
  BlockEditor: ({ value }) => (
    <div data-testid="editor">{JSON.stringify(value || {})}</div>
  ),
  BlockView: () => <div />,
}));

const toasts = [];
vi.mock("../ui/kit.jsx", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    useToast: () => ({ show: (m) => toasts.push(m) }),
    useConfirm: () => async () => true,
  };
});

const responses = new Map();
vi.mock("../lib/api.js", () => ({
  api: vi.fn(async (path, options) => {
    const key = `${options?.method || "GET"} ${path}`;
    if (!responses.has(key)) throw new Error(`no stub for ${key}`);
    const value = responses.get(key);
    return typeof value === "function" ? value(options) : value;
  }),
}));

const DOC_ID = "doc-1";

function stubDocument({ version = 3 } = {}) {
  responses.set(`GET /api/knowledge/documents/${DOC_ID}`, {
    id: DOC_ID,
    title: "주간 회의록",
    version,
    current: { version_no: 2, body: { type: "doc", content: [] } },
    tags: [],
    relations: [],
    backlinks: [],
  });
  responses.set(`GET /api/knowledge/documents/${DOC_ID}/versions`, {
    current_version_no: 2,
    items: [
      { id: "v2", version_no: 2, change_reason: "오타 수정", source: "USER", ai_used: false },
      { id: "v1", version_no: 1, change_reason: "문서를 만들었습니다.", source: "USER", ai_used: false },
    ],
  });
}

async function renderDoc() {
  const { KnowledgeDoc } = await import("./KnowledgeDoc.jsx");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/knowledge/${DOC_ID}`]}>
        <Routes>
          <Route path="/knowledge/:id" element={<KnowledgeDoc />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText("주간 회의록");
}

beforeEach(() => {
  responses.clear();
  toasts.length = 0;
  stubDocument();
});

describe("문서 저장", () => {
  it("새 판이 쌓였을 때와 안 쌓였을 때를 **다르게** 말한다", async () => {
    responses.set(`PUT /api/knowledge/documents/${DOC_ID}`, { created_version: true, version: 4 });
    await renderDoc();

    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(toasts).toContain("저장했고 새 판을 이력에 남겼습니다."));

    toasts.length = 0;
    responses.set(`PUT /api/knowledge/documents/${DOC_ID}`, { created_version: false, version: 4 });
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() =>
      expect(toasts).toContain("저장했습니다. 본문이 그대로라 새 판은 만들지 않았습니다."));
  });

  it("저장 요청에 잠금 값을 함께 보낸다", async () => {
    const seen = [];
    responses.set(`PUT /api/knowledge/documents/${DOC_ID}`, (options) => {
      seen.push(options.body);
      return { created_version: true, version: 4 };
    });
    await renderDoc();
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].base_version).toBe(3);
  });
});

describe("판 이력", () => {
  it("지금 보는 판을 표시하고 그 판의 되돌리기는 막는다", async () => {
    await renderDoc();
    await userEvent.click(screen.getByRole("tab", { name: /이력/ }));

    expect(await screen.findByText("2판")).toBeInTheDocument();
    expect(screen.getByText("지금 보는 판")).toBeInTheDocument();

    const buttons = screen.getAllByRole("button", { name: "되돌리기" });
    // 두 판 중 지금 판(2판)의 버튼만 꺼져 있어야 한다 — 둘 다 꺼져 있으면 되돌릴 수 없고,
    // 둘 다 켜져 있으면 「이미 그 판」을 눌러 409 를 받는다.
    expect(buttons.filter((b) => b.disabled)).toHaveLength(1);
  });

  it("되돌리기가 잠금 값을 함께 보낸다", async () => {
    const seen = [];
    responses.set(`POST /api/knowledge/documents/${DOC_ID}/versions/1/restore`, (options) => {
      seen.push(options.body);
      return { id: DOC_ID, version: 4, current: { version_no: 3 } };
    });
    await renderDoc();
    await userEvent.click(screen.getByRole("tab", { name: /이력/ }));

    const buttons = await screen.findAllByRole("button", { name: "되돌리기" });
    await userEvent.click(buttons.find((b) => !b.disabled));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].base_version).toBe(3);
    expect(toasts.join(" ")).toContain("이력은 그대로 남아 있습니다");
  });
});

describe("판 사이의 차이", () => {
  it("바뀐 문단만 그 종류와 함께 보여 준다", async () => {
    responses.set(`GET /api/knowledge/documents/${DOC_ID}/diff?base=1&target=2`, {
      base: { version_no: 1 },
      target: { version_no: 2 },
      changes: [
        { block_id: "b1", change: "changed", before: "옛 문장", after: "새 문장" },
        { block_id: "b2", change: "added", before: "", after: "덧붙인 문장" },
      ],
    });
    await renderDoc();
    await userEvent.click(screen.getByRole("tab", { name: /이력/ }));

    const compare = await screen.findAllByRole("button", { name: "지금 판과 비교" });
    await userEvent.click(compare.find((b) => !b.disabled));

    expect(await screen.findByText("옛 문장")).toBeInTheDocument();
    expect(screen.getByText("새 문장")).toBeInTheDocument();
    expect(screen.getByText("덧붙인 문장")).toBeInTheDocument();
    expect(screen.getByText("수정")).toBeInTheDocument();
    expect(screen.getByText("추가")).toBeInTheDocument();
  });

  it("차이가 없으면 그 사실을 말한다 — 빈 화면으로 두지 않는다", async () => {
    responses.set(`GET /api/knowledge/documents/${DOC_ID}/diff?base=1&target=2`, {
      base: { version_no: 1 }, target: { version_no: 2 }, changes: [],
    });
    await renderDoc();
    await userEvent.click(screen.getByRole("tab", { name: /이력/ }));
    const compare = await screen.findAllByRole("button", { name: "지금 판과 비교" });
    await userEvent.click(compare.find((b) => !b.disabled));

    expect(await screen.findByText("두 판의 본문이 같습니다.")).toBeInTheDocument();
  });
});
