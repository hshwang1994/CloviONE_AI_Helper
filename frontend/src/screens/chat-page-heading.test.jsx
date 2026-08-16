import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* SEM-03 재검증(2026-08-13) — 2026-08-12 "구현완료" 기록은 이 파일 소스의 리터럴
 * component="h1"만 grep으로 셌다(1개) — PageHeader(kit.jsx)가 내부적으로 만드는 h1은
 * 다른 파일이라 안 잡혀, 실제로는 PageHeader의 고정 title("AI 도우미")과 대화 제목 막대
 * 까지 h1이 둘이었다(실제 렌더로 재확인). 이 화면은 지금까지 전체 렌더 시험이 하나도
 * 없었다(Chat.jsx 자체 주석: "격자 상태 기계는 테스트가 없고") — 이 h1 시험이 최소
 * 마운트 검증을 겸한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { Chat } from "./Chat.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

// useChat()이 목록/서랍 반응형 판정에 window.matchMedia를 직접 쓴다 — jsdom에는 없어 stub한다
// (app/assistant-drawer-composer.test.jsx의 wideViewport()와 동일한 필요, 같은 해법).
function stubMatchMedia() {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

function renderChat() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/chat"]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Chat />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  stubMatchMedia();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/conversations")) return Promise.resolve({ items: [] });
    if (p.startsWith("/api/me/ai-quota")) return Promise.resolve({ used: 0, limit: 100 });
    return Promise.resolve({});
  });
});

describe("AI 도우미 화면 — h1이 하나뿐이다 (SEM-03 재검증)", () => {
  it("대화가 없을 때(cid 없음) PageHeader가 'AI 도우미'를 h1으로 보여주고 하나뿐이다", async () => {
    // PA-RC-0020: 사이드바 라벨·breadcrumb·h1 세 문자열을 "AI 도우미"로 통일한다 —
    // 이 h1만 "채팅"으로 남아 있으면 사이드바에서 누른 이름과 도착 화면 제목이 갈린다.
    renderChat();
    await screen.findByRole("button", { name: /대화 목록/ });
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent("AI 도우미");
  });
});
