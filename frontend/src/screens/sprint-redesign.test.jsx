import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation, useParams } from "react-router-dom";

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

/* ─────────────────────────────────────────────────────────────────────────────
 * 5단계 재설계 (과제 #6) — 회의에서 실제로 하는 순서대로 화면을 다시 짠다.
 *
 *   머리(요약 + 번다운) → 담당자 카드 격자 → 남은 것(미할당) 배분 → 다음 계획.
 *
 * 여기서 지키는 것은 네 가지다:
 *   1) 화면이 스스로 **'날짜 범위 기준'** 이라고 말한다. Notion 의 스프린트 데이터베이스는
 *      이 포털 연동에 공유돼 있지 않아 읽지 못한다 — 즉 포털의 '이번 주' 와 팀이 Notion 에서
 *      만든 스프린트는 **다른 것**이다. 화면이 말하지 않으면 두 사람이 서로 다른 것을 같은
 *      이름으로 부르며 회의를 한다.
 *   2) 조건(프로젝트·담당자 등)은 **주소에 남는다** — 회의 링크를 그대로 공유할 수 있어야 한다.
 *   3) 담당자는 긴 목록이 아니라 **카드 격자**다(1인 1카드). 그리고 같은 줄 카드의 바닥을
 *      맞춘다 — 사용자가 지적한 Q5("카드 크기가 제각각")를 되살리지 않는다.
 *   4) 미할당은 담당자별 목록에 섞이지 않고 **자기 패널**에 있다(회의의 "이건 누가 가져갈까").
 *
 * 응답 모양은 지금의 백엔드 그대로다: app/sprints/service.py 는 `by_assignee` 를 주고,
 * 그 안의 티켓은 목록 API 와 **같은 dict**(ticket_views)라 프로젝트·담당자 id 를 싣는다.
 * 위쪽 PAYLOAD 는 그 필드가 없던 옛 모양(developers 폴백)이라 일부러 그대로 둔다.
 * ────────────────────────────────────────────────────────────────────────────*/

const T34 = {
  id: "t-34", tid: 34, title: "배포 스크립트 정리", status: "진행", due: "2026-08-07",
  est_wd: 2, project_ids: ["p-b"], project: "인프라", assignee_user_ids: ["u-1", "u-2"],
};

const WEEKLY = {
  window: { start: "2026-08-03", end_exclusive: "2026-08-10" },
  team: { done: 2, in_progress: 1, est_done_total: 3.5, overdue: 1 },
  developers: [
    { name: "서윤경", user_id: "u-1", has_tickets: true, assigned: 2, done: 1, prog: 1,
      verify: 0, plan: 1, est_done: 2, est_all: 3, overdue: 1 },
    { name: "김철수", user_id: "u-2", has_tickets: true, assigned: 1, done: 0, prog: 1,
      verify: 0, plan: 0, est_done: 0, est_all: 1.5, overdue: 0 },
    // 이번 주 배정이 없는 사람은 0짜리 카드로 늘어서지 않는다(WD 밸런스 막대와 같은 규칙).
    { name: "홍길동", user_id: "u-3", has_tickets: false, assigned: 0, done: 0, prog: 0,
      verify: 0, plan: 0, est_done: 0, est_all: 0, overdue: 0 },
  ],
  by_assignee: [
    { user_id: "u-1", name: "서윤경", tickets: [
      { id: "t-12", tid: 12, title: "로그인 오류 수정", status: "계획", due: "2026-08-05",
        est_wd: 1, project_ids: ["p-a"], project: "포털", assignee_user_ids: ["u-1"] },
      T34,
    ] },
    // 34번은 담당자가 둘이라 양쪽 버킷에 들어 있다 — 담당자 조건의 함정이 여기 있다.
    { user_id: "u-2", name: "김철수", tickets: [T34] },
  ],
  unassigned: [{ id: "un-9", tid: 99, title: "담당자 없는 티켓", status: "계획" }],
  planned: [{ id: "t-12", tid: 12, title: "로그인 오류 수정", status: "계획", assignee_names: ["서윤경"] }],
  burndown: {
    total_est_wd: 3,
    points: [
      { date: "2026-08-03", planned: 3, open: 3 },
      { date: "2026-08-06", planned: 2, open: 2 },
      { date: "2026-08-10", planned: 0, open: 0 },
    ],
  },
};

