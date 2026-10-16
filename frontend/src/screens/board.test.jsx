/* qa-contract-change: UI 3차 조합 계약 C-1 — 목록 위 단독 결과 줄(「전체 N건」)을 걷어 결과 수를 필터 면 안 조건 줄과 목록 끝 줄이 말하게 됐다. 건수 단언을 끝 줄 문장으로 옮기고 단독 줄이 되살아나지 않음을 더한다. */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 자유게시판 목록 계약 테스트.
 *
 * MUI 재설계로 마크업을 통째로 바꾸기 때문에, '무엇이 지켜져야 하는지'를 먼저 못 박는다.
 * 여기서 보는 것들은 전부 조용히 틀릴 수 있는 것들이다:
 *   1) 빈 화면 두 종류를 구분한다 — '아직 글이 없다'와 '검색·필터에 걸리는 글이 없다'는
 *      사용자가 해야 할 일이 정반대다(첫 글을 쓰라 vs 필터를 지워라). 예전엔 둘 다
 *      "아직 게시글이 없습니다 / 첫 이야기를 남겨 보세요"로 뭉개져 있었다.
 *   2) 카테고리 선택이 서버 쿼리에 실제로 반영된다(눌러도 아무 일 없는 필터 방지).
 *   3) 고정 글 배지와 댓글 수가 목록에 남아 있다.
 *
 * qa-contract-change: 카테고리 칩 토글 줄을 칸 안에 이름이 선 선택(FilterSelect)으로 옮겼다(핸드오프 B-4, 계획 P-20).
 * 칩 버튼을 누르던 단언은 선택 칸에서 고르는 단언으로 옮기고, 걸린 조건 칩과 정렬 칸에 빈 항목이 없다는 단언을 더한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Board, PostFormModal } from "./Board.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderBoard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Board />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const META = { categories: ["공지", "질문", "자유"], reaction_emojis: ["👍", "🎉"] };

function mockApi(postsByQuery) {
  apiMock.mockImplementation((url) => {
    if (url === "/api/board/meta") return Promise.resolve(META);
    if (String(url).startsWith("/api/board/posts")) return Promise.resolve(postsByQuery(String(url)));
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
});

async function pickOption(user, comboName, optionName) {
  await user.click(screen.getByRole("combobox", { name: comboName }));
  await user.click(await screen.findByRole("option", { name: optionName }));
}

describe("빈 화면은 '아직 글이 없음'과 '검색 결과 없음'을 구분한다", () => {
  it("필터가 없으면 첫 글을 쓰라고 안내한다", async () => {
    mockApi(() => ({ items: [] }));
    renderBoard();
    expect(await screen.findByRole("heading", { name: "아직 게시글이 없습니다" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "검색 결과가 없습니다" })).toBeNull();
  });

  it("카테고리를 고른 뒤 0건이면 '검색 결과가 없습니다' + 지우기 CTA", async () => {
    mockApi((url) => (url.includes("category=") ? { items: [] } : { items: [] }));
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("heading", { name: "아직 게시글이 없습니다" });

    await pickOption(user, "카테고리", "질문");

    expect(await screen.findByRole("heading", { name: "검색 결과가 없습니다" })).toBeInTheDocument();
    // 걸린 조건은 조건 칩으로 선다 — 칸이 닫혀도 무엇으로 좁혔는지 보인다.
    expect(screen.getByText("카테고리: 질문")).toBeInTheDocument();
    const clear = screen.getByRole("button", { name: "검색 조건 초기화" });
    expect(clear).toBeInTheDocument();

    // CTA를 누르면 실제로 필터가 풀려 원래의 온보딩 빈 상태로 돌아온다.
    await user.click(clear);
    expect(await screen.findByRole("heading", { name: "아직 게시글이 없습니다" })).toBeInTheDocument();
  });
});

describe("제목 계층 — 필터·목록 구획 (SEM-02, PA-F-031)", () => {
  it("h1 하나뿐이던 화면에 필터·목록 h2가 있다", async () => {
    // 빈 목록으로 재면 EmptyState 자신의 제목도 h2(role=heading aria-level=2, kit.jsx)라
    // 셋이 섞인다 - 그건 별개의 기존 규약이라, 글이 있는 상태로 필터/목록 h2 둘만 본다.
    mockApi(() => ({
      items: [{ id: "p1", title: "사내 보안 공지", category: "공지", author_name: "김운영",
        view_count: 12, comment_count: 3, is_pinned: true, created_at: "2026-08-01T01:00:00" }],
    }));
    renderBoard();
    await screen.findByText("사내 보안 공지");

    expect(screen.getByRole("heading", { level: 1, name: "자유게시판" })).toBeInTheDocument();
    const h2s = screen.getAllByRole("heading", { level: 2 }).map((el) => el.textContent);
    expect(h2s).toEqual(["필터", "목록"]);
  });
});

describe("카테고리 선택은 서버 쿼리에 반영된다", () => {
  it("카테고리를 고르면 category= 파라미터가 붙은 요청이 나간다", async () => {
    mockApi(() => ({ items: [] }));
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("heading", { name: "아직 게시글이 없습니다" });

    await pickOption(user, "카테고리", "공지");

    await waitFor(() => {
      const urls = apiMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("category=" + encodeURIComponent("공지")))).toBe(true);
    });
  });
});

