import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* AI-69: archiveConv/deleteConv의 낙관적 캐시 갱신이 ["conversations", showArchived]를 썼는데
 * 실제 쿼리 키는 ["conversations", showArchived, debouncedQ, convLimit]이었다(AI-18로 convLimit이
 * 추가되기 전에도 이미 debouncedQ가 빠져 있었다). setQueryData는 정확히 일치하는 키만 찾으므로
 * 이 낙관 갱신은 캐시 어디에도 안 닿아 조용히 아무 효과가 없었고, 실제로는 뒤이은
 * invalidateQueries(비동기 재조회)만 화면을 갱신해 왔다.
 *
 * 여기서는 재조회 응답을 일부러 영영 안 끝나게 묶어 둔다 — 그런데도 목록에서 항목이 이미
 * 빠졌다면, 그 변화는 재조회가 아니라 낙관적 갱신이 실제 캐시를 건드렸다는 뜻이다. */

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

describe("대화 보관/삭제 낙관적 캐시 갱신이 실제 쿼리 키를 맞춘다 (AI-69)", () => {
  beforeEach(async () => {
    stubMatchMedia();
    apiMock.mockReset();
    ({ useChat } = await import("./useChat.js"));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function mount(initialItems) {
    let convFetchCount = 0;
    apiMock.mockImplementation((url, opts) => {
      if (opts && (opts.method === "PATCH" || opts.method === "DELETE")) {
        return Promise.resolve({ conversation: { id: "c1", archived: true }, ok: true });
      }
      if (url.startsWith("/api/conversations")) {
        convFetchCount += 1;
        if (convFetchCount === 1) return Promise.resolve({ items: initialItems, total: initialItems.length });
        // invalidateQueries가 거는 재조회 — 일부러 영영 안 끝난다. 그래도 아래 단언이
        // 성립해야 낙관적 갱신 자체가 캐시를 건드렸다고 말할 수 있다.
        return new Promise(() => {});
      }
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    const view = render(<QueryClientProvider client={qc}><Harness /></QueryClientProvider>);
    return { view, getConvFetchCount: () => convFetchCount };
  }

  const items = () => [
    { id: "c1", title: "대화1", archived: false, updated_at: "2026-01-01T00:00:00" },
  ];

  it("보관하면 재조회가 끝나기 전에도 목록 캐시에서 즉시 빠진다", async () => {
    mount(items());
    await waitFor(() => expect(latestHook.convs.data && latestHook.convs.data.items.length).toBe(1));

    await act(async () => {
      await latestHook.archiveConv.mutateAsync({ id: "c1", archived: true });
    });

    expect(latestHook.convs.data.items.map((c) => c.id)).toEqual([]);
    expect(latestHook.convs.data.total).toBe(0);
  });

  it("삭제하면 재조회가 끝나기 전에도 목록 캐시에서 즉시 빠진다", async () => {
    mount(items());
    await waitFor(() => expect(latestHook.convs.data && latestHook.convs.data.items.length).toBe(1));

    await act(async () => {
      await latestHook.deleteConv.mutateAsync("c1");
    });

    expect(latestHook.convs.data.items.map((c) => c.id)).toEqual([]);
    expect(latestHook.convs.data.total).toBe(0);
  });
});
