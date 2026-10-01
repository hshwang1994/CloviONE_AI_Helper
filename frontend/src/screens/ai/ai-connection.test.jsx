import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI 연결 화면 (계획 A3, D-539) — `/ai-connection`.
 *
 * qa-contract-replaced-by: frontend/src/screens/settings/ai-settings.test.jsx
 * qa-contract-replaced-by: frontend/src/screens/llm-console.test.jsx
 *
 * 옛 설정 탭의 시험이 지키던 약속 — 상태 낱말은 서버의 판정이다, 확인이 큐에 있는 동안 결과를 지어내지 않는다, Anthropic 에는
 * 계정 로그인이 없다, 기능 스위치는 설정 API 로 곧바로 간다 — 은 여기서 다시 잰다. 바뀐 약속:
 *   1) 「AI 답변 생성」 초안 스위치와 저장 단추가 없다. AI 사용도 누르는 즉시 저장한다(P-118).
 *   2) 모델은 인증 뒤 저절로 받는다. 모델이 비어 있으면 추천을 auto 표지와 함께 저장한다. 고르면 곧바로 저장한다.
 *   3) 「모델 불러오기」는 실패했을 때의 회복 동작(「다시 불러오기」 · 「직접 입력」)으로만 남는다.
 *   4) 한 열 흐름이다 - 카드는 연결 상태 면 하나이고 구획은 카드가 아니다. 기술 값은 「기술 정보」 접기 안에만 있다.
 *   5) 고른 연결이 지금 연결과 다르면 「이 연결로 바꾸기」가 그 연결의 모델 목록을 받아 함께 저장한다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { AiConnection } from "./AiConnection.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const ANTHROPIC = {
  key: "anthropic", label: "Anthropic", help: "Anthropic 은 콘솔에서 발급한 API 키로만 연결할 수 있습니다.",
  auth_methods: [{
    key: "api_key", label: "API 키", secret_slot: "ai.anthropic.api_key", account: false, secret_set: true,
    help: "Claude 구독 계정으로는 연결할 수 없습니다. Anthropic 콘솔에서 발급한 API 키를 넣으세요.",
    secret_hint: "끝자리 WXYZ", ready: true,
  }],
};
const OPENAI = {
  key: "openai", label: "OpenAI", help: "OpenAI 는 API 키나 ChatGPT 계정으로 연결할 수 있습니다.",
  auth_methods: [
    { key: "api_key", label: "API 키", secret_slot: "ai.openai.api_key", account: false, secret_set: true, help: "키", ready: true },
    { key: "chatgpt", label: "ChatGPT 계정", secret_slot: "ai.openai.chatgpt", account: true, secret_set: false, help: "계정", ready: false },
  ],
};

function overview(over = {}) {
  const base = {
    config: { generation_enabled: false, provider: "anthropic", auth_method: "api_key", model: "claude-old",
      timeout_seconds: 60, max_concurrency: 4 },
    state: {
      state: "unverified", verifying: false, verify_job_id: null, last_success_at: null, checked_at: null,
      display: { key: "unverified", label: "확인 전", kind: "info", message: "아직 연결을 확인하지 않았습니다." },
    },
    providers: [ANTHROPIC, OPENAI],
    features: { chat_enabled: true, assistant_narrative_enabled: false, game_ai_enabled: false },
    limits: { timeout_seconds: [5, 300], max_concurrency: [1, 8] },
    chatgpt: { connected: false, disconnected: false, flow: "paste" },
    capabilities: { tools: "unknown", checked_at: null },
    index: { documents: 3, chunks: 12, embedded: 0, semantic: false },
    technical: { proxy: "proxy.corp.example:3128", reason_code: null },
    token_settings: {},
  };
  return { ...base, ...over, config: { ...base.config, ...(over.config || {}) }, state: { ...base.state, ...(over.state || {}) } };
}

