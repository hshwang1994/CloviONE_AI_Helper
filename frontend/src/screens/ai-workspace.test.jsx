import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

/* 「문서에서 찾기」가 **사람에게 정확히 말하는가** (S10 Exit · D-538).
 *
 * qa-contract-change: 작업 공간의 「물어보기」(`/api/ai/ask`)를 걷었다 — 질문은 AI 도우미 한 차례가 답한다(D-535). 이 화면은
 * 문서 찾기 · 그 문단으로 가기 · 초안 쓰기를 하고, 질문은 「AI 도우미에게 묻기」가 같은 질문을 새 대화로 넘긴다. 옛 「답변이 오면
 * 근거와 함께 보여 준다」는 넘기는 길(`/chat?ask=`)을 재는 시험으로 바뀌었고, 막힌 단추가 왜 막혔는지 말하는 성질은 도우미 칸
 * (`assistant`)의 까닭 문장으로 그대로 잰다.
 *
 * 서버 쪽 동작은 `tests/integration/test_ai_router.py` 와
 * `tests/security/test_ai_retrieval_permission.py` 가 실제 요청으로 본다. 여기서 보는
 * 것은 화면이 그 답을 어떻게 옮기는가다:
 *
 *   * **생성이 막혀 있어도 근거는 나온다** — 그리고 화면이 그 사실을 말한다.
 *   * **인용을 누르면 그 문단까지 간다** — 주소에 블록 앵커가 실려 있어야 한다.
 *   * **못 쓰는 기능을 숨기지 않는다** — 단추가 조용히 사라지면 기능이 없는 줄 안다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
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

function stubStatus({ generate = true, embed = true, assistant = true } = {}) {
  responses.set("GET /api/ai/status", {
    assistant: assistant
      ? { available: true, reason: null, notice: null, mode: "tools", can_configure: false }
      : { available: false, reason: "off", notice: "AI 사용이 꺼져 있어 지금은 답할 수 없습니다.", mode: "unknown",
          can_configure: false },
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
          <Route path="/chat" element={<Probe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: /문서에서 찾기/ });
}

beforeEach(() => {
  responses.clear();
  toasts.length = 0;
});

describe("문서에서 찾기", () => {
  it("AI 를 쓸 수 없어도 근거를 찾고, 묻기 단추가 왜 막혔는지 말한다", async () => {
    stubStatus({ generate: false, assistant: false });
    responses.set("GET /api/ai/search*", {
      query: "연차", citations: [CITATION], lane_counts: { trgm: 3 },
      semantic: true, vector_notice: null,
    });
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText(/찾을 내용/), "연차");
    // 못 쓰는 단추를 **숨기지 않는다.** 있고, 눌리지 않고, 왜인지가 옆에 적혀 있다.
    expect(screen.getByRole("button", { name: "AI 도우미에게 묻기" })).toBeDisabled();
    expect(screen.getByText(/AI 사용이 꺼져 있어 지금은 답할 수 없습니다/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "문서 찾기" }));

    expect(await screen.findByText("연차 사용 안내")).toBeInTheDocument();
    expect(screen.getByText("3문단")).toBeInTheDocument();
    // 생성이 막혔으면 초안 단추도 없다(근거는 그대로 보인다).
    expect(screen.queryByRole("button", { name: "이 근거로 초안 쓰기" })).toBeNull();
  });

  it("인용을 누르면 **그 문단까지** 간다", async () => {
    stubStatus();
    responses.set("GET /api/ai/search*", {
      query: "연차", citations: [CITATION], lane_counts: {}, semantic: true, vector_notice: null,
    });
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText(/찾을 내용/), "연차");
    await userEvent.click(screen.getByRole("button", { name: "문서 찾기" }));
    await userEvent.click(await screen.findByRole("button", { name: "문서에서 보기" }));

    // 🔴 문서까지가 아니라 **블록 앵커까지** 실려야 한다. 앵커가 빠지면 사용자는 긴
    // 문서의 맨 위에 도착하고, 인용이 어느 문장이었는지 다시 찾아야 한다.
    await waitFor(() =>
      expect(screen.getByTestId("here")).toHaveTextContent("/knowledge/doc-9?block=blk-7"),
    );
  });

  it("질문은 AI 도우미에게 새 대화로 넘긴다 — 이 화면은 옛 물어보기 경로를 부르지 않는다", async () => {
    stubStatus();
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText(/찾을 내용/), "연차 신청 방법");
    await userEvent.click(screen.getByRole("button", { name: "AI 도우미에게 묻기" }));

    await waitFor(() =>
      expect(screen.getByTestId("here")).toHaveTextContent("/chat?ask=" + encodeURIComponent("연차 신청 방법")),
    );
    const { api } = await import("../lib/api.js");
    expect(api.mock.calls.some(([path]) => path === "/api/ai/ask")).toBe(false);
  });

  it("쓰기 승인 정책이 걸리면 초안을 승인에 올렸다고 말하고 문서로 가지 않는다", async () => {
    // D-519: 서버가 문서 대신 승인 요청을 만들었다. 초안은 만들어졌으니 대화상자를 닫고, 문서 화면으로 가지 않는다.
    stubStatus();
    responses.set("GET /api/projects*", { items: [], total: 0, page: 1, page_size: 200 });
    responses.set("GET /api/ai/search*", {
      query: "연차", citations: [CITATION], lane_counts: {}, semantic: true, vector_notice: null,
    });
    responses.set("POST /api/ai/documents", {
      query: "연차", citations: [CITATION], status: "ok", answer: "초안", notice: null, document: null,
      approval: { id: "ap-1", status: "pending", request_id: "req-1", route: "/my-approvals?box=requested" },
    });
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText(/찾을 내용/), "연차");
    await userEvent.click(screen.getByRole("button", { name: "문서 찾기" }));
    await userEvent.click(await screen.findByRole("button", { name: "이 근거로 초안 쓰기" }));
    await userEvent.click(await screen.findByRole("button", { name: "초안 쓰기" }));

    await waitFor(() => expect(toasts).toContain("초안을 만들어 승인을 요청했습니다. 승인되면 문서가 추가됩니다."));
    expect(screen.queryByTestId("here")).toBeNull();
  });

  it("임베딩 모델이 없으면 **지금 무엇으로 찾고 있는지**를 말한다", async () => {
    stubStatus({ embed: false });
    await renderWorkspace();
    expect(screen.getByText("의미 검색 모델이 없어 낱말이 맞는 문서만 찾습니다.")).toBeInTheDocument();
    // 생성이 켜진 설치에서 「AI 기능이 꺼져 있습니다」라고 거짓을 말하지 않는다.
    expect(screen.queryByText(/AI 기능이 꺼져 있습니다/)).toBeNull();
  });

  it("찾은 것이 없으면 데이터가 없다고 하지 않고 **다시 찾아보라**고 한다", async () => {
    stubStatus();
    responses.set("GET /api/ai/search*", {
      query: "없는말", citations: [], lane_counts: {}, semantic: true, vector_notice: null,
    });
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText(/찾을 내용/), "없는말");
    await userEvent.click(screen.getByRole("button", { name: "문서 찾기" }));

    expect(await screen.findByText("검색 조건에 맞는 문서가 없습니다.")).toBeInTheDocument();
  });
});
