import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* AI-44: 백엔드는 채팅마다 쿼터를 예약·차감하는데(app/chat/router.py의 ai_quotas.reserve)
 * 남은 양이 화면 어디에도 안 보였다. useChat()이 새 자기서비스 경로(/api/me/ai-quota)를
 * 불러 aiQuota로 노출하는지만 여기서 확인한다 — 실제 배지 렌더는 Chat.jsx(화면 셸,
 * 라우팅·세션 컨텍스트가 필요해 이 파일의 훅 전용 하네스로는 직접 못 돈다) 몫이고,
 * 숫자 자체의 정확성은 tests/integration/test_chat_quota.py가 진다. */

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

describe("useChat이 자기 AI 쿼터를 노출한다", () => {
  beforeEach(async () => {
    vi.useFakeTimers();
    stubMatchMedia();
    apiMock.mockReset();
    ({ useChat } = await import("./useChat.js"));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("/api/me/ai-quota를 불러 aiQuota.data에 담는다", async () => {
    apiMock.mockImplementation((url) => {
      if (url === "/api/me/ai-quota") {
        return Promise.resolve({
          user_id: "u1",
          periods: [
            { period: "day", limit: 100, used: 32, source: "user", resets_at: "2026-08-11T00:00:00" },
            { period: "month", limit: null, used: 32, source: null, resets_at: "2026-09-01T00:00:00" },
          ],
        });
      }
      return Promise.resolve({ items: [] });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    const view = render(<QueryClientProvider client={qc}><Harness /></QueryClientProvider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(latestHook.aiQuota.data.periods.find((p) => p.period === "day")).toEqual(
      expect.objectContaining({ limit: 100, used: 32 })
    );
    expect(apiMock.mock.calls.some(([url]) => url === "/api/me/ai-quota")).toBe(true);
    view.unmount();
  });
});
