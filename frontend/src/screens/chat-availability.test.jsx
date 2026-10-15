import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI 도우미 화면의 「쓸 수 없음」과 「찾지 못함」은 다른 상태다 (D-538).
 *
 * 쓸 수 없음(꺼짐 · 미설정 · 연결 막힘)은 서버의 도우미 칸(`/api/ai/status` 의 `assistant`)이 말하고, 화면은 그 까닭 문장을
 * 판 전체에 세우며 입력 칸을 닫는다. 시스템 관리자에게만 「AI 연결 열기」가 있다. 보내는 순간 409 `ai_unavailable` 이 오면
 * 실패 문장 대신 상태를 다시 읽어 판을 그린다. 첫 화면은 할 수 있는 일만 약속한다. `/ai` 의 「AI 도우미에게 묻기」는
 * `?ask=` 로 와서 새 대화로 한 번만 보내진다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { Chat } from "./Chat.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function stubMatchMedia() {
  window.matchMedia = (query) => ({
    matches: false, media: query,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    onchange: null, dispatchEvent: () => false,
  });
}

function Here() {
  const loc = useLocation();
  return <div data-testid="here">{loc.pathname + loc.search}</div>;
}

function renderChat(path = "/chat") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes>
                <Route path="/chat" element={<><Chat /><Here /></>} />
                <Route path="/chat/:id" element={<><Chat /><Here /></>} />
              </Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const OFF = { available: false, reason: "unconfigured", notice: "AI 가 아직 연결되지 않았습니다.", mode: "unknown", can_configure: false };
const ON = { available: true, reason: null, notice: null, mode: "tools", can_configure: false };

function conflict() {
  const e = new Error("AI 사용이 꺼져 있어 지금은 답할 수 없습니다.");
  e.status = 409;
  e.body = { error: { code: "ai_unavailable", message: e.message, details: { reason: "off" } } };
  return e;
}

let assistant;
beforeEach(() => {
  apiMock.mockReset();
  stubMatchMedia();
  assistant = ON;
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    const method = (opts && opts.method) || "GET";
    if (p === "/api/ai/status") return Promise.resolve({ assistant });
    if (p.startsWith("/api/conversations?")) return Promise.resolve({ items: [] });
    if (p === "/api/conversations" && method === "POST") return Promise.resolve({ conversation: { id: "c1", title: "새 대화" } });
    if (p === "/api/conversations/c1/messages" && method === "POST") {
      return Promise.resolve({ message: { id: "m1", role: "user", content: "x", processing_status: "pending" }, job_id: "j1" });
    }
    if (p === "/api/conversations/c1/messages") return Promise.resolve({ items: [] });
    if (p.startsWith("/api/me/ai-quota")) return Promise.resolve({ periods: [] });
    return Promise.resolve({});
  });
});

describe("AI 도우미 — 쓸 수 있을 때의 첫 화면", () => {
  it("할 수 있는 일만 약속하고 시작 예시를 보인다", async () => {
    renderChat();
    // 찾는 범위를 이름으로 말하고, 팀 채팅은 찾지 않는다는 사실을 함께 말한다(A8 · 사용자 결정 2026-10-15).
    expect(await screen.findByText("문서, 티켓, 프로젝트, 결재, 알림, 회의록을 내 권한 안에서 찾아 답합니다. 팀 채팅 대화는 찾지 않습니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내가 담당하는 미완료 티켓을 알려 줘" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내가 작성한 문서가 몇 개야?" })).toBeInTheDocument();
    expect(screen.queryByText(/티켓 생성/)).toBeNull();
    expect(screen.getByLabelText("메시지 입력")).not.toBeDisabled();
  });
});

describe("AI 도우미 — 쓸 수 없을 때", () => {
  it("까닭 문장을 판 전체에 세우고 입력 칸을 닫는다(일반 사용자에게는 설정 링크가 없다)", async () => {
    assistant = OFF;
    renderChat();
    expect(await screen.findByText("AI 가 아직 연결되지 않았습니다.")).toBeInTheDocument();
    expect(screen.getByText("관리자가 AI 를 연결하면 쓸 수 있습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "AI 연결 열기" })).toBeNull();
    // 문서 찾기는 모델을 부르지 않으므로 그대로 권한다(머리의 단추 + 판 안의 단추).
    expect(screen.getAllByRole("link", { name: "문서에서 찾기" }).length).toBeGreaterThanOrEqual(2);
    await waitFor(() => expect(screen.getByLabelText("메시지 입력")).toBeDisabled());
  });

  it("시스템 관리자에게는 AI 연결 화면으로 가는 길이 있다", async () => {
    assistant = { ...OFF, reason: "blocked", notice: "AI 연결에 문제가 있어 지금은 답할 수 없습니다.", can_configure: true };
    renderChat();
    expect(await screen.findByText("AI 연결에 문제가 있어 지금은 답할 수 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("AI 연결 화면에서 연결 상태를 확인하세요.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI 연결 열기" })).toHaveAttribute("href", "#/ai-connection");
  });

  it("보내는 순간 409 가 오면 실패 문장 대신 상태를 다시 읽어 판을 그리고 쓴 글을 잃지 않는다", async () => {
    const user = userEvent.setup();
    let sent = 0;
    apiMock.mockImplementation((path, opts) => {
      const p = String(path);
      const method = (opts && opts.method) || "GET";
      if (p === "/api/ai/status") return Promise.resolve({ assistant });
      if (p.startsWith("/api/conversations?")) return Promise.resolve({ items: [] });
      if (p === "/api/conversations" && method === "POST") return Promise.resolve({ conversation: { id: "c1", title: "새 대화" } });
      if (p === "/api/conversations/c1/messages" && method === "POST") {
        sent += 1;
        assistant = { ...OFF, reason: "off", notice: "AI 사용이 꺼져 있어 지금은 답할 수 없습니다." };
        return Promise.reject(conflict());
      }
      if (p.startsWith("/api/conversations/c1")) return Promise.resolve({ items: [] });
      return Promise.resolve({});
    });
    renderChat();
    const box = await screen.findByLabelText("메시지 입력");
    await user.type(box, "연차 며칠이야?");
    await user.click(screen.getByRole("button", { name: /전송/ }));

    expect(await screen.findByText("AI 사용이 꺼져 있어 지금은 답할 수 없습니다.")).toBeInTheDocument();
    expect(sent).toBe(1);
    expect(screen.getByLabelText("메시지 입력")).toHaveValue("연차 며칠이야?");
  });
});

describe("「AI 도우미에게 묻기」(`?ask=`)", () => {
  it("새 대화로 한 번만 보내고 주소에서 질문을 지운 뒤 그 대화의 주소로 간다", async () => {
    // qa-contract-change: 주소가 정본이 되어(AI 채팅 개선 회차) 보낸 뒤의 주소는 `/chat` 이 아니라 `/chat/<새 대화 id>` 다.
    renderChat("/chat?ask=" + encodeURIComponent("휴가 신청 방법"));
    await waitFor(() => {
      const posts = apiMock.mock.calls.filter(([p, o]) => p === "/api/conversations/c1/messages" && o && o.method === "POST");
      expect(posts).toHaveLength(1);
      expect(posts[0][1].body.content).toBe("휴가 신청 방법");
    });
    await waitFor(() => expect(screen.getByTestId("here")).toHaveTextContent(/^\/chat\/c1$/));
    const created = apiMock.mock.calls.filter(([p, o]) => p === "/api/conversations" && o && o.method === "POST");
    expect(created).toHaveLength(1);
  });
});
