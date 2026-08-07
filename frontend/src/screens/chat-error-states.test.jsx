import React from "react";
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 채팅 화면의 **없음 / 못 불러왔음 / 불러오는 중** 구분 (E-4 · E-5) + 유휴 신호 배선 (X12).
 *
 * 세 상태가 화면에서 똑같이 보이면 사용자는 기다려야 하는지, 다시 눌러야 하는지, 아니면
 * 정말 아무것도 없는 것인지 알 방법이 없다. 여기서 고정하는 것:
 *
 *  1. 홈의 팀 채팅 위젯이 오류를 **조용히 숨기지 않는다**(예전엔 통째로 사라졌다).
 *  2. 기능이 없는 것(404)과 고장난 것(500)은 다르게 다룬다 — 없는 기능의 오류 상자는 소음이다.
 *  3. 불러오는 중에는 스켈레톤이 자리를 잡는다(빈 화면과 구분된다).
 *  4. **이미 읽던 대화가 있는데 폴링만 실패한 경우 대화를 지우지 않는다.** 예전에는 이때
 *     대화 전체가 "불러오지 못했습니다." 한 줄로 대체됐다 — 잠깐의 끊김이 화면에서는
 *     대화가 지워진 것처럼 보였다.
 *  5. 자리를 비운 뒤의 폴링에는 `idle=1` 이 붙고, 자리에 있을 때는 붙지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { TeamChatWidget } from "./TeamChatWidget.jsx";
import { ChatPane } from "./ChatPane.jsx";
import { IDLE_AFTER_MS } from "../lib/idle.js";

function httpError(status, message) {
  const e = new Error(message);
  e.status = status;
  return e;
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
}

function wrap(node, qc = newClient()) {
  return { qc, ...render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>) };
}

function messagesPayload(messages) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "방", member_count: 2 },
    members: [], messages, seq: messages.length, people: {},
    you: { user_id: "u1", role: "member", last_read_seq: 99, is_member: true },
  };
}

function messageUrls() {
  return apiMock.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.startsWith("/api/team-chat/rooms/r1/messages"));
}

beforeEach(() => { apiMock.mockReset(); });
afterEach(() => { vi.restoreAllMocks(); });

// ── 1. 홈 팀 채팅 위젯 ──────────────────────────────────────────────────────

describe("홈 팀 채팅 위젯", () => {
  it("서버 오류를 조용히 숨기지 않는다 — 제목, 이유, 다시 시도가 남는다", async () => {
    apiMock.mockRejectedValue(httpError(500, "서버에서 문제가 생겼습니다."));
    wrap(<TeamChatWidget />);

    // 제목이 남아야 '어느 카드가 실패했는지'를 알 수 있다.
    expect(await screen.findByText("팀 채팅")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /다시 시도/ })).toBeInTheDocument();
  });

  it("기능이 없는 것(404)은 고장이 아니다 — 그때만 숨긴다", async () => {
    apiMock.mockRejectedValue(httpError(404, "찾을 수 없습니다."));
    const { container } = wrap(<TeamChatWidget />);
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    await waitFor(() => expect(container.textContent).not.toContain("팀 채팅"));
  });

  it("불러오는 중에는 빈 화면이 아니라 스켈레톤이 자리를 잡는다", async () => {
    apiMock.mockImplementation(() => new Promise(() => {}));  // 끝나지 않는다 = 로딩 상태
    const { container } = wrap(<TeamChatWidget />);
    expect(await screen.findByText("팀 채팅")).toBeInTheDocument();
    // 낭독용 문구("불러오는 중…")만 보면 회색 한 줄짜리 안내도 통과한다 —
    // **자리를 잡는 회색 블록**이 실제로 그려졌는지를 본다(레이아웃이 나중에 튀지 않게).
    expect(await screen.findByText("불러오는 중…")).toBeInTheDocument();
    expect(container.querySelectorAll(".MuiSkeleton-root").length).toBeGreaterThan(0);
  });
});

// ── 2. 대화창 ───────────────────────────────────────────────────────────────