// VIS-92: 다른 필터 화면(표 기반 목록·티켓 필터)은 전부 "왼쪽 검색 + 오른쪽 필터"인데
// 이 화면만 카테고리(왼쪽)·검색(오른쪽)으로 뒤집혀 있었다.
describe("필터 순서 — 다른 화면과 같은 관용(왼쪽 검색 먼저)", () => {
  it("검색창이 카테고리 칩보다 DOM에서 먼저 온다", async () => {
    mockApi(() => ({ items: [] }));
    renderBoard();
    await screen.findByRole("heading", { name: "아직 게시글이 없습니다" });

    const search = screen.getByRole("searchbox", { name: "검색" });
    const categoryGroup = screen.getByRole("combobox", { name: "카테고리" });
    expect(search.compareDocumentPosition(categoryGroup) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("정렬 칸에는 「전체」 항목이 없다 — 정렬 없음은 고를 수 있는 값이 아니다", async () => {
    mockApi(() => ({ items: [] }));
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("heading", { name: "아직 게시글이 없습니다" });

    await user.click(screen.getByRole("combobox", { name: "정렬" }));
    const names = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(names).toEqual(["최신순", "조회순", "공감순"]);
  });
});

describe("작성 중인 글은 배경 새로고침에 지워지지 않는다", () => {
  // PostFormModal의 폼 초기화 useEffect가 `categories` 배열을 의존성에 넣고 있으면, board-meta
  // 쿼리가 배경에서 다시 불려 값은 같아도 새 배열 참조를 받을 때마다(react-query 재조회, 네트워크
  // 재연결 등) 이펙트가 다시 돌아 제목·본문을 빈 문자열로 되돌린다 — 모달은 열려 있고 사용자는
  // 여전히 타이핑 중인데 입력이 조용히 사라진다.
  function wrap(qc, categories) {
    return (
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <PostFormModal open categories={categories} onClose={() => {}} mode="create" kind="free" />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    );
  }

  it("categories 참조가 새로 와도(값은 같아도) 입력한 제목이 지워지지 않는다", async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(wrap(qc, ["공지", "질문"]));

    // 필수 입력 라벨은 MUI가 "제목 *"로 그린다(별표는 aria-hidden 이지만 텍스트 콘텐츠에는 남는다).
    const title = await screen.findByLabelText(/^제목/);
    await user.type(title, "임시로 적어 둔 제목");
    expect(title).toHaveValue("임시로 적어 둔 제목");

    // board-meta 쿼리가 배경에서 다시 응답하면 항상 새 배열(같은 값)이 온다 — fetch/JSON.parse는
    // 매번 새 객체를 만든다. 여기서는 그 상황을 부모 리렌더 하나로 재현한다.
    rerender(wrap(qc, ["공지", "질문"]));

    expect(screen.getByLabelText(/^제목/)).toHaveValue("임시로 적어 둔 제목");
  });
});

describe("목록 표시", () => {
  it("고정 배지와 댓글 수가 함께 보인다", async () => {
    mockApi(() => ({
      items: [
        { id: "p1", title: "사내 보안 공지", category: "공지", author_name: "김운영", view_count: 12, comment_count: 3, is_pinned: true, created_at: "2026-08-01T01:00:00" },
        { id: "p2", title: "점심 추천", category: "자유", author_name: "박개발", view_count: 4, comment_count: 0, is_pinned: false, created_at: "2026-08-02T01:00:00" },
      ],
    }));
    renderBoard();

    expect(await screen.findByText("사내 보안 공지")).toBeInTheDocument();
    expect(screen.getByText("고정")).toBeInTheDocument();
    expect(screen.getByText("[3]")).toBeInTheDocument();
    // 댓글이 0건인 글에는 대괄호 표시를 붙이지 않는다.
    expect(screen.queryByText("[0]")).toBeNull();
    // 첫 열이 render()를 써도 행이 열기 이름(aria-label)을 갖는다(openLabel).
    expect(screen.getByRole("row", { name: "상세 보기: 사내 보안 공지" })).toBeInTheDocument();
  });

  // VIS-141: like_count는 아이디어 전용 값이 아니다(서버가 두 종류 모두에 채워 준다) —
  // 자유게시판도 댓글 수처럼 반응 수를 볼 수 있어야 "볼 만한 글"을 고를 신호가 갖춰진다.
  it("자유게시판도 반응(공감) 수를 보여준다(아이디어 전용이 아니다)", async () => {
    mockApi(() => ({
      items: [
        { id: "p1", title: "사내 보안 공지", category: "공지", author_name: "김운영", view_count: 12, comment_count: 3, like_count: 7, is_pinned: true, created_at: "2026-08-01T01:00:00" },
      ],
    }));
    renderBoard();

    expect(await screen.findByText("사내 보안 공지")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "공감" })).toBeInTheDocument();
    expect(screen.getByText("👍 7")).toBeInTheDocument();
  });
});

