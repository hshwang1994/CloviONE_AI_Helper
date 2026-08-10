import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* AI-38: 대화 목록 검색이 제목뿐 아니라 본문도 찾도록 서버(q 파라미터)로 넘어갔다.
 * 여기서는 그 배선(useChat.js의 debouncedQ) — 타이핑마다 왕복하지 않고 300ms 지나서야
 * api("/api/conversations?...q=...")를 부르는지 — 만 진짜 훅 + 가짜 타이머로 확인한다.
 * 백엔드 쿼리 자체(제목·본문 매칭, IDOR 격리)는 tests/integration/test_chat_api.py가 진다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args) }));

function stubMatchMedia() {
  if (typeof window.matchMedia === "function") return;
  window.matchMedia = () => ({
    matches: false, media: "", onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  });
}

let useChat;
let latestHook;
function Harness() {
  latestHook = useChat();
  return null;
}

describe("대화 목록 검색 — 서버 q 파라미터로 debounce 넘긴다", () => {
  beforeEach(async () => {
    vi.useFakeTimers();
    stubMatchMedia();
    apiMock.mockReset();
    apiMock.mockImplementation(() => Promise.resolve({ items: [] }));
    ({ useChat } = await import("./useChat.js"));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function mount() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    return render(<QueryClientProvider client={qc}><Harness /></QueryClientProvider>);
  }

  it("검색어를 치면 즉시가 아니라 300ms 뒤에만 q= 포함 요청을 보낸다", async () => {
    const view = mount();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    apiMock.mockClear();

    act(() => { latestHook.setConvFilter("포스코DX"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(200); });
    expect(apiMock.mock.calls.some(([url]) => url.includes("q="))).toBe(false);

    await act(async () => { await vi.advanceTimersByTimeAsync(150); });
    expect(apiMock.mock.calls.some(([url]) => url.includes("q=" + encodeURIComponent("포스코DX")))).toBe(true);
    view.unmount();
  });

  it("검색어를 지우면 다시 q 없이 전체 목록을 부른다", async () => {
    const view = mount();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { latestHook.setConvFilter("포스코DX"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    apiMock.mockClear();

    act(() => { latestHook.setConvFilter(""); });
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    expect(apiMock.mock.calls.some(([url]) => url.startsWith("/api/conversations") && !url.includes("q="))).toBe(true);
    view.unmount();
  });
});
