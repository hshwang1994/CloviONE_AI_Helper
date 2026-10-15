import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ConversationSidebar } from "./chat/ConversationSidebar.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* 빈 대화 보관 — 무엇이 빈 대화인지는 **서버가** 정한다(AI 채팅 개선 회차).
 *
 * qa-contract-change: 예전에는 화면이 받아 온 쪽에서 제목 「새 대화」만 보고 대상을 골라 PATCH 를 여러 번 보냈다 — 메시지가 있는데
 * 제목만 「새 대화」인 대화까지 보관할 수 있었고, 받아 오지 않은 쪽의 빈 대화는 세지 못했다. 지금은 목록 응답의 `empty_total`
 * (지우지 않은 메시지가 0개이고 만든 지 2분이 지난 내 대화, 지금 연 대화 제외)이 수이고, 보관은
 * `POST /api/conversations/archive-empty` 한 번이다. 이 시험은 (1) 수가 0 이면 단추가 없고 (2) 수가 있으면 그 수로 서고 (3) 확인
 * 창이 수와 「메시지가 있는 대화는 건드리지 않는다」를 말한 뒤에만 보관하며 (4) 취소하면 아무것도 하지 않는지 본다. */

function conv(id, extra = {}) {
  return { id, title: "새 대화", archived: false, last_message_at: "2026-08-10T00:00:00", message_count: 0, ...extra };
}

function baseProps(overrides = {}) {
  return {
    convs: { isLoading: false, isError: false },
    convItems: [conv("c1"), conv("c2", { title: "이번 주 마감 티켓", message_count: 4 })],
    convFilter: "", setConvFilter: () => {}, showArchived: false, setShowArchived: () => {},
    cid: null, onSelect: vi.fn(), onNew: vi.fn(),
    renameConv: { mutateAsync: vi.fn() },
    archiveConv: { mutate: vi.fn(), mutateAsync: vi.fn(() => Promise.resolve()) },
    deleteConv: { mutate: vi.fn() },
    confirm: vi.fn(() => Promise.resolve(true)),
    emptyTotal: 0, onArchiveEmpty: vi.fn(),
    ...overrides,
  };
}

function renderSidebar(overrides) {
  const props = baseProps(overrides);
  render(<ThemeModeProvider><ConversationSidebar {...props} /></ThemeModeProvider>);
  return props;
}

describe("빈 대화 보관", () => {
  it("서버가 센 빈 대화가 없으면 단추가 없다 — 제목이 「새 대화」여도 화면이 대상을 고르지 않는다", () => {
    renderSidebar({ emptyTotal: 0, convItems: [conv("c1"), conv("c2")] });
    expect(screen.queryByRole("button", { name: /빈 대화/ })).toBeNull();
  });

  it("서버가 센 수 그대로 단추가 선다", () => {
    renderSidebar({ emptyTotal: 3 });
    expect(screen.getByRole("button", { name: "빈 대화 3개 보관" })).toBeInTheDocument();
  });

  it("확인 창이 수와 메시지가 있는 대화는 건드리지 않음을 말한 뒤에 한 번만 보관한다", async () => {
    const user = userEvent.setup();
    const props = renderSidebar({ emptyTotal: 2 });
    await user.click(screen.getByRole("button", { name: "빈 대화 2개 보관" }));
    expect(props.confirm).toHaveBeenCalledTimes(1);
    const [message, options] = props.confirm.mock.calls[0];
    expect(message).toContain("2개");
    expect(message).toContain("메시지가 있는 대화는 건드리지 않");
    expect(options.confirmLabel).toBe("2개 보관");
    await waitFor(() => expect(props.onArchiveEmpty).toHaveBeenCalledTimes(1));
    expect(props.archiveConv.mutateAsync).not.toHaveBeenCalled();
  });

  it("확인을 취소하면 아무것도 보관하지 않는다", async () => {
    const user = userEvent.setup();
    const props = renderSidebar({ emptyTotal: 2, confirm: vi.fn(() => Promise.resolve(false)) });
    await user.click(screen.getByRole("button", { name: "빈 대화 2개 보관" }));
    await waitFor(() => expect(props.confirm).toHaveBeenCalled());
    expect(props.onArchiveEmpty).not.toHaveBeenCalled();
  });

  it("보관함을 보는 동안에는 단추가 없다", () => {
    renderSidebar({ emptyTotal: 2, showArchived: true });
    expect(screen.queryByRole("button", { name: /빈 대화/ })).toBeNull();
  });
});
