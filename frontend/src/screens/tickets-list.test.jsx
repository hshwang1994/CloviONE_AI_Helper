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
 * 2) 정상 목록 — 프로젝트별 그룹 머리행이 나오고, 제목을 누르면 /tickets/:id 로 간다.
 *    **조건은 서버가 건다**: 상태를 고르면 그 값이 질의로 나가고, 화면은 서버가 준 목록만
 *    그린다(예전에는 전체 목록을 받아 화면에서 걸렀는데, 서버가 20건씩 자르기 시작한 뒤로는
 *    그 방식이 "총 40건인데 3건만 보인다"가 된다). 필터가 주소에 남는 것은
 *    ticket-filters.test.jsx 가 본다.
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

import { MyTickets, Unassigned } from "./MyTickets.jsx";

const ROWS = [
  { id: "t-1", tid: 1, title: "서버 등록 IP 중복 방지", status: "진행", project: "인프라", due: "2026-08-20", assignee_names: ["나"] },
  { id: "t-2", tid: 2, title: "월간 리포트 오탈자", status: "완료", project: "리포트", due: "2026-07-30", assignee_names: ["나"] },
];
const META = { configured: true, ok: true, statuses: ["진행", "완료"], priorities: [], difficulties: [] };

/* 서버처럼 답한다 — `status` 를 받으면 그 상태만 돌려준다. 화면이 거르는지 서버가 거르는지를
 * 가르는 자리다: 화면이 몰래 거르고 있으면 이 mock 을 통과해도 다른 검사에서 어긋난다. */
function mockMine(payload) {
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/tickets/meta")) return Promise.resolve(META);
    if (p.startsWith("/api/tickets/mine")) {
      if (payload.items === undefined && payload.tickets === undefined) return Promise.resolve(payload);
      const qs = new URLSearchParams(p.includes("?") ? p.slice(p.indexOf("?") + 1) : "");
      const want = qs.get("status");
      const items = (payload.items || payload.tickets || []).filter((t) => !want || t.status === want);
      return Promise.resolve({ ...payload, items, total: items.length, page: 1, page_size: 20 });
    }
    return Promise.resolve({});
  });
}

const TICKETS = { configured: true, ok: true, mapped: true, items: ROWS, total: ROWS.length, page: 1, page_size: 20 };

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

