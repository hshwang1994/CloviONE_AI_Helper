/* 문서 틀을 화면에서 관리한다 (문서 개편 7번).
 *
 * ## 무엇이 없었나
 *
 * 0027 이 표와 CRUD 를 만들었고 `useTemplate(id)` 훅에는 「고치는 화면이 여는 자리다」라는
 * 주석까지 있었다. 그런데 그 화면이 없었다 — 「분류 관리」 창에는 분류와 태그 두 탭뿐이라,
 * 틀을 만들거나 고치거나 지울 방법이 제품 어디에도 없었다. 서버만 있고 입구가 없는 기능은
 * 사용자에게 없는 기능이다.
 *
 * ## 여기서 보는 것
 *
 *   1. 틀 탭이 목록을 보여 주고 「빈 문서」에는 고치기·지우기를 안 준다.
 *   2. 새 틀을 만든다 — 본문 글자가 Block JSON 으로 나간다.
 *   3. 고치기는 **본문이 온 뒤에** 열린다(빈 칸을 저장해 본문을 지우지 않게).
 *   4. 🔴 고치기와 지우기가 **문서 목록을 다시 부르지 않는다** — 틀을 고쳐도 이미 만든
 *      문서는 안 바뀌는 것이 이 기능의 계약이고, 목록을 함께 무효화하면 화면이 그 반대를
 *      그린다.
 *   5. 글자 ↔ Block JSON 왕복이 시드 본문에서 정확하다.
 *
 * 왕복은 **0027 이 실제로 시드한 본문 셋 전부**로도 쟀다(meeting · requirements ·
 * ops-guide, 10·13·11줄, 셋 다 바이트까지 같음). 아래 `SEED_BODY` 는 그 셋이 쓰는 마디
 * 다섯을 한 판에 모은 것이라, 시드를 이 파일에 복제하지 않고도 같은 것을 잰다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { id: "u-1", display_name: "나", role: "admin" } }),
}));

import { bodyToText, textToBody } from "./knowledge/templateText.js";
import { TaxonomyManager } from "./knowledge/TaxonomyManager.jsx";
import { Knowledge } from "./Knowledge.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROWS = [
  { id: "blank", name: "빈 문서", help: "아무것도 없는 상태에서 시작합니다.", empty: true, builtin: true },
  { id: "t-1", name: "회의록", help: "회의 목적과 참석자를 남깁니다.", empty: false, builtin: false },
];

/* 0027 이 시드한 본문과 같은 모양 — 마디 다섯을 전부 담는다. */
const SEED_BODY = {
  type: "doc",
  content: [
    { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "회의 개요" }] },
    { type: "paragraph", content: [{ type: "text", text: "언제 어디서 누가 모였는지 적습니다." }] },
    {
      type: "bulletList",
      content: [
        { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "참석자" }] }] },
        { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "안건" }] }] },
      ],
    },
    { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "할 일" }] },
    {
      type: "orderedList",
      content: [
        { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "첫째" }] }] },
        { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "둘째" }] }] },
      ],
    },
  ],
};

function renderManager(overrides = {}) {
  const props = {
    open: true,
    onClose: vi.fn(),
    canManage: true,
    busy: false,
    categories: [],
    tags: [],
    templates: ROWS,
    onAddCategory: vi.fn(),
    onRenameCategory: vi.fn(),
    onRemoveCategory: vi.fn(),
    onAddTag: vi.fn(),
    onRenameTag: vi.fn(),
    onRemoveTag: vi.fn(),
    editingTemplate: null,
    onOpenTemplate: vi.fn(),
    onCancelTemplate: vi.fn(),
    onCreateTemplate: vi.fn(),
    onSaveTemplate: vi.fn(),
    onRemoveTemplate: vi.fn(),
    ...overrides,
  };
  render(<TaxonomyManager {...props} />);
  return props;
}

async function openTemplateTab(user) {
  await user.click(screen.getByRole("tab", { name: "틀" }));
}

describe("글자 ↔ Block JSON 왕복", () => {
  it("🔴 시드 본문이 글자를 거쳐 **같은 모양으로** 돌아온다", () => {
    const text = bodyToText(SEED_BODY);
    expect(text).toBe(
      "## 회의 개요\n언제 어디서 누가 모였는지 적습니다.\n- 참석자\n- 안건\n## 할 일\n1. 첫째\n2. 둘째",
    );
    expect(textToBody(text)).toEqual(SEED_BODY);
  });

  it("붙어 있는 글머리 줄은 목록 **하나**로 묶인다 — 줄마다 목록을 만들지 않는다", () => {
    const body = textToBody("- 하나\n- 둘\n- 셋");
    expect(body.content).toHaveLength(1);
    expect(body.content[0].type).toBe("bulletList");
    expect(body.content[0].content).toHaveLength(3);
  });

  it("아무것도 안 적은 틀도 문단 하나로 시작한다 — 서버가 빈 문서를 거절한다", () => {
    expect(textToBody("")).toEqual({ type: "doc", content: [{ type: "paragraph" }] });
  });
});

