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
 *   6) 상태 면은 서버가 준 사실(`facts`)과 다음 할 일(`next`)만 그린다(D-558). 자격이 없으면 모델 줄이 없고 「AI 사용」을 켤 수 없다.
 *   7) ChatGPT 계정 연결은 모든 설치에서 API 키와 함께 표에 선다(D-566). 고르면 요금제 공유 한 줄과 세 단계가 서고 바로 시작할 수 있다.
 *   8) 여섯 구획이 이 순서로 선다(D-574): 현재 상태 · 제공자와 인증 · 모델 · 실행 옵션 · AI 기능 · 확인과 오류. [지금 확인] 은 화면에
 *      하나뿐이고 ⑥ 에 있다. 막힌 까닭은 ⑥ 의 메시지 상자 하나다. 최근 확인 · 최근 성공 시각은 ⑥ 의 줄이고 ① 의 띠에 다시 서지 않는다.
 *   9) 의미 검색 줄은 서버가 지은 낱말(`index.embed_status_label`)을 그대로 쓰고, 없으면 예전 낱말(있음 · 없음)이다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 * qa-contract-change: 실행 옵션 저장 실패는 ⑥ 「확인과 오류」가 아니라 그 「저장」 곁에 선다(설정 저장 왕복 하네스가 1366 에서 화면 아래 82px 로 잰 자리) — 실패 시험의 자리 단언을 옮겼다.

 * qa-contract-change: 실행 옵션 칸 이름을 계획 §6 대로 바꿨다 — 「제한 시간(초) · 동시 실행 수」 → 「요청 제한 시간(초) · 동시 요청 수」(AI 요청 하나의 제한 시간과 동시에 나가는 요청 수다). 저장 · 되돌리기 단언은 그대로다.
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
    secret_hint: "끝자리 WXYZ", ready: true, issue_url: "https://console.anthropic.com/settings/keys",
  }],
};
const OPENAI = {
  key: "openai", label: "OpenAI", help: "OpenAI 는 API 키나 ChatGPT 계정으로 연결할 수 있습니다.",
  auth_methods: [
    { key: "api_key", label: "API 키", secret_slot: "ai.openai.api_key", account: false, secret_set: true, help: "키", ready: true,
      issue_url: "https://platform.openai.com/api-keys" },
    { key: "chatgpt", label: "ChatGPT 계정", secret_slot: "ai.openai.chatgpt", account: true, secret_set: false, help: "계정",
      ready: false },
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
    credentials: { ready: true, method: "api_key", account_label: null },
    facts: [
      { key: "provider", label: "제공자", value: "Anthropic" },
      { key: "auth", label: "인증 방식", value: "API 키" },
      { key: "model", label: "모델", value: "claude-old" },
    ],
    next: { label: "지금 확인을 눌러 실제 답을 받는지 확인하세요.", action: "verify" },
    login: { open: false, transaction_id: null, expires_at: null },
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

const SIX = ["현재 상태", "제공자와 인증", "모델", "실행 옵션", "AI 기능", "확인과 오류"];

/* ⑥ 구획 — 제목에서 그 구획(`section`)으로 올라간다. */
function checksSection() {
  return screen.getByRole("heading", { name: "확인과 오류" }).closest("section");
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

  it("막힌 연결은 까닭 문장을 ⑥ 의 메시지 상자 하나로 세우고, 상태 면은 낱말로만 말한다", async () => {
    data = overview({ state: { state: "error", display: { key: "error", label: "연결 오류", kind: "error",
      message: "AI 연결을 쓸 수 없습니다. API 키가 거부되었습니다." } } });
    renderScreen();
    const card = await screen.findByTestId("ai-state");
    expect(within(card).getByText("연결 오류")).toBeInTheDocument();
    expect(within(card).queryByText(/API 키가 거부되었습니다/)).toBeNull();
    const reason = within(checksSection()).getByText(/API 키가 거부되었습니다/);
    expect(reason.closest(".k-callout")).not.toBeNull();
    expect(screen.getAllByText(/API 키가 거부되었습니다/)).toHaveLength(1);
  });

  it("기술 값은 「기술 정보」 접기 안에만 있다", async () => {
    renderScreen();
    await screen.findByTestId("ai-state");
    expect(screen.getByText("proxy.corp.example:3128")).not.toBeVisible();
    for (const summary of screen.getAllByText("기술 정보")) expect(summary).toBeVisible();
  });

  it("한 열 흐름이다 - 카드는 상태 면과 그 아래 판 하나이고 구획은 카드가 아니다", async () => {
    const { container } = renderScreen();
    await screen.findByTestId("ai-connection-form");
    expect(container.querySelectorAll("[data-surface='plate'] [data-surface='plate']")).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "현재 상태" }).closest("[data-surface='plate']")).toBe(screen.getByTestId("ai-state"));
    for (const title of SIX.slice(1)) {
      const heading = screen.getByRole("heading", { name: title });
      expect(heading.closest("[data-surface='plate']")).toBe(screen.getByTestId("ai-connection-form"));
    }
    expect(screen.queryByText(/답변 생성/)).toBeNull();
  });
});

