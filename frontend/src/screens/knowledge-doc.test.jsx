/* qa-contract-replaced-by: frontend/src/screens/teamdoc-edit.test.jsx
 * qa-contract-replaced-by: frontend/src/screens/teamdoc.test.jsx
 *
 * 옛 문서 화면(`TeamDoc.jsx`)의 상세·편집 계약을 이 파일이 이어받는다 (S14 · C2).
 * 편집 쪽 셋은 그대로 산다: 저장이 **새 지문을 받아 다음 저장에 쓰는가** · 판이 쌓였을
 * 때와 안 쌓였을 때를 다르게 말하는가 · 되돌리기가 잠금 값을 함께 보내는가. 옛 파일의
 * 나머지(Notion 블록 렌더러 `DocBody`·`safeExternal`, 본문만 따로 실패하는 장애 격리)는
 * **대상이 사라졌다** — 본문의 정본이 블록 JSON 이 되면서 실시간 원격 읽기 자체가 없다.
 * 댓글과 열람 제한은 서버 쪽으로 옮겨 `tests/integration/test_knowledge_comments.py` 와
 * `tests/security/test_search_restricted_documents.py` 가 실제 요청으로 본다.
 *
 * qa-contract-change: 화면이 탭 둘에서 편집기와 곁열 두 열로 재설계돼(지시 22.6) 이력이 탭이 아니라 버튼이 됐다. 옛 성질 다섯은 그대로 두고 이동·관계·첨부 배선을 더했다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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
    /* 🔴 `useToast()` 는 **함수**를 돌려준다(kit.jsx 의 `ToastCtx.Provider value={push}`).
       예전에는 이 대역이 `{ show }` 객체였고, 그래서 화면이 `toast.show(...)` 를 부르는
       동안에도 시험이 초록이었다 — 실제 브라우저에서는 그 줄이 전부 TypeError 였다.
       대역이 진짜 계약과 다르면 시험은 제품이 아니라 대역을 확인한다. */
    useToast: () => (m) => toasts.push(m),
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
    space_id: "space-1",
    space_name: "우리 공간",
    project: { id: "proj-1", code: "AAAAAA", name: "알파 프로젝트" },
    folder_id: null,
    updated_at: "2026-08-20T01:00:00",
    created_at: "2026-08-01T01:00:00",
    author: { user_id: "u-1", display_name: "김동현" },
    current: { version_no: 2, body: { type: "doc", content: [] } },
    tags: [{ id: "tag-1", name: "회의록", slug: "meeting" }],
    category: { id: "cat-1", name: "회의 기록" },
    relations: [{ document_id: "doc-2", kind: "relates_to", label: "관련 문서", title: "요구사항 정의서" }],
    backlinks: [],
    attachments: [
      { id: "att-1", filename: "회의자료.pdf", size_bytes: 2048, mime_type: "application/pdf" },
    ],
  });
  responses.set("GET /api/knowledge/spaces/space-1/tree", {
    folders: [{ id: "f-1", name: "01. 기획", depth: 0, children: [] }],
  });
  // 곁열의 「분류」 카드가 카테고리 어휘를 묻는다(0026).
  responses.set("GET /api/knowledge/categories", {
    items: [
      { id: "cat-1", name: "회의 기록", slug: "회의 기록", sort_order: 1024, document_count: 2 },
      { id: "cat-2", name: "기술 문서", slug: "기술 문서", sort_order: 2048, document_count: 0 },
    ],
  });
  // 이동 대화상자의 ProjectPicker 가 쓴다(§14.4) — 지금 프로젝트(alpha)와 다른 프로젝트(beta)
  // 로 실제로 옮기는 시험에 필요하다.
  /* qa-contract-change: 후보 질의가 `?page=1&page_size=100` 이 됐다. 예전 주소는
     `page_size=200` 이었는데 **서버가 그것을 422 로 거절한다**(상한 100) — 대역이 옛
     주소를 그대로 받아 주는 바람에 시험은 초록인데 운영은 빈 목록이었다. 대역의 주소가
     실제 계약과 같아야 이 시험이 그 사실을 본다. */
  responses.set("GET /api/projects?page=1&page_size=100", {
    items: [
      { id: "proj-1", code: "AAAAAA", name: "알파 프로젝트" },
      { id: "proj-2", code: "BBBBBB", name: "베타 프로젝트" },
    ],
    total: 2,
  });
  // 화면이 본문 아래에 논의를 함께 그린다 (S14 · C2). 대역이 없으면 그 자리가 오류 상태로
  // 뜨는데, 이 파일이 보려는 것은 판·차이·되돌리기라 소음만 는다.
  responses.set(`GET /api/knowledge/documents/${DOC_ID}/comments`, {
    ok: true, comments: [], people: {},
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
    await userEvent.click(screen.getByRole("button", { name: /이력/ }));

    /* 「2판」은 두 자리에 선다 — 상단 맥락의 「현재 판」과 이력의 그 줄. 그것이 의도다:
       본문을 읽다가 몇 판인지 보려고 이력을 열 이유가 없다. */
    expect((await screen.findAllByText("2판")).length).toBeGreaterThan(1);
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
    await userEvent.click(screen.getByRole("button", { name: /이력/ }));

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
    await userEvent.click(screen.getByRole("button", { name: /이력/ }));

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
    await userEvent.click(screen.getByRole("button", { name: /이력/ }));
    const compare = await screen.findAllByRole("button", { name: "지금 판과 비교" });
    await userEvent.click(compare.find((b) => !b.disabled));

    expect(await screen.findByText("두 판의 본문이 같습니다.")).toBeInTheDocument();
  });
});

