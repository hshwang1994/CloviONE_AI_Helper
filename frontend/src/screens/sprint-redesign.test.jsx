import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useParams } from "react-router-dom";

/* 스프린트 회의 재설계 회귀(docs/NEXT_SESSION_PLAN.md §B).
 *
 * 세 가지가 계약이다:
 *   1) '티켓 배분' 섹션은 없다 — 미할당 티켓 화면과 중복이라 의도적으로 지웠다. 누군가 "빠진 것
 *      같다"며 되살리면 이 테스트가 막는다(지운 이유를 코드가 기억하게 하는 장치).
 *   2) '완료 현황' 카운트 표 대신 담당자별 '티켓 목록'이 나온다.
 *   3) 제목을 누르면 /tickets/:id 로 간다 — 회의 중 바로 상세를 여는 게 이 재설계의 핵심 동작이다.
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

import { Sprint, assigneeTicketRows } from "./Sprint.jsx";

/* 실제 백엔드(app/sprints/service.py + app/reports/service.py) 응답 모양 그대로다:
 *   - developers[].tickets 는 _ticket_detail() 결과라 앱 티켓 id가 **없다**(tid만 있다).
 *   - planned/unassigned 는 tickets_service 결과라 앱 id가 있다.
 * 그래서 tid 12 는 planned 에서 id를 찾아 링크가 되고, tid 34 는 못 찾아 링크가 되지 않는다. */
const PAYLOAD = {
  window: { start: "2026-08-03", end_exclusive: "2026-08-10" },
  team: { done: 2, in_progress: 1, est_done_total: 3.5, overdue: 0 },
  developers: [
    {
      name: "서윤경", has_tickets: true, done: 1, prog: 1, verify: 0, plan: 1, est_done: 2,
      tickets: [
        { tid: 12, title: "로그인 오류 수정", status: "계획", due: "2026-08-05", est_wd: 1 },
        { tid: 34, title: "배포 스크립트 정리", status: "진행", due: "2026-08-07", est_wd: 2 },
      ],
    },
    // 이번 주 티켓이 없는 팀원 — 담당자별 목록에 빈 그룹으로 나오면 안 된다(예전 카운트 표는
    // has_tickets=false 행을 걸러서 보여줬다, 목록도 같은 기준이어야 한다).
    { name: "홍길동", has_tickets: false, done: 0, prog: 0, verify: 0, plan: 0, est_done: 0, tickets: [] },
  ],
  unassigned: [{ id: "u-9", tid: 99, title: "담당자 없는 티켓", status: "계획" }],
  planned: [{ id: "p-12", tid: 12, title: "로그인 오류 수정", status: "계획", assignee_names: ["서윤경"] }],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/sprint/summary")) return Promise.resolve(PAYLOAD);
    return Promise.resolve({});
  });
});

function TicketRouteProbe() {
  const { id } = useParams();
  return <div>티켓 상세 라우트: {id}</div>;
}

