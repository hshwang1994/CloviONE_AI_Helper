import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* ChatGPT 계정 로그인 — 세 단계 카드 + 새 창 승인 + 주소 붙여 넣기 자동 완료 (계획 A3, D-540 · D-566 · P3 ②).
 *
 * qa-contract-replaced-by: frontend/src/screens/settings/chatgpt-connect.test.jsx
 *
 * 옛 시험은 연결 도우미(명령 · 내려받기 · 단계 폴링)를 쟀다. 도우미는 걷었고 다시 들이지 않는다. 남는 약속 — 토큰 입력칸이
 * 없다, 공식 단추 문구를 쓴다, 처음 연결 안내를 한 번 보인다, 연결을 끊을 때 확인을 받는다 — 은 여기서 다시 잰다. 약속:
 *   1) 요금제 공유 안내 한 줄이 보이고 바로 시작할 수 있다(동의 체크 없음, D-566). 토큰 입력칸은 없다.
 *   2) 세 단계가 단추를 누르기 **전부터** 선다 — 둘째 단계가 「127.0.0.1 … 연결할 수 없습니다」 오류 화면이 정상이라고 먼저 말한다.
 *   3) 같은 클릭 안에서 새 창을 열고 opener 를 끊는다. 서버 응답이 오면 그 창을 승인 주소로 옮긴다. 막히면 링크를 준다.
 *   4) 맞는 주소를 붙여 넣는 순간 단추 없이 연결한다. 다른 시도의 주소 · 주소가 아닌 글은 한 문장으로 거절한다. 남은 시간을
 *      보이고, 만료되면 「다시 시작」이다.
 *   5) 연결되면 새 창을 닫고 단계 안내를 접어 「ChatGPT 계정으로 연결됨」 한 줄만 남긴다.
 *   6) 서버가 열린 시도를 알고 있으면(새로고침) 붙여 넣기 칸을 되찾는다. 서버가 `flow: "redirect"` 를 주면 같은 창이 승인으로 간다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import {
  ChatGptLogin, CONNECTED_LABEL, EXPIRED_TEXT, NOT_A_CALLBACK, PASTE_STEPS, PLAN_NOTICE, WRONG_ATTEMPT,
  matchAttempt,
} from "./ChatGptLogin.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const AUTHORIZE = "https://auth.openai.com/oauth/authorize?client_id=dynamic_agent_client&state=s1";
const REDIRECT = "http://127.0.0.1:51234/auth/callback";
const CALLBACK = `${REDIRECT}?code=c1&state=s1&client_id=oaiapp_1`;

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

async function begin(user) {
  await user.click(screen.getByRole("button", { name: /Continue with ChatGPT/ }));
  return screen.findByLabelText("주소 붙여 넣기");
}

async function paste(user, box, text) {
  await user.click(box);
  await user.paste(text);
}

