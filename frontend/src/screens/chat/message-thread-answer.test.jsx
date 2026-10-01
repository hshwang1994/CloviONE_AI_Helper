/* 도우미 답 말풍선 — 서버가 만든 구조만 그린다 (D-535).
 *
 * qa-contract-replaced-by: frontend/src/screens/chat/message-thread-response-time.test.jsx
 *
 * 걸린 시간은 서버가 잰 한 차례의 시간(`elapsed_ms`)이고, 「찾지 못함」은 정상 답(오류색 아님)에 찾아본 검색어와 다음 길이
 * 붙는다. 글 속 티켓 키는 그 답의 출처에 있을 때만 링크다 — 모델이 지어낸 키는 링크가 되지 않는다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { Message, TypingBubble } from "./MessageThread.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

function renderMessage(m, props) {
  return render(
    <ThemeModeProvider>
      <Message m={m} isLast {...props} />
    </ThemeModeProvider>,
  );
}

function answer(structured, content = "답입니다.") {
  return { id: "a1", role: "assistant", content, processing_status: "done", created_at: "2026-01-01T00:00:03", structured };
}

describe("도우미 답의 구조", () => {
  it("걸린 시간은 서버가 잰 값이다", () => {
    renderMessage(answer({ kind: "assistant", elapsed_ms: 3200 }));
    expect(screen.getByText("3.2초")).toBeInTheDocument();
  });

  it("「찾지 못함」은 찾아본 검색어와 문서에서 찾기 길을 함께 보인다", () => {
    renderMessage(answer({ kind: "assistant", notice: "no_results", tools: [
      { name: "search_documents", label: "사내 문서 검색", ok: true, count: 0, query: "연차 신청" },
    ] }, "사내 문서에서 '연차 신청'과 맞는 문서를 찾지 못했습니다."));
    expect(screen.getByText(/찾아본 검색어는 연차 신청입니다/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "문서에서 찾기" })).toHaveAttribute("href", "#/ai?q=" + encodeURIComponent("연차 신청"));
    expect(screen.queryByText("처리하지 못했습니다.")).toBeNull();
  });

  it("도구를 쓰지 못한 답은 그 사실을 말한다", () => {
    renderMessage(answer({ kind: "assistant", mode: "search_only" }));
    expect(screen.getByText("도구를 쓸 수 없어 검색 결과로만 답했습니다.")).toBeInTheDocument();
  });

  it("확인한 내용은 접혀 있다가 펼치면 도구와 검색어를 문장으로 말한다", async () => {
    const user = userEvent.setup();
    renderMessage(answer({ kind: "assistant", tools: [
      { name: "search_documents", label: "사내 문서 검색", ok: true, count: 1, query: "연차" },
      { name: "my_work", label: "내 업무", ok: true, count: 2 },
    ] }));
    expect(screen.queryByText(/사내 문서 검색에서/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "확인한 내용 보기" }));
    expect(screen.getByText("사내 문서 검색에서 「연차」를 찾았습니다.")).toBeInTheDocument();
    expect(screen.getByText("내 업무를 확인했습니다.")).toBeInTheDocument();
  });

  it("글 속 티켓 키는 그 답의 출처에 있을 때만 링크다", () => {
    renderMessage(answer({ kind: "assistant", sources: [
      { type: "ticket", id: "t-1", title: "결재 화면", route: "/tickets/t-1", key: "ABCDEF-12" },
    ] }, "ABCDEF-12 는 진행 중이고 ZZZZZZ-99 는 모릅니다."));
    const links = screen.getAllByRole("link", { name: "ABCDEF-12" });
    expect(links[0]).toHaveAttribute("href", "#/tickets/t-1");
    expect(screen.queryByRole("link", { name: "ZZZZZZ-99" })).toBeNull();
  });

  it("지난 답의 인용은 출처로 그려지고, 레일이 그 출처를 들면 말풍선 안에서는 숨는다", () => {
    const old = answer({ citations: [{ document_id: "d1", document_title: "연차 규정", route: "/knowledge/d1" }] });
    const { unmount } = renderMessage(old);
    expect(screen.getByRole("link", { name: "연차 규정" })).toBeInTheDocument();
    unmount();
    renderMessage(old, { showSources: false });
    expect(screen.queryByRole("link", { name: "연차 규정" })).toBeNull();
  });

  it("오류 안내 말풍선에는 출처 · 걸린 시간 · 복사가 붙지 않는다", () => {
    renderMessage(answer({ error_notice: true, elapsed_ms: 1000, sources: [
      { type: "document", id: "d1", title: "연차 규정", route: "/knowledge/d1" },
    ] }, "AI 연결이 끊겨 있습니다. 관리자에게 알려 주세요."));
    expect(screen.queryByRole("link", { name: "연차 규정" })).toBeNull();
    expect(screen.queryByText("1.0초")).toBeNull();
    expect(screen.queryByRole("button", { name: "복사" })).toBeNull();
  });
});

describe("입력 중 말풍선", () => {
  it("서버가 적은 진행 문구를 보인다", () => {
    render(<ThemeModeProvider><TypingBubble label="사내 문서를 찾고 있습니다." /></ThemeModeProvider>);
    expect(screen.getAllByText(/사내 문서를 찾고 있습니다/).length).toBeGreaterThan(0);
  });
});
