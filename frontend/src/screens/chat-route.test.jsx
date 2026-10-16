import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI 도우미는 **주소가 정본**이다(AI 채팅 개선 회차).
 *
 * 예전에는 연 대화가 화면 상태와 이 탭의 저장소에만 있었다 — 뒤로 가기가 대화를 오가지 않았고, 새로고침이 다른 대화를 열 수
 * 있었으며, 목록 캐시를 먼저 보던 머리 제목은 첫 답 뒤에도 「새 대화」에 남았다. 여기서 못박는 것:
 *   - `/chat` 은 초안이다. 목록이 있어도 다른 대화를 저절로 열지 않는다.
 *   - 줄을 고르면 `/chat/<id>` 이고, 뒤로 · 앞으로가 대화를 오간다. 머리 제목 · 고른 줄 · 스레드가 주소의 대화와 같다.
 *   - 첫 전송은 대화를 만든 뒤 `/chat/<새 id>` 로 **바꾼다**(replace — 되돌아가기에 빈 초안이 남지 않는다). 보낸 말은 남는다.
 *   - 없는 · 남의 대화는 판 안 오류와 「새 대화 시작」 길로 끝난다.
 *   - 빠르게 여러 줄을 눌러도 늦게 온 앞 대화의 응답이 화면을 덮지 않는다.
 *   - 답이 오면 목록을 다시 읽는다 — 첫 답의 의도 제목이 머리와 목록 줄에 함께 선다.
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1", display_name: "시험 사용자" } }) }));

import { Chat } from "./Chat.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ON = { available: true, reason: null, notice: null, mode: "tools", can_configure: false };

function conv(id, title) {
  return { id, title, archived: false, created_at: "2026-10-15T00:00:00", last_message_at: "2026-10-15T01:00:00", message_count: 2 };
}

const CONVS = [conv("c1", "연차 규정 정리"), conv("c2", "이번 주 마감 티켓"), conv("c3", "SK하이닉스 프로젝트 현황")];

function threadOf(id) {
  const c = CONVS.find((x) => x.id === id);
  return {
    conversation: { ...c },
    items: [
      { id: `${id}-q`, role: "user", content: `${c.title} 질문입니다`, processing_status: "done", created_at: "2026-10-15T01:00:00" },
      { id: `${id}-a`, role: "assistant", content: `${c.title} 답입니다.`, processing_status: "done", created_at: "2026-10-15T01:00:05" },
    ],
  };
}

/* 서버 시각은 Z 없는 UTC 다 — 기다리는 질문은 「지금」이어야 폴링이 멈추지 않는다(10분이 지나면 멈춘 것으로 본다). */
function nowNaive(offsetSec = 0) {
  return new Date(Date.now() + offsetSec * 1000).toISOString().slice(0, 19);
}

function notFound(status) {
  const e = new Error("not_found");
  e.status = status;
  return e;
}

/* 기본 서버 — 목록 셋, 대화마다 문답 한 쌍, 모르는 대화는 404. 시험이 `messages` 만 바꿔 끼운다. */
function server({ messages, list } = {}) {
  return (path, opts) => {
    const p = String(path);
    const method = (opts && opts.method) || "GET";
    if (p === "/api/ai/status") return Promise.resolve({ assistant: ON });
    if (p.startsWith("/api/me/ai-quota")) return Promise.resolve({ periods: [] });
    if (p.startsWith("/api/conversations?")) return Promise.resolve(list ? list() : { items: CONVS, total: CONVS.length, empty_total: 0 });
    const m = p.match(/^\/api\/conversations\/([^/]+)\/messages$/);
    if (m && method === "GET") {
      if (messages) return messages(m[1]);
      return CONVS.some((c) => c.id === m[1]) ? Promise.resolve(threadOf(m[1])) : Promise.reject(notFound(404));
    }
    return Promise.resolve({});
  };
}

function Here() {
  const loc = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <div data-testid="here">{loc.pathname}</div>
      <button type="button" onClick={() => navigate(-1)}>뒤로</button>
      <button type="button" onClick={() => navigate(1)}>앞으로</button>
    </>
  );
}