describe("분류 관리 — 틀 탭", () => {
  beforeEach(() => vi.clearAllMocks());

  it("틀 목록을 보여 주고 「빈 문서」에는 고치기·지우기를 안 준다", async () => {
    const user = userEvent.setup();
    renderManager();
    await openTemplateTab(user);

    expect(screen.getByText("빈 문서")).toBeTruthy();
    expect(screen.getByText("회의록")).toBeTruthy();
    expect(screen.getByText("기본 제공")).toBeTruthy();
    // 지울 수 있는 것은 조직이 만든 틀 하나뿐이다.
    expect(screen.getAllByRole("button", { name: "삭제" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "수정" })).toHaveLength(1);
  });

  it("새 틀을 만든다 — 본문 글자가 Block JSON 으로 나간다", async () => {
    const user = userEvent.setup();
    const props = renderManager({ editingTemplate: { id: "new" } });
    await openTemplateTab(user);

    await user.type(screen.getByLabelText(/^틀 이름/), "장애 보고서");
    await user.type(screen.getByLabelText("설명"), "무슨 일이 있었는지 적습니다.");
    await user.type(screen.getByLabelText("본문"), "## 경위{enter}- 처음 신고");
    await user.click(screen.getByRole("button", { name: "추가" }));

    expect(props.onCreateTemplate).toHaveBeenCalledTimes(1);
    expect(props.onCreateTemplate.mock.calls[0][0]).toEqual({
      name: "장애 보고서",
      help: "무슨 일이 있었는지 적습니다.",
      body: {
        type: "doc",
        content: [
          { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "경위" }] },
          {
            type: "bulletList",
            content: [{
              type: "listItem",
              content: [{ type: "paragraph", content: [{ type: "text", text: "처음 신고" }] }],
            }],
          },
        ],
      },
    });
  });

  it("고치기 판은 서버가 준 본문으로 채워진다 — 빈 칸을 저장해 본문을 지우지 않는다", async () => {
    const user = userEvent.setup();
    const props = renderManager({
      editingTemplate: { id: "t-1", name: "회의록", help: "회의 목적", body: SEED_BODY },
    });
    await openTemplateTab(user);

    expect(screen.getByLabelText("본문").value).toContain("## 회의 개요");
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(props.onSaveTemplate).toHaveBeenCalledWith("t-1", {
      name: "회의록",
      help: "회의 목적",
      body: SEED_BODY,
    });
  });

  it("이름을 비우면 저장할 수 없다", async () => {
    const user = userEvent.setup();
    renderManager({ editingTemplate: { id: "new" } });
    await openTemplateTab(user);
    expect(screen.getByRole("button", { name: "추가" }).disabled).toBe(true);
  });

  it("틀을 고치는 동안 창의 발은 하나이고 취소 → 확정이다 — 몸 안에 둘째 단추 줄이 없다(핸드오프 RULES §8)", async () => {
    const user = userEvent.setup();
    const props = renderManager({ editingTemplate: { id: "new" } });
    await openTemplateTab(user);
    const dialog = screen.getByRole("dialog");
    const footers = dialog.querySelectorAll("[data-action-footer]");
    expect(footers).toHaveLength(1);
    expect(footers[0].getAttribute("data-action-footer")).toBe("modal");
    expect([...footers[0].querySelectorAll("button")].map((b) => b.textContent)).toEqual(["취소", "추가"]);
    // 틀 판의 칸들은 몸 안이고, 몸에는 취소 · 추가 단추가 없다.
    const body = screen.getByLabelText(/^틀 이름/).closest(".MuiDialogContent-root") || dialog;
    expect([...body.querySelectorAll("button")].some((b) => ["취소", "추가"].includes(b.textContent) && !footers[0].contains(b))).toBe(false);
    // 취소는 흰 면 보조이고, 누르면 틀 판을 닫는다.
    const cancel = within(footers[0]).getByRole("button", { name: "취소" });
    expect(cancel.className).toMatch(/MuiButton-outlined/);
    await user.click(cancel);
    expect(props.onCancelTemplate).toHaveBeenCalledTimes(1);
  });

  it("틀 목록의 줄 동작은 표 행과 같은 `RowActions` 다 — 삭제는 파괴 단추다", async () => {
    const user = userEvent.setup();
    renderManager();
    await openTemplateTab(user);
    const actions = document.querySelectorAll("[data-row-actions]");
    expect(actions).toHaveLength(1);
    const remove = within(actions[0]).getByRole("button", { name: "삭제" });
    expect(remove.className).not.toMatch(/MuiButton-text/);
    expect(within(actions[0]).getByRole("button", { name: "수정" }).className).toMatch(/MuiButton-outlined/);
  });

  it("🔴 운영자가 아니면 고치기·지우기가 안 보인다 — 그러나 **만들기는 보인다**", async () => {
    const user = userEvent.setup();
    renderManager({ canManage: false });
    await openTemplateTab(user);

    /* 서버가 정한 사다리와 같아야 한다: 만들기는 `DOCUMENT_UPDATE`(누구나), 고치기·지우기는
       `DOCUMENT_DELETE`(운영자). 화면만 더 좁히면 서버가 허락한 일을 사람이 못 하게 되고
       그 차이는 아무 데도 안 적혀 있다. */
    expect(screen.getByRole("button", { name: "새 틀" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "수정" })).toBeNull();
    expect(screen.queryByRole("button", { name: "삭제" })).toBeNull();
    expect(screen.getByText(/운영자만 할 수 있습니다/)).toBeTruthy();
  });

  it("🔴 탭이 「틀을 고쳐도 이미 만든 문서는 그대로」라고 먼저 말한다", async () => {
    const user = userEvent.setup();
    renderManager();
    await openTemplateTab(user);
    await waitFor(() =>
      expect(screen.getByText(/이미 추가한 문서는[\s\S]*그대로 남습니다/)).toBeTruthy());
  });
});


