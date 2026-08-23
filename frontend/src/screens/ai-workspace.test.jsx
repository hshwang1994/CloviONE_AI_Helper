import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

/* AI 작업공간이 **사람에게 정확히 말하는가** (S10 Exit).
 *
 * 서버 쪽 동작은 `tests/integration/test_ai_router.py` 와
 * `tests/security/test_ai_retrieval_permission.py` 가 실제 요청으로 본다. 여기서 보는
 * 것은 화면이 그 답을 어떻게 옮기는가다:
 *
 *   * **생성이 막혀 있어도 근거는 나온다** — 그리고 화면이 그 사실을 말한다.
 *   * **인용을 누르면 그 문단까지 간다** — 주소에 블록 앵커가 실려 있어야 한다.
 *   * **못 쓰는 기능을 숨기지 않는다** — 단추가 조용히 사라지면 기능이 없는 줄 안다.
 */

const toasts = [];
vi.mock("../ui/kit.jsx", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    // `useToast()` 는 **함수**를 돌려준다(kit.jsx). 대역이 계약과 다르면 시험은 제품이
    // 아니라 대역을 확인한다.
    useToast: () => (m) => toasts.push(m),
    useConfirm: () => async () => true,
  };
});

const responses = new Map();
vi.mock("../lib/api.js", () => ({
  api: vi.fn(async (path, options) => {
    const key = `${options?.method || "GET"} ${path}`;
    for (const [pattern, value] of responses) {
      if (key === pattern || (pattern.endsWith("*") && key.startsWith(pattern.slice(0, -1)))) {
        return typeof value === "function" ? value(options) : value;
      }
    }
    throw new Error(`no stub for ${key}`);
  }),
}));

const CITATION = {
  chunk_id: "c-1",
  document_id: "doc-9",
  document_title: "연차 사용 안내",
  route: "/knowledge/doc-9?block=blk-7",
  where: "3문단",
  excerpt: "연차는 남은 일수 안에서 자유롭게 씁니다.",
  source_kind: "document",
  anchor_kind: "block",
  filename: "",
  lanes: ["trgm", "vector"],
};

function stubStatus({ generate = true, embed = true } = {}) {
  responses.set("GET /api/ai/status", {
    capabilities: {
      embed: embed
        ? { name: "embed", available: true, status: "ok", model: "m", notice: null, detail: "" }
        : {
            name: "embed", available: false, status: "model_missing", model: "m",
            notice: "서버에 AI 모델 파일이 없습니다.", detail: "",
          },
      rerank: {
        name: "rerank", available: false, status: "unsupported", model: "",
        notice: "이 기능을 하는 AI 어댑터가 없습니다.", detail: "",
      },
      generate: generate
        ? { name: "generate", available: true, status: "ok", model: "g", notice: null, detail: "" }
        : {
            name: "generate", available: false, status: "not_logged_in", model: "g",
            notice: "서버의 AI 명령줄 도구에 로그인되어 있지 않습니다.", detail: "",
          },
    },
    index: { chunks: 12, embedded: 12, pending_embedding: 0, documents: { ok: 3 } },
  });
  responses.set("GET /api/knowledge/spaces", []);
}

function Probe() {
  const location = useLocation();
  return <div data-testid="here">{location.pathname + location.search}</div>;
}

async function renderWorkspace() {
  const { AiWorkspace } = await import("./AiWorkspace.jsx");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/ai"]}>
        <Routes>
          <Route path="/ai" element={<AiWorkspace />} />
          <Route path="/knowledge/:id" element={<Probe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: /AI 작업공간/ });
}

beforeEach(() => {
  responses.clear();
  toasts.length = 0;
});

describe("AI 작업공간", () => {
  it("생성이 막혀 있어도 근거를 찾고, 왜 답을 못 만드는지 말한다", async () => {
    stubStatus({ generate: false });
    responses.set("GET /api/ai/search*", {
      query: "연차", citations: [CITATION], lane_counts: { trgm: 3 },
      semantic: true, vector_notice: null,
    });
    await renderWorkspace();

    // 못 쓰는 단추를 **숨기지 않는다.** 있고, 눌리지 않고, 왜인지가 옆에 적혀 있다.
    expect(screen.getByRole("button", { name: "물어보기" })).toBeDisabled();
    expect(screen.getByText(/로그인되어 있지 않습니다/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/무엇을 찾고 있습니까/), "연차");
    await userEvent.click(screen.getByRole("button", { name: "문서 찾기" }));

    expect(await screen.findByText("연차 사용 안내")).toBeInTheDocument();
    expect(screen.getByText("3문단")).toBeInTheDocument();
  });

  it("인용을 누르면 **그 문단까지** 간다", async () => {
    stubStatus();
    responses.set("GET /api/ai/search*", {
      query: "연차", citations: [CITATION], lane_counts: {}, semantic: true, vector_notice: null,
    });
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText(/무엇을 찾고 있습니까/), "연차");
    await userEvent.click(screen.getByRole("button", { name: "문서 찾기" }));
    await userEvent.click(await screen.findByRole("button", { name: "문서에서 보기" }));

    // 🔴 문서까지가 아니라 **블록 앵커까지** 실려야 한다. 앵커가 빠지면 사용자는 긴
    // 문서의 맨 위에 도착하고, 인용이 어느 문장이었는지 다시 찾아야 한다.
    await waitFor(() =>
      expect(screen.getByTestId("here")).toHaveTextContent("/knowledge/doc-9?block=blk-7"),
    );
  });

  it("답변이 오면 근거와 함께 보여 준다", async () => {
    stubStatus();
    responses.set("POST /api/ai/ask", {
      query: "연차", citations: [CITATION], lane_counts: {}, semantic: true,
      vector_notice: null, answer: "연차는 남은 일수 안에서 씁니다 [1].", status: "ok",
      model: "g", notice: null, truncated: false, delimiter_conflict: false,
    });
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText(/무엇을 찾고 있습니까/), "연차");
    await userEvent.click(screen.getByRole("button", { name: "물어보기" }));

    expect(await screen.findByText(/연차는 남은 일수 안에서 씁니다/)).toBeInTheDocument();
    expect(screen.getByText("연차 사용 안내")).toBeInTheDocument();
  });

  it("임베딩 모델이 없으면 **지금 무엇으로 찾고 있는지**를 말한다", async () => {
    stubStatus({ embed: false });
    await renderWorkspace();
    expect(screen.getByText(/낱말이 일치하는 문서만 찾습니다/)).toBeInTheDocument();
  });

  it("찾은 것이 없으면 데이터가 없다고 하지 않고 **다시 찾아보라**고 한다", async () => {
    stubStatus();
    responses.set("GET /api/ai/search*", {
      query: "없는말", citations: [], lane_counts: {}, semantic: true, vector_notice: null,
    });
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText(/무엇을 찾고 있습니까/), "없는말");
    await userEvent.click(screen.getByRole("button", { name: "문서 찾기" }));

    expect(await screen.findByText("찾은 문서가 없습니다")).toBeInTheDocument();
  });
});
