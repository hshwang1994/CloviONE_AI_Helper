import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* ChatGPT 계정 연결 (계획 3.14 · 3.15, D-516).
 *
 * 못박는 것:
 *   1) OpenAI 의 ChatGPT 계정 방식에는 토큰 입력칸이 없고 「Continue with ChatGPT」만 있다. Anthropic 에는 없다.
 *   2) 시작하면 서버가 준 명령과 도우미 파일을 보이고, 서버의 단계(도우미 대기 → 브라우저 승인 → 연결됨)를 따라 그린다.
 *   3) 처음 연결하면 공식 안내(You're using your ChatGPT plan)를 한 번 보인다.
 *   4) 연결돼 있으면 「Using ChatGPT plan」과 계정, 「Manage usage」를 보이고, 로그아웃은 확인을 받은 뒤 보낸다.
 *   5) 요금제 한도에 닿았으면 「Manage usage」를 주 동작으로 권한다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { AiSettings } from "./AiSettings.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const OPENAI = {
  key: "openai", label: "OpenAI", help: "OpenAI 는 API 키나 ChatGPT 계정으로 연결할 수 있습니다.",
  auth_methods: [
    { key: "api_key", label: "API 키", help: "키", secret_slot: "ai.openai.api_key", account: false, secret_set: false, secret_hint: null },
    { key: "chatgpt", label: "ChatGPT 계정", help: "요금제", secret_slot: "ai.openai.chatgpt", account: true, secret_set: false, secret_hint: null },
  ],
};
const ANTHROPIC = {
  key: "anthropic", label: "Anthropic", help: "Anthropic 은 조직 API 키로만 연결할 수 있습니다.",
  auth_methods: [{ key: "api_key", label: "API 키", help: "키", secret_slot: "ai.anthropic.api_key", account: false, secret_set: true, secret_hint: null }],
};

function overview({ provider = "openai", auth = "chatgpt", chatgpt = {}, state = {} } = {}) {
  return {
    config: { generation_enabled: false, provider, auth_method: auth, model: "", timeout_seconds: 60, max_concurrency: 2 },
    state: { state: "unconfigured", label: "미설정", message: "정하지 않은 것이 있습니다.", problems: [], reason: null,
      reason_code: null, checked_at: null, last_success_at: null, ...state },
    providers: [ANTHROPIC, OPENAI],
    features: { chat_enabled: true, assistant_narrative_enabled: false, game_ai_enabled: false },
    limits: { timeout_seconds: [5, 300], max_concurrency: [1, 8] },
    chatgpt: { connected: false, disconnected: false, account_label: null, manage_usage_url: "https://chatgpt.com/settings/usage", ...chatgpt },
    token_settings: { ai_openai_access_ttl_fallback_seconds: 3600, ai_openai_refresh_ttl_fallback_days: 30, ai_token_refresh_lead_seconds: 300 },
    proxy: null,
  };
}

const START = {
  transaction_id: "tx-1", phase: "waiting_helper", message: "연결 도우미를 기다리고 있습니다.", expires_at: "2026-09-30T12:10:00",
  server_url: "https://clovirassist.example", fingerprint: "sha256:" + "ab".repeat(32),
  commands: {
    windows: 'powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\\Downloads\\clovirassist-connect.ps1" -Server "https://clovirassist.example" -Token "TOKEN-1"',
    unix: "python3 ~/Downloads/clovirassist-connect.py --server https://clovirassist.example --token TOKEN-1",
  },
  downloads: [
    { name: "clovirassist-connect.ps1", href: "/connect/clovirassist-connect.ps1", sha256: "1".repeat(64) },
    { name: "clovirassist-connect.py", href: "/connect/clovirassist-connect.py", sha256: "2".repeat(64) },
  ],
};

let phases = [];

