import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  mascotMode, MASCOT_PHASE_TEXT, pollDelayMs, structuredCards,
  POLL_BASE_MS, POLL_MAX_MS, POLL_MAX_FAILURES, POLL_RECOVERY_MS,
} from "./chat-helpers.js";

/* 채팅 화면의 '상태' 쪽 테스트.
 *
 * chat-helpers.test.js가 순수 파서·포맷터를 지킨다면 이 파일은 두 가지를 지킨다:
 *   1) 마스코트가 **앱이 실제로 있는 상태만** 연기하는가(mascotMode).
 *   2) 느린 러너를 상대로 폴링이 백오프하고, 완전히 포기하는 대신 느리게 계속 회복을 확인하는가
 *      (AI-11) — 가짜 타이머로 진짜 훅을 돌린다. 이 화면의 값어치 대부분이 여기 있는데, 예전엔
 *      refetchInterval 콜백 안에 인라인 산술로만 존재해 아무도 검증할 수 없었다.
 */

// ── 1. 마스코트 단계 매핑 ───────────────────────────────────────────────────

describe("mascotMode", () => {
  it("아무 일도 없으면 idle", () => {
    expect(mascotMode()).toBe("idle");
    expect(mascotMode({})).toBe("idle");
  });

  it("컴포저에 포커스가 있으면 listening", () => {
    expect(mascotMode({ composerFocused: true })).toBe("listening");
  });

  it("전송 중이면 thinking", () => {
    expect(mascotMode({ sending: true })).toBe("thinking");
  });

  it("답을 기다리는 중이면 thinking", () => {
    expect(mascotMode({ awaitingReply: true })).toBe("thinking");
    expect(mascotMode({ busy: true })).toBe("thinking");
  });

  it("방금 답이 도착했고 결과 카드가 없으면 responding", () => {
    expect(mascotMode({ justAnswered: true })).toBe("responding");
    expect(mascotMode({ justAnswered: true, hasResult: false })).toBe("responding");
  });

  it("방금 답이 도착했고 결과 카드가 있으면 success", () => {
    expect(mascotMode({ justAnswered: true, hasResult: true })).toBe("success");
  });

  it("실패했으면 error", () => {
    expect(mascotMode({ failed: true })).toBe("error");
  });

  it("점검·속도제한으로 막혔으면 error", () => {
    expect(mascotMode({ blocked: true })).toBe("error");
  });

  it("우선순위: 실패가 처리 중·답변 도착·포커스를 모두 이긴다", () => {
    expect(mascotMode({ failed: true, busy: true, justAnswered: true, composerFocused: true })).toBe("error");
  });

  it("우선순위: 처리 중이 '방금 도착'과 포커스를 이긴다", () => {
    // 새 요청이 이미 날아간 뒤라면 직전 답변의 responding을 계속 연기하면 안 된다.
    expect(mascotMode({ busy: true, justAnswered: true, composerFocused: true })).toBe("thinking");
  });

  it("우선순위: '방금 도착'이 포커스를 이긴다", () => {
    // 답이 오는 순간 사용자의 커서는 대개 컴포저에 있다 — 그때 listening으로 되돌아가면
    // 답이 도착했다는 사실 자체가 화면에서 사라진다.
    expect(mascotMode({ justAnswered: true, composerFocused: true })).toBe("responding");
  });

  it("'방금 도착'이 지나가면 (포커스가 있으면) listening으로 돌아온다", () => {
    expect(mascotMode({ justAnswered: false, composerFocused: true })).toBe("listening");
  });

  it("앱이 쓰는 모든 단계에 낭독용 문구가 있다 — 그림만으로 상태를 전하지 않는다", () => {
    const modes = ["idle", "listening", "thinking", "responding", "success", "error"];
    modes.forEach((m) => {
      expect(typeof MASCOT_PHASE_TEXT[m]).toBe("string");
      expect(MASCOT_PHASE_TEXT[m].length).toBeGreaterThan(0);
    });
  });
});

// ── 2. 폴링 스케줄(순수) ────────────────────────────────────────────────────