let win;
let startReply;
beforeEach(() => {
  apiMock.mockReset();
  win = fakeWindow();
  vi.spyOn(window, "open").mockImplementation(() => win);
  startReply = { transaction_id: "tx-1", phase: "browser", flow: "paste", authorize_url: AUTHORIZE, redirect_uri: REDIRECT,
    expires_at: new Date(Date.now() + 10 * 60_000).toISOString() };
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

describe("ChatGPT 로그인 — 시작 전", () => {
  it("요금제 공유 안내 한 줄이 보이고 바로 시작할 수 있으며 토큰 입력칸이 없다", () => {
    renderLogin();
    expect(screen.getByText(PLAN_NOTICE)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByRole("button", { name: /Continue with ChatGPT/ })).not.toBeDisabled();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("세 단계가 단추를 누르기 전부터 서고, 둘째 단계가 오류 화면이 정상이라고 먼저 말한다", () => {
    const { container } = renderLogin();
    const steps = screen.getByTestId("chatgpt-steps");
    expect(PASTE_STEPS).toHaveLength(3);
    for (const step of PASTE_STEPS) expect(steps).toHaveTextContent(step);
    expect(PASTE_STEPS[1]).toMatch(/127\.0\.0\.1 … 서버에 연결할 수 없습니다/);
    expect(PASTE_STEPS[1]).toMatch(/정상입니다/);
    expect(container.textContent).not.toMatch(/PKCE|client id|OAuth|localhost|도우미|PowerShell/i);
  });
});

describe("ChatGPT 로그인 — 새 창", () => {
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

  it("브라우저가 창을 막으면 링크로 열 수 있다", async () => {
    const user = userEvent.setup();
    window.open.mockImplementation(() => null);
    renderLogin();
    await begin(user);
    expect(screen.getByText(/창이 열리지 않았습니다/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ChatGPT 승인 창 열기" })).toHaveAttribute("href", AUTHORIZE);
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

describe("ChatGPT 로그인 — 붙여 넣기", () => {
  it("맞는 주소를 붙여 넣는 순간 단추 없이 연결하고, 새 창을 닫고 단계 안내를 접는다", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    renderLogin({ onConnected });
    const box = await begin(user);
    expect(screen.getByText(/남은 시간 \d+:\d\d/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "연결" })).toBeNull();
    await paste(user, box, CALLBACK);
    await waitFor(() => expect(onConnected).toHaveBeenCalledWith(expect.objectContaining({ verify_job_id: "j-1" })));
    expect(win.close).toHaveBeenCalled();
    expect(screen.queryByTestId("chatgpt-paste-steps")).toBeNull();
    const sent = apiMock.mock.calls.filter(([p]) => String(p).endsWith("/complete"));
    expect(sent).toHaveLength(1);
    expect(sent[0][1].body).toEqual({ callback_url: CALLBACK });
  });

  it("다른 시도의 주소와 주소가 아닌 글은 한 문장으로 거절하고 연결을 부르지 않는다", async () => {
    const user = userEvent.setup();
    renderLogin();
    const box = await begin(user);
    await paste(user, box, "http://127.0.0.1:60000/auth/callback?code=c1&state=s1");
    expect(await screen.findByText(WRONG_ATTEMPT)).toBeInTheDocument();
    await user.clear(box);
    await paste(user, box, `${REDIRECT}?code=c1&state=other`);
    expect(await screen.findByText(WRONG_ATTEMPT)).toBeInTheDocument();
    await user.clear(box);
    await paste(user, box, "https://chatgpt.com/auth/login");
    expect(await screen.findByText(NOT_A_CALLBACK)).toBeInTheDocument();
    expect(apiMock.mock.calls.some(([p]) => String(p).endsWith("/complete"))).toBe(false);
  });

  it("붙여넣기 단추는 클립보드를 읽고, 막히면 Ctrl+V 를 안내한다", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    renderLogin({ onConnected });
    await begin(user);
    const read = vi.fn().mockRejectedValueOnce(new Error("denied")).mockResolvedValueOnce(CALLBACK);
    Object.defineProperty(navigator, "clipboard", { value: { readText: read }, configurable: true });
    await user.click(screen.getByRole("button", { name: "붙여넣기" }));
    expect(await screen.findByText("붙여넣기 단추를 쓸 수 없습니다. 칸을 누르고 Ctrl+V 를 누르세요.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "붙여넣기" }));
    await waitFor(() => expect(onConnected).toHaveBeenCalled());
  });

  it("시도가 만료되면 붙여 넣을 수 없고 다시 시작한다", async () => {
    const user = userEvent.setup();
    startReply = { ...startReply, expires_at: new Date(Date.now() - 1000).toISOString() };
    renderLogin();
    const box = await begin(user);
    expect(await screen.findByText(EXPIRED_TEXT)).toBeInTheDocument();
    expect(box).toBeDisabled();
    startReply = { ...startReply, transaction_id: "tx-2", expires_at: new Date(Date.now() + 60_000).toISOString() };
    await user.click(screen.getByRole("button", { name: "다시 시작" }));
    await waitFor(() => expect(apiMock.mock.calls.filter(([p]) => String(p).endsWith("/start"))).toHaveLength(2));
    expect(await screen.findByText(/남은 시간/)).toBeInTheDocument();
  });

  it("서버가 열린 시도를 알고 있으면 붙여 넣기 칸을 되찾는다", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    renderLogin({ onConnected, login: { open: true, transaction_id: "tx-1", expires_at: new Date(Date.now() + 60_000).toISOString() } });
    const box = await screen.findByLabelText("주소 붙여 넣기");
    expect(screen.getByText(/앞서 시작한 로그인이 아직 열려 있습니다/)).toBeInTheDocument();
    await paste(user, box, CALLBACK);
    await waitFor(() => expect(onConnected).toHaveBeenCalled());
  });
});

describe("ChatGPT 로그인 — 연결된 뒤", () => {
  it("연결돼 있으면 한 줄과 다시 로그인 · 연결 끊기만 있고 계정 주소는 보이지 않는다", async () => {
    const user = userEvent.setup();
    const onLoggedOut = vi.fn();
    renderLogin({ chatgpt: { connected: true, account_label: "owner@example.com" }, onLoggedOut });
    expect(screen.getByText(CONNECTED_LABEL)).toBeInTheDocument();
    expect(screen.queryByText("owner@example.com")).toBeNull();
    expect(screen.queryByTestId("chatgpt-steps")).toBeNull();
    expect(screen.getByRole("button", { name: "다시 로그인" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "연결 끊기" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "연결 끊기" }));
    await waitFor(() => expect(onLoggedOut).toHaveBeenCalled());
  });
});

describe("matchAttempt", () => {
  const attempt = { redirect_uri: REDIRECT, authorize_url: AUTHORIZE };
  it("모양 · 포트 · state 를 맞춰 보고, 짧은 글에는 아직 아무 말도 하지 않는다", () => {
    expect(matchAttempt("", attempt)).toEqual({ ok: false, note: null });
    expect(matchAttempt("http://127", attempt)).toEqual({ ok: false, note: null });
    expect(matchAttempt(`  ${CALLBACK}  `, attempt)).toEqual({ ok: true, url: CALLBACK });
    expect(matchAttempt("http://127.0.0.1:60000/auth/callback?code=c&state=s1", attempt).note).toBe(WRONG_ATTEMPT);
    expect(matchAttempt(`${REDIRECT}?code=c&state=zz`, attempt).note).toBe(WRONG_ATTEMPT);
    expect(matchAttempt("https://chatgpt.com/auth/login?x=1", attempt).note).toBe(NOT_A_CALLBACK);
    expect(matchAttempt(CALLBACK, { transaction_id: "tx" })).toEqual({ ok: true, url: CALLBACK });
  });
});

describe("ChatGPT 로그인 — 만료 시각 규약과 붙여 넣은 글 (랩에서 본 결함, 2026-10-13)", () => {
  it("서버가 Z 없이 준 UTC 만료 시각을 지역 시각으로 읽지 않는다 — 한국에서 9시간 일찍 「만료」가 되던 결함", async () => {
    const user = userEvent.setup();
    startReply = { ...startReply, expires_at: new Date(Date.now() + 10 * 60_000).toISOString().replace(/Z$/, "") };
    renderLogin();
    const box = await begin(user);
    expect(box).not.toBeDisabled();
    expect(screen.queryByText(EXPIRED_TEXT)).toBeNull();
    expect(screen.getByText(/남은 시간 (9:5\d|10:00)/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시작" })).toBeNull();
  });

  it("오류 화면의 글을 통째로 붙여 넣어도 그 안의 주소를 찾아 연결한다", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    renderLogin({ onConnected });
    const box = await begin(user);
    await paste(user, box, `Firefox가 127.0.0.1:51234 서버에 연결할 수 없습니다. ${CALLBACK} 다시 시도`);
    await waitFor(() => expect(onConnected).toHaveBeenCalled());
    const sent = apiMock.mock.calls.filter(([p]) => String(p).endsWith("/complete"));
    expect(sent[0][1].body).toEqual({ callback_url: CALLBACK });
  });

  it("matchAttempt 는 글 안의 주소를 찾고, 주소가 없으면 그대로 거절한다", () => {
    const attempt = { redirect_uri: REDIRECT, authorize_url: AUTHORIZE };
    expect(matchAttempt(`앞 글 ${CALLBACK} 뒤 글`, attempt)).toEqual({ ok: true, url: CALLBACK });
    expect(matchAttempt("Firefox가 서버에 연결할 수 없습니다. 주소가 없음", attempt).note).toBe(NOT_A_CALLBACK);
  });
});
