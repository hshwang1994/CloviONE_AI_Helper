import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ConversationSidebar } from "./chat/ConversationSidebar.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* AI-56: 목록에 정리 수단이 없어 시험 삼아 만든 "새 대화"가 영구히 상단을 차지했다.
 * 여기서는 (1) 2개 미만이면 버튼이 안 보이고, (2) 2개 이상이면 정확한 개수로 보이고
 * 확인 후 전부 보관되는지, (3) 활성 대화(cid)와 이미 보관된 항목은 빠지는지만 본다. */

function conv(id, extra = {}) {
  return { id, title: "새 대화", archived: false, updated_at: "2026-08-10T00:00:00", ...extra };
}

function baseProps(overrides = {}) {
  return {
    asideRef: { current: null }, listIsDrawer: false, sideOpen: false,
    closeSideDrawer: () => {}, setSideOpen: () => {},
    convs: { isLoading: false, isError: false },
    convItems: [],
    convFilter: "", setConvFilter: () => {}, showArchived: false, setShowArchived: () => {},
    cid: null, setCid: () => {}, setComposingNew: () => {}, clearDraft: () => {}, textareaRef: { current: null },
    renameConv: { mutateAsync: vi.fn() },
    archiveConv: { mutate: vi.fn(), mutateAsync: vi.fn(() => Promise.resolve()) },
    deleteConv: { mutate: vi.fn() },
    confirm: vi.fn(() => Promise.resolve(true)),
    ...overrides,
  };
}

function renderSidebar(overrides) {
  const props = baseProps(overrides);
  render(<ThemeModeProvider><ConversationSidebar {...props} /></ThemeModeProvider>);
  return props;
}

describe("빈 '새 대화' 일괄 보관", () => {
  it("빈 대화가 1개뿐이면 일괄 보관 버튼이 안 보인다", () => {
    renderSidebar({ convItems: [conv("c1")] });
    expect(screen.queryByRole("button", { name: /일괄 보관/ })).toBeNull();
  });

  it("빈 대화가 2개 이상이면 정확한 개수로 버튼이 보인다", () => {
    renderSidebar({ convItems: [conv("c1"), conv("c2"), conv("c3")] });
    expect(screen.getByRole("button", { name: '빈 "새 대화" 3개 일괄 보관' })).toBeInTheDocument();
  });

  it("활성 대화(cid)와 이미 보관된 항목, 제목이 바뀐 대화는 대상에서 빠진다", () => {
    renderSidebar({
      cid: "c1",
      convItems: [
        conv("c1"), // 활성 — 제외
        conv("c2", { archived: true }), // 이미 보관 — 제외
        conv("c3", { title: "이번 주 마감 티켓" }), // 제목 있음 — 제외
        conv("c4"), conv("c5"), // 대상
      ],
    });
    expect(screen.getByRole("button", { name: '빈 "새 대화" 2개 일괄 보관' })).toBeInTheDocument();
  });

  it("확인 후 대상 전부에 archiveConv.mutateAsync({archived:true})가 호출된다", async () => {
    const user = userEvent.setup();
    const props = renderSidebar({ convItems: [conv("c1"), conv("c2")] });
    await user.click(screen.getByRole("button", { name: /일괄 보관/ }));
    await waitFor(() => expect(props.archiveConv.mutateAsync).toHaveBeenCalledTimes(2));
    expect(props.archiveConv.mutateAsync).toHaveBeenCalledWith({ id: "c1", archived: true });
    expect(props.archiveConv.mutateAsync).toHaveBeenCalledWith({ id: "c2", archived: true });
  });

  it("확인을 취소하면 아무것도 보관하지 않는다", async () => {
    const user = userEvent.setup();
    const props = renderSidebar({ convItems: [conv("c1"), conv("c2")], confirm: vi.fn(() => Promise.resolve(false)) });
    await user.click(screen.getByRole("button", { name: /일괄 보관/ }));
    await waitFor(() => expect(props.confirm).toHaveBeenCalled());
    expect(props.archiveConv.mutateAsync).not.toHaveBeenCalled();
  });
});