describe("AI 연결 — 여섯 구획 (D-574)", () => {
  it("여섯 구획의 제목(h2)이 이 순서로 선다", async () => {
    renderScreen();
    await screen.findByTestId("ai-connection-form");
    const titles = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(titles).toEqual(SIX);
  });

  it("[지금 확인] 은 화면에 하나뿐이고 ⑥ 에 있으며, 누르면 연결 확인을 시작한다", async () => {
    const user = userEvent.setup();
    renderScreen();
    const card = await screen.findByTestId("ai-state");
    expect(within(card).queryByRole("button", { name: "연결 확인" })).toBeNull();
    const buttons = screen.getAllByRole("button", { name: "연결 확인" });
    expect(buttons).toHaveLength(1);
    expect(checksSection().contains(buttons[0])).toBe(true);
    await user.click(buttons[0]);
    await waitFor(() => expect(calls("/api/admin/ai/verify", "POST")).toHaveLength(1));
  });

  it("최근 확인 · 최근 성공 시각은 ⑥ 의 줄이고 상태 면의 띠에 다시 서지 않는다", async () => {
    data = overview({
      state: { state: "ok", last_success_at: "2026-10-12T05:18:00", checked_at: "2026-10-12T05:18:00",
        display: { key: "ok", label: "정상", kind: "ok", message: "AI 연결이 정상입니다." } },
      facts: [
        { key: "provider", label: "제공자", value: "Anthropic" },
        { key: "model", label: "모델", value: "claude-old" },
        { key: "last_success", label: "최근 성공", value: "2026-10-12T05:18:00", kind: "time" },
      ],
      next: null,
    });
    renderScreen();
    const card = await screen.findByTestId("ai-state");
    expect(within(card).queryByText("최근 성공")).toBeNull();
    expect(within(card).getByText("claude-old")).toBeInTheDocument();
    const rows = within(screen.getByTestId("ai-checks"));
    expect(rows.getByText("최근 확인")).toBeInTheDocument();
    expect(rows.getByText("최근 성공")).toBeInTheDocument();
    expect(rows.queryByText("아직 없음")).toBeNull();
  });

  it("확인한 적이 없으면 두 줄이 「아직 없음」이다", async () => {
    renderScreen();
    await screen.findByTestId("ai-checks");
    expect(within(screen.getByTestId("ai-checks")).getAllByText("아직 없음")).toHaveLength(2);
  });

  it("실행 옵션 저장에 실패하면 그 까닭이 그 「저장」 곁에 선다 — ⑥ 에 겹쳐 세우지 않는다(r23 설정 저장 왕복)", async () => {
    const user = userEvent.setup();
    const base = apiMock.getMockImplementation();
    apiMock.mockImplementation((path, opt) => {
      if (String(path) === "/api/admin/ai/config" && opt && opt.body && opt.body.timeout_seconds === 90) {
        return Promise.reject(Object.assign(new Error("제한 시간은 300초를 넘을 수 없습니다."), { status: 422 }));
      }
      return base(path, opt);
    });
    renderScreen();
    const timeout = await screen.findByLabelText("요청 제한 시간(초)");
    await user.clear(timeout);
    await user.type(timeout, "90");
    await user.click(screen.getByRole("button", { name: "저장" }));
    // 예전에는 오른쪽 열 ⑥ 에만 섰다 — 1366 에서 「저장」을 누른 사람의 화면 아래 82px 이었다(설정 저장 왕복 하네스).
    const failure = await screen.findByText(/제한 시간은 300초를 넘을 수 없습니다/);
    expect(failure.closest("[data-run-save-error]")).not.toBeNull();
    expect(failure.closest(".k-callout")).not.toBeNull();
    expect(within(checksSection()).queryByText(/제한 시간은 300초를 넘을 수 없습니다/)).toBeNull();
  });
});

