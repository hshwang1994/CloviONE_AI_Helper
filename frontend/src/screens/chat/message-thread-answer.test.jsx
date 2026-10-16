/* 도우미 답 말풍선 — 서버가 만든 구조만 그린다 (D-535).
 *
 * qa-contract-change: AI 채팅 개선 회차 — 「걸린 시간 N초」는 「N초 걸림」, 「확인한 내용」은 답의 「더 보기」 메뉴 안, 답 아래 출처는
 * 접기 「참고 자료 N개」(넓은 틀의 참고 자료 판이 서면 `panelDocked` 로 숨는다), 「찾아본 자료」도 같은 접기다. 단언 수는 그대로다.
 *
 * qa-contract-replaced-by: frontend/src/screens/chat/message-thread-response-time.test.jsx
 *
 * 걸린 시간은 서버가 잰 한 차례의 시간(`elapsed_ms`)이고, 「찾지 못함」은 정상 답(오류색 아님)에 찾아본 검색어와 다음 길이
 * 붙는다. 글 속 티켓 키는 그 답의 출처에 있을 때만 링크다 — 모델이 지어낸 키는 링크가 되지 않는다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
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
    expect(screen.getByText("3.2초 걸림")).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: "답 더 보기" }));
    await user.click(screen.getByRole("menuitem", { name: "확인한 내용 보기" }));
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

  it("지난 답의 인용은 접힌 「참고 자료」로 그려지고, 참고 자료 판이 서면 답 아래에서는 숨는다", async () => {
    const user = userEvent.setup();
    const old = answer({ citations: [{ document_id: "d1", document_title: "연차 규정", route: "/knowledge/d1" }] });
    const { unmount } = renderMessage(old);
    await user.click(screen.getByRole("button", { name: "참고 자료 1개" }));
    expect(screen.getByRole("link", { name: "연차 규정" })).toBeInTheDocument();
    unmount();
    renderMessage(old, { panelDocked: true, onShowSources: () => {} });
    expect(screen.queryByRole("link", { name: "연차 규정" })).toBeNull();
    expect(screen.getByRole("button", { name: "참고 자료 1" })).toBeInTheDocument();
  });

  it("오류 안내 말풍선에는 출처 · 걸린 시간 · 복사가 붙지 않는다", () => {
    renderMessage(answer({ error_notice: true, elapsed_ms: 1000, sources: [
      { type: "document", id: "d1", title: "연차 규정", route: "/knowledge/d1" },
    ] }, "AI 연결이 끊겨 있습니다. 관리자에게 알려 주세요."));
    expect(screen.queryByRole("link", { name: "연차 규정" })).toBeNull();
    expect(screen.queryByText(/1\.0초/)).toBeNull();
    expect(screen.queryByRole("button", { name: "답 복사" })).toBeNull();
  });
});

/* A8(D-569) — 답 안의 「[제목](경로)」는 그 답의 출처에 있는 경로일 때만 링크이고, 「확인한 내용」은 서버가 센 전체 수를 함께 말한다. */
describe("답 안의 출처 링크와 확인한 수", () => {
  const SOURCES = [
    { type: "document", id: "d1", title: "연차 규정", route: "/knowledge/d1?block=b1" },
    { type: "ticket", id: "t-1", title: "결재 화면", route: "/tickets/t-1", key: "ABCDEF-12" },
    { type: "sprint", id: "s-1", title: "10월 2주 회차", route: "/sprint?team=dep-1&sprint=s-1" },
  ];

  it("출처에 있는 경로만 링크가 되고, 지어낸 경로는 글자 그대로 남는다", () => {
    renderMessage(answer({ kind: "assistant", sources: SOURCES },
      "- [규정 문서](/knowledge/d1) **중요**\n- [회의 결정](/sprint?team=dep-1&sprint=s-1)\n- [없는 문서](/knowledge/zz)"));
    expect(screen.getByRole("link", { name: "규정 문서" })).toHaveAttribute("href", "#/knowledge/d1?block=b1");
    expect(screen.getByRole("link", { name: "회의 결정" })).toHaveAttribute("href", "#/sprint?team=dep-1&sprint=s-1");
    expect(screen.queryByRole("link", { name: "없는 문서" })).toBeNull();
    expect(screen.getByText(/\[없는 문서\]\(\/knowledge\/zz\)/)).toBeInTheDocument();
    expect(screen.getByText("중요").tagName).toBe("STRONG");
  });

  it("참고 자료 판이 출처를 대신 보여 줄 때(답 아래 출처 숨김)도 답 안 링크는 그대로다", () => {
    renderMessage(answer({ kind: "assistant", sources: SOURCES }, "[규정 문서](/knowledge/d1)를 보세요."), { panelDocked: true });
    expect(screen.getByRole("link", { name: "규정 문서" })).toHaveAttribute("href", "#/knowledge/d1?block=b1");
    expect(screen.queryByRole("link", { name: "연차 규정" })).toBeNull();
  });

  it("오류 안내 말풍선의 마크다운 링크는 링크가 아니다(출처가 없다)", () => {
    renderMessage(answer({ kind: "assistant", error_notice: true, sources: SOURCES }, "[규정 문서](/knowledge/d1)"));
    expect(screen.queryByRole("link", { name: "규정 문서" })).toBeNull();
  });

  it("「확인한 내용」은 전체 수가 더 많으면 「N건 중 M건」을, 같으면 「N건」을, 모르면 아무것도 붙이지 않는다", async () => {
    const user = userEvent.setup();
    renderMessage(answer({ kind: "assistant", tools: [
      { name: "search_documents", label: "사내 문서 검색", ok: true, count: 8, total: 25, query: "연차" },
      { name: "my_documents", label: "내 문서", ok: true, count: 3, total: 3 },
      { name: "my_work", label: "내 업무", ok: true, count: 2, total: null },
    ] }));
    await user.click(screen.getByRole("button", { name: "답 더 보기" }));
    await user.click(screen.getByRole("menuitem", { name: "확인한 내용 보기" }));
    expect(screen.getByText("사내 문서 검색에서 「연차」를 찾았습니다. (전체 25건 중 8건)")).toBeInTheDocument();
    expect(screen.getByText("내 문서를 확인했습니다. (전체 3건)")).toBeInTheDocument();
    expect(screen.getByText("내 업무를 확인했습니다.")).toBeInTheDocument();
  });
});