function renderSprint() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/sprint"]}>
        <Routes>
          <Route path="/sprint" element={<Sprint />} />
          <Route path="/tickets/:id" element={<TicketRouteProbe />} />
          <Route path="/unassigned" element={<div>미할당 티켓 라우트</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// 담당자별 섹션만 좁혀서 본다 — 같은 티켓이 아래 '계획 논의' 섹션에도 나올 수 있어(계획 상태면
// 양쪽에 정당하게 등장한다) 화면 전체에서 제목으로 찾으면 어느 섹션의 것인지 구분되지 않는다.
async function findAssigneeSection() {
  renderSprint();
  return screen.findByRole("region", { name: /담당자별 티켓/ });
}

describe("스프린트 회의 재설계", () => {
  it("'티켓 배분' 섹션이 없고 담당자별 티켓 섹션이 그 자리를 대신한다", async () => {
    renderSprint();
    expect(await screen.findByRole("heading", { name: /담당자별 티켓/ })).toBeInTheDocument();
    // 지운 섹션의 제목이 어떤 형태로도 다시 나타나면 안 된다.
    expect(screen.queryByText(/티켓 배분/)).toBeNull();
    // 카운트 표의 열 머리('개발자', '완료 업무량')도 함께 사라졌다.
    expect(screen.queryByText("개발자")).toBeNull();
    expect(screen.queryByText("완료 업무량")).toBeNull();
    // 계획 논의 섹션은 유지된다.
    expect(screen.getByRole("heading", { name: /계획 논의/ })).toBeInTheDocument();
  });

  it("담당자별로 그 주의 티켓 목록이 그려진다(티켓 없는 팀원은 빈 그룹을 만들지 않는다)", async () => {
    const section = await findAssigneeSection();
    // 섹션 제목이 담당자 수(1명)를 알려준다 — 홍길동은 이번 주 티켓이 없어 포함되지 않는다.
    expect(screen.getByRole("heading", { name: /담당자별 티켓/ })).toHaveTextContent("담당자별 티켓 (1명)");
    // 그룹 머리행에 담당자 이름과 건수가 있다.
    expect(within(section).getByText("서윤경")).toBeInTheDocument();
    expect(within(section).getByText("2건")).toBeInTheDocument();
    expect(within(section).queryByText("홍길동")).toBeNull();
    // 각 티켓 제목과 티켓 번호가 실제로 목록에 있다.
    expect(within(section).getByText("배포 스크립트 정리")).toBeInTheDocument();
    expect(within(section).getByText("GIT-12")).toBeInTheDocument();
    expect(within(section).getByText("GIT-34")).toBeInTheDocument();
  });

  it("제목을 누르면 그 티켓의 /tickets/:id 상세로 이동한다", async () => {
    const user = userEvent.setup();
    const section = await findAssigneeSection();
    const title = within(section).getByRole("button", { name: "로그인 오류 수정" });
    await user.click(title);
    expect(await screen.findByText("티켓 상세 라우트: p-12")).toBeInTheDocument();
  });

  it("앱 id를 알 수 없는 티켓은 죽은 링크 대신 일반 텍스트로 그린다", async () => {
    const section = await findAssigneeSection();
    // tid 34 는 planned/unassigned 어디에도 없어 id를 붙일 수 없다 → 링크(button)로 만들지 않는다.
    expect(within(section).getByText("배포 스크립트 정리")).toBeInTheDocument();
    expect(within(section).queryByRole("button", { name: "배포 스크립트 정리" })).toBeNull();
  });

  it("미할당 티켓은 목록을 다시 그리지 않고 그 화면으로 보내기만 한다", async () => {
    const user = userEvent.setup();
    renderSprint();
    const link = await screen.findByRole("button", { name: /미할당 티켓/ });
    // 미할당 티켓의 제목이 이 화면에 그대로 복제되어 있으면 안 된다(중복 제거가 재설계의 이유다).
    expect(screen.queryByText("담당자 없는 티켓")).toBeNull();
    await user.click(link);
    expect(await screen.findByText("미할당 티켓 라우트")).toBeInTheDocument();
  });
});

describe("assigneeTicketRows", () => {
  it("developers[].tickets 에서 담당자별 행을 만들고 tid로 앱 id를 채운다", () => {
    const rows = assigneeTicketRows(PAYLOAD);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ tid: 12, id: "p-12", assignee_names: ["서윤경"] });
    // 짝이 되는 온전한 행이 없으면 id는 undefined로 남는다(가짜 id를 만들어 내지 않는다).
    expect(rows[1].tid).toBe(34);
    expect(rows[1].id).toBeUndefined();
  });

  it("서버가 by_assignee를 주면 그것을 우선 쓴다(그룹 배열 모양)", () => {
    const rows = assigneeTicketRows({
      by_assignee: [{ name: "김철수", tickets: [{ id: "t-1", tid: 7, title: "서버 이전", status: "완료" }] }],
      developers: PAYLOAD.developers,   // 폴백은 무시되어야 한다
    });
    expect(rows).toEqual([expect.objectContaining({ id: "t-1", tid: 7, assignee_names: ["김철수"] })]);
  });

  it("by_assignee가 {이름: [티켓]} 사전 모양이어도 받아들인다", () => {
    const rows = assigneeTicketRows({ by_assignee: { 김철수: [{ id: "t-2", tid: 8, title: "백업 점검" }] } });
    expect(rows).toEqual([expect.objectContaining({ id: "t-2", assignee_names: ["김철수"] })]);
  });

  it("같은 담당자 밑의 중복 티켓을 한 줄로 합친다", () => {
    // 백엔드는 티켓의 담당자 id마다 버킷에 한 번씩 넣는다. 앱에 연결되지 않은 Notion 계정은 전부
    // '(미확인 담당자)' 한 사람으로 해석되므로, 담당자가 둘인 티켓이 같은 버킷에 두 번 들어온다.
    const rows = assigneeTicketRows({
      developers: [{
        name: "(미확인 담당자)",
        tickets: [
          { tid: 1103, title: "사용자, 어드민 대쉬보드 기획", status: "계획" },
          { tid: 1103, title: "사용자, 어드민 대쉬보드 기획", status: "계획" },
          { tid: 1405, title: "VM 생성 플로우 테스트", status: "검증" },
        ],
      }],
    });
    expect(rows.map((r) => r.tid)).toEqual([1103, 1405]);
  });

  it("빈/이상한 응답에도 던지지 않고 빈 배열을 돌려준다", () => {
    expect(assigneeTicketRows(null)).toEqual([]);
    expect(assigneeTicketRows({})).toEqual([]);
    expect(assigneeTicketRows({ developers: [{ name: "A" }] })).toEqual([]);
  });
});
