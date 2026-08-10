import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 내 활동 피드 — '내가 한 일'과 '나에게 일어난 일'이 한 줄기로 읽히는가.
 *
 * 서버가 두 원천(감사 로그·알림)을 합쳐서 준다. 화면은 그걸 날짜로 묶어 보여 주고,
 * 목적지가 있는 항목에만 '열기'를 붙인다 — 목적지가 없는데 버튼을 붙이면 눌러도
 * 아무 일도 안 나는 죽은 컨트롤이 된다(이 저장소가 특히 싫어하는 것).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Activity } from "./Activity.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const FEED = {
  items: [
    {
      id: "audit:1", kind: "did", at: "2026-08-03T05:00:00", action: "ticket.update",
      object_type: "notion_task", object_id: "p-1", title: "티켓을(를) 고침", body: null,
      result: "success", route: "/tickets/p-1", read_at: null,
    },
    {
      id: "noti:1", kind: "happened", at: "2026-08-03T04:00:00", action: "chat_mentioned",
      object_type: "chat_mention", object_id: "r-1", title: "누가 나를 불렀다",
      body: "회의록 좀 봐 주세요", result: "success", route: "/chat-rooms/r-1", read_at: null,
    },
    {
      id: "audit:2", kind: "did", at: "2026-08-02T09:00:00", action: "user.login_failed",
      object_type: "user", object_id: "u-1", title: "로그인에 실패했습니다", body: null,
      result: "failure", route: null, read_at: null,
    },
  ],
  total: 3, page: 1, page_size: 20,
};

function renderActivity() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/activity"]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Activity />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("내 활동", () => {
  it("두 원천을 날짜별로 묶어 보여 준다", async () => {
    apiMock.mockResolvedValue(FEED);
    renderActivity();
    expect(await screen.findByText("티켓을(를) 고침")).toBeInTheDocument();
    expect(screen.getByText("누가 나를 불렀다")).toBeInTheDocument();
    // 날짜 머리글 두 개(08-03, 08-02).
    expect(screen.getByText("2026-08-03")).toBeInTheDocument();
    expect(screen.getByText("2026-08-02")).toBeInTheDocument();
  });

  it("실패한 활동은 실패라고 표시한다 — 숨기면 본인이 알아챌 창이 닫힌다", async () => {
    apiMock.mockResolvedValue(FEED);
    renderActivity();
    await screen.findByText("로그인에 실패했습니다");
    expect(screen.getByText("실패")).toBeInTheDocument();
  });

  it("목적지가 있는 항목에만 '열기'가 붙는다", async () => {
    apiMock.mockResolvedValue(FEED);
    renderActivity();
    await screen.findByText("티켓을(를) 고침");
    // route 가 있는 항목은 둘, 없는 항목(로그인 실패)에는 안 붙는다.
    expect(screen.getAllByRole("button", { name: "열기" })).toHaveLength(2);
  });

  it("종류를 고르면 그 종류로 서버에 다시 묻는다", async () => {
    apiMock.mockResolvedValue(FEED);
    renderActivity();
    await screen.findByText("티켓을(를) 고침");
    await userEvent.click(screen.getByRole("button", { name: "내가 한 일" }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith("/api/me/activity?page=1&page_size=20&kind=did")
    );
  });

  it("고른 종류에 기록이 없을 때와 아예 없을 때를 다르게 말한다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    renderActivity();
    expect(await screen.findByText("아직 활동 기록이 없습니다")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "내가 한 일" }));
    expect(await screen.findByText("이 종류의 활동이 없습니다")).toBeInTheDocument();
    // 필터 때문에 비었을 때만 되돌릴 길을 준다.
    expect(screen.getByRole("button", { name: "전체 보기" })).toBeInTheDocument();
  });

  it("조회가 실패하면 다시 시도할 길을 준다", async () => {
    apiMock.mockRejectedValue(Object.assign(new Error("서버 오류"), { status: 500 }));
    renderActivity();
    expect(await screen.findByText("불러오지 못했습니다")).toBeInTheDocument();
  });

  // /api/me/activity는 total을 안 준다(app/profiles/activity.py) — Pager가 공용 컴포넌트로
  // 바뀌면서(DS-22) total 없이도 페이지 이동이 동작해야 한다. 가득 찬 페이지(20건)면 '다음'이
  // 눌리고, 덜 찬 페이지면 더 볼 게 없다는 뜻이라 '다음'이 막힌다.
  it("total 없이도(활동 로그는 총 개수를 안 줌) 다음 페이지 존재 여부로 '다음' 버튼이 열리고 닫힌다", async () => {
    const fullPage = {
      items: Array.from({ length: 20 }, (_, i) => ({
        id: "audit:" + i, kind: "did", at: "2026-08-03T05:00:00", action: "ticket.update",
        object_type: "notion_task", object_id: "p-" + i, title: "티켓을(를) 고침 " + i, body: null,
        result: "success", route: "/tickets/p-" + i, read_at: null,
      })),
      page: 1, page_size: 20,
    };
    apiMock.mockResolvedValue(fullPage);
    renderActivity();
    await screen.findByText("1페이지");
    expect(screen.getByRole("button", { name: "다음" })).toBeEnabled();

    const shortPage = { ...fullPage, items: fullPage.items.slice(0, 5), page: 2 };
    apiMock.mockResolvedValue(shortPage);
    await userEvent.click(screen.getByRole("button", { name: "다음" }));
    await screen.findByText("2페이지");
    expect(screen.getByRole("button", { name: "다음" })).toBeDisabled();
  });
});