let data;
let models;
function route() {
  apiMock.mockImplementation((path, opt) => {
    const p = String(path);
    const method = (opt && opt.method) || "GET";
    if (p === "/api/admin/ai" && method === "GET") return Promise.resolve(data);
    if (p === "/api/admin/ai/config") {
      data = overview({ ...data, config: { ...data.config, ...(opt.body || {}) } });
      return Promise.resolve({ ...data, verify_job_id: null });
    }
    if (p.startsWith("/api/admin/ai/models")) return models(p);
    if (p === "/api/admin/ai/verify") return Promise.resolve({ job_id: "j-1", status: "queued" });
    if (p.startsWith("/api/admin/secrets")) {
      return Promise.resolve({ items: [{ slot: "ai.anthropic.api_key", stored: true, updated_at: null }] });
    }
    if (p.startsWith("/api/admin/settings/")) return Promise.resolve({});
    return Promise.resolve({});
  });
}

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/ai-connection"]}>
              <AiConnection />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function calls(path, method) {
  return apiMock.mock.calls.filter(([p, o]) => String(p) === path && ((o && o.method) || "GET") === method);
}

beforeEach(() => {
  apiMock.mockReset();
  data = overview();
  models = () => Promise.resolve({
    models: [{ id: "claude-old", label: "Claude Old", recommended: false },
      { id: "claude-sonnet-9", label: "Claude Sonnet 9", recommended: true }],
    recommended_id: "claude-sonnet-9",
  });
  route();
});

describe("AI 연결 — 상태 면", () => {
  it("상태 낱말은 서버의 판정이고 정상을 지어내지 않는다", async () => {
    renderScreen();
    const card = await screen.findByTestId("ai-state");
    expect(within(card).getByText("확인 전")).toBeInTheDocument();
    expect(within(card).queryByText("정상")).toBeNull();
    expect(within(card).getByText("Anthropic")).toBeInTheDocument();
    expect(within(card).getByText("claude-old")).toBeInTheDocument();
  });

  it("막힌 연결은 까닭 문장을 메시지 상자로 세운다", async () => {
    data = overview({ state: { state: "error", display: { key: "error", label: "연결 오류", kind: "error",
      message: "AI 연결을 쓸 수 없습니다. API 키가 거부되었습니다." } } });
    renderScreen();
    expect(await screen.findByText("연결 오류")).toBeInTheDocument();
    expect(screen.getByText(/API 키가 거부되었습니다/)).toBeInTheDocument();
  });

  it("기술 값은 「기술 정보」 접기 안에만 있다", async () => {
    renderScreen();
    await screen.findByTestId("ai-state");
    expect(screen.getByText("proxy.corp.example:3128")).not.toBeVisible();
    expect(screen.getByText("기술 정보")).toBeVisible();
  });

  it("한 열 흐름이다 - 카드는 상태 면과 그 아래 판 하나이고 구획은 카드가 아니다", async () => {
    const { container } = renderScreen();
    await screen.findByTestId("ai-connection-form");
    expect(container.querySelectorAll("[data-surface='plate'] [data-surface='plate']")).toHaveLength(0);
    for (const title of ["제공자와 인증", "모델", "실행 옵션", "AI 기능"]) {
      const heading = screen.getByRole("heading", { name: title });
      expect(heading.closest("[data-surface='plate']")).toBe(screen.getByTestId("ai-connection-form"));
    }
    expect(screen.queryByText(/답변 생성/)).toBeNull();
  });
});

