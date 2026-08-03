import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

/* 통합 검색 결과 화면.
 *
 * 고정하는 것 세 가지:
 *   1) **빈 상태를 구분한다.** '아직 안 쳤다' / '쳤는데 없다' / '데이터가 없다' 는 서로 다른
 *      화면이다. 특히 '쳤는데 없다'는 art="search"(검색 결과 없음) 여야 하고, 여기에
 *      '데이터 없음' 그림을 쓰면 사용자는 데이터가 사라졌다고 생각한다.
 *   2) **유형별 그룹을 서버 응답 그대로** 그린다 — 화면에 유형별 if 가 없다.
 *   3) **짧은 검색어를 숨기지 않는다.** mode:"like" 를 사용자에게 말해 준다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Search } from "./Search.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const RESULT = {
  query: "회의록",
  mode: "fts",
  total: 3,
  truncated: false,
  groups: [
    {
      kind: "ticket", label: "티켓", total: 2,
      items: [
        { kind: "ticket", id: "p1", title: "스프린트 회의록 정리", subtitle: "GIT-901 · 진행", route: "/tickets/p1", url: "https://notion/x" },
        { kind: "ticket", id: "p2", title: "회의록 템플릿", subtitle: "GIT-902", route: "/tickets/p2", url: null },
      ],
    },
    {
      kind: "document", label: "문서", total: 1,
      items: [{ kind: "document", id: "d1", title: "회의록 초안", subtitle: "보고서", route: "/team-docs/d1", url: null }],
    },
  ],
};

function renderAt(path) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <Routes>
                <Route path="/search" element={<Search />} />
                <Route path="/tickets/:id" element={<div>티켓 상세 화면</div>} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("통합 검색 결과 화면", () => {
  it("검색어가 없으면 '검색 결과 없음'이 아니라 안내를 보여 준다", async () => {
    renderAt("/search");
    expect(await screen.findByText("무엇을 찾을까요?")).toBeInTheDocument();
    expect(screen.queryByText("검색 결과 없음")).not.toBeInTheDocument();
    // 아직 묻지 않았으므로 서버에 물어보지도 않는다.
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("유형별 그룹과 건수를 서버 응답 그대로 그린다", async () => {
    apiMock.mockResolvedValue(RESULT);
    renderAt("/search?q=" + encodeURIComponent("회의록"));

    expect(await screen.findByRole("heading", { name: "티켓" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "문서" })).toBeInTheDocument();
    expect(screen.getByText("스프린트 회의록 정리")).toBeInTheDocument();
    expect(screen.getByText("회의록 초안")).toBeInTheDocument();
    expect(screen.getByText(/총 3건/)).toBeInTheDocument();
  });

  it("검색어를 q 파라미터로 서버에 넘긴다", async () => {
    apiMock.mockResolvedValue(RESULT);
    renderAt("/search?q=" + encodeURIComponent("린트 회"));
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    const url = apiMock.mock.calls[0][0];
    expect(url.startsWith("/api/search?")).toBe(true);
    // URLSearchParams 는 공백을 '+'로 쓴다 — 같은 파서로 되읽어야 한다.
    expect(new URLSearchParams(url.split("?")[1]).get("q")).toBe("린트 회");
  });

  it("결과를 누르면 서버가 준 route 로 이동한다", async () => {
    apiMock.mockResolvedValue(RESULT);
    renderAt("/search?q=" + encodeURIComponent("회의록"));
    const row = await screen.findByText("스프린트 회의록 정리");
    await userEvent.click(row);
    expect(await screen.findByText("티켓 상세 화면")).toBeInTheDocument();
  });

  it("결과가 0건이면 '검색 결과 없음'을 보여 주고 검색어를 지울 수 있다", async () => {
    apiMock.mockResolvedValue({ query: "없는말", mode: "fts", total: 0, truncated: false, groups: [] });
    renderAt("/search?q=" + encodeURIComponent("없는말"));

    expect(await screen.findByText("검색 결과 없음")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "검색어 지우기" }));
    // 검색어가 사라지면 '아직 안 쳤다' 상태로 돌아간다(두 상태가 다르다는 증거).
    expect(await screen.findByText("무엇을 찾을까요?")).toBeInTheDocument();
  });

  it("LIKE 폴백으로 답했다는 사실을 사용자에게 말해 준다", async () => {
    apiMock.mockResolvedValue({ ...RESULT, mode: "like", query: "회의" });
    renderAt("/search?q=" + encodeURIComponent("회의"));
    expect(await screen.findByText(/부분 일치로 찾았습니다/)).toBeInTheDocument();
  });

  it("두 글자 검색어도 서버에 보낸다 — 프런트에서 막으면 LIKE 폴백이 죽은 코드가 된다", async () => {
    apiMock.mockResolvedValue({ ...RESULT, mode: "like" });
    renderAt("/search?q=" + encodeURIComponent("회의"));
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
  });

  it("한 글자 검색어도 서버에 보낸다", async () => {
    apiMock.mockResolvedValue({ ...RESULT, mode: "like" });
    renderAt("/search?q=" + encodeURIComponent("회"));
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
  });

  it("서버 오류는 오류 상태로 보여 준다(빈 결과로 위장하지 않는다)", async () => {
    apiMock.mockRejectedValue(Object.assign(new Error("서버 오류"), { status: 500 }));
    renderAt("/search?q=" + encodeURIComponent("회의록"));
    expect(await screen.findByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    expect(screen.queryByText("검색 결과 없음")).not.toBeInTheDocument();
  });

  it("그룹 전체 건수보다 적게 보여 줄 때 그 사실을 적는다", async () => {
    apiMock.mockResolvedValue({
      ...RESULT,
      truncated: true,
      groups: [{ ...RESULT.groups[0], total: 40 }],
    });
    renderAt("/search?q=" + encodeURIComponent("회의록"));
    expect(await screen.findByText(/40건 중 2건을 보여 줍니다/)).toBeInTheDocument();
  });
});
