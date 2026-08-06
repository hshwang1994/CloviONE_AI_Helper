import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 기능 개선 제안 게시판 화면 계약 (7단계 사용자 지적 #1).
 *
 * 자유게시판과 **같은 화면 코드**를 종류만 바꿔 쓴다. 그래서 여기서 못 박는 것은 두 가지,
 * 둘 다 조용히 틀릴 수 있는 것들이다:
 *
 *   1. **상태 필터가 주소에 남는가.** `useState` 에만 두면 상세를 보고 돌아왔을 때 필터가
 *      풀린다 - 이 저장소가 티켓·문서에서 이미 두 번 지적받은 증상이고, 그래서
 *      `lib/useQueryState.js` 가 생겼다. 화면에 칩이 눌린 것처럼 보이는 것만으로는
 *      확인이 안 된다(로컬 상태로도 그렇게 보인다). 주소를 본다.
 *   2. **자유게시글에 상태 배지가 뜨지 않는가.** 상태는 아이디어에만 뜻이 있다.
 *      서버가 실수로 값을 실어 보내더라도 자유게시판은 그리면 안 되므로, 일부러
 *      `idea_status` 가 실린 자유게시글을 넣고 확인한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Board, IdeaBoard } from "./Board.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

let lastSearch = "";

function LocationSpy() {
  lastSearch = useLocation().search;
  return null;
}

function renderScreen(node) {
  lastSearch = "";
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <LocationSpy />
              {node}
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const IDEA_META = {
  categories: ["기능", "사용성", "성능", "기타"],
  statuses: ["제안", "검토중", "진행", "완료", "보류"],
  reaction_emojis: ["👍", "🎉"],
  can_change_status: true,
};
const FREE_META = { categories: ["공지", "질문", "자유"], reaction_emojis: ["👍", "🎉"], statuses: [] };

function mockApi(listFor) {
  apiMock.mockImplementation((url) => {
    const u = String(url);
    if (u.startsWith("/api/board/meta")) {
      return Promise.resolve(u.includes("kind=idea") ? IDEA_META : FREE_META);
    }
    if (u.startsWith("/api/board/posts")) return Promise.resolve(listFor(u));
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("상태 필터는 주소에 남는다", () => {
  it("상태 칩을 누르면 주소에 status= 가 붙는다", async () => {
    mockApi(() => ({ items: [] }));
    const user = userEvent.setup();
    renderScreen(<IdeaBoard />);
    await screen.findByRole("button", { name: "검토중" });

    await user.click(screen.getByRole("button", { name: "검토중" }));

    await waitFor(() => {
      expect(decodeURIComponent(lastSearch)).toContain("status=검토중");
    });
  });

  it("주소에 실린 상태로 목록을 부른다(새로고침, 링크 공유가 이 위에 선다)", async () => {
    mockApi(() => ({ items: [] }));
    const user = userEvent.setup();
    renderScreen(<IdeaBoard />);
    await screen.findByRole("button", { name: "진행" });

    await user.click(screen.getByRole("button", { name: "진행" }));

    await waitFor(() => {
      const urls = apiMock.mock.calls.map((c) => decodeURIComponent(String(c[0])));
      expect(urls.some((u) => u.includes("kind=idea") && u.includes("status=진행"))).toBe(true);
    });
  });

  it("전체로 되돌리면 주소에서 status 가 빠진다", async () => {
    mockApi(() => ({ items: [] }));
    const user = userEvent.setup();
    renderScreen(<IdeaBoard />);
    await screen.findByRole("button", { name: "보류" });

    await user.click(screen.getByRole("button", { name: "보류" }));
    await waitFor(() => expect(decodeURIComponent(lastSearch)).toContain("status=보류"));

    await user.click(screen.getByRole("button", { name: "전체 상태" }));
    await waitFor(() => expect(lastSearch).not.toContain("status="));
  });
});

describe("상태 배지는 아이디어에만 뜬다", () => {
  const IDEA_ROWS = {
    items: [
      {
        id: "i1", kind: "idea", title: "다크 모드를 켜 주세요", category: "사용성",
        idea_status: "검토중", like_count: 4, author_name: "김제안", view_count: 3,
        comment_count: 0, is_pinned: false, created_at: "2026-08-01T01:00:00",
      },
    ],
  };

  it("아이디어 목록은 상태와 공감 수를 보여 준다", async () => {
    mockApi(() => IDEA_ROWS);
    renderScreen(<IdeaBoard />);

    expect(await screen.findByText("다크 모드를 켜 주세요")).toBeInTheDocument();
    /* '검토중' 은 화면에 둘 있다: 위쪽 **필터 칩**(누르는 것)과 행의 **배지**(읽는 것).
       칩만 보고 통과하면 목록에 상태가 안 붙어도 초록불이 된다 - 버튼이 아닌 쪽,
       즉 배지가 실제로 그려졌는지를 본다. */
    const badge = screen.getAllByText("검토중").filter((el) => !el.closest("button"));
    expect(badge.length).toBeGreaterThan(0);
    expect(screen.getByText("👍 4")).toBeInTheDocument();
  });

  it("자유게시판은 값이 실려 와도 상태 배지를 그리지 않는다", async () => {
    /* 서버가 실수로 실어 보낼 수 있다. 화면이 그리지 않는 것이 계약이다. */
    mockApi(() => ({
      items: [
        {
          id: "f1", kind: "free", title: "점심 뭐 먹지", category: "자유",
          idea_status: "검토중", author_name: "박개발", view_count: 4,
          comment_count: 0, is_pinned: false, created_at: "2026-08-02T01:00:00",
        },
      ],
    }));
    renderScreen(<Board />);

    expect(await screen.findByText("점심 뭐 먹지")).toBeInTheDocument();
    expect(screen.queryByText("검토중")).toBeNull();
  });

  it("자유게시판에는 상태 필터 자체가 없다", async () => {
    mockApi(() => ({ items: [] }));
    renderScreen(<Board />);
    await screen.findByRole("heading", { name: "아직 게시글이 없습니다" });

    expect(screen.queryByRole("group", { name: "상태" })).toBeNull();
  });
});