/* 서버에 있는데 화면이 없던 것들 (지시 22.6). 「연결했다」는 주장은 요청으로만 확인된다. */
describe("곁열이 문서에 대한 것을 든다", () => {
  it("작성자, 공간, 태그, 관련 문서, 첨부가 한자리에 있다", async () => {
    await renderDoc();
    expect(screen.getByText("김동현")).toBeInTheDocument();
    expect(screen.getAllByText("알파 프로젝트").length).toBeGreaterThan(0);
    expect(screen.getByText("요구사항 정의서")).toBeInTheDocument();
    expect(screen.getByText("회의자료.pdf")).toBeInTheDocument();
  });

  it("문서 잇기 창의 확정 단추는 고르기 전에도 선다 — 꺼져 있을 뿐 사라지지 않는다(핸드오프 RULES §3)", async () => {
    await renderDoc();
    await userEvent.click(screen.getByRole("button", { name: "문서 잇기" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "잇기" });
    expect(confirm).toBeDisabled();
    // 발은 모달 발 하나이고 취소 → 확정 순서다.
    const footer = confirm.closest("[data-action-footer]");
    expect(footer.getAttribute("data-action-footer")).toBe("modal");
    expect([...footer.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["취소", "잇기"]);
  });

  /* qa-contract-change: 「이동이 폴더와 잠금 값을 함께 보낸다」가 여기 있었다. 폴더 축이
     화면에서 걷히면서(문서 개편 1·5번) 이동 대화상자에 폴더 칸이 없다. 잠금 값
     (`base_version`)은 아래 프로젝트 이동 시험이 계속 잰다 — 그 계약은 그대로다. */

  it("🔴 이동이 새 프로젝트 id 와 잠금 값을 함께 보낸다 — 옮기는 사이 남이 저장했으면 서버가 막아야 한다", async () => {
    const seen = [];
    responses.set(`POST /api/knowledge/documents/${DOC_ID}/move`, (options) => {
      seen.push(options.body);
      return { id: DOC_ID, version: 4 };
    });
    await renderDoc();

    await userEvent.click(screen.getByRole("button", { name: "이동" }));
    const dialog = await screen.findByRole("dialog");
    /* qa-contract-change: 라벨이 「문서 범위」에서 **「프로젝트」**로 돌아왔다. 후보의
       비프로젝트 값을 「프로젝트 미지정」이라 부르게 되면서 축 이름이 내용에 대해
       거짓말하지 않게 됐다(D-415 를 잇는 결정). */
    await userEvent.click(within(dialog).getByLabelText("프로젝트"));
    await userEvent.click(await screen.findByRole("option", { name: /베타 프로젝트/ }));

    await userEvent.click(within(dialog).getByRole("button", { name: "옮기기" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].project_id).toBe("proj-2");
    expect(seen[0].base_version).toBe(3);
    // 폴더는 이제 이 요청의 축이 아니다.
    expect(seen[0].folder_id).toBeUndefined();
  });

  it("🔴 「프로젝트 미지정」이 센티널로 실제로 나간다 — 조용한 no-op 이 아니다", async () => {
    /* `allLabel` 로 그리면 **빈 값**의 이름만 바뀌어 서버에 아무것도 안 간다. 후보에
       넣어야 값이 돈다 — 그 차이를 여기서 잰다. */
    const seen = [];
    responses.set(`POST /api/knowledge/documents/${DOC_ID}/move`, (options) => {
      seen.push(options.body);
      return { id: DOC_ID, version: 4 };
    });
    await renderDoc();

    await userEvent.click(screen.getByRole("button", { name: "이동" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByLabelText("프로젝트"));
    await userEvent.click(await screen.findByRole("option", { name: "프로젝트 미지정" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "옮기기" }));

    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].project_id).toBe("none");
  });

  it("태그도 저장 버튼 하나로 함께 저장된다 — 버튼마다 다른 것이 저장되면 아무도 못 외운다", async () => {
    const seen = [];
    responses.set(`PUT /api/knowledge/documents/${DOC_ID}`, (options) => {
      seen.push(options.body);
      return { created_version: false, version: 4 };
    });
    await renderDoc();
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].tag_names).toEqual(["회의록"]);
  });

  it("분류도 저장 버튼 하나로 함께 저장된다 — 해제는 null 로 나간다(0026)", async () => {
    const seen = [];
    responses.set(`PUT /api/knowledge/documents/${DOC_ID}`, (options) => {
      seen.push(options.body);
      return { created_version: false, version: 4 };
    });
    await renderDoc();
    /* 서버가 준 분류가 select 의 출발값이다. */
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].category_id).toBe("cat-1");

    /* 「분류 없음」을 고르면 **null** 이 나간다 — 안 보내는 것과 다른 요청이다(서버의
       model_fields_set 게이트가 그 차이를 읽는다). */
    const select = screen.getByLabelText("분류");
    await userEvent.click(select);
    await userEvent.click(await screen.findByRole("option", { name: "분류 없음" }));
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(seen).toHaveLength(2));
    expect(seen[1].category_id).toBeNull();
  });
});

