import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { Message } from "./MessageThread.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* AI-36/AI-68: 재생성·삭제·피드백(👍/👎) 버튼 배선 — 확인 대화상자 자체는 useChat.js의
 * doDeleteMessage가 useConfirm()으로 처리한다(team_chat/ChatPane.jsx의 같은 기능과 동일
 * 원칙). 여기서는 Message가 "보여야 할 때 보이고, 누르면 정확한 콜백을 부르는지"만 본다 —
 * Message 자신은 확인 로직을 모르는 순수 컴포넌트다. */

function renderMessage(m, props) {
  return render(
    <ThemeModeProvider>
      <Message m={m} {...props} />
    </ThemeModeProvider>
  );
}

const DONE_ASSISTANT = {
  id: "a1", role: "assistant", content: "답변입니다.", processing_status: "done",
  created_at: "2026-01-01T00:00:03",
};

describe("재생성 버튼 (AI-36)", () => {
  it("마지막 어시스턴트 메시지에만 뜬다", () => {
    renderMessage(DONE_ASSISTANT, { isLast: true, onRegenerate: vi.fn() });
    expect(screen.getByRole("button", { name: "답변 다시 생성" })).toBeInTheDocument();
  });

  it("마지막 메시지가 아니면 안 뜬다 — 백엔드의 _is_last_turn 가드와 같은 취지", () => {
    renderMessage(DONE_ASSISTANT, { isLast: false, onRegenerate: vi.fn() });
    expect(screen.queryByRole("button", { name: "답변 다시 생성" })).toBeNull();
  });

  it("onRegenerate가 없으면(핸들러 미배선) 안 뜬다", () => {
    renderMessage(DONE_ASSISTANT, { isLast: true });
    expect(screen.queryByRole("button", { name: "답변 다시 생성" })).toBeNull();
  });

  it("누르면 콜백이 인자 없이 호출된다 — 대상은 항상 '마지막 질문'뿐(useChat.js lastUserMsg)", async () => {
    const user = userEvent.setup();
    const onRegenerate = vi.fn();
    renderMessage(DONE_ASSISTANT, { isLast: true, onRegenerate });
    await user.click(screen.getByRole("button", { name: "답변 다시 생성" }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it("regenerating이면 버튼이 비활성화된다 — 이중 클릭 방지", () => {
    renderMessage(DONE_ASSISTANT, { isLast: true, onRegenerate: vi.fn(), regenerating: true });
    expect(screen.getByRole("button", { name: "답변 다시 생성" })).toBeDisabled();
  });
});

describe("피드백 버튼 (AI-68)", () => {
  it("어시스턴트 메시지에만 뜬다", () => {
    renderMessage(DONE_ASSISTANT, { isLast: true, onFeedback: vi.fn() });
    expect(screen.getByRole("button", { name: "좋은 답변" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "아쉬운 답변" })).toBeInTheDocument();
  });

  it("사용자 메시지엔 안 뜬다", () => {
    renderMessage({ ...DONE_ASSISTANT, role: "user" }, { isLast: true, onFeedback: vi.fn() });
    expect(screen.queryByRole("button", { name: "좋은 답변" })).toBeNull();
  });

  it("누르면 (메시지, 값)으로 호출된다", async () => {
    const user = userEvent.setup();
    const onFeedback = vi.fn();
    renderMessage(DONE_ASSISTANT, { isLast: true, onFeedback });
    await user.click(screen.getByRole("button", { name: "좋은 답변" }));
    expect(onFeedback).toHaveBeenCalledWith(DONE_ASSISTANT, "up");
    await user.click(screen.getByRole("button", { name: "아쉬운 답변" }));
    expect(onFeedback).toHaveBeenCalledWith(DONE_ASSISTANT, "down");
  });

  it("이미 up인 메시지는 aria-pressed로 상태를 알린다", () => {
    renderMessage({ ...DONE_ASSISTANT, feedback: "up" }, { isLast: true, onFeedback: vi.fn() });
    expect(screen.getByRole("button", { name: "좋은 답변" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "아쉬운 답변" })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("삭제 버튼 (AI-36)", () => {
  it("사용자·어시스턴트 메시지 둘 다에 뜬다 — 소유권은 대화 단위", () => {
    renderMessage(DONE_ASSISTANT, { isLast: true, onDelete: vi.fn() });
    expect(screen.getByRole("button", { name: "메시지 삭제" })).toBeInTheDocument();
  });

  it("onDelete가 없으면 안 뜬다", () => {
    renderMessage(DONE_ASSISTANT, { isLast: true });
    expect(screen.queryByRole("button", { name: "메시지 삭제" })).toBeNull();
  });

  it("처리 중 메시지에는 안 뜬다 — 아직 확정 안 된 상태를 지우면 잡 상태와 어긋난다", () => {
    renderMessage({ ...DONE_ASSISTANT, processing_status: "pending" }, { isLast: true, onDelete: vi.fn() });
    expect(screen.queryByRole("button", { name: "메시지 삭제" })).toBeNull();
  });

  it("누르면 메시지 객체 그대로 콜백에 전달된다 — 확인 대화상자는 useChat.js가 담당", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    renderMessage(DONE_ASSISTANT, { isLast: true, onDelete });
    await user.click(screen.getByRole("button", { name: "메시지 삭제" }));
    expect(onDelete).toHaveBeenCalledWith(DONE_ASSISTANT);
  });
});