describe("pollDelayMs", () => {
  it("실패가 없으면 기본 간격", () => {
    expect(pollDelayMs(0)).toBe(POLL_BASE_MS);
    expect(pollDelayMs(undefined)).toBe(POLL_BASE_MS);
  });
  it("실패가 쌓이면 2배씩 늘되 상한에서 멈춘다", () => {
    expect(pollDelayMs(1)).toBe(3000);
    expect(pollDelayMs(2)).toBe(POLL_MAX_MS);   // 6000 → 5000으로 잘림
    expect(pollDelayMs(3)).toBe(POLL_MAX_MS);
    expect(pollDelayMs(4)).toBe(POLL_MAX_MS);
  });
  it("연속 실패가 한도에 닿으면 완전히 멈추는 대신 느린 회복 확인 간격으로 내려간다 (AI-11)", () => {
    expect(pollDelayMs(POLL_MAX_FAILURES)).toBe(POLL_RECOVERY_MS);
    expect(pollDelayMs(POLL_MAX_FAILURES + 3)).toBe(POLL_RECOVERY_MS);
  });
});

// ── 3. 구조화 결과 정규화 ───────────────────────────────────────────────────

describe("structuredCards", () => {
  it("structured가 없으면 아무것도 없다", () => {
    const p = structuredCards({ role: "assistant" });
    expect(p.hasCards).toBe(false);
    expect(p.hasAny).toBe(false);
    expect(p.tickets).toEqual([]);
  });
  it("tickets 배열과 단일 ticket을 이어붙이되 순번 기준(ticketsArr)은 배열분만이다", () => {
    const p = structuredCards({ structured: { tickets: [{ title: "A" }, { title: "B" }], ticket: { title: "C" } } });
    expect(p.tickets.map((t) => t.title)).toEqual(["A", "B", "C"]);
    expect(p.ticketsArr).toHaveLength(2);   // 본문 번호 목록과 짝이 맞는 것은 이 둘뿐
    expect(p.hasAny).toBe(true);
  });
  it("스칼라·null이 와도 터지지 않는다", () => {
    const p = structuredCards({ structured: { tickets: "nope", projects: 3, items: null } });
    expect(p.tickets).toEqual([]);
    expect(p.projects).toEqual([]);
    expect(p.hasCards).toBe(false);
  });
  it("카드가 없고 허용 도메인 문서 링크만 있으면 그 링크를 낸다", () => {
    const p = structuredCards({ structured: { notion_url: "https://www.notion.so/x" } });
    expect(p.notionUrl).toBe("https://www.notion.so/x");
    expect(p.notionUnsafe).toBe("");
    expect(p.hasAny).toBe(true);
  });
  it("allowlist에 걸린 링크도 버리지 않고 '열 수 없는 참조'로 남긴다", () => {
    const p = structuredCards({ structured: { notion_url: "https://evil.com/x" } });
    expect(p.notionUrl).toBe("");
    expect(p.notionUnsafe).toBe("https://evil.com/x");
    expect(p.hasAny).toBe(true);
  });
});

// ── 4. 진짜 훅 + 가짜 타이머로 본 폴링 백오프·포기 ──────────────────────────

// api 모듈을 갈아끼워 훅이 실제로 부르는 URL과 시각을 기록한다.
const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args) }));

// useChat은 matchMedia로 좁은 폭을 감지한다(jsdom 기본 구현이 없을 수 있다).
function stubMatchMedia() {
  if (typeof window.matchMedia === "function") return;
  window.matchMedia = () => ({
    matches: false, media: "", onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  });
}

// 훅만 돌리는 최소 하네스 — 화면(JSX)은 이 테스트의 관심사가 아니다.
let useChat;
function Harness() {
  useChat();
  return null;
}

