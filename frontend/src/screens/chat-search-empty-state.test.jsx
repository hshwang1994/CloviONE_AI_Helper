import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ConversationSidebar } from "./chat/ConversationSidebar.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* AI-70: 검색어가 있는데 결과가 0건이면 "검색 결과가 없습니다"를 말해야 하는데, 예전엔
 * 그 분기가 죽은 코드였다 — `filtered`가 `convItems`의 단순 별칭(AI-38로 서버 검색 전환
 * 후)이라 `filtered.length`는 바깥 `!convItems.length` 분기가 이미 걸러낸 뒤에는 항상
 * 참이었다. 그래서 검색 결과 0건도 늘 "아직 대화가 없습니다"(또는 "보관된 대화가
 * 없습니다")로 잘못 나왔다 — 오류는 아니지만 "검색 중이었다"는 맥락을 잃는 UX 정확도
 * 문제. `convFilter`를 직접 보고 분기하도록 고쳤다(chat-conversation-load-more.test.jsx와
 * 같은 직접-props 렌더 방식).
 */

function baseProps(overrides = {}) {
  return {
    asideRef: { current: null }, listIsDrawer: false, sideOpen: false,
    closeSideDrawer: () => {}, setSideOpen: () => {},
    convs: { isLoading: false, isError: false, isFetching: false },
    convItems: [],
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

describe("대화 목록 검색 빈 상태 (AI-70)", () => {
  it("검색어가 있고 결과가 0건이면 '검색 결과가 없습니다'를 말한다", () => {
    renderSidebar({ convFilter: "존재안함", convItems: [] });
    expect(screen.getByText("검색 결과가 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("아직 대화가 없습니다")).toBeNull();
  });

  it("검색어가 있으면 보관 필터가 켜져 있어도 '검색 결과가 없습니다'가 우선한다", () => {
    renderSidebar({ convFilter: "존재안함", convItems: [], showArchived: true });
    expect(screen.getByText("검색 결과가 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("보관된 대화가 없습니다")).toBeNull();
  });

  it("검색어가 없으면 기존대로 '아직 대화가 없습니다'다(회귀 없음)", () => {
    renderSidebar({ convFilter: "", convItems: [] });
    expect(screen.getByText("아직 대화가 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("검색 결과가 없습니다")).toBeNull();
  });

  it("검색어가 공백뿐이면(trim 후 빈 문자열) 검색 중으로 안 친다", () => {
    renderSidebar({ convFilter: "   ", convItems: [] });
    expect(screen.getByText("아직 대화가 없습니다")).toBeInTheDocument();
  });
});
