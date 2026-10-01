import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* ChatGPT 계정 로그인 — 새 창 승인 + 주소 붙여 넣기 (계획 A3, D-540).
 *
 * qa-contract-replaced-by: frontend/src/screens/settings/chatgpt-connect.test.jsx
 *
 * 옛 시험은 연결 도우미(명령 · 내려받기 · 단계 폴링)를 쟀다. 도우미는 걷었고 다시 들이지 않는다. 남는 약속 — 토큰 입력칸이
 * 없다, 공식 단추 문구를 쓴다, 처음 연결 안내를 한 번 보인다, 연결을 끊을 때 확인을 받는다 — 은 여기서 다시 잰다. 새 약속:
 *   1) 같은 클릭 안에서 새 창을 열고 opener 를 끊는다. 서버 응답이 오면 그 창을 승인 주소로 옮긴다.
 *   2) 안내는 세 문장이다. 일반 화면에 PKCE · client id · OAuth · localhost 낱말이 없다.
 *   3) 「붙여넣기」는 클립보드를 읽고, 브라우저가 막으면 Ctrl+V 를 안내한다.
 *   4) 연결되면 새 창을 닫고 단계 안내를 접어 「ChatGPT 계정으로 연결됨」 한 줄만 남긴다.
 *   5) 서버가 `flow: "redirect"` 를 주면 같은 창이 승인으로 간다(새 창을 닫는다).
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatGptLogin, PASTE_STEPS, SHARED_PLAN_NOTICE } from "./ChatGptLogin.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const AUTHORIZE = "https://auth.openai.com/oauth/authorize?client_id=dynamic_agent_client&state=s1";
const CALLBACK = "http://127.0.0.1:51234/auth/callback?code=c1&state=s1&client_id=oaiapp_1";

function fakeWindow() {
  return { opener: { real: true }, closed: false, location: { href: "about:blank" }, close: vi.fn(function close() { this.closed = true; }) };
}

