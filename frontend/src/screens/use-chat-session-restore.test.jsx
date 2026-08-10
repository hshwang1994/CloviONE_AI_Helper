/* `/chat` 새로고침 복원(sessionStorage) 경합 — 조사 중 발견한 부수 버그.
 *
 * 마운트 시점엔 cid가 항상 null이다. 복원 이펙트는 conversations 쿼리가 응답할 때까지
 * 기다려야 하는데, 저장 이펙트는 그걸 모르고 "cid가 null이니 대화 없음"으로 오해해
 * sessionStorage를 먼저 지워 버렸다 — 복원 이펙트가 나중에 실행돼도 읽을 값이 이미
 * 사라진 뒤였다. 결과: 실패 상황(convs 쿼리 오류)에서는 "복원용 대화 id가 조용히
 * 사라지는" 방식으로 FAIL-01(대화 이력이 지워진 것처럼 보인다)을 더 악화시키고,
 * **성공 경로에서도** 매 새로고침마다 복원이 조용히 실패해 items[0]으로만 튕겨나갔다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api.js", () => ({ api: vi.fn() }));
import { api } from "../lib/api.js";
import { useChat } from "./useChat.js";
import { CHAT_LAST_CONV_KEY } from "./chat-helpers.js";

// items[0]이 최신순 맨 위(실제 목록 정렬과 동일) — sessionStorage로 복원할 대상은
// 일부러 items[0]이 아닌 것으로 둔다. 복원 대상을 items[0]과 같게 두면, 복원이
// 고장 나서 그냥 items[0]로 폴백해도 우연히 같은 id가 나와 이 테스트가 버그를 못 잡는다.
const CONVS = {
  items: [
    { id: "new-conv", title: "방금 바뀐 대화", updated_at: "2026-08-09T00:00:00Z" },
    { id: "old-conv", title: "예전에 보던 대화", updated_at: "2026-08-01T00:00:00Z" },
  ],
};

function wrapper({ children }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30 * 1000 } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  window.sessionStorage.clear();
  api.mockReset();
  // jsdom엔 matchMedia가 없다 — useChat이 대화목록 드로어 폭 감지에 쓴다.
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
});

describe("useChat — sessionStorage 복원 경합", () => {
  it("성공 경로: sessionStorage에 남겨 둔 대화를 items[0]이 아니라 그 대화로 복원한다", async () => {
    window.sessionStorage.setItem(CHAT_LAST_CONV_KEY, "old-conv");
    api.mockImplementation((path) => {
      if (path.startsWith("/api/conversations/")) return Promise.resolve({ messages: [] });
      // 실제 네트워크 왕복처럼 마이크로태스크 한 틱보다 늦게 응답한다 — 마운트 시점 이펙트가
      // 먼저 전부 도는 것을 보장해야, 저장 이펙트가 응답을 기다리지 않고 sessionStorage를
      // 먼저 지워 버리는 경합을 이 테스트가 실제로 잡는다(즉시 resolve하면 우연히 순서가
      // 맞아 버그가 안 드러난다).
      if (path.startsWith("/api/conversations")) {
        return new Promise((resolve) => setTimeout(() => resolve(CONVS), 0));
      }
      return Promise.reject(new Error("unexpected path: " + path));
    });

    const { result } = renderHook(() => useChat(), { wrapper });

    await waitFor(() => expect(result.current.cid).toBe("old-conv"));
    // items[0]("new-conv")로 잘못 튕겨나가지 않았는지 명시적으로도 확인.
    expect(result.current.cid).not.toBe("new-conv");
  });

  it("실패 경로: conversations 쿼리가 실패해도 sessionStorage의 복원용 id를 지우지 않는다", async () => {
    window.sessionStorage.setItem(CHAT_LAST_CONV_KEY, "old-conv");
    api.mockImplementation((path) => {
      if (path.startsWith("/api/conversations")) {
        return Promise.reject(Object.assign(new Error("서버 응답을 해석하지 못했습니다."), { status: 200, kind: "invalid_response" }));
      }
      return Promise.reject(new Error("unexpected path: " + path));
    });

    const { result } = renderHook(() => useChat(), { wrapper });

    await waitFor(() => expect(result.current.convs.isError).toBe(true));
    // 대화 목록을 못 받았으니 cid는 여전히 null이어야 하고, 무엇보다 복원 포인터를
    // 지우면 안 된다 — 나중에 재시도/새로고침이 성공했을 때 그 값을 다시 읽어야 한다.
    expect(result.current.cid).toBeNull();
    expect(window.sessionStorage.getItem(CHAT_LAST_CONV_KEY)).toBe("old-conv");
  });
});