describe("입력 중 말풍선", () => {
  it("서버가 적은 진행 문구를 보인다", () => {
    render(<ThemeModeProvider><TypingBubble label="사내 문서를 찾고 있습니다." /></ThemeModeProvider>);
    expect(screen.getAllByText(/사내 문서를 찾고 있습니다/).length).toBeGreaterThan(0);
  });
});

/* P-133 — 답이 아무 출처도 인용하지 않으면(찾지 못함 · 뜻만 가까운 문서) 출처 묶음은 「참고한 자료」가 아니라 접힌 「찾아본 자료」다. */
describe("인용하지 않은 출처", () => {
  const NEAR = [
    { type: "document", id: "d7", title: "출장비 정산 안내", route: "/knowledge/d7", cited: false },
    { type: "document", id: "d8", title: "해외 출장 체크리스트", route: "/knowledge/d8", cited: false },
  ];

  it("하나도 인용하지 않은 답은 「찾아본 자료」를 접어 두고, 펼치면 그 뜻을 한 문장으로 말한다", async () => {
    const user = userEvent.setup();
    renderMessage(answer({ kind: "assistant", notice: "no_results", sources: NEAR }, "사내 문서에서 2031년 우주 출장 규정을 찾지 못했습니다."));
    expect(screen.queryByRole("button", { name: /^참고 자료/ })).toBeNull();
    expect(screen.queryByRole("link", { name: "출장비 정산 안내" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "찾아본 자료 2개" }));
    expect(screen.getByText("답을 찾는 동안 살펴봤지만 답에는 쓰지 않은 자료입니다.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "출장비 정산 안내" })).toHaveAttribute("href", "#/knowledge/d7");
    expect(screen.getByRole("button", { name: "찾아본 자료 2개" })).toHaveAttribute("aria-expanded", "true");
  });

  it("하나라도 인용했거나 인용 표시가 없는 옛 답이면 「참고 자료」다 — 인용한 것만 센다", () => {
    const { unmount } = renderMessage(answer({ kind: "assistant", sources: [{ ...NEAR[0], cited: true }, NEAR[1]] }, "[출장비 정산 안내](/knowledge/d7)를 보세요."));
    expect(screen.getByRole("button", { name: "참고 자료 1개" })).toBeInTheDocument();
    unmount();
    renderMessage(answer({ kind: "assistant", sources: NEAR.map(({ cited, ...rest }) => rest) }));
    expect(screen.getByRole("button", { name: "참고 자료 2개" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /찾아본 자료/ })).toBeNull();
  });
});
