import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* AI 설정 화면 (계획 3.13 · 3.14, D-515).
 *
 * qa-contract-replaced-by: frontend/src/screens/llm-console.test.jsx
 *
 * 옛 화면의 시험(명령줄 도구 로그인 안내, 서버 환경 변수 값의 출처, 사용 여부 세 상태)은 그 기능과 함께 사라졌다.
 * 남는 약속 — 큐에 있는 동안 결과를 지어내지 않는다, 결과 문장은 서버가 준 것을 쓴다, 저장은 바뀐 값만 보낸다 — 은
 * 여기서 다시 잰다. 새로 못박는 것:
 *   1) 제공자가 지원하는 인증 방식만 그린다. Anthropic 에는 계정 로그인 칸이 없다.
 *   2) 연결 상태 배지는 서버의 판정이다(여섯 상태). 설정만 보고 「정상」을 그리지 않는다.
 *   3) 저장은 바뀐 값만, 연결 확인은 잡이다. 저장하지 않은 변경이 있으면 연결 확인을 누를 수 없다.
 *   4) AI 기능 스위치는 설정 API 로 곧바로 저장한다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { AiSettings } from "./AiSettings.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

function overview(over = {}) {
  return {
    config: { generation_enabled: false, provider: "anthropic", auth_method: "api_key", model: "claude-old",
      timeout_seconds: 60, max_concurrency: 2 },
    state: { state: "unverified", label: "확인 전", message: "설정을 저장했지만 아직 연결을 확인하지 않았습니다.",
      problems: [], reason: null, checked_at: null, last_success_at: null },
    providers: [{
      key: "anthropic", label: "Anthropic", help: "Anthropic 은 조직 API 키로만 연결할 수 있습니다.",
      auth_methods: [{ key: "api_key", label: "API 키", help: "조직 API 키를 넣습니다.", secret_slot: "ai.anthropic.api_key",
        secret_set: true, secret_hint: "끝자리 WXYZ" }],
    }],
    features: { chat_enabled: true, assistant_narrative_enabled: false, game_ai_enabled: false },
    limits: { timeout_seconds: [5, 300], max_concurrency: [1, 8] },
    ...over,
  };
}

let verifyReplies = [];

function route(data) {
  apiMock.mockImplementation((path, opt) => {
    const p = String(path);
    if (p === "/api/admin/ai") return Promise.resolve(data);
    if (p === "/api/admin/ai/config") return Promise.resolve({ ...data, config: { ...data.config, ...(opt && opt.body) } });
    if (p.startsWith("/api/admin/ai/models")) return Promise.resolve({ models: [{ id: "claude-a", label: "Claude A" }] });
    if (p === "/api/admin/ai/verify") return Promise.resolve({ job_id: "j-1", status: "queued" });
    if (p === "/api/admin/ai/verify/j-1") return Promise.resolve(verifyReplies.shift() || { job_id: "j-1", pending: true, result: null });
    if (p.startsWith("/api/admin/secrets")) return Promise.resolve({ items: [{ slot: "ai.anthropic.api_key", stored: true, updated_at: null }] });
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
            <MemoryRouter initialEntries={["/settings?tab=ai"]}>
              <AiSettings />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  verifyReplies = [];
  route(overview());
});

describe("AI 설정", () => {
  it("연결 상태 배지는 서버가 판정한 상태다 — 설정만 보고 정상을 그리지 않는다", async () => {
    renderScreen();
    expect(await screen.findByText("확인 전")).toBeInTheDocument();
    expect(screen.getByText(/아직 성공한 호출이 없습니다/)).toBeInTheDocument();
    expect(screen.queryByText("정상")).toBeNull();
  });

  it("Anthropic 에는 API 키 칸만 있다 — 계정 로그인은 공식 정책이 금지한다", async () => {
    renderScreen();
    expect(await screen.findByText(/조직 API 키로만 연결할 수 있습니다/)).toBeInTheDocument();
    expect(screen.getAllByText("API 키").length).toBeGreaterThan(0);
    expect(screen.queryByText(/계정 로그인/)).toBeNull();
    expect(screen.queryByRole("combobox", { name: "인증 방식" })).toBeNull();
    expect(screen.getByText(/끝자리 WXYZ/)).toBeInTheDocument();
  });

  it("저장은 바뀐 값만 보내고, 저장 전에는 연결 확인을 누를 수 없다", async () => {
    const user = userEvent.setup();
    renderScreen();
    const model = await screen.findByRole("textbox", { name: "모델" });
    await user.clear(model);
    await user.type(model, "claude-new");
    expect(screen.getByRole("button", { name: "연결 확인" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/ai/config", {
      method: "PUT", body: { model: "claude-new" },
    }));
  });

  it("AI 답변 생성 스위치는 저장을 눌러야 적용되고, 기능 스위치는 곧바로 설정 API 로 간다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("switch", { name: "AI 채팅" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/settings/chat_enabled", {
      method: "PUT", body: { value: false },
    }));
    await user.click(screen.getByRole("switch", { name: "AI 답변 생성" }));
    expect(apiMock.mock.calls.some(([p]) => p === "/api/admin/ai/config")).toBe(false);
    await user.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/ai/config", {
      method: "PUT", body: { generation_enabled: true },
    }));
  });

  /* D-525 — 저장 중에 다른 기능 스위치를 끄지 않는다. 예전에는 한 기능을 저장하는 동안 셋 모두가 비활성이었다. */
  it("기능 스위치는 저장이 도는 동안에도 켜져 있고 누른 순간 바뀐다", async () => {
    const user = userEvent.setup();
    const base = apiMock.getMockImplementation();
    let release = () => {};
    apiMock.mockImplementation((path, opt) => {
      if (String(path).startsWith("/api/admin/settings/") && opt && opt.method === "PUT") {
        return new Promise((resolve) => { release = () => resolve({}); });
      }
      return base(path, opt);
    });
    renderScreen();
    const chat = await screen.findByRole("switch", { name: "AI 채팅" });
    const narrative = screen.getByRole("switch", { name: "홈 AI 문장 요약" });
    expect(chat).toBeChecked();
    await user.click(chat);
    expect(chat).not.toBeChecked();
    expect(chat).toBeEnabled();
    expect(narrative).toBeEnabled();
    expect(apiMock).toHaveBeenCalledWith("/api/admin/settings/chat_enabled", { method: "PUT", body: { value: false } });
    await act(async () => { release(); });
  });

  it("모델 불러오기는 제공자의 목록을 받아 고르게 한다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "모델 불러오기" }));
    await waitFor(() => expect(apiMock.mock.calls.some(([p]) =>
      String(p) === "/api/admin/ai/models?provider=anthropic&auth_method=api_key")).toBe(true));
    expect(await screen.findByRole("combobox", { name: "모델" })).toBeInTheDocument();
  });

  it("연결 확인은 큐에 있는 동안 결과를 지어내지 않고, 실패하면 서버가 준 까닭을 말한다", async () => {
    const user = userEvent.setup();
    verifyReplies = [
      { job_id: "j-1", pending: true, result: null },
      { job_id: "j-1", pending: false, result: { ok: false, message: "API 키가 거부되었습니다. 키를 다시 넣으세요." } },
    ];
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "연결 확인" }));
    expect(screen.queryByText(/API 키가 거부되었습니다/)).toBeNull();
    expect(await screen.findByText(/연결 확인에 실패했습니다\. API 키가 거부되었습니다/, {}, { timeout: 5000 }))
      .toBeInTheDocument();
  });
});
