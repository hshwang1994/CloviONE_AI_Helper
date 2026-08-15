import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* PA-RC-0002: deleteConv의 onError 폴백이 "삭제하지 못했습니다."로 끝나 회복 절이 없는
 * 막다른 길이었다 — 실패 이유(e.message)가 없을 때 사용자가 다음에 뭘 해야 하는지 말이 없었다. */

const toastSpy = vi.fn();
vi.mock("../ui/kit.jsx", async () => {
  const actual = await vi.importActual("../ui/kit.jsx");
  return { ...actual, useToast: () => toastSpy };
});

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

describe("대화 삭제 실패 문구 (PA-RC-0002)", () => {
  beforeEach(async () => {
    stubMatchMedia();
    apiMock.mockReset();
    toastSpy.mockReset();
    ({ useChat } = await import("./useChat.js"));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("서버 응답에 이유가 없으면(e.message 없음) 회복 절이 있는 폴백 문구를 쓴다", async () => {
    apiMock.mockImplementation((url, opts) => {
      if (opts && opts.method === "DELETE") return Promise.reject({});
      if (url.startsWith("/api/conversations")) return Promise.resolve({ items: [], total: 0 });
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><Harness /></QueryClientProvider>);
    await waitFor(() => expect(latestHook).toBeTruthy());

    await act(async () => {
      try { await latestHook.deleteConv.mutateAsync("c1"); } catch (e) { /* onError already handled it */ }
    });

    expect(toastSpy).toHaveBeenCalledWith("삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error");
  });
});
