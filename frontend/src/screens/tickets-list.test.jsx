import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useParams } from "react-router-dom";

/* 티켓 목록 화면(내 티켓)의 두 가지 표면.
 *
 * 1) Notion 미구성 상태 — 사내 신규 설치와 로컬 개발에서 이 화면의 **첫인상**이 항상 이것이다
 *    (scripts/ui_qa/README.md '알려진 제약' 참고). 경고 한 줄로 끝내지 않고 무엇이 필요한지·
 *    무엇을 하면 되는지까지 보여주는 빈 상태여야 한다. 목록·툴바가 함께 그려지면 안 된다
 *    (예전에 connCallout을 컴포넌트로 만들었다가 항상 truthy가 되어 본문이 통째로 사라진 적이 있다 —
 *    반대 방향 회귀도 여기서 같이 막는다).
 * 2) 정상 목록 — 상태 필터가 실제로 행을 거르고, 프로젝트별 그룹 머리행이 나오며, 제목을 누르면
 *    /tickets/:id 로 간다.
 *
 * 네트워크·타이머 없음: api는 mock. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "me-1" } }),
}));

import { MyTickets } from "./MyTickets.jsx";

const TICKETS = {
  tickets: [
    { id: "t-1", tid: 1, title: "서버 등록 IP 중복 방지", status: "진행", project: "인프라", due: "2026-08-20", assignee_names: ["나"] },
    { id: "t-2", tid: 2, title: "월간 리포트 오탈자", status: "완료", project: "리포트", due: "2026-07-30", assignee_names: ["나"] },
  ],
};

function mockMine(payload) {
  apiMock.mockImplementation((path) => {
    if (path === "/api/tickets/mine") return Promise.resolve(payload);
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
  mockMine(TICKETS);
});

function TicketRouteProbe() {
  const { id } = useParams();
  return <div>티켓 상세 라우트: {id}</div>;
}

function renderMyTickets() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/my-tickets"]}>
        <Routes>
          <Route path="/my-tickets" element={<MyTickets />} />
          <Route path="/tickets/:id" element={<TicketRouteProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("내 티켓 — Notion 미구성 안내", () => {
  it("연동이 없으면 '무엇을 하면 되는지'까지 담은 빈 상태를 보여주고 목록은 그리지 않는다", async () => {
    mockMine({ configured: false, tickets: [] });
    renderMyTickets();
    expect(await screen.findByText("Notion 연동이 아직 설정되지 않았습니다")).toBeInTheDocument();
    // 막다른 경고가 아니라 다음 행동이 적혀 있어야 한다.
    expect(screen.getByText(/관리자에게 Notion 연동 설정을 요청하세요/)).toBeInTheDocument();
    expect(screen.getByText(/필요한 것/)).toBeInTheDocument();
    // 목록/툴바는 그려지지 않는다.
    expect(screen.queryByRole("combobox", { name: "상태" })).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("내 Notion 계정이 연결되지 않은 경우는 다른 안내를 보여준다", async () => {
    mockMine({ configured: true, mapped: false, tickets: [] });
    renderMyTickets();
    expect(await screen.findByText("내 계정이 Notion 사용자와 연결되어 있지 않습니다")).toBeInTheDocument();
    expect(screen.getByText(/‘Notion 사용자 연결’을 요청하세요/)).toBeInTheDocument();
  });
});

describe("내 티켓 — 목록", () => {
  it("기본은 진행 중만 보여주고, 상태를 '전체'로 바꾸면 완료 티켓도 나온다", async () => {
    const user = userEvent.setup();
    renderMyTickets();
    expect(await screen.findByText("서버 등록 IP 중복 방지")).toBeInTheDocument();
    expect(screen.queryByText("월간 리포트 오탈자")).toBeNull();
    // 프로젝트별 그룹 머리행.
    expect(screen.getByText("인프라")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "상태" }));
    await user.click(await screen.findByRole("option", { name: "전체" }));

    expect(await screen.findByText("월간 리포트 오탈자")).toBeInTheDocument();
    expect(screen.getByText("리포트")).toBeInTheDocument();
    expect(screen.getByText("2건")).toBeInTheDocument();   // 툴바의 건수도 함께 갱신된다
  });

  it("제목을 누르면 그 티켓 상세로 이동한다", async () => {
    const user = userEvent.setup();
    renderMyTickets();
    await user.click(await screen.findByRole("button", { name: "서버 등록 IP 중복 방지" }));
    expect(await screen.findByText("티켓 상세 라우트: t-1")).toBeInTheDocument();
  });

  it("표 머리행에 열 이름이 모두 있다(그룹 표가 하나의 table을 공유한다)", async () => {
    renderMyTickets();
    const table = await screen.findByRole("table");
    const head = within(table).getAllByRole("columnheader").map((c) => c.textContent);
    expect(head).toEqual(expect.arrayContaining(["티켓", "제목", "상태", "우선순위", "난이도", "예상 WD", "마감", "담당자"]));
  });
});
