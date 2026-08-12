import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { Message, TypingBubble } from "./MessageThread.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* AI-08: "진행 표시가 가짜" — 러너가 응답마다 timing.{total_ms,ai_ms}를 돌려주고 플랫폼이
 * 그대로 저장하는데(structured_payload_json), 화면 어디서도 안 읽었다. 완료된 메시지엔
 * 실제 처리 시간을, 대기 중엔(아직 timing이 없으니) 최소한 실제 경과 시간을 보여준다 —
 * 둘 다 이전엔 전혀 없던 정보다. */

function renderMessage(m, props) {
  return render(
    <ThemeModeProvider>
      <Message m={m} isLast hideCards={false} {...props} />
    </ThemeModeProvider>
  );
}

describe("완료된 어시스턴트 메시지가 실제 처리 시간을 보여준다 (AI-08)", () => {
  it("structured.timing.total_ms가 있으면 '3.2초' 같은 캡션이 뜬다", () => {
    renderMessage({
      id: "m1", role: "assistant", content: "답변입니다.", processing_status: "done",
      created_at: "2026-01-01T00:00:03", structured: { timing: { total_ms: 3200, ai_ms: 2800 } },
    });
    expect(screen.getByText("3.2초")).toBeInTheDocument();
  });

  it("timing이 없는 메시지(옛 데이터·오류 안내)엔 캡션이 안 뜬다", () => {
    renderMessage({
      id: "m2", role: "assistant", content: "안내 문구입니다.", processing_status: "done",
      created_at: "2026-01-01T00:00:03", structured: { error_notice: true },
    });
    expect(screen.queryByText(/\d\.\d초/)).toBeNull();
  });

  it("사용자 메시지엔(timing이 있어도) 캡션을 안 그린다 — 처리 시간은 어시스턴트 응답의 것", () => {
    renderMessage({
      id: "m3", role: "user", content: "질문입니다.", processing_status: "done",
      created_at: "2026-01-01T00:00:03", structured: { timing: { total_ms: 9999 } },
    });
    expect(screen.queryByText(/초$/)).toBeNull();
  });
});

describe("타이핑 말풍선이 실제 경과 시간을 보여준다 (AI-08)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  function renderBubble(since) {
    return render(
      <ThemeModeProvider>
        <TypingBubble since={since} />
      </ThemeModeProvider>
    );
  }

  it("since가 없으면(예전 그대로) 경과 초 표시가 없다", () => {
    renderBubble(undefined);
    expect(screen.queryByText(/^\d+초$/)).toBeNull();
  });

  it("since가 있으면 1초마다 경과 초가 올라간다(무한 반복 애니메이션만 있던 것과 다르게)", () => {
    const start = Date.parse("2026-01-01T00:00:00Z");
    vi.useFakeTimers();
    vi.setSystemTime(start);
    renderBubble("2026-01-01T00:00:00Z");
    expect(screen.getByText("0초")).toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(3000); });
    expect(screen.getByText("3초")).toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(8000); });
    expect(screen.getByText("11초")).toBeInTheDocument();
  });
});
