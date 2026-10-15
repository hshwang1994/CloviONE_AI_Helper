import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI 도우미의 틀 — 몇 칸이 서는지는 **카드가 놓인 폭**(rem)이 정한다(AI 채팅 개선 회차, `chat/useChatLayout.js`).
 *
 * 예전에는 창 폭(1536px · 2200px)으로 정해, 앱 사이드바 · 확대 · 4K 루트 글자 크기에 따라 같은 창에서도 칸이 모자랐고
 * 참고 자료 칸은 2200 이상에서만 섰다. 여기서 못박는 것:
 *   - 폭 → 모드: 1600 넓음(세 칸) · 1070 보통(두 칸) · 728 좁음(대화 + 서랍) · 358 휴대폰. 루트 글자가 크면 같은 픽셀이 한 단 좁다.
 *   - 넓음에서만 참고 자료 칸이 서고(그 대화에 자료가 있을 때), 사람이 닫은 상태는 이 브라우저에 남는다.
 *   - 보통 이하에서는 참고 자료가 답 아래 접기다.
 *   - 서랍은 닫혀 있으면 inert 이고, 열면 초점이 안으로 들어가며 배경 대화가 inert 가 되고, Esc 는 닫고 여는 단추로 돌아온다. */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1", display_name: "시험 사용자" } }) }));

import { Chat } from "../Chat.jsx";
import { chatLayoutMode } from "./useChatLayout.js";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const ON = { available: true, reason: null, notice: null, mode: "tools", can_configure: false };
const CONV = { id: "c1", title: "연차 규정 정리", archived: false, created_at: "2026-10-15T00:00:00", last_message_at: "2026-10-15T01:00:00", message_count: 2 };
const THREAD = {
  conversation: CONV,
  items: [
    { id: "q1", role: "user", content: "연차 규정 알려 줘", processing_status: "done", created_at: "2026-10-15T01:00:00" },
    {
      id: "a1", role: "assistant", content: "연차는 입사 첫해에 매달 하루씩 생깁니다.", processing_status: "done", created_at: "2026-10-15T01:00:05",
      structured: { sources: [{ type: "document", id: "d1", title: "연차 규정", route: "/knowledge/d1", cited: true }] },
    },
  ],
};

let layoutWidth = 1600;

