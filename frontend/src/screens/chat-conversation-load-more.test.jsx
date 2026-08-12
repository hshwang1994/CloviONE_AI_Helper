import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ConversationSidebar } from "./chat/ConversationSidebar.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* AI-18: 대화 목록이 100개 고정 상한이었고 그 이상은 스크롤로도 영영 안 보였다. 이제
 * useChat.js가 total로 상한 너머를 판단해 hasMoreConvs를 내려주면, 여기(사이드바)는 그 값만
 * 보고 "대화 더 보기" 버튼을 그리거나 숨긴다 — 훅의 페이지네이션 계산과 화면의 렌더링을
 * 분리해서 본다(chat-bulk-archive-empty.test.jsx와 같은 직접-props 렌더 방식). */

function conv(id, extra = {}) {
  return { id, title: "대화 " + id, archived: false, updated_at: "2026-08-10T00:00:00", ...extra };
}

function baseProps(overrides = {}) {
  return {
    asideRef: { current: null }, listIsDrawer: false, sideOpen: false,
    closeSideDrawer: () => {}, setSideOpen: () => {},
    convs: { isLoading: false, isError: false, isFetching: false },
    convItems: [conv("c1")],
    convFilter: "", setConvFilter: () => {}, showArchived: false, setShowArchived: () => {},
    cid: null, setCid: () => {}, setComposingNew: () => {}, clearDraft: () => {}, textareaRef: { current: null },
    renameConv: { mutateAsync: vi.fn() },
    archiveConv: { mutate: vi.fn(), mutateAsync: vi.fn(() => Promise.resolve()) },
    deleteConv: { mutate: vi.fn() },
    confirm: vi.fn(() => Promise.resolve(true)),
    hasMoreConvs: false,
    loadMoreConvs: vi.fn(),
    ...overrides,
  };
}

function renderSidebar(overrides) {
  const props = baseProps(overrides);
  render(<ThemeModeProvider><ConversationSidebar {...props} /></ThemeModeProvider>);
  return props;
}

describe("대화 목록 '더 보기' (AI-18)", () => {
  it("hasMoreConvs가 false면 버튼이 없다(대화가 상한 이하인 절대다수)", () => {
    renderSidebar({ hasMoreConvs: false });
    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
  });

  it("hasMoreConvs가 true면 버튼이 보이고 누르면 loadMoreConvs를 부른다", async () => {
    const user = userEvent.setup();
    const props = renderSidebar({ hasMoreConvs: true });
    const btn = screen.getByRole("button", { name: "대화 더 보기" });
    await user.click(btn);
    expect(props.loadMoreConvs).toHaveBeenCalledTimes(1);
  });

  it("다음 페이지를 받는 동안(isFetching) 버튼이 비활성화되고 문구가 바뀐다", () => {
    renderSidebar({ hasMoreConvs: true, convs: { isLoading: false, isError: false, isFetching: true } });
    const btn = screen.getByRole("button", { name: "불러오는 중…" });
    expect(btn).toBeDisabled();
  });

  it("목록이 비어 있으면 hasMoreConvs가 true여도 버튼을 그리지 않는다", () => {
    // total도 함께 0이 되어 실제로는 훅이 hasMoreConvs:false를 내려주지만, 화면 쪽 렌더링
    // 자체가 빈 상태 분기 안에 더 보기 버튼을 둘 수 없는 구조인지 독립적으로 확인한다.
    renderSidebar({ convItems: [], hasMoreConvs: true });
    expect(screen.getByText("아직 대화가 없습니다")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
  });
});