function AddressProbe() {
  const loc = useLocation();
  return <div data-testid="addr">{loc.search}</div>;
}

const addr = () => screen.getByTestId("addr").textContent;

function renderWeekly() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/sprint"]}>
        <AddressProbe />
        <Routes>
          <Route path="/sprint" element={<Sprint />} />
          <Route path="/tickets/:id" element={<TicketRouteProbe />} />
          <Route path="/unassigned" element={<div>미할당 티켓 라우트</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/* jsdom 은 레이아웃을 하지 않아 "몇 열로 그려졌나"를 물어볼 수 없다. 그래서 emotion 이
 * 실제로 내보낸 CSS 규칙을 읽어 **판정 규칙 자체**를 본다(새 티켓 격자 테스트와 같은 수법 —
 * frontend/src/screens/new-ticket-layout.test.jsx 에 이 방식이 왜 필요한지 길게 적혀 있다). */
function rulesFor(el) {
  const classes = [...el.classList].filter((c) => c.startsWith("css-"));
  const css = [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n");
  const found = [];
  const scan = (text, cond) => {
    let i = 0;
    while (i < text.length) {
      const open = text.indexOf("{", i);
      if (open === -1) break;
      const head = text.slice(i, open).trim();
      let depth = 1;
      let j = open + 1;
      while (j < text.length && depth > 0) {
        if (text[j] === "{") depth += 1;
        else if (text[j] === "}") depth -= 1;
        j += 1;
      }
      if (head.startsWith("@")) scan(text.slice(open + 1, j - 1), cond ? `${cond} && ${head}` : head);
      else if (head.split(",").some((s) => classes.includes(s.trim().replace(/^\./, "")))) {
        found.push({ cond, body: text.slice(open + 1, j - 1) });
      }
      i = j;
    }
  };
  scan(css, "");
  return found;
}

function declaration(rule, prop) {
  const m = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`).exec(rule.body);
  return m ? m[1].trim() : null;
}

function columnCount(track) {
  const repeat = /^repeat\(\s*(\d+)\s*,/.exec(track || "");
  if (repeat) return Number(repeat[1]);
  return String(track || "").replace(/\([^)]*\)/g, "x").split(/\s+/).filter(Boolean).length;
}

/** 담당자 카드 격자와 그 카드들. 카드는 눌러서 그 사람만 보는 버튼이다. */
async function personGrid() {
  const section = await screen.findByRole("region", { name: /담당자 현황/ });
  const cards = within(section).getAllByRole("button");
  return { section, cards, grid: cards[0].parentElement };
}

describe("스프린트 회의 5단계 재설계", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/sprint/summary")) return Promise.resolve(WEEKLY);
      if (path === "/api/tickets/projects") {
        return Promise.resolve({ projects: [{ id: "p-a", name: "포털" }, { id: "p-b", name: "인프라" }] });
      }
      if (path === "/api/tickets/assignees") {
        return Promise.resolve({ assignees: [
          { user_id: "u-1", display_name: "서윤경" }, { user_id: "u-2", display_name: "김철수" },
        ] });
      }
      if (path === "/api/tickets/meta") return Promise.resolve({ statuses: ["계획", "진행"], priorities: [], difficulties: [] });
      return Promise.resolve({});
    });
  });

  it("무엇을 기준으로 모은 화면인지 말한다 — '날짜 범위 기준'", async () => {
    renderWeekly();
    expect(await screen.findByText("날짜 범위 기준")).toBeInTheDocument();
    // 왜 그렇게 말해야 하는지까지 화면에 있다: Notion 스프린트와 같은 것이 아니다.
    expect(screen.getByText(/Notion 에서 만든 스프린트/)).toBeInTheDocument();
  });

  it("머리에 요약 카드와 번다운이 함께 있다", async () => {
    renderWeekly();
    expect(await screen.findByText("완료(건)")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "번다운" })).toBeInTheDocument();
    // 서버가 준 points 를 실제로 그렸는지 — 빈 그림으로 때우지 않았는지 본다.
    expect(screen.getByText(/이 주에 마감인 업무량 3인일 중 3인일이 아직 완료되지 않았습니다/)).toBeInTheDocument();
  });

  it("담당자는 긴 목록이 아니라 카드 격자다(1인 1카드, 같은 줄 바닥을 맞춘다)", async () => {
    renderWeekly();
    const { cards, grid } = await personGrid();
    // 이번 주 배정이 있는 두 사람만 카드가 된다.
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText("서윤경")).toBeInTheDocument();

    const rules = rulesFor(grid);
    const base = rules.find((r) => r.cond === "");
    expect(declaration(base, "display")).toBe("grid");
    // Q5(카드 높이 편차) 재발 방지 — start 로 되돌리면 카드 바닥이 들쭉날쭉해진다.
    expect(declaration(base, "align-items")).toBe("stretch");
    // '1열 격자' 로 만들어 놓고 격자라 우기지 못하게 — 넓어지면 실제로 여러 열이 된다.
    const tracks = rules.map((r) => declaration(r, "grid-template-columns")).filter(Boolean);
    expect(Math.max(...tracks.map(columnCount))).toBeGreaterThanOrEqual(2);
  });

  it("카드에 그 사람의 건수, 업무량, 지연이 함께 있다", async () => {
    renderWeekly();
    const { cards } = await personGrid();
    const mine = cards[0];
    expect(within(mine).getByText("2건")).toBeInTheDocument();
    expect(within(mine).getByText("3인일")).toBeInTheDocument();
    expect(within(mine).getByText("1건")).toBeInTheDocument();
  });

  it("카드를 누르면 그 사람 티켓만 남고, 그 조건이 주소에 남는다", async () => {
    const user = userEvent.setup();
    renderWeekly();
    await personGrid();
    await user.click(screen.getByRole("button", { name: /김철수/ }));

    await waitFor(() => expect(addr()).toContain("assignee_user_id=u-2"));
    const list = screen.getByRole("region", { name: /담당자별 티켓/ });
    expect(within(list).getByText("김철수")).toBeInTheDocument();
    /* 34번은 담당자가 둘이다. "담당자 중 한 명이라도 맞으면 통과"(서버 규칙)만 쓰면 이 티켓이
       서윤경 그룹에도 남아, '그 사람만' 을 누른 사용자에게 남의 이름이 하나 더 붙어 나온다. */
    expect(within(list).queryByText("서윤경")).toBeNull();
  });

  it("프로젝트 조건도 주소에 남고 목록을 실제로 거른다", async () => {
    const user = userEvent.setup();
    renderWeekly();
    await screen.findByRole("region", { name: /담당자별 티켓/ });
    await user.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await user.click(await screen.findByRole("option", { name: "포털" }));

    await waitFor(() => expect(addr()).toContain("project_id=p-a"));
    const list = screen.getByRole("region", { name: /담당자별 티켓/ });
    expect(within(list).getByText("로그인 오류 수정")).toBeInTheDocument();
    expect(within(list).queryByText("배포 스크립트 정리")).toBeNull();
  });

  it("미할당은 담당자별 목록에 섞이지 않고 자기 패널에 있다", async () => {
    renderWeekly();
    const panel = await screen.findByRole("region", { name: /미할당/ });
    // 배분 대상이 몇 건인지 패널 제목이 그 자리에서 말한다.
    expect(within(panel).getByRole("heading")).toHaveTextContent("배분 대상 1건");
    expect(within(panel).getByRole("button", { name: /미할당 티켓/ })).toBeInTheDocument();
    // 담당자별 티켓 영역 안에 있으면 그 목록의 일부처럼 읽힌다 — 별도 패널이어야 한다.
    const list = screen.getByRole("region", { name: /담당자별 티켓/ });
    expect(list.contains(panel)).toBe(false);
  });
});
