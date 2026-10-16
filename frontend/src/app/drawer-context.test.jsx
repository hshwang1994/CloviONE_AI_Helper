/* 서랍의 화면 대상 — 지금 보는 티켓 · 프로젝트 · 문서 한 건을 기준으로 묻는다 (D-538).
 *
 * qa-contract-replaced-by: frontend/src/app/assistant-drawer.test.jsx
 *
 * 옛 시험은 「현재 문맥: 내 티켓」 같은 화면 이름 표의 계약을 지켰다. 그 이름은 서버가 쓰지 않는 장식이었다 — 목록 화면을
 * 기준으로 답한다고 약속할 근거가 없다. 이제 문맥 줄은 대상이 있을 때만 서고, 그 대상이 메시지와 함께 서버로 가며(서버가
 * 권한으로 다시 읽는다), AI 를 쓸 수 없는 사람에게는 서랍 단추 자체가 없다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
const authState = { data: { role: "user", id: "u1" } };
vi.mock("./auth.jsx", () => ({ useAuth: () => authState }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV, navWithFeatures } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { screenContextLine, screenTargetFor } from "../screens/chat/screenContext.js";

function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query), media: query,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    onchange: null, dispatchEvent: () => false,
  });
}

function renderShell(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={USER_NAV} ariaLabel="사용자 메뉴" isUser showMenu>
                <div>본문</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function openDrawer() {
  await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
  fireEvent.click(screen.getAllByLabelText("클로비 AI 도우미 열기")[0]);
  return screen.findByLabelText("클로비에게 질문");
}

function api({ status } = {}) {
  return (path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (path.startsWith("/api/team-chat/rooms")) return Promise.resolve({ items: [], global: null, unread_total: 0 });
    if (path.startsWith("/api/notifications")) return Promise.resolve({ items: [], unread: 0, badge: 0, by_type: {} });
    if (path === "/api/ai/status") return Promise.resolve(status || { assistant: { available: true, reason: null } });
    if (path.startsWith("/api/conversations?") && method === "GET") return Promise.resolve({ items: [] });
    if (path === "/api/conversations" && method === "POST") return Promise.resolve({ conversation: { id: "c9", title: "새 대화" } });
    if (path === "/api/conversations/c9/messages" && method === "POST") {
      return Promise.resolve({ message: { id: "m1", role: "user", content: "x", processing_status: "pending" }, job_id: "j1" });
    }
    if (path === "/api/conversations/c9/messages") return Promise.resolve({ items: [] });
    return Promise.resolve({});
  };
}

describe("화면 대상", () => {
  it("상세 한 건만 대상이다 — 목록 · 하위 경로 · 이상한 값은 대상이 아니다", () => {
    expect(screenTargetFor("/tickets/abc-123")).toEqual({ kind: "ticket", ref: "abc-123", label: "티켓" });
    expect(screenTargetFor("/projects/p1")).toEqual({ kind: "project", ref: "p1", label: "프로젝트" });
    expect(screenTargetFor("/knowledge/d1")).toEqual({ kind: "document", ref: "d1", label: "문서" });
    for (const path of ["/my-tickets", "/tickets", "/tickets/a/edit", "/knowledge", "/tickets/a b", "", undefined]) {
      expect(screenTargetFor(path)).toBeNull();
    }
  });

  it("문맥 줄은 대상의 이름에 맞는 조사를 쓴다", () => {
    expect(screenContextLine(screenTargetFor("/tickets/t1"))).toBe("지금 보는 티켓을 기준으로 물어볼 수 있습니다.");
    expect(screenContextLine(screenTargetFor("/projects/p1"))).toBe("지금 보는 프로젝트를 기준으로 물어볼 수 있습니다.");
    expect(screenContextLine(null)).toBe("");
  });
});

describe("서랍", () => {
  beforeEach(() => {
    apiMock.mockReset();
    authState.data = { role: "user", id: "u1" };
    wideViewport();
  });

  it("티켓 상세에서는 문맥 줄과 티켓 제안이 서고, 대상이 메시지와 함께 간다", async () => {
    apiMock.mockImplementation(api());
    renderShell("/tickets/t-9");
    const box = await openDrawer();
    expect(screen.getAllByText("지금 보는 티켓을 기준으로 물어볼 수 있습니다.").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "이 티켓을 요약해 줘" })).toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(box, "요약해 줘");
    await user.click(screen.getByRole("button", { name: "질문 전송" }));
    await waitFor(() => {
      const sent = apiMock.mock.calls.find(([path, opts]) => path === "/api/conversations/c9/messages" && opts && opts.method === "POST");
      expect(sent).toBeTruthy();
      expect(sent[1].body.screen_context).toEqual({ kind: "ticket", ref: "t-9", label: "티켓" });
    });
  });

  it("목록 화면에서는 문맥 줄을 세우지 않는다", async () => {
    apiMock.mockImplementation(api());
    renderShell("/my-tickets");
    await openDrawer();
    expect(screen.queryByText(/기준으로 물어볼 수 있습니다/)).toBeNull();
    expect(screen.getByRole("button", { name: "오늘 내가 할 일을 정리해 줘" })).toBeInTheDocument();
  });

  it("AI 를 쓸 수 없으면 까닭을 말하고 입력 칸을 막는다", async () => {
    apiMock.mockImplementation(api({ status: { assistant: {
      available: false, reason: "unconfigured", notice: "AI 가 아직 연결되지 않았습니다.", mode: "unknown", can_configure: false,
    } } }));
    renderShell("/my-tickets");
    const box = await openDrawer();
    expect(await screen.findByText("AI 가 아직 연결되지 않았습니다.")).toBeInTheDocument();
    expect(screen.getByText("관리자가 AI를 연결하면 쓸 수 있습니다.")).toBeInTheDocument();
    await waitFor(() => expect(box).toBeDisabled());
    expect(screen.queryByRole("link", { name: "AI 연결 열기" })).toBeNull();
  });

  it("AI 사용 권한이 없는 사람에게는 서랍 단추가 없고 메뉴에서도 빠진다", async () => {
    apiMock.mockImplementation(api());
    authState.data = { role: "user", id: "u1", capabilities: { ai_use: false } };
    renderShell("/my-tickets");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    expect(screen.queryByLabelText("클로비 AI 도우미 열기")).toBeNull();
    const items = navWithFeatures(USER_NAV, { chat_enabled: true }, { ai_use: false })
      .flatMap((group) => group.items || []);
    expect(items.some((item) => item.to === "/chat")).toBe(false);
    const allowed = navWithFeatures(USER_NAV, { chat_enabled: true }, { ai_use: true }).flatMap((g) => g.items || []);
    expect(allowed.some((item) => item.to === "/chat")).toBe(true);
  });
});