beforeEach(() => {
  layoutWidth = 1600;
  try { window.localStorage.removeItem("chat.sources.hidden"); } catch (e) { /* 저장소가 없으면 그대로 */ }
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p === "/api/ai/status") return Promise.resolve({ assistant: ON });
    if (p.startsWith("/api/me/ai-quota")) return Promise.resolve({ periods: [] });
    if (p.startsWith("/api/conversations?")) return Promise.resolve({ items: [CONV], total: 1, empty_total: 0 });
    if (p === "/api/conversations/c1/messages") return Promise.resolve(THREAD);
    return Promise.resolve({});
  });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function rect() {
    const width = this.hasAttribute && this.hasAttribute("data-chat-layout") ? layoutWidth : 0;
    return { width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0, toJSON() { return {}; } };
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderAt(width, path = "/chat/c1") {
  layoutWidth = width;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes>
                <Route path="/chat" element={<Chat />} />
                <Route path="/chat/:id" element={<Chat />} />
              </Routes>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const layout = () => document.querySelector("[data-chat-layout]").getAttribute("data-chat-layout");
const drawer = () => document.getElementById("chat-conv-drawer");

describe("chatLayoutMode — 폭(rem)이 틀을 정한다", () => {
  it("1600 · 1070 · 728 · 358 은 넓음 · 보통 · 좁음 · 휴대폰이다", () => {
    expect(chatLayoutMode(1600)).toBe("wide");
    expect(chatLayoutMode(1070)).toBe("medium");
    expect(chatLayoutMode(728)).toBe("narrow");
    expect(chatLayoutMode(358)).toBe("mobile");
  });

  it("루트 글자가 크면(4K 의 18px) 같은 픽셀이 한 단 좁다 — 문턱은 rem 이다", () => {
    expect(chatLayoutMode(1300)).toBe("wide");
    expect(chatLayoutMode(1300, 18)).toBe("medium");
    expect(chatLayoutMode(880)).toBe("medium");
    expect(chatLayoutMode(880, 18)).toBe("narrow");
  });

  it("폭을 못 재면(0 · NaN) 보통으로 둔다 — 첫 그림이 서랍으로 튀지 않는다", () => {
    expect(chatLayoutMode(0)).toBe("medium");
    expect(chatLayoutMode(Number.NaN)).toBe("medium");
  });
});

describe("틀 — 목록 · 대화 · 참고 자료", () => {
  it("넓은 틀은 목록 · 대화 · 참고 자료가 각자 칸으로 선다", async () => {
    renderAt(1600);
    expect(await screen.findByText("연차는 입사 첫해에 매달 하루씩 생깁니다.")).toBeInTheDocument();
    expect(layout()).toBe("wide");
    expect(screen.getByRole("region", { name: "대화 목록" })).toBeInTheDocument();
    expect(drawer()).toBeNull();
    expect(screen.queryByRole("button", { name: "대화 목록 열기" })).toBeNull();
    const panel = document.querySelector("[data-sources-panel]");
    expect(panel).not.toBeNull();
    expect(within(panel).getByRole("link", { name: /연차 규정/ })).toHaveAttribute("href", "#/knowledge/d1");
    // 칸이 선 동안 답 아래의 접기는 숨는다 — 같은 자료를 두 번 세우지 않는다.
    expect(screen.queryByRole("button", { name: "참고 자료 1개" })).toBeNull();
  });

  it("참고 자료 칸을 닫으면 이 브라우저에 남고, 머리 단추로 다시 연다", async () => {
    const user = userEvent.setup();
    renderAt(1600);
    await screen.findByText("연차는 입사 첫해에 매달 하루씩 생깁니다.");
    await user.click(screen.getByRole("button", { name: "참고 자료 닫기" }));
    expect(document.querySelector("[data-sources-panel]")).toBeNull();
    expect(window.localStorage.getItem("chat.sources.hidden")).toBe("1");
    const toggle = screen.getByRole("button", { name: "참고 자료 1" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle);
    expect(document.querySelector("[data-sources-panel]")).not.toBeNull();
    expect(window.localStorage.getItem("chat.sources.hidden")).toBe("0");
  });

  it("보통 틀은 목록 · 대화 두 칸이고, 참고 자료는 답 아래 접기다", async () => {
    const user = userEvent.setup();
    renderAt(1070);
    await screen.findByText("연차는 입사 첫해에 매달 하루씩 생깁니다.");
    expect(layout()).toBe("medium");
    expect(screen.getByRole("region", { name: "대화 목록" })).toBeInTheDocument();
    expect(document.querySelector("[data-sources-panel]")).toBeNull();
    await user.click(screen.getByRole("button", { name: "참고 자료 1개" }));
    expect(screen.getByRole("link", { name: "연차 규정" })).toHaveAttribute("href", "#/knowledge/d1");
  });

  it("좁은 틀은 대화만 선다 — 닫힌 서랍은 inert, 열면 초점이 안으로 가고 배경이 inert, Esc 는 닫고 단추로 돌아온다", async () => {
    const user = userEvent.setup();
    renderAt(728);
    await screen.findByText("연차는 입사 첫해에 매달 하루씩 생깁니다.");
    expect(layout()).toBe("narrow");
    const toggle = screen.getByRole("button", { name: "대화 목록 열기" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(drawer()).toHaveAttribute("inert");
    expect(drawer()).toHaveAttribute("aria-hidden", "true");

    await user.click(toggle);
    expect(drawer()).not.toHaveAttribute("inert");
    expect(drawer()).toHaveAttribute("aria-modal", "true");
    expect(drawer().contains(document.activeElement)).toBe(true);
    expect(toggle.closest("[inert]")).not.toBeNull();

    await user.keyboard("{Escape}");
    expect(drawer()).toHaveAttribute("inert");
    expect(toggle.closest("[inert]")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(toggle));
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("서랍에서 대화를 고르면 서랍이 닫힌다", async () => {
    const user = userEvent.setup();
    renderAt(728, "/chat");
    await user.click(await screen.findByRole("button", { name: "대화 목록 열기" }));
    await user.click(screen.getByRole("link", { name: /연차 규정 정리/ }));
    expect(await screen.findByText("연차는 입사 첫해에 매달 하루씩 생깁니다.")).toBeInTheDocument();
    expect(drawer()).toHaveAttribute("inert");
  });

  it("휴대폰 틀의 서랍은 판 전체이고 안에 닫기 단추가 있다", async () => {
    const user = userEvent.setup();
    renderAt(358);
    await screen.findByText("연차는 입사 첫해에 매달 하루씩 생깁니다.");
    expect(layout()).toBe("mobile");
    await user.click(screen.getByRole("button", { name: "대화 목록 열기" }));
    const close = screen.getAllByRole("button", { name: "대화 목록 닫기" }).find((b) => drawer().contains(b));
    expect(close).toBeTruthy();
    await user.click(close);
    expect(drawer()).toHaveAttribute("inert");
  });
});
