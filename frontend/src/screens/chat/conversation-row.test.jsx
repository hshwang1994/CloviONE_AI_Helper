import React from "react";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { ConversationRow, ConversationSidebar } from "./ConversationSidebar.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";
import { fmtListStamp } from "../../lib/format.js";

/* 대화 목록의 한 줄(AI 채팅 개선 회차) — 채팅방 목록과 같은 어휘다.
 *
 * 사용자 캡처에서 고른 줄이 `나/* 행 안 동작은 30 이다(핸드오프 RULES §5) —` 로 보였다. 저장된 제목도 선택 상태도 아니었다 —
 * 행 동작 단추 옆의 JSX 주석이 화면에 글로 그려져 제목을 한 글자로 밀었다(W1, `ui/jsx-comments.test.js` 가 소스 전체를 잰다).
 * 여기서는 줄이 약속하는 것을 잰다:
 *   - 고른 줄은 `aria-current="page"` 이고, 제목 링크는 `#/chat/<id>` 다(새 탭으로 열 수 있다). 보통 누르면 주소만 바꾼다.
 *   - 제목은 두 줄까지이고 전체 제목은 `title` 이다. 시각은 마지막 대화 시각(목록 순서와 같은 값)이다.
 *   - 보조 동작은 「대화 동작: <제목>」 메뉴 하나다(툴팁이 이웃 줄을 가리지 않는다).
 *   - 이름 바꾸기는 줄 안 입력이다. 한글 조합 중 Enter 는 저장하지 않고, 끝나면 초점이 줄 링크로 돌아온다.
 *   - 줄에 주석 글이 새지 않는다. */

function renderRow(props) {
  const all = {
    c: { id: "c1", title: "나에게 할당된 티켓 보여줘", archived: false, last_message_at: "2026-10-14T05:00:00", updated_at: "2026-10-15T05:00:00" },
    active: false, onSelect: vi.fn(), onRename: vi.fn(() => Promise.resolve()), onArchive: vi.fn(), onDelete: vi.fn(),
    ...props,
  };
  render(<ThemeModeProvider><ul><ConversationRow {...all} /></ul></ThemeModeProvider>);
  return all;
}

describe("대화 줄", () => {
  it("고른 줄만 aria-current 이고, 제목 링크는 그 대화의 주소다", () => {
    renderRow({ active: true });
    const link = screen.getByRole("link", { name: /나에게 할당된 티켓 보여줘/ });
    expect(link).toHaveAttribute("aria-current", "page");
    expect(link).toHaveAttribute("href", "#/chat/c1");
    expect(link.closest("li")).toHaveAttribute("data-active");
  });

  it("고르지 않은 줄은 aria-current 가 없다", () => {
    renderRow({ active: false });
    expect(screen.getByRole("link", { name: /나에게 할당된 티켓 보여줘/ })).not.toHaveAttribute("aria-current");
  });

  it("전체 제목은 title 이고, 시각은 마지막 대화 시각이다(이름 · 보관이 바꾸는 updated_at 이 아니다)", () => {
    const long = "SK하이닉스 프로젝트 진행률과 이번 분기 마감 일정과 담당자별 남은 일을 한꺼번에 정리해 줘";
    renderRow({ c: { id: "c2", title: long, archived: false, last_message_at: "2026-10-14T05:00:00", updated_at: "2026-10-15T05:00:00" } });
    expect(screen.getByTitle(long)).toBeInTheDocument();
    const time = document.querySelector("time");
    expect(time).toHaveAttribute("dateTime", "2026-10-14T05:00:00");
    expect(time).toHaveTextContent(fmtListStamp("2026-10-14T05:00:00"));
  });

  it("보통 누르면 고른다(주소만 바꾼다). Ctrl · 가운데 단추는 브라우저에 맡긴다", () => {
    const props = renderRow();
    const link = screen.getByRole("link", { name: /나에게 할당된 티켓 보여줘/ });
    fireEvent.click(link, { ctrlKey: true });
    fireEvent.click(link, { button: 1 });
    expect(props.onSelect).not.toHaveBeenCalled();
    fireEvent.click(link);
    expect(props.onSelect).toHaveBeenCalledWith("c1");
  });

  it("보조 동작은 제목을 이름에 단 메뉴 하나다 — 이름 바꾸기 · 보관 · 삭제", async () => {
    const user = userEvent.setup();
    const props = renderRow();
    await user.click(screen.getByRole("button", { name: "대화 동작: 나에게 할당된 티켓 보여줘" }));
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["이름 바꾸기", "보관하기", "삭제"]);
    await user.click(screen.getByRole("menuitem", { name: "보관하기" }));
    expect(props.onArchive).toHaveBeenCalledWith(true);
  });

  it("보관한 대화의 메뉴는 「보관함에서 꺼내기」다", async () => {
    const user = userEvent.setup();
    const props = renderRow({ c: { id: "c3", title: "옛 대화", archived: true, last_message_at: "2026-09-01T00:00:00" } });
    await user.click(screen.getByRole("button", { name: "대화 동작: 옛 대화" }));
    await user.click(screen.getByRole("menuitem", { name: "보관함에서 꺼내기" }));
    expect(props.onArchive).toHaveBeenCalledWith(false);
  });

  it("이름 바꾸기 — 한글 조합 중 Enter 는 저장하지 않고, Enter 로 저장한 뒤 초점이 줄 링크로 돌아온다", async () => {
    const user = userEvent.setup();
    const props = renderRow();
    await user.click(screen.getByRole("button", { name: "대화 동작: 나에게 할당된 티켓 보여줘" }));
    await user.click(screen.getByRole("menuitem", { name: "이름 바꾸기" }));
    const input = await screen.findByRole("textbox", { name: "이름 바꾸기: 나에게 할당된 티켓 보여줘" });
    await user.clear(input);
    await user.type(input, "내 담당 티켓");
    fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(props.onRename).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(props.onRename).toHaveBeenCalledWith("내 담당 티켓");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("link", { name: /나에게 할당된 티켓 보여줘/ })));
  });

  it("Esc 는 저장하지 않고 닫는다", async () => {
    const user = userEvent.setup();
    const props = renderRow();
    await user.click(screen.getByRole("button", { name: "대화 동작: 나에게 할당된 티켓 보여줘" }));
    await user.click(screen.getByRole("menuitem", { name: "이름 바꾸기" }));
    const input = await screen.findByRole("textbox", { name: "이름 바꾸기: 나에게 할당된 티켓 보여줘" });
    await user.type(input, " 고침");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(props.onRename).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("줄에 소스 주석 글이 새지 않는다", () => {
    renderRow({ active: true });
    const text = document.querySelector("li").textContent;
    expect(text).not.toMatch(/\/\*|\*\/|RULES/);
  });
});