/* ── 화면에 붙은 자리 ─────────────────────────────────────────────────────────
 *
 * 위 판(`TaxonomyManager`)만 재면 **연결이 안 됐다**를 못 잡는다. 여기서는 문서 화면을
 * 통째로 띄워 「분류 관리」를 열고, 틀을 고치는 요청이 실제로 나가는지와 그때 문서 목록을
 * 다시 부르지 않는지를 함께 잰다. */

const TEMPLATE_ROWS = {
  items: [
    { id: "blank", name: "빈 문서", help: "빈 상태로 시작합니다.", empty: true, builtin: true },
    { id: "t-1", name: "회의록", help: "회의 목적", empty: false, builtin: false },
  ],
};

const calls = [];

function routes(path) {
  const text = String(path);
  if (text.startsWith("/api/knowledge/tags")) return { items: [] };
  if (text.startsWith("/api/knowledge/categories")) return { items: [] };
  if (text === "/api/knowledge/summary") return { total: 1, recent: 0, favorites: 0, drafts: 0 };
  if (text === "/api/knowledge/templates") return TEMPLATE_ROWS;
  if (text === "/api/knowledge/templates/t-1") {
    return { ...TEMPLATE_ROWS.items[1], body: SEED_BODY };
  }
  if (text.startsWith("/api/knowledge/recent")) return { items: [] };
  if (text.startsWith("/api/projects")) return { items: [], total: 0 };
  if (text.startsWith("/api/knowledge/documents")) {
    return { items: [], total: 0, limit: 100, offset: 0 };
  }
  return { ok: true };
}

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/knowledge?project=none"]}>
          <Knowledge />
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("문서 화면에서 틀을 고친다", () => {
  beforeEach(() => {
    calls.length = 0;
    apiMock.mockReset();
    apiMock.mockImplementation((path, opts) => {
      calls.push({ path: String(path), method: (opts && opts.method) || "GET", body: opts && opts.body });
      return Promise.resolve(routes(path));
    });
  });

  it("🔴 「분류 관리」에서 틀을 고치면 PATCH 가 나가고, **문서 목록은 다시 안 부른다**", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(await screen.findByRole("button", { name: "분류 관리" }));
    await user.click(await screen.findByRole("tab", { name: "틀" }));
    await user.click(await screen.findByRole("button", { name: "수정" }));

    // 본문이 온 뒤에야 판이 채워진다 — 그 전에 저장하면 본문을 지운다.
    await waitFor(() => expect(screen.getByLabelText("본문").value).toContain("## 회의 개요"));

    const before = calls.filter((c) => c.path.startsWith("/api/knowledge/documents")).length;
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => {
      const patch = calls.find((c) => c.method === "PATCH" && c.path === "/api/knowledge/templates/t-1");
      expect(patch).toBeTruthy();
      expect(patch.body.name).toBe("회의록");
      expect(patch.body.body).toEqual(SEED_BODY);
    });

    /* 틀을 고쳐도 이미 만든 문서는 안 바뀐다 — 목록을 함께 무효화하면 화면이 그 반대를
       그린다. 요청 수가 그대로여야 한다. */
    const after = calls.filter((c) => c.path.startsWith("/api/knowledge/documents")).length;
    expect(after).toBe(before);
  });
});