describe("대화창", () => {
  it("처음부터 실패하면 이유와 다시 시도를 보여 준다", async () => {
    apiMock.mockRejectedValue(httpError(500, "서버에서 문제가 생겼습니다."));
    wrap(<ChatPane roomId="r1" interval={false} />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /다시 시도/ })).toBeInTheDocument();
  });

  it("불러오는 중에는 스켈레톤이 보인다", async () => {
    apiMock.mockImplementation(() => new Promise(() => {}));
    const { container } = wrap(<ChatPane roomId="r1" interval={false} />);
    expect(await screen.findByText("불러오는 중…")).toBeInTheDocument();
    // 회색 한 줄 안내와 구분한다 — 예전 화면이 정확히 그 한 줄이었다.
    expect(container.querySelectorAll(".MuiSkeleton-root").length).toBeGreaterThan(0);
  });

  it("읽던 대화가 있는데 폴링만 실패하면 대화를 지우지 않는다", async () => {
    apiMock.mockResolvedValue(messagesPayload([
      { seq: 1, kind: "text", sender_user_id: "u2", sender_name: "동료",
        body: "내일 회의 자료 올려 뒀어요", created_at: "2026-08-07T09:00:00", images: [] },
    ]));
    const { qc } = wrap(<ChatPane roomId="r1" interval={false} />);
    expect(await screen.findByText("내일 회의 자료 올려 뒀어요")).toBeInTheDocument();

    // 다음 폴링이 끊긴다.
    apiMock.mockRejectedValue(httpError(503, "서버에 연결할 수 없습니다."));
    await qc.refetchQueries({ queryKey: ["team-chat-msgs", "r1"] });

    // 대화는 그대로 남아 있어야 한다.
    expect(await screen.findByText("내일 회의 자료 올려 뒀어요")).toBeInTheDocument();
    // 그리고 낡았다는 사실은 말해야 한다.
    expect(await screen.findByText(/새 메시지를 받지 못했습니다/)).toBeInTheDocument();
  });
});

// ── 3. 유휴 신호 (X12) ──────────────────────────────────────────────────────

describe("유휴 신호", () => {
  it("자리에 있는 동안에는 idle 을 붙이지 않는다", async () => {
    apiMock.mockResolvedValue(messagesPayload([]));
    wrap(<ChatPane roomId="r1" interval={false} />);
    await waitFor(() => expect(messageUrls().length).toBeGreaterThan(0));
    expect(messageUrls().every((u) => !u.includes("idle="))).toBe(true);
  });

  it("입력이 없는 채로 임계값을 넘기면 그 다음 폴링에 idle=1 이 붙는다", async () => {
    // 마운트 시각을 고정한 뒤 시계만 앞으로 민다 — 실제 10분을 기다리지 않는다.
    const t0 = 1_800_000_000_000;
    const clock = vi.spyOn(Date, "now").mockReturnValue(t0);

    apiMock.mockResolvedValue(messagesPayload([]));
    const { qc } = wrap(<ChatPane roomId="r1" interval={false} />);
    await waitFor(() => expect(messageUrls().length).toBeGreaterThan(0));

    clock.mockReturnValue(t0 + IDLE_AFTER_MS + 1000);
    await qc.refetchQueries({ queryKey: ["team-chat-msgs", "r1"] });

    const last = messageUrls().at(-1);
    expect(last).toContain("idle=1");
  });

  it("돌아와서 한 번 움직이면 그 다음 폴링에서 idle 이 떨어진다", async () => {
    const t0 = 1_800_000_000_000;
    const clock = vi.spyOn(Date, "now").mockReturnValue(t0);

    apiMock.mockResolvedValue(messagesPayload([]));
    const { qc } = wrap(<ChatPane roomId="r1" interval={false} />);
    await waitFor(() => expect(messageUrls().length).toBeGreaterThan(0));

    clock.mockReturnValue(t0 + IDLE_AFTER_MS + 1000);
    await qc.refetchQueries({ queryKey: ["team-chat-msgs", "r1"] });
    expect(messageUrls().at(-1)).toContain("idle=1");

    // 사람이 돌아와 마우스를 움직였다.
    window.dispatchEvent(new Event("pointermove"));
    await qc.refetchQueries({ queryKey: ["team-chat-msgs", "r1"] });
    expect(messageUrls().at(-1)).not.toContain("idle=");
  });
});