describe("스레드 폴링 — 백오프하고, 완전히 포기하는 대신 느리게 계속 확인한다 (AI-11)", () => {
  const T0 = Date.parse("2026-01-01T00:00:00Z");
  let messageCallTimes;

  beforeEach(async () => {
    vi.useFakeTimers();
    vi.setSystemTime(T0);
    stubMatchMedia();
    apiMock.mockReset();
    messageCallTimes = [];
    // useChat은 api를 모듈 최상단에서 import하므로, 모킹이 걸린 뒤에 동적으로 불러와야 한다.
    ({ useChat } = await import("./useChat.js"));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function mountWith({ failAfterFirstMessageFetch, recoverAtFetch = Infinity }) {
    let messageFetches = 0;
    apiMock.mockImplementation((url) => {
      if (url.startsWith("/api/conversations/") && url.endsWith("/messages")) {
        messageFetches += 1;
        messageCallTimes.push(Date.now());
        if (failAfterFirstMessageFetch && messageFetches > 1 && messageFetches < recoverAtFetch) {
          return Promise.reject(Object.assign(new Error("boom"), { status: 500 }));
        }
        return Promise.resolve({
          items: [{ id: "m1", role: "user", content: "안녕", processing_status: "pending", created_at: "2026-01-01T00:00:00" }],
        });
      }
      if (url.startsWith("/api/conversations")) {
        return Promise.resolve({ items: [{ id: "c1", title: "대화", updated_at: "2026-01-01T00:00:00" }] });
      }
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    return render(
      <QueryClientProvider client={qc}><Harness /></QueryClientProvider>
    );
  }

  it("정상일 때는 기본 간격(1.5초)으로 계속 따라간다", async () => {
    const view = mountWith({ failAfterFirstMessageFetch: false });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_BASE_MS * 3 + 100); });
    const gaps = messageCallTimes.slice(1).map((t, i) => t - messageCallTimes[i]);
    expect(messageCallTimes.length).toBeGreaterThanOrEqual(4);
    gaps.forEach((g) => expect(g).toBe(POLL_BASE_MS));
    view.unmount();
  });

  it("실패가 쌓이면 간격을 2배씩 늘리고(상한 5초), 5회 넘으면 완전히 멈추는 대신 20초 회복 확인으로 내려간다 (AI-11)", async () => {
    const view = mountWith({ failAfterFirstMessageFetch: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    // 1.5s + 3s + 5s + 5s + 5s = 19.5s 안에 실패 5회가 모두 일어난다.
    await act(async () => { await vi.advanceTimersByTimeAsync(19500); });

    const gaps = messageCallTimes.slice(1).map((t, i) => t - messageCallTimes[i]);
    // 첫 성공 이후: 1500 → 3000 → 5000(6000이 상한에 잘림) → 5000 → 5000
    expect(gaps.slice(0, 3)).toEqual([POLL_BASE_MS, 3000, POLL_MAX_MS]);
    // 성공 1회 + 실패 5회 = 6회.
    expect(messageCallTimes).toHaveLength(1 + POLL_MAX_FAILURES);

    // AI-11: 예전엔 여기서 완전히 멈췄다(그 뒤로 몇 분을 흘려보내도 호출 0). 이제 죽은 서버를
    // 촘촘히 두드리지는 않지만(POLL_RECOVERY_MS=20초 간격), 완전히 사라지지도 않는다 — 계속
    // 흘려보내면 20초마다 한 번씩 계속 조용히 확인한다.
    const beforeRecoveryProbes = messageCallTimes.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_RECOVERY_MS * 3); });
    const probes = messageCallTimes.slice(beforeRecoveryProbes);
    expect(probes).toHaveLength(3);
    const probeGaps = probes.map((t, i) => t - (i === 0 ? messageCallTimes[beforeRecoveryProbes - 1] : probes[i - 1]));
    probeGaps.forEach((g) => expect(g).toBe(POLL_RECOVERY_MS));
    view.unmount();
  });

  it("회복 확인이 성공하면 사람이 아무것도 안 눌러도 기본 간격으로 저절로 돌아온다 (AI-11)", async () => {
    // 2~6번째 호출(실패 5회로 포기 상태 진입)까지는 위 시험과 같고, 7번째부터 서버가 살아난다.
    const view = mountWith({ failAfterFirstMessageFetch: true, recoverAtFetch: 7 });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(19500); });
    expect(messageCallTimes).toHaveLength(1 + POLL_MAX_FAILURES); // 6, 포기 상태

    // 20초 뒤 회복 확인(7번째 호출)이 이번엔 성공한다.
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_RECOVERY_MS); });
    expect(messageCallTimes).toHaveLength(7);
    expect(messageCallTimes[6] - messageCallTimes[5]).toBe(POLL_RECOVERY_MS);

    // 성공했으니 pollFailRef가 0으로 리셋되고, 다음 간격은 기본값(1.5초)으로 저절로 돌아온다 —
    // "새로고침" 버튼을 누르는 사람의 개입이 전혀 없었다.
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_BASE_MS + 100); });
    expect(messageCallTimes).toHaveLength(8);
    expect(messageCallTimes[7] - messageCallTimes[6]).toBe(POLL_BASE_MS);
    view.unmount();
  });
});