function route(data) {
  apiMock.mockImplementation((path, opt) => {
    const p = String(path);
    if (p === "/api/admin/ai") return Promise.resolve(data);
    if (p === "/api/admin/ai/oauth/openai/start") return Promise.resolve(START);
    if (p === "/api/admin/ai/oauth/openai/transactions/tx-1") {
      const phase = phases.length > 1 ? phases.shift() : phases[0];
      return Promise.resolve({ transaction_id: "tx-1", phase, message: phase === "done" ? "ChatGPT 계정을 연결했습니다." : "기다리는 중입니다.",
        account_label: phase === "done" ? "owner@example.com" : null, expires_at: START.expires_at, error_code: null });
    }
    if (p === "/api/admin/ai/oauth/openai/logout") return Promise.resolve({ revoked: true, removed: true, message: "ChatGPT 계정 연결을 끊었습니다." });
    if (p.startsWith("/api/admin/secrets")) return Promise.resolve({ items: [] });
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
  phases = ["waiting_helper"];
  try { window.localStorage.clear(); } catch (e) { /* 저장소가 없는 환경 */ }
});

describe("ChatGPT 계정 연결", () => {
  it("ChatGPT 방식에는 토큰 입력칸이 없고 공식 로그인 단추만 있다", async () => {
    route(overview());
    renderScreen();
    expect(await screen.findByRole("button", { name: "Continue with ChatGPT" })).toBeInTheDocument();
    // 토큰을 붙여 넣는 비밀 칸이 없다 - 계정 연결은 로그인으로만 채운다.
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(screen.queryByRole("button", { name: "ChatGPT 계정 저장" })).toBeNull();
  });

  it("Anthropic 에는 계정 로그인 단추가 없다", async () => {
    route(overview({ provider: "anthropic", auth: "api_key" }));
    renderScreen();
    expect(await screen.findByText(/조직 API 키로만 연결할 수 있습니다/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue with ChatGPT" })).toBeNull();
  });

  it("시작하면 명령과 도우미를 보이고, 서버의 단계를 따라가다 처음 연결 안내를 한 번 보인다", async () => {
    const user = userEvent.setup();
    phases = ["waiting_helper", "browser", "done"];
    route(overview());
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "Continue with ChatGPT" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/ai/oauth/openai/start", { method: "POST" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("tab", { name: "Windows" }));
    expect(within(dialog).getByRole("textbox", { name: "실행할 명령" }).value).toContain("clovirassist-connect.ps1");
    const link = within(dialog).getByRole("link", { name: /clovirassist-connect\.ps1 내려받기/ });
    expect(link.getAttribute("href")).toBe("/connect/clovirassist-connect.ps1");
    expect(within(dialog).getByText(/도우미를 실행할 수 없을 때/)).toBeInTheDocument();
    expect(await screen.findByText("You're using your ChatGPT plan", {}, { timeout: 6000 })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Got it" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(window.localStorage.getItem("clovirassist.chatgpt-plan-notice")).toBe("1");
  }, 15000);

  it("연결돼 있으면 요금제 사용 표시와 사용량 관리, 확인을 받는 로그아웃이 있다", async () => {
    const user = userEvent.setup();
    route(overview({ chatgpt: { connected: true, account_label: "owner@example.com", access_expires_at: "2026-09-30T13:00:00", refresh_expires_at: "2026-10-30T12:00:00", expiry_source: "expires_in+fallback" } }));
    renderScreen();
    expect(await screen.findByText("Using ChatGPT plan")).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage usage" }).getAttribute("href")).toBe("https://chatgpt.com/settings/usage");
    await user.click(screen.getByRole("button", { name: "로그아웃" }));
    expect(apiMock.mock.calls.some(([p]) => p === "/api/admin/ai/oauth/openai/logout")).toBe(false);
    await user.click(await screen.findByRole("button", { name: "연결 끊기" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/ai/oauth/openai/logout", { method: "POST" }));
  });

  it("요금제 한도에 닿았으면 사용량 관리를 주 동작으로 권한다", async () => {
    route(overview({ chatgpt: { connected: true, account_label: "owner@example.com" },
      state: { state: "degraded", label: "일시 장애", reason_code: "plan_usage_limit", reason: "ChatGPT 요금제 사용량 한도에 닿았습니다." } }));
    renderScreen();
    expect(await screen.findByText(/한도가 풀리면 다음 호출부터 다시 답합니다/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Manage usage" }).length).toBe(2);
  });
});