/* 🔴 서버가 자른 목록에는 **쪽을 넘길 길**이 있어야 한다 (S15 · C7).
 *
 * `/api/board/posts` 는 처음부터 20건에서 자르고 `total` 을 함께 줬다. 화면은 그 총 건수를
 * 「총 87건」이라고 적어 놓고 페이저를 안 그렸다 — 21번째 글부터는 **있다는 사실만 보이고
 * 열 방법이 없었다.** 오류가 아니라 침묵이라 아무도 신고하지 않는다. */
describe("묶음 이어 받기", () => {
  const page = (n, total) => ({
    items: Array.from({ length: Math.min(20, total - (n - 1) * 20) }, (_, i) => ({
      id: `p${(n - 1) * 20 + i}`, title: `글 ${(n - 1) * 20 + i}`, category: "자유",
      author_name: "작성자", view_count: 0, comment_count: 0, created_at: "2026-08-01T01:00:00",
    })),
    total, page: n, page_size: 20,
  });

  it("총 건수가 한 묶음을 넘으면 다음 묶음을 실제로 요청하고 이어 붙인다", async () => {
    const asked = [];
    apiMock.mockImplementation((url) => {
      if (url === "/api/board/meta") return Promise.resolve(META);
      const s = String(url);
      if (!s.startsWith("/api/board/posts")) return Promise.resolve({});
      asked.push(s);
      const n = Number(new URLSearchParams(s.slice(s.indexOf("?") + 1)).get("page") || 1);
      return Promise.resolve(page(n, 45));
    });
    renderBoard();
    expect(await screen.findByText("글 0")).toBeInTheDocument();
    // 목록 끝 줄이 말하는 45건이 실제로 닿을 수 있는 숫자인가. 목록 위 단독 결과 줄은 없다(조합 계약 C-1).
    expect(screen.queryByText("전체 45건")).toBeNull();
    expect(document.querySelector("[data-result-line]")).toBeNull();
    expect(document.querySelector("[data-condition-line]")).toBeNull();
    expect(screen.getByText("전체 45건 중 20건 표시")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "글 더 보기" }));
    await waitFor(() => expect(asked.some((u) => u.includes("page=2"))).toBe(true));
    expect(await screen.findByText("글 20")).toBeInTheDocument();
    /* 갈아 끼운 게 아니라 **이어 붙였다** — 앞 묶음의 첫 글이 그대로 남아 있다. */
    expect(screen.getByText("글 0")).toBeInTheDocument();
    expect(await screen.findByText("전체 45건 중 40건 표시")).toBeInTheDocument();
  });

  it("조건을 바꾸면 첫 묶음부터 다시 받는다 — 한참 내려간 자리에서 걸러 놓고 빈 화면을 보면 안 된다", async () => {
    const asked = [];
    apiMock.mockImplementation((url) => {
      if (url === "/api/board/meta") return Promise.resolve(META);
      const s = String(url);
      if (!s.startsWith("/api/board/posts")) return Promise.resolve({});
      asked.push(s);
      const n = Number(new URLSearchParams(s.slice(s.indexOf("?") + 1)).get("page") || 1);
      return Promise.resolve(page(n, 45));
    });
    renderBoard();
    expect(await screen.findByText("글 0")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "글 더 보기" }));
    await waitFor(() => expect(asked.some((u) => u.includes("page=2"))).toBe(true));

    await pickOption(userEvent, "카테고리", "공지");
    await waitFor(() => expect(asked.some((u) => u.includes("category=%EA%B3%B5%EC%A7%80"))).toBe(true));
    const last = asked[asked.length - 1];
    expect(last).not.toContain("page=2");
  });
});