describe("AI 연결 — 의미 검색 낱말 (서버가 짓는다)", () => {
  it("서버가 지은 낱말이 있으면 그 글을 그대로 쓴다", async () => {
    data = overview({ index: { documents: 3, chunks: 12, embedded: 0, semantic: false, embed_status: "model_missing",
      embed_status_label: "의미 검색 모델이 설치되지 않아 낱말로 찾습니다." } });
    renderScreen();
    await screen.findByTestId("ai-state");
    expect(screen.getByText("의미 검색 모델이 설치되지 않아 낱말로 찾습니다.")).toBeInTheDocument();
    expect(screen.getByText("model_missing")).toBeInTheDocument();
    expect(screen.queryByText("없음(낱말로 찾습니다)")).toBeNull();
  });

  it("새 색인 응답은 문서 수 · 조각 수를 글로 쓰고, 의미 검색을 켜는 문장은 단추 없이 글로 선다", async () => {
    data = overview({ index: {
      documents: { pending: 0, ok: 634, failed: 0 }, documents_total: 634, chunks: 2237, embedded: 0, pending_embedding: 2237,
      semantic: false, embed_status: "disabled", embed_status_label: "낱말 검색(의미 검색 기능 꺼짐, 모델 설치됨)",
      embed_hint: "의미 검색을 켜려면 서버에서 sudo clovirassist ai --with-ai 를 실행하세요.", model_installed: true,
    } });
    renderScreen();
    const card = await screen.findByTestId("ai-state");
    expect(within(card).getByText("634건, 조각 2237개")).toBeInTheDocument();
    expect(within(card).getByText("처리됨 634건, 기다림 0건, 실패 0건")).toBeInTheDocument();
    expect(card.textContent).not.toMatch(/object Object/);
    expect(within(card).getByText("낱말 검색(의미 검색 기능 꺼짐, 모델 설치됨)")).toBeInTheDocument();
    const hint = within(card).getByTestId("ai-embed-hint");
    expect(hint).toHaveTextContent("sudo clovirassist ai --with-ai");
    expect(within(hint).queryByRole("button")).toBeNull();
  });

  it("의미 검색이 켜져 있으면 벡터가 붙은 조각 수를 함께 쓰고 켜는 문장은 없다", async () => {
    data = overview({ index: {
      documents: { pending: 0, ok: 10, failed: 1 }, documents_total: 11, chunks: 40, embedded: 38, semantic: true,
      embed_status: "ok", embed_status_label: "의미 검색", embed_hint: "의미 검색을 켜려면 서버에서 명령을 실행하세요.",
    } });
    renderScreen();
    const card = await screen.findByTestId("ai-state");
    expect(within(card).getByText("11건, 조각 40개, 의미 검색에 쓰는 조각 38/40개")).toBeInTheDocument();
    expect(within(card).queryByTestId("ai-embed-hint")).toBeNull();
  });

  it("낱말이 없는 옛 응답이면 예전 낱말로 돌아간다", async () => {
    renderScreen();
    await screen.findByTestId("ai-state");
    expect(screen.getByText("없음(낱말로 찾습니다)")).toBeInTheDocument();
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
    data = overview({ config: { provider: "", auth_method: "", model: "" }, credentials: { ready: false, method: null, account_label: null },
      facts: [], next: { label: "AI 제공자를 아직 고르지 않았습니다.", action: "configure" } });
    renderScreen();
    expect(await screen.findByRole("switch", { name: "AI 사용" })).toBeDisabled();
    expect(screen.getByText("제공자를 연결하면 활성화할 수 있습니다.")).toBeInTheDocument();
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
    const timeout = screen.getByLabelText("요청 제한 시간(초)");
    await user.clear(timeout);
    await user.type(timeout, "90");
    expect(save).not.toBeDisabled();
    await user.click(save);
    await waitFor(() => expect(calls("/api/admin/ai/config", "PUT").some(([, o]) => o.body.timeout_seconds === 90)).toBe(true));
  });
});