function renderChat(entries) {
  const list = Array.isArray(entries) ? entries : [entries];
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={list} initialIndex={list.length - 1}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes>
                <Route path="/home" element={<Here />} />
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

const here = () => screen.getByTestId("here").textContent;
const headTitle = (name) => screen.getByRole("heading", { level: 2, name });
const row = (name) => screen.getByRole("link", { name: new RegExp(name) });

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(server());
  /* 판이 놓인 폭 — 넓은 틀(목록이 늘 서 있다)로 잰다. 좁은 틀의 서랍은 `chat/chat-layout.test.jsx` 가 본다. */
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function rect() {
    const width = this.hasAttribute && this.hasAttribute("data-chat-layout") ? 1600 : 0;
    return { width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0, toJSON() { return {}; } };
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("주소가 정본이다", () => {
  it("/chat 은 초안이다 — 목록이 있어도 다른 대화를 저절로 열지 않는다", async () => {
    renderChat("/chat");
    expect(await screen.findByRole("link", { name: /연차 규정 정리/ })).toBeInTheDocument();
    expect(headTitle("새 대화")).toBeInTheDocument();
    expect(here()).toBe("/chat");
    expect(document.querySelector("[aria-current='page']")).toBeNull();
    expect(apiMock.mock.calls.filter(([p]) => String(p).endsWith("/messages"))).toHaveLength(0);
  });

  it("줄을 고르면 /chat/<id> 로 가고, 뒤로 · 앞으로가 대화를 오간다 — 머리 · 고른 줄 · 스레드가 늘 주소의 대화다", async () => {
    const user = userEvent.setup();
    renderChat("/chat/c1");
    expect(await screen.findByText("연차 규정 정리 답입니다.")).toBeInTheDocument();
    expect(headTitle("연차 규정 정리")).toBeInTheDocument();
    expect(row("연차 규정 정리")).toHaveAttribute("aria-current", "page");
    const box = screen.getByLabelText("메시지 입력");

    await user.click(row("이번 주 마감 티켓"));
    expect(here()).toBe("/chat/c2");
    expect(await screen.findByText("이번 주 마감 티켓 답입니다.")).toBeInTheDocument();
    expect(headTitle("이번 주 마감 티켓")).toBeInTheDocument();
    expect(row("이번 주 마감 티켓")).toHaveAttribute("aria-current", "page");
    expect(row("연차 규정 정리")).not.toHaveAttribute("aria-current");
    expect(screen.queryByText("연차 규정 정리 답입니다.")).toBeNull();
    // 대화를 바꿔도 화면은 그대로다(다시 마운트되지 않는다 — 입력 칸이 같은 노드).
    expect(screen.getByLabelText("메시지 입력")).toBe(box);

    await user.click(screen.getByRole("button", { name: "뒤로" }));
    expect(here()).toBe("/chat/c1");
    expect(await screen.findByText("연차 규정 정리 답입니다.")).toBeInTheDocument();
    expect(headTitle("연차 규정 정리")).toBeInTheDocument();
    expect(row("연차 규정 정리")).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("button", { name: "앞으로" }));
    expect(here()).toBe("/chat/c2");
    expect(await screen.findByText("이번 주 마감 티켓 답입니다.")).toBeInTheDocument();
    expect(headTitle("이번 주 마감 티켓")).toBeInTheDocument();
  });

  it("이미 연 대화를 다시 눌러도 주소를 쌓지 않는다 — 뒤로 가기는 앞 대화로 간다", async () => {
    const user = userEvent.setup();
    renderChat(["/chat/c1", "/chat/c2"]);
    expect(await screen.findByText("이번 주 마감 티켓 답입니다.")).toBeInTheDocument();
    await user.click(row("이번 주 마감 티켓"));
    await user.click(row("이번 주 마감 티켓"));
    expect(here()).toBe("/chat/c2");
    await user.click(screen.getByRole("button", { name: "뒤로" }));
    expect(here()).toBe("/chat/c1");
  });

  it("첫 전송은 대화를 만든 뒤 주소를 /chat/<새 id> 로 바꾼다 — 보낸 말이 남고, 뒤로 가기에 빈 초안이 끼지 않는다", async () => {
    const user = userEvent.setup();
    const base = server();
    let sent = false;
    apiMock.mockImplementation((path, opts) => {
      const p = String(path);
      const method = (opts && opts.method) || "GET";
      if (p === "/api/conversations" && method === "POST") return Promise.resolve({ conversation: { id: "c9", title: "새 대화" } });
      if (p === "/api/conversations/c9/messages" && method === "POST") {
        sent = true;
        return Promise.resolve({ message: { id: "m9", role: "user", content: opts.body.content, processing_status: "pending" }, job_id: "j9" });
      }
      if (p === "/api/conversations/c9/messages") {
        return Promise.resolve({
          conversation: { id: "c9", title: "내 문서 보여 줘", archived: false },
          items: sent ? [{ id: "m9", role: "user", content: "내 문서 보여 줘", processing_status: "pending", created_at: "2026-10-15T02:00:00" }] : [],
        });
      }
      return base(path, opts);
    });
    renderChat(["/home", "/chat"]);
    const box = await screen.findByLabelText("메시지 입력");
    await user.type(box, "내 문서 보여 줘");
    await user.click(screen.getByRole("button", { name: /전송/ }));

    await waitFor(() => expect(here()).toBe("/chat/c9"));
    expect(await screen.findByText("내 문서 보여 줘", { selector: "p, span, div" })).toBeInTheDocument();
    expect(screen.getByLabelText("메시지 입력")).toBe(box);
    await waitFor(() => expect(headTitle("내 문서 보여 줘")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "뒤로" }));
    expect(here()).toBe("/home");
  });

  it("머리에서 이름을 바꾸면 머리 · 목록 줄이 같은 새 이름이고, 초점은 「대화 동작」 단추로 돌아온다", async () => {
    const user = userEvent.setup();
    const base = server();
    let renamed = null;
    apiMock.mockImplementation((path, opts) => {
      const p = String(path);
      const method = (opts && opts.method) || "GET";
      if (p === "/api/conversations/c1" && method === "PATCH") {
        renamed = opts.body.title;
        return Promise.resolve({ conversation: { ...CONVS[0], title: renamed } });
      }
      if (renamed && p.startsWith("/api/conversations?")) {
        return Promise.resolve({ items: [{ ...CONVS[0], title: renamed }, CONVS[1], CONVS[2]], total: 3, empty_total: 0 });
      }
      return base(path, opts);
    });
    renderChat("/chat/c1");
    await screen.findByText("연차 규정 정리 답입니다.");
    await user.click(screen.getByRole("button", { name: "대화 동작" }));
    await user.click(screen.getByRole("menuitem", { name: "이름 바꾸기" }));
    const input = await screen.findByRole("textbox", { name: "이름 바꾸기: 연차 규정 정리" });
    await waitFor(() => expect(document.activeElement).toBe(input));
    await user.keyboard("연차 규정 요약{Enter}");
    expect(renamed).toBe("연차 규정 요약");
    await waitFor(() => expect(headTitle("연차 규정 요약")).toBeInTheDocument());
    await waitFor(() => expect(row("연차 규정 요약")).toHaveAttribute("aria-current", "page"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "대화 동작" })));
  });

  it.each([[404], [403]])("없는 · 남의 대화(%i)는 판 안 오류와 「새 대화 시작」 길로 끝난다", async (status) => {
    const user = userEvent.setup();
    apiMock.mockImplementation(server({ messages: () => Promise.reject(notFound(status)) }));
    renderChat("/chat/nope");
    expect(await screen.findByText("대화를 찾을 수 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("삭제되었거나 열 수 없는 대화입니다. 새 대화를 시작해 주세요.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "새 대화 시작" }));
    expect(here()).toBe("/chat");
    expect(screen.queryByText("대화를 찾을 수 없습니다.")).toBeNull();
    expect(headTitle("새 대화")).toBeInTheDocument();
  });

  it("빠르게 A → B → C 를 눌러도 늦게 온 A · B 의 응답이 화면을 덮지 않는다", async () => {
    const user = userEvent.setup();
    const late = {};
    apiMock.mockImplementation(server({
      messages: (id) => (id === "c3"
        ? Promise.resolve(threadOf(id))
        : new Promise((resolve) => { late[id] = () => resolve(threadOf(id)); })),
    }));
    renderChat("/chat");
    await screen.findByRole("link", { name: /연차 규정 정리/ });
    await user.click(row("연차 규정 정리"));
    await user.click(row("이번 주 마감 티켓"));
    await user.click(row("SK하이닉스 프로젝트 현황"));
    expect(await screen.findByText("SK하이닉스 프로젝트 현황 답입니다.")).toBeInTheDocument();

    await act(async () => { late.c1(); late.c2(); });
    expect(here()).toBe("/chat/c3");
    expect(headTitle("SK하이닉스 프로젝트 현황")).toBeInTheDocument();
    expect(row("SK하이닉스 프로젝트 현황")).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link").filter((a) => a.getAttribute("aria-current") === "page")).toHaveLength(1);
    expect(screen.queryByText("연차 규정 정리 답입니다.")).toBeNull();
    expect(screen.queryByText("이번 주 마감 티켓 답입니다.")).toBeNull();
  });

  it("답을 기다리던 대화에 답이 오면 목록을 다시 읽어 의도 제목이 머리와 목록 줄에 함께 선다", async () => {
    let answered = false;
    let listReads = 0;
    const asked = nowNaive(-2);
    const waiting = { id: "c5", title: "내 담당 티켓 보여", archived: false, created_at: "2026-10-15T00:00:00", last_message_at: "2026-10-15T03:00:00", message_count: 1 };
    const titled = { ...waiting, title: "내 담당 티켓 조회", message_count: 2 };
    apiMock.mockImplementation(server({
      list: () => { listReads += 1; return { items: [answered ? titled : waiting, ...CONVS], total: 4, empty_total: 0 }; },
      messages: () => {
        const question = { id: "q5", role: "user", content: "나에게 할당된 티켓 보여줘", processing_status: answered ? "done" : "processing", created_at: asked };
        if (!answered) { answered = true; return Promise.resolve({ conversation: waiting, items: [question] }); }
        return Promise.resolve({
          conversation: titled,
          items: [question, { id: "a5", role: "assistant", content: "담당 티켓은 3건입니다.", processing_status: "done", created_at: nowNaive() }],
        });
      },
    }));
    renderChat("/chat/c5");
    expect(await screen.findByText("나에게 할당된 티켓 보여줘")).toBeInTheDocument();
    const before = listReads;
    expect(await screen.findByText("담당 티켓은 3건입니다.", {}, { timeout: 4000 })).toBeInTheDocument();
    await waitFor(() => expect(listReads).toBeGreaterThan(before));
    await waitFor(() => expect(row("내 담당 티켓 조회")).toHaveAttribute("aria-current", "page"));
    expect(headTitle("내 담당 티켓 조회")).toBeInTheDocument();
  }, 10000);
});