describe("내 티켓 — 목록을 못 읽었을 때", () => {
  it("'무엇을 하면 되는지'까지 담은 빈 상태를 보여주고 목록은 그리지 않는다", async () => {
    mockMine({ configured: false, tickets: [] });
    renderMyTickets();
    expect(await screen.findByText("지금은 티켓 목록을 불러올 수 없습니다")).toBeInTheDocument();
    // 막다른 경고가 아니라 다음 행동이 적혀 있어야 한다.
    //
    // 예전에는 그 다음 행동이 「관리자에게 Notion 연동 설정을 요청하세요」였다. 그 절차는
    // 없어졌으므로(S14 · D-284) 안내도 바뀌었다 — 없어진 절차를 계속 시키면 사용자는
    // 관리자에게 존재하지 않는 설정을 요청하러 간다.
    expect(screen.getByText(/잠시 뒤 다시 불러와 보세요/)).toBeInTheDocument();
    expect(screen.queryByText(/Notion/)).toBeNull();
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
  it("조건이 없으면 서버가 준 목록을 그대로 그린다(프로젝트별 그룹 머리행 포함)", async () => {
    renderMyTickets();
    expect(await screen.findByText("서버 등록 IP 중복 방지")).toBeInTheDocument();
    expect(screen.getByText("월간 리포트 오탈자")).toBeInTheDocument();
    // 프로젝트별 그룹 머리행.
    expect(screen.getByText("인프라")).toBeInTheDocument();
    expect(screen.getByText("리포트")).toBeInTheDocument();
    // 건수 줄은 이제 **조건과의 관계**를 말한다 (C2) — 조건이 없으면 "전체 N건".
    expect(screen.getByText("전체 2건")).toBeInTheDocument();
  });

  it("SEM-02: h1 하나뿐이던 화면에 필터·목록 구획용 h2가 있다(시각적으로는 안 보임)", async () => {
    renderMyTickets();
    await screen.findByText("서버 등록 IP 중복 방지");

    expect(screen.getByRole("heading", { level: 1, name: "내 티켓" })).toBeInTheDocument();
    const h2s = screen.getAllByRole("heading", { level: 2 }).map((el) => el.textContent);
    expect(h2s).toEqual(["필터", "목록"]);
  });

  it("상태를 고르면 그 값이 서버 질의로 나가고, 서버가 준 결과만 남는다", async () => {
    const user = userEvent.setup();
    renderMyTickets();
    await screen.findByText("서버 등록 IP 중복 방지");

    await user.click(screen.getByRole("combobox", { name: "상태" }));
    await user.click(await screen.findByRole("option", { name: "완료" }));

    // 조건이 걸리면 그 사실이 건수 옆에 함께 선다 — 숫자만 보고 "왜 1건이지"를 되묻지 않게.
    expect(await screen.findByText("조건 1개, 결과 1건")).toBeInTheDocument();
    expect(screen.getByText("월간 리포트 오탈자")).toBeInTheDocument();
    expect(screen.queryByText("서버 등록 IP 중복 방지")).toBeNull();
    // 화면이 몰래 거른 것이 아니라 **서버에 물어본** 결과다.
    const asked = apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith("/api/tickets/mine"));
    expect(asked.some((p) => p.includes("status=%EC%99%84%EB%A3%8C") || p.includes("status=완료"))).toBe(true);
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

/* UB-26: 개인 범위(내 티켓/미할당)는 팀 티켓과 달리 동기화 배너 자체가 아예 없었다 —
 * 미러가 한 번도 안 됐는데 error도 아니면 "담당한 티켓이 없습니다"만 보여, 정말 0건인지
 * 아직 못 재본 것인지 구분이 안 됐다. 백엔드는 이미 두 엔드포인트(mine/unassigned) 모두
 * `_with_sync`로 sync 블록을 얹어 주고 있었다(`app/tickets/router.py`) — 화면만 안 그렸다.
 * 이제는 어느 화면에도 동기화 버튼이 없다(부를 엔드포인트가 없어졌다) — 아래 단언들이
 * 그 사실을 개인 범위에서도 지킨다. 팀 범위는 team-tickets-sync.test.jsx 가 같이 지킨다. */
describe("내 티켓/미할당 — 미러 안내가 없다", () => {
  it("내 티켓: 옛 sync 블록이 되돌아와도 「한 번도 동기화 안 됨」을 안 그린다", async () => {
    /* 예전에는 이 시험이 반대를 단언했다: "정말 담당 티켓이 0건"과 "아직 한 번도
       가져오지 않았다"를 구분해 말한다. 티켓 표가 이 서버의 정본이 된 뒤로 빈 목록은
       언제나 정말 0건이고, 서버도 `sync` 블록을 안 싣는다. 화면이 옛 필드를 보고
       안내를 되살리면 사실이 아닌 말을 하게 된다. */
    mockMine({ ...TICKETS, sync: { status: "pending", ticket_count: 0, last_success_at: null } });
    renderMyTickets();
    await screen.findByText("서버 등록 IP 중복 방지");
    expect(screen.queryByText(/아직 한 번도 동기화되지 않았습니다/)).toBeNull();
    // 어느 범위에도 동기화를 시작하는 버튼이 없다 — 부를 엔드포인트 자체가 없다.
    expect(screen.queryByRole("button", { name: "지금 동기화" })).toBeNull();
  });

  it("내 티켓: 미러가 정상이면 아무 안내도 안 그린다 (지시 1)", async () => {
    mockMine({ ...TICKETS, sync: { status: "ok", ticket_count: 12, last_success_at: "2026-08-10T00:00:00Z" } });
    renderMyTickets();
    await screen.findByText("서버 등록 IP 중복 방지");
    // 예전에는 "마지막 동기화: 2026. 8. 10. …, 티켓 12개"가 상시로 떴다.
    expect(screen.queryByText(/마지막 동기화/)).toBeNull();
    expect(screen.queryByText(/아직 한 번도/)).toBeNull();
  });

  it("미할당: 옛 sync 블록이 error 로 되돌아와도 실패 안내를 안 그린다", async () => {
    apiMock.mockImplementation((path) => {
      const p = String(path);
      if (p.startsWith("/api/tickets/meta")) return Promise.resolve(META);
      if (p.startsWith("/api/tickets/unassigned")) {
        return Promise.resolve({
          configured: true, ok: true, items: [], total: 0, page: 1, page_size: 20,
          sync: { status: "error", ticket_count: 12, last_success_at: "2026-08-10T00:00:00Z" },
        });
      }
      return Promise.resolve({});
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/unassigned"]}>
          <Routes><Route path="/unassigned" element={<Unassigned />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText("담당자 없는 활성 티켓입니다. ‘나에게 배정’ 또는 ‘수정’으로 지정하세요.");
    expect(screen.queryByText(/마지막 정상 데이터를 보고 있습니다/)).toBeNull();
    expect(screen.queryByText(/최근 동기화에 실패했습니다/)).toBeNull();
    expect(screen.queryByRole("button", { name: "지금 동기화" })).toBeNull();
  });
});