describe("AI 연결 — 인증과 모델", () => {
  it("Anthropic 에는 API 키 칸만 있고 계정 로그인 단추가 없다", async () => {
    renderScreen();
    expect(await screen.findByText(/Claude 구독 계정으로는 연결할 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "API 키 저장하고 확인" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Continue with ChatGPT/ })).toBeNull();
  });

  it("모델 목록은 저절로 받고, 고르면 곧바로 저장한다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await waitFor(() => expect(apiMock.mock.calls.some(([p]) => String(p).startsWith("/api/admin/ai/models"))).toBe(true));
    await user.click(await screen.findByRole("combobox", { name: "모델" }));
    await user.click(await screen.findByRole("option", { name: "Claude Sonnet 9 (추천)" }));
    await waitFor(() => expect(calls("/api/admin/ai/config", "PUT").some(([, o]) => o.body.model === "claude-sonnet-9")).toBe(true));
    expect(screen.queryByRole("button", { name: "모델 불러오기" })).toBeNull();
  });

  it("모델이 비어 있으면 추천을 auto 표지와 함께 한 번 저장한다", async () => {
    data = overview({ config: { model: "" } });
    renderScreen();
    await waitFor(() => {
      const puts = calls("/api/admin/ai/config", "PUT");
      expect(puts).toHaveLength(1);
      expect(puts[0][1].body).toEqual({ model: "claude-sonnet-9", auto_model: true });
    });
    expect(await screen.findByText("추천 모델로 정했습니다. 바꿀 수 있습니다.")).toBeInTheDocument();
  });

  it("목록을 못 받으면 까닭과 함께 직접 입력으로 저장할 수 있다", async () => {
    const user = userEvent.setup();
    models = () => Promise.reject(Object.assign(new Error("모델 목록을 가져오지 못했습니다. API 키가 거부되었습니다."), { status: 502 }));
    renderScreen();
    expect(await screen.findByText(/모델 목록을 가져오지 못했습니다/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "직접 입력" }));
    const box = screen.getByLabelText("모델 이름");
    await user.clear(box);
    await user.type(box, "claude-custom");
    await user.click(screen.getByRole("button", { name: "모델 저장" }));
    await waitFor(() => expect(calls("/api/admin/ai/config", "PUT").some(([, o]) => o.body.model === "claude-custom")).toBe(true));
  });

  it("고른 연결이 지금과 다르면 「이 연결로 바꾸기」가 그 연결의 모델 목록을 받아 함께 저장한다", async () => {
    const user = userEvent.setup();
    models = (p) => Promise.resolve(p.includes("provider=openai")
      ? { models: [{ id: "gpt-5", label: "gpt-5", recommended: true }], recommended_id: "gpt-5" }
      : { models: [{ id: "claude-old", label: "Claude Old", recommended: false }], recommended_id: null });
    renderScreen();
    await user.click(await screen.findByRole("tab", { name: "OpenAI" }));
    expect(await screen.findByText("지금 쓰는 연결은 Anthropic API 키입니다.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "이 연결로 바꾸기" }));
    await waitFor(() => {
      const put = calls("/api/admin/ai/config", "PUT").at(-1);
      expect(put && put[1].body).toEqual({ provider: "openai", auth_method: "api_key", model: "gpt-5", auto_model: true });
    });
  });
});

describe("AI 연결 — 실행 옵션과 기능", () => {
  it("AI 사용은 누르는 즉시 저장되고 다른 저장 단추가 없다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("switch", { name: "AI 사용" }));
    await waitFor(() => expect(calls("/api/admin/ai/config", "PUT").some(([, o]) => o.body.generation_enabled === true)).toBe(true));
  });

  it("제공자 · 모델이 없으면 AI 사용을 켤 수 없다", async () => {
    data = overview({ config: { provider: "", auth_method: "", model: "" } });
    renderScreen();
    expect(await screen.findByRole("switch", { name: "AI 사용" })).toBeDisabled();
    expect(screen.getByText("제공자, 인증, 모델을 정하면 켤 수 있습니다.")).toBeInTheDocument();
  });

  it("기능 스위치는 설정 API 로 곧바로 간다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("switch", { name: "게임 퀴즈 AI" }));
    await waitFor(() => expect(calls("/api/admin/settings/game_ai_enabled", "PUT")).toHaveLength(1));
    expect(calls("/api/admin/settings/game_ai_enabled", "PUT")[0][1].body).toEqual({ value: true });
  });

  it("실행 옵션은 그 구획의 저장 · 되돌리기만 쓴다", async () => {
    const user = userEvent.setup();
    renderScreen();
    const save = await screen.findByRole("button", { name: "저장" });
    expect(save).toBeDisabled();
    const timeout = screen.getByLabelText("제한 시간(초)");
    await user.clear(timeout);
    await user.type(timeout, "90");
    expect(save).not.toBeDisabled();
    await user.click(save);
    await waitFor(() => expect(calls("/api/admin/ai/config", "PUT").some(([, o]) => o.body.timeout_seconds === 90)).toBe(true));
  });
});