describe("AI 연결 — 서버가 준 사실과 다음 할 일 (D-558 · D-566)", () => {
  it("자격이 없으면 모델 줄이 없고 다음 할 일 한 문장과 단추가 선다 - 같은 문장을 두 번 쓰지 않는다", async () => {
    const message = "ChatGPT 계정을 아직 연결하지 않았습니다.";
    data = overview({
      config: { provider: "openai", auth_method: "chatgpt", model: "gpt-5" },
      state: { state: "unconfigured", display: { key: "unconfigured", label: "미설정", kind: "muted", message } },
      credentials: { ready: false, method: "chatgpt", account_label: null },
      facts: [{ key: "provider", label: "제공자", value: "OpenAI" }, { key: "auth", label: "인증 방식", value: "ChatGPT 계정" }],
      next: { label: message, action: "login" },
    });
    const { container } = renderScreen();
    const card = await screen.findByTestId("ai-state");
    expect(within(card).getByText("미설정")).toBeInTheDocument();
    expect(within(card).queryByText("gpt-5")).toBeNull();
    expect(within(card).getAllByText(message)).toHaveLength(1);
    expect(within(card).getByText("다음 할 일")).toBeInTheDocument();
    expect(within(container.querySelector(".k-ai-next")).getByRole("button", { name: "ChatGPT 로그인" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "AI 사용" })).toBeDisabled();
    expect(screen.getByText("제공자를 연결하면 활성화할 수 있습니다.")).toBeInTheDocument();
    expect(within(checksSection()).getByRole("button", { name: "연결 확인" })).toBeDisabled();
    expect(within(checksSection()).getByText("제공자를 연결하고 모델을 고르면 확인할 수 있습니다.")).toBeInTheDocument();
  });

  it("다음 할 일이 확인이면 ⑥ 의 「지금 확인」 하나가 주 동작이고, 켜기면 다음 할 일 단추가 곧바로 켠다", async () => {
    const user = userEvent.setup();
    const { container, unmount } = renderScreen();
    await screen.findByTestId("ai-state");
    expect(within(container.querySelector(".k-ai-next")).queryByRole("button")).toBeNull();
    const verifyButtons = screen.getAllByRole("button", { name: "연결 확인" });
    expect(verifyButtons).toHaveLength(1);
    expect(verifyButtons[0].className).toMatch(/containedPrimary/);
    unmount();
    data = overview({ state: { display: { key: "off", label: "꺼짐", kind: "muted", message: "AI 사용이 꺼져 있어 AI 기능이 답을 만들지 않습니다." } },
      next: { label: "AI 사용을 켜면 도우미와 요약이 답을 만듭니다.", action: "enable" } });
    const second = renderScreen();
    await screen.findByTestId("ai-state");
    await user.click(within(second.container.querySelector(".k-ai-next")).getByRole("button", { name: "AI 사용 활성화" }));
    await waitFor(() => expect(calls("/api/admin/ai/config", "PUT").some(([, o]) => o.body.generation_enabled === true)).toBe(true));
  });

  it("OpenAI 는 모든 설치에서 API 키와 ChatGPT 계정 두 방식이 서고, API 키가 먼저다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("tab", { name: "OpenAI" }));
    const methods = within(screen.getByRole("tablist", { name: "인증 방식" })).getAllByRole("tab");
    expect(methods.map((t) => t.textContent)).toEqual(["API 키", "ChatGPT 계정"]);
    expect(screen.queryByTestId("chatgpt-disabled-note")).toBeNull();
    expect(screen.getByRole("link", { name: "OpenAI 키 발급처 열기" })).toHaveAttribute("href", "https://platform.openai.com/api-keys");
  });

  it("ChatGPT 계정을 고르면 요금제 공유 한 줄과 세 단계가 서고 바로 시작할 수 있다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("tab", { name: "OpenAI" }));
    await user.click(screen.getByRole("tab", { name: "ChatGPT 계정" }));
    expect(await screen.findByTestId("chatgpt-steps")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByRole("button", { name: /Continue with ChatGPT/ })).not.toBeDisabled();
  });
});