function renderSidebar(overrides = {}) {
  const props = {
    convs: { isLoading: false, isError: false },
    convItems: [{ id: "c1", title: "연차 규정 정리", archived: false, last_message_at: "2026-10-14T05:00:00" }],
    convFilter: "", setConvFilter: vi.fn(), showArchived: false, setShowArchived: vi.fn(),
    cid: null, onSelect: vi.fn(), onNew: vi.fn(),
    renameConv: { mutateAsync: vi.fn(() => Promise.resolve()) },
    archiveConv: { mutateAsync: vi.fn(() => Promise.resolve()) },
    deleteConv: { mutate: vi.fn() },
    confirm: vi.fn(() => Promise.resolve(true)), toast: vi.fn(),
    emptyTotal: 0, onArchiveEmpty: vi.fn(), headingId: "h",
    ...overrides,
  };
  render(<ThemeModeProvider><ConversationSidebar {...props} /></ThemeModeProvider>);
  return props;
}

describe("대화 목록 판", () => {
  it("「대화 | 보관함」 보기를 바꾼다", async () => {
    const user = userEvent.setup();
    const props = renderSidebar();
    expect(screen.getByRole("tab", { name: "대화" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("tab", { name: "보관함" }));
    expect(props.setShowArchived).toHaveBeenCalledWith(true);
  });

  it("대화도 검색어도 없으면 검색 칸이 없고, 보관함이 비면 그 사실을 말한다", () => {
    renderSidebar({ convItems: [], showArchived: true });
    expect(screen.queryByRole("searchbox", { name: "대화 목록 검색" })).toBeNull();
    expect(screen.getByText("보관한 대화가 없습니다")).toBeInTheDocument();
  });

  it("삭제는 확인한 뒤에만 한다", async () => {
    const user = userEvent.setup();
    const props = renderSidebar({ confirm: vi.fn(() => Promise.resolve(false)) });
    await user.click(screen.getByRole("button", { name: "대화 동작: 연차 규정 정리" }));
    await user.click(screen.getByRole("menuitem", { name: "삭제" }));
    await waitFor(() => expect(props.confirm).toHaveBeenCalled());
    expect(props.confirm.mock.calls[0][0]).toContain("「연차 규정 정리」");
    expect(props.deleteConv.mutate).not.toHaveBeenCalled();
  });

  it("보관하면 보관함에서 다시 꺼낼 수 있다고 알린다", async () => {
    const user = userEvent.setup();
    const props = renderSidebar();
    await user.click(screen.getByRole("button", { name: "대화 동작: 연차 규정 정리" }));
    await user.click(screen.getByRole("menuitem", { name: "보관하기" }));
    await waitFor(() => expect(props.toast).toHaveBeenCalledWith("대화를 보관했습니다. 보관함에서 다시 꺼낼 수 있습니다.", "success"));
    expect(props.archiveConv.mutateAsync).toHaveBeenCalledWith({ id: "c1", archived: true });
  });
});