/* 붙은 그림을 문서 화면에서 볼 수 있는가 (사용자 지시 「미리보기까지 다 들고와야 한다」).
 *
 * 예전에는 그림도 파일 이름 한 줄이었다 — 문서를 열어 놓고 붙은 그림을 훑을 방법이 없고
 * 하나 보려면 새 탭을 열어야 했다. 티켓 화면은 같은 첨부를 이미 썸네일과 라이트박스로
 * 그리고 있었으므로, 같은 첨부가 화면마다 다르게 다뤄지고 있었던 것이다. */
describe("문서 첨부의 그림 미리보기", () => {
  const IMAGE = {
    id: "att-img", filename: "구성도.png", mime_type: "image/png", size_bytes: 2048,
  };
  const FILE = {
    id: "att-pdf", filename: "매뉴얼.pdf", mime_type: "application/pdf", size_bytes: 4096,
  };

  function withAttachments(list) {
    const doc = responses.get(`GET /api/knowledge/documents/${DOC_ID}`);
    responses.set(`GET /api/knowledge/documents/${DOC_ID}`, { ...doc, attachments: list });
  }

  it("🔴 그림은 실제 <img> 로 선다 — 이름 링크만 있으면 미리보기가 아니다", async () => {
    withAttachments([IMAGE, FILE]);
    await renderDoc();

    const shot = await screen.findByAltText("구성도.png");
    expect(shot.tagName).toBe("IMG");
    expect(shot.getAttribute("src")).toBe("/api/knowledge/attachments/att-img/content");
    // 그림이 아닌 첨부는 그림으로 그리지 않는다 — 반례가 없으면 「전부 그린다」도 초록이다.
    expect(screen.queryByAltText("매뉴얼.pdf")).toBeNull();
  });

  it("크게 보기 단추가 그림마다 선다", async () => {
    withAttachments([IMAGE, FILE]);
    await renderDoc();
    expect(await screen.findByRole("button", { name: "구성도.png 크게 보기" })).toBeTruthy();
  });

  it("그림도 이름과 삭제 단추를 그대로 갖는다 — 뗄 방법을 잃지 않는다", async () => {
    withAttachments([IMAGE]);
    await renderDoc();
    expect(await screen.findByText("구성도.png")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "삭제" }).length).toBeGreaterThan(0);
  });
});