function renderLogin(props = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <ChatGptLogin chatgpt={{ connected: false, disconnected: false, flow: "paste" }} {...props} />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

let win;
let startReply;
beforeEach(() => {
  apiMock.mockReset();
  win = fakeWindow();
  vi.spyOn(window, "open").mockImplementation(() => win);
  startReply = { transaction_id: "tx-1", phase: "browser", flow: "paste", authorize_url: AUTHORIZE,
    redirect_uri: "http://127.0.0.1:51234/auth/callback" };
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p === "/api/admin/ai/oauth/openai/start") return Promise.resolve(startReply);
    if (p === "/api/admin/ai/oauth/openai/transactions/tx-1/complete") {
      return Promise.resolve({ ok: true, account_label: "owner@example.com", verify_job_id: "j-1" });
    }
    if (p === "/api/admin/ai/oauth/openai/logout") return Promise.resolve({ revoked: true, removed: true, message: "끊었습니다." });
    return Promise.resolve({});
  });
  try { window.localStorage.setItem("clovirassist.chatgpt-plan-notice", "1"); } catch (e) { /* 없음 */ }
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChatGPT 로그인", () => {
  it("연결 전에는 요금제를 함께 쓴다는 주의와 공식 단추만 있고 토큰 입력칸이 없다", () => {
    renderLogin();
    expect(screen.getByText(SHARED_PLAN_NOTICE)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue with ChatGPT/ })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("같은 클릭 안에서 새 창을 열고 opener 를 끊은 뒤 응답이 오면 승인 주소로 옮긴다", async () => {
    const user = userEvent.setup();
    let release;
    apiMock.mockImplementation((path) => (String(path).endsWith("/start")
      ? new Promise((resolve) => { release = () => resolve(startReply); }) : Promise.resolve({})));
    renderLogin();
    await user.click(screen.getByRole("button", { name: /Continue with ChatGPT/ }));
    expect(window.open).toHaveBeenCalledWith("about:blank", "_blank");
    expect(win.opener).toBeNull();
    expect(win.location.href).toBe("about:blank");
    release();
    await waitFor(() => expect(win.location.href).toBe(AUTHORIZE));
  });

  it("안내는 세 문장이고 일반 화면에 기술 낱말이 없다", async () => {
    const user = userEvent.setup();
    const { container } = renderLogin();
    await user.click(screen.getByRole("button", { name: /Continue with ChatGPT/ }));
    const steps = await screen.findByTestId("chatgpt-paste-steps");
    expect(PASTE_STEPS).toHaveLength(3);
    for (const step of PASTE_STEPS) expect(steps).toHaveTextContent(step);
    expect(screen.getByText("승인 뒤 새 창에 오류 화면이 보여도 정상입니다.")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/PKCE|client id|OAuth|localhost|도우미|PowerShell/i);
  });

  it("붙여넣기 단추는 클립보드를 읽고, 막히면 Ctrl+V 를 안내한다", async () => {
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole("button", { name: /Continue with ChatGPT/ }));
    await screen.findByTestId("chatgpt-paste-steps");
    const read = vi.fn().mockResolvedValueOnce(CALLBACK).mockRejectedValueOnce(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", { value: { readText: read }, configurable: true });
    await user.click(screen.getByRole("button", { name: "붙여넣기" }));
    await waitFor(() => expect(screen.getByLabelText("주소 붙여 넣기")).toHaveValue(CALLBACK));
    await user.click(screen.getByRole("button", { name: "붙여넣기" }));
    expect(await screen.findByText("붙여넣기 단추를 쓸 수 없습니다. 칸을 누르고 Ctrl+V 를 누르세요.")).toBeInTheDocument();
  });

  it("연결되면 새 창을 닫고 단계 안내를 접는다", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    renderLogin({ onConnected });
    await user.click(screen.getByRole("button", { name: /Continue with ChatGPT/ }));
    const box = await screen.findByLabelText("주소 붙여 넣기");
    const connect = screen.getByRole("button", { name: "연결" });
    expect(connect).toBeDisabled();
    await user.type(box, CALLBACK);
    await user.click(connect);
    await waitFor(() => expect(onConnected).toHaveBeenCalledWith(expect.objectContaining({ verify_job_id: "j-1" })));
    expect(win.close).toHaveBeenCalled();
    expect(screen.queryByTestId("chatgpt-paste-steps")).toBeNull();
    const sent = apiMock.mock.calls.find(([p]) => String(p).endsWith("/complete"));
    expect(sent[1].body).toEqual({ callback_url: CALLBACK });
  });

  it("연결돼 있으면 한 줄과 다시 로그인 · 연결 끊기만 있고 계정 주소는 보이지 않는다", async () => {
    const user = userEvent.setup();
    const onLoggedOut = vi.fn();
    renderLogin({ chatgpt: { connected: true, account_label: "owner@example.com" }, onLoggedOut });
    expect(screen.getByText("ChatGPT 계정으로 연결됨")).toBeInTheDocument();
    expect(screen.queryByText("owner@example.com")).toBeNull();
    expect(screen.getByRole("button", { name: "다시 로그인" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "연결 끊기" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "연결 끊기" }));
    await waitFor(() => expect(onLoggedOut).toHaveBeenCalled());
  });

  it("서버가 redirect 흐름을 주면 같은 창이 승인으로 간다", async () => {
    const user = userEvent.setup();
    const redirect = vi.fn();
    startReply = { ...startReply, flow: "redirect" };
    renderLogin({ redirect });
    await user.click(screen.getByRole("button", { name: /Continue with ChatGPT/ }));
    await waitFor(() => expect(redirect).toHaveBeenCalledWith(AUTHORIZE));
    expect(win.close).toHaveBeenCalled();
    expect(screen.queryByTestId("chatgpt-paste-steps")).toBeNull();
  });
});
