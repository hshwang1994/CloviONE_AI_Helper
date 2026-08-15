import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

/* 명령 팔레트(Ctrl+K) — **진짜 검색에 연결돼 있는가**.
 *
 * 이 파일이 존재하는 이유: 예전 팔레트는 메뉴만 찾았고, 상단바 '통합 검색' 입력은 팔레트를
 * 여는 것 외엔 아무 일도 하지 않는 죽은 컨트롤이었다. '되는 척'을 다시 만들지 않기 위해
 * "서버에 실제로 물어보고, 그 결과로 실제로 이동한다"를 테스트로 못박는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { CommandPalette } from "./CommandPalette.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const NAV_GROUPS = [
  { group: "내 업무", items: [{ to: "/my-tickets", label: "내 티켓" }, { to: "/new-ticket", label: "새 티켓" }] },
  { group: "문서", items: [{ to: "/team-docs", label: "문서" }] },
];

const SERVER_RESULT = {
  query: "회의록",
  mode: "fts",
  total: 2,
  truncated: false,
  groups: [
    {
      kind: "ticket", label: "티켓", total: 1,
      items: [{ kind: "ticket", id: "p1", title: "스프린트 회의록 정리", subtitle: "GIT-901", route: "/tickets/p1", url: null }],
    },
    {
      kind: "board", label: "게시판", total: 1,
      items: [{ kind: "board", id: "b1", title: "회의록 공지", subtitle: "공지", route: "/board/b1", url: null }],
    },
  ],
};

function renderPalette() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const utils = render(
    <QueryClientProvider client={client}>
      <ThemeModeProvider>
        <MemoryRouter initialEntries={["/me"]}>
          <Routes>
            <Route path="/me" element={<CommandPalette open onClose={onClose} groups={NAV_GROUPS} />} />
            <Route path="/tickets/:id" element={<div>티켓 상세 화면</div>} />
            <Route path="/search" element={<div>검색 결과 화면</div>} />
          </Routes>
        </MemoryRouter>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
  return { ...utils, onClose };
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue(SERVER_RESULT);
  window.localStorage.clear();
});

describe("명령 팔레트", () => {
  it("입력 전에는 서버에 묻지 않는다", async () => {
    renderPalette();
    expect(apiMock).not.toHaveBeenCalled();
  });

  // SRCH-04 — 예전엔 빈 검색어로 팔레트를 열면 지금 콘솔의 메뉴 전부(사이드바와 같은 목록)를
  // 그대로 나열했다 — 사이드바가 바로 옆에 열려 있는데 같은 걸 모달로 한 번 더 보여 주는
  // 셈이었다. 이제는 실제로 다녀간 경로("최근 방문")만, 그것도 없으면 아예 없다.
  it("최근 방문이 없으면 빈 검색어에서 메뉴를 나열하지 않는다(사이드바 복제 금지)", async () => {
    renderPalette();
    expect(screen.queryByText("내 티켓")).not.toBeInTheDocument();
    expect(screen.getByText("메뉴 이름이나 티켓, 문서, 게시글 제목을 입력하세요.")).toBeInTheDocument();
  });

  it("빈 검색어에서는 실제로 다녀간 메뉴만 '최근 방문'으로 보여준다", async () => {
    window.localStorage.setItem("cv.recentNav.v1", JSON.stringify(["/team-docs"]));
    renderPalette();
    expect(screen.getByText("최근 방문")).toBeInTheDocument();
    expect(screen.getByText("문서")).toBeInTheDocument();
    // 다녀간 적 없는 메뉴("내 티켓")는 여전히 안 보인다 — 사이드바 전체 복제가 아니다.
    expect(screen.queryByText("내 티켓")).not.toBeInTheDocument();
  });

  it("역할이 바뀌어 더는 못 보는 메뉴는 최근 방문에 남아 있어도 안 보인다", async () => {
    // 실제로는 없어진 경로 — groups(현재 역할이 볼 수 있는 메뉴)에 없으면 자연히 걸러진다.
    window.localStorage.setItem("cv.recentNav.v1", JSON.stringify(["/admin/system", "/team-docs"]));
    renderPalette();
    expect(await screen.findByText("문서")).toBeInTheDocument();
    expect(screen.queryByText("/admin/system")).not.toBeInTheDocument();
  });

  // 사용자 지적: 빈 검색어로 팔레트를 열면 사이드바 그룹 이름("운영" 등)이 그대로 나열돼
  // 이게 검색 결과인지 메뉴 이동인지 구분이 안 됐다. 메뉴 그룹 라벨을 서버 검색 그룹
  // 라벨(예: "티켓")과 구분되게 "메뉴 › "로 시작하게 한다. 가운뎃점(·)이 아니라 "›"인
  // 이유: 가운뎃점은 화면 문구 금지 문자(scripts/check_user_text.py) — PageHeader의
  // breadcrumb("관리자 › 운영")이 이미 쓰는 구분자와 통일한다.
  it("검색어를 치면 메뉴 그룹 라벨이 '메뉴 › '로 시작해 서버 검색 결과 그룹과 구분된다", async () => {
    renderPalette();
    await userEvent.type(screen.getByRole("textbox", { name: "통합 검색" }), "내");
    expect(await screen.findByText("메뉴 › 내 업무")).toBeInTheDocument();
  });

  it("메뉴 검색은 서버 없이 즉시 걸러진다", async () => {
    renderPalette();
    await userEvent.type(screen.getByRole("textbox", { name: "통합 검색" }), "새 티켓");
    expect(screen.getByText("새 티켓")).toBeInTheDocument();
    expect(screen.queryByText("문서")).not.toBeInTheDocument();
  });

  it("입력하면 서버 검색 결과를 유형별 그룹으로 함께 보여 준다", async () => {
    renderPalette();
    await userEvent.type(screen.getByRole("textbox", { name: "통합 검색" }), "회의록");

    expect(await screen.findByText("스프린트 회의록 정리")).toBeInTheDocument();
    expect(screen.getByText("회의록 공지")).toBeInTheDocument();
    // 그룹 제목도 서버가 준 라벨 그대로다.
    expect(screen.getByText("티켓")).toBeInTheDocument();
    expect(screen.getByText("게시판")).toBeInTheDocument();
  });

  it("서버 왕복은 디바운스한다 — 글자마다 요청하지 않는다", async () => {
    renderPalette();
    await userEvent.type(screen.getByRole("textbox", { name: "통합 검색" }), "회의록");
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(apiMock.mock.calls.length).toBe(1);
  });

  it("검색 결과를 누르면 서버가 준 route 로 이동하고 팔레트가 닫힌다", async () => {
    const { onClose } = renderPalette();
    await userEvent.type(screen.getByRole("textbox", { name: "통합 검색" }), "회의록");
    await userEvent.click(await screen.findByText("스프린트 회의록 정리"));

    expect(await screen.findByText("티켓 상세 화면")).toBeInTheDocument();
    expect(onClose).toHaveBeenCalled();
  });

  it("'모두 보기'로 결과 화면에 갈 수 있다", async () => {
    renderPalette();
    await userEvent.type(screen.getByRole("textbox", { name: "통합 검색" }), "회의록");
    await userEvent.click(await screen.findByText(/검색 결과 모두 보기/));
    expect(await screen.findByText("검색 결과 화면")).toBeInTheDocument();
  });

  it("결과가 하나도 없어도 Enter 는 결과 화면으로 보낸다(친 것이 사라지지 않게)", async () => {
    apiMock.mockResolvedValue({ query: "없는말", mode: "fts", total: 0, truncated: false, groups: [] });
    renderPalette();
    const input = screen.getByRole("textbox", { name: "통합 검색" });
    await userEvent.type(input, "zzz없는말zzz");
    await waitFor(() => expect(screen.getByText("검색 결과 없음")).toBeInTheDocument());

    await userEvent.type(input, "{Enter}");
    expect(await screen.findByText("검색 결과 화면")).toBeInTheDocument();
  });

  it("두 글자 검색어도 서버에 보낸다 — LIKE 폴백을 프런트가 막지 않는다", async () => {
    renderPalette();
    await userEvent.type(screen.getByRole("textbox", { name: "통합 검색" }), "회의");
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
  });

  it("서버 결과가 늦게 와서 목록이 짧아져도 Enter 가 엉뚱한 곳으로 가지 않는다", async () => {
    renderPalette();
    const input = screen.getByRole("textbox", { name: "통합 검색" });
    // 메뉴에 없는 말이라 로컬 결과가 0건 → 서버 결과가 오기 전 목록이 비어 있다.
    await userEvent.type(input, "회의록");
    await screen.findByText("스프린트 회의록 정리");

    await userEvent.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}{Enter}");
    // 어디로 가든 라우트가 존재해야 한다 — 커서가 목록 밖이면 아무 일도 안 하거나 깨진다.
    await waitFor(() =>
      expect(
        screen.queryByText("티켓 상세 화면") || screen.queryByText("검색 결과 화면"),
      ).toBeTruthy(),
    );
  });
});
