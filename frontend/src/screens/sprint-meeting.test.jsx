import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

/* qa-contract-replaced-by: frontend/src/screens/sprint-redesign.test.jsx
 *
 * qa-contract-change: 회의 화면이 회차를 **구성하는 곳**에서 **리뷰하고 결정하는 곳**으로 바뀌었다(D-484). 후보 표의 「추가」·논의 행의 「빼기」 단정은 그 기능과 함께 걷고(편성은 작업 보드의 일), 대신 새 계약을 단정한다: 회차는 팀의 것이라 머리가 팀을 말한다(D-482), 프로젝트 필터는 논의 목록만 좁힌다, 줄을 누르면 상세가 아니라 미리보기다(D-483), 작성 중인 회의록은 회차별로 남는다, 요약 타일은 누르는 단추가 아니다. 단언 수는 늘었다.
 *
 * 스프린트 회의가 **회차를 아는가** (지시 4). 이 파일이 지키는 것:
 *
 *  1) 회차를 안 골랐으면 **그 팀의 열려 있는 회차**를 고른다.
 *  2) 「오늘 논의할 항목」이 유형별이고, 프로젝트 필터는 그 목록만 좁힌다.
 *  3) 회의록이 저장되고, 적다 만 글이 회차별로 남는다.
 *  4) 티켓을 확인하는 일이 회의를 떠나지 않는다(미리보기).

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { Sprint } from "./Sprint.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { SIGNALS } from "../lib/ticketSignals.js";
import { readSessionDraft } from "../lib/useSessionDraft.js";

/* 회의 화면은 차트 셋(번다운·게이지·범위 변경)을 함께 그려, 전량 vitest 의 병렬 부하에서 첫 그림이
   5초를 넘긴 적이 있다(단독 실행은 1초 안). 기다림의 상한만 늘린다 — 단언은 그대로다. */
configure({ asyncUtilTimeout: 15000 });

const TEAM = {
  selected: "d-a",
  options: [{ id: "d-a", name: "A팀", path: [{ id: "d-hq", name: "본부" }, { id: "d-a", name: "A팀" }], manageable: true }],
  manageable: true,
};
const SPRINTS = {
  sprints: [
    { id: "sp-now", name: "8월 넷째 주", department_id: "d-a", starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active", active: true, goal: "결제 모듈을 붙입니다." },
    { id: "sp-old", name: "8월 셋째 주", department_id: "d-a", starts_on: "2026-08-17", ends_on: "2026-08-23", state: "closed", goal: null },
  ],
  team: TEAM,
};

function row(over) {
  return {
    id: "t-late", page_id: "pg-late", key: "ABC-1", title: "늦은 일",
    status: "진행", priority: "높음", difficulty: "보통", due: "2026-08-25",
    est_wd: 2, project: "포털", project_uid: "p-1", version: 1,
    assignees: [], assignee_names: [], assignee_tokens: 0,
    issue: false, blocked: false, blocked_reason: null,
    ...over,
  };
}

const STUCK = row({ id: "t-stuck", page_id: "pg-stuck", key: "ABC-2", title: "막힌 일", blocked: true, due: null, project: "인프라", project_uid: "p-2" });

const MEETING = {
  sprint: SPRINTS.sprints[0],
  team: { id: "d-a", name: "A팀", path: [{ id: "d-hq", name: "본부" }, { id: "d-a", name: "A팀" }] },
  neighbours: { prev: SPRINTS.sprints[1], next: null },
  today: "2026-08-27",
  summary: {
    total: 4, done: 1, in_progress: 2, canceled: 0,
    overdue: 1, issue: 0, blocked: 1, remaining_wd: 6, planned_wd: 7,
  },
  health: { score: 62.5, progress_pct: 25, elapsed_pct: 50 },
  phase: "during",
  burndown: {
    total_est_wd: 7,
    start_est_wd: 7,
    points: [
      { date: "2026-08-24", ideal: 7, remaining: 6, scope: 7, done: 1 },
      { date: "2026-08-25", ideal: 5, remaining: 4, scope: 7, done: 3 },
      { date: "2026-08-26", ideal: 3, remaining: 3, scope: 7, done: 4 },
    ],
  },
  workload: [
    { user_id: "u-2", display_name: "개발자", avatar_url: null, avatar_default_key: null, remaining_wd: 6, open: 3, unestimated: 1 },
  ],
  scope: {
    tracked: true, added: 1, removed: 0,
    trend: [
      { date: "2026-08-24", added: 0, removed: 0 },
      { date: "2026-08-25", added: 1, removed: 0 },
      { date: "2026-08-26", added: 1, removed: 0 },
    ],
  },
  discuss: {
    overdue: { items: [row()], total: 1, truncated: false },
    blocked: { items: [STUCK], total: 1, truncated: false },
    issue: { items: [], total: 0, truncated: false },
    unassigned: { items: [], total: 0, truncated: false },
    due_soon: { items: [], total: 0, truncated: false },
    no_estimate: { items: [], total: 0, truncated: false },
    no_due: { items: [], total: 0, truncated: false },
    scope_changes: { items: [], total: 0, truncated: false },
  },
  discuss_project_id: null,
  tickets: [row(), STUCK],
  tickets_total: 2,
  decisions: [
    {
      id: "d-1", kind: "action", body: "결제 모듈은 다음 회차로 미룹니다.",
      ticket_id: null, ticket_key: null, ticket_page_id: null,
      assignee_user_id: null, assignee: null, due_date: null, done: false,
      created_at: "2026-08-27T01:00:00",
    },
  ],
};

const STATUSES = {
  statuses: [
    { key: "계획", label: "계획", terminal: false, board: "column" },
    { key: "진행", label: "진행 중", terminal: false, board: "column" },
    { key: "완료", label: "완료", terminal: true, board: "column" },
  ],
};

const TICKET = {
  configured: true, ok: true, can_edit: true,
  ticket: { id: "pg-late", key: "ABC-1", title: "늦은 일", status: "진행", project: "포털", project_uid: "p-1", sprint_id: "sp-now", assignee_people: [] },
  body_markdown: "결제 응답 코드를 정리합니다.",
};

function stub(path) {
  if (path.startsWith("/api/tickets/projects")) {
    return Promise.resolve({ projects: [{ id: "p-1", name: "포털", dept_id: "d-a" }, { id: "p-2", name: "인프라", dept_id: "d-a" }] });
  }
  if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
  if (path.startsWith("/api/tickets/pg-")) return Promise.resolve(TICKET);
  if (path.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
  if (path.startsWith("/api/work/sprints?") || path === "/api/work/sprints") return Promise.resolve(SPRINTS);
  if (/\/api\/work\/sprints\/[^/]+\/meeting/.test(path)) return Promise.resolve(MEETING);
  return Promise.resolve({});
}

function Here() {
  const loc = useLocation();
  return <div data-testid="here">{`${loc.pathname}${loc.search}`}</div>;
}

function Landing() {
  const loc = useLocation();
  return <div data-landed={`${loc.pathname}${loc.search}`} data-from={(loc.state && loc.state.from) || ""}>도착</div>;
}

function renderSprint(entry = "/sprint") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <Here />
            <Routes>
              <Route path="/sprint" element={<Sprint />} />
              <Route path="/tickets/:id" element={<Landing />} />
              <Route path="/work-board" element={<Landing />} />
            </Routes>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
  const out = render(<MemoryRouter initialEntries={[entry]}>{ui}</MemoryRouter>);
  return { ...out, qc, ui };
}

function meetingCalls() {
  return apiMock.mock.calls.map(([p]) => String(p)).filter((p) => /\/meeting/.test(p));
}

describe("스프린트 회의", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    apiMock.mockReset();
    apiMock.mockImplementation(stub);
  });

  it("🔴 회차를 안 골랐으면 그 팀의 열려 있는 회차를 스스로 고른다", async () => {
    renderSprint();
    await waitFor(() => expect(meetingCalls().some((p) => p.startsWith("/api/work/sprints/sp-now/meeting"))).toBe(true));
    expect(meetingCalls().some((p) => p.startsWith("/api/work/sprints/sp-old/meeting"))).toBe(false);
    // 팀도 주소에 실린다 — 서버가 준 기본 팀이다.
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("team=d-a"));
    expect(apiMock.mock.calls.some(([p]) => String(p).includes("/api/work/sprints?department_id=d-a"))).toBe(true);
  });

  it("🔴 회차 개요가 어느 팀의 회차인지, 기간·오늘·단계를 말한다", async () => {
    renderSprint();
    await waitFor(() => expect(screen.getByText(/8\/24.*~.*8\/30/)).toBeTruthy(), { timeout: 15000 });
    expect(screen.getByText("본부 › A팀")).toBeTruthy();
    expect(screen.getByText(/오늘 8\/27/)).toBeTruthy();
    expect(screen.getByText(/진행 중인 회차입니다/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "회차 개요" })).toBeTruthy();
    // 이전·다음 회차는 개요 안에 있고, 같은 팀의 이웃이다.
    expect(screen.getByRole("button", { name: "이전 회차" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "다음 회차" })).toBeDisabled();
    // 회차 이름에 프로젝트를 붙이던 문장은 없다.
    expect(screen.queryByText(/의 회차입니다/)).toBeNull();
  });

  it("🔴 논의 항목은 유형별 칩이고 각 칩이 건수를 말한다", async () => {
    renderSprint();
    const OVERDUE = `${SIGNALS.overdue.label} 1`;
    await waitFor(() => expect(screen.getByRole("tab", { name: OVERDUE })).toBeTruthy(), { timeout: 15000 });
    for (const name of [`${SIGNALS.blocked.label} 1`, `${SIGNALS.issue.label} 0`,
      "미할당 0", "마감 임박 0", "예상 WD 없음 0", "마감 없음 0", "범위 변경 0"]) {
      expect(screen.getByRole("tab", { name })).toBeTruthy();
    }
    expect(screen.getByText("늦은 일")).toBeTruthy();
    expect(screen.queryByText("막힌 일")).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: `${SIGNALS.blocked.label} 1` }));
    await waitFor(() => expect(screen.getByText("막힌 일")).toBeTruthy());
    // 고른 갈래는 주소에 남는다 — 상세를 다녀와도 같은 갈래다.
    expect(screen.getByTestId("here").textContent).toContain("discuss=blocked");
  });

  it("🔴 프로젝트 필터는 논의 목록만 좁힌다 — 회차 문맥은 그대로고 서버에 그렇게 묻는다", async () => {
    renderSprint();
    await screen.findByText(/오늘 8\/27/);
    const sprintsBefore = apiMock.mock.calls.filter(([p]) => String(p).startsWith("/api/work/sprints?")).length;
    await userEvent.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await userEvent.click(await screen.findByRole("option", { name: "인프라" }));
    await waitFor(() => expect(meetingCalls().some((p) => p.includes("project_id=p-2"))).toBe(true));
    // 회차는 그대로다 — 필터가 회차 선택을 비우지 않는다.
    expect(screen.getByTestId("here").textContent).toContain("sprint=sp-now");
    expect(screen.getByTestId("here").textContent).toContain("project=p-2");
    // 회차 목록을 다시 읽지 않는다 — 프로젝트는 회차의 축이 아니다.
    expect(apiMock.mock.calls.filter(([p]) => String(p).startsWith("/api/work/sprints?")).length).toBe(sprintsBefore);
    expect(screen.getByText("이 필터는 논의 목록만 좁힙니다.")).toBeTruthy();
  });

  it("🔴 회의에는 후보 표도 「빼기」도 없다 — 편성은 작업 보드의 일이다(D-484)", async () => {
    renderSprint();
    await screen.findByText("늦은 일");
    expect(screen.queryByText("이번 회차 후보")).toBeNull();
    expect(screen.queryByRole("button", { name: "빼기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "추가" })).toBeNull();
    expect(screen.getByText("티켓을 담거나 빼는 일은 작업 보드에서 합니다.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "작업 보드에서 회차 관리" }));
    const landed = await screen.findByText("도착");
    expect(landed.getAttribute("data-landed")).toBe("/work-board?team=d-a&sprint=sp-now");
  });

  it("요약 타일은 읽는 것이지 누르는 단추가 아니다", async () => {
    renderSprint();
    const group = await screen.findByRole("group", { name: "이번 회차 요약" });
    expect(within(group).queryAllByRole("button")).toHaveLength(0);
    expect(group.textContent).toContain("4");
    expect(screen.getByText(/회차 전체의 숫자입니다/)).toBeTruthy();
  });

  it("🔴 논의 줄을 누르면 상세가 아니라 미리보기가 열린다 — 회의 문맥은 그대로다", async () => {
    renderSprint();
    await userEvent.click(await screen.findByText("늦은 일"));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("peek=pg-late"));
    expect(screen.getByTestId("here").textContent).toContain("sprint=sp-now");
    expect(screen.queryByText("도착")).toBeNull();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/결제 응답 코드를 정리합니다/)).toBeTruthy();
    // 미리보기에는 편성 단추가 없다.
    expect(within(dialog).queryByRole("button", { name: /빼기/ })).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "티켓 상세 보기" }));
    const landed = await screen.findByText("도착");
    expect(landed.getAttribute("data-landed")).toBe("/tickets/pg-late");
    expect(landed.getAttribute("data-from")).toBe("/sprint");
  });

  it("🔴 회의록을 적으면 저장 API 를 부르고, 적은 뒤 초안은 지워진다", async () => {
    renderSprint();
    await waitFor(() => expect(screen.getByLabelText("내용")).toBeTruthy());
    await userEvent.type(screen.getByLabelText("내용"), "다음 회차에서 다시 봅니다.");
    // 적는 동안 초안이 회차별로 남는다.
    await waitFor(() => expect(readSessionDraft("cv.meetingDraft.v1:sp-now")).toMatchObject({ body: "다음 회차에서 다시 봅니다." }));
    // qa-contract-change: 회의 결정 입력 단추가 동사표의 「회의록에 추가」다(r23 #52 — 「적기」). 단언하는 동작은 그대로다.
    await userEvent.click(screen.getByRole("button", { name: "회의록에 추가" }));
    await waitFor(() =>
      expect(
        apiMock.mock.calls.some(
          ([p, opts]) =>
            p === "/api/work/sprints/sp-now/decisions" &&
            opts && opts.method === "POST" &&
            opts.body.kind === "decision" &&
            opts.body.body === "다음 회차에서 다시 봅니다."
        )
      ).toBe(true)
    );
    await waitFor(() => expect(readSessionDraft("cv.meetingDraft.v1:sp-now")).toBeUndefined());
  });

  it("「내용」 칸의 제출이 같은 틱에 두 번 와도 회의록은 한 번만 적힌다 (P4)", async () => {
    /* 회의록은 Enter(폼 제출)로도 적힌다. 예전에는 그 제출에 진행 중 가드가 없고 「적기」가 꺼지는 것은 다음 렌더의
       일이라, 그 전에 온 둘째 제출이 같은 기록을 한 번 더 남겼다. 응답을 붙잡아 그 창을 연다. */
    const posted = [];
    apiMock.mockImplementation((path, opts) => {
      if (String(path) === "/api/work/sprints/sp-now/decisions" && opts && opts.method === "POST") {
        posted.push(opts.body);
        return new Promise(() => {});
      }
      return stub(path, opts);
    });
    renderSprint();
    const body = await screen.findByLabelText("내용");
    await userEvent.type(body, "배포 창을 목요일로 옮깁니다.");
    const form = body.closest("form");
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    await waitFor(() => expect(posted).toHaveLength(1));
    await act(async () => {});
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({ kind: "decision", body: "배포 창을 목요일로 옮깁니다." });
  });

  it("🔴 적다 만 회의록은 화면을 떠났다 와도 그 회차에 남는다(D-483)", async () => {
    const first = renderSprint();
    await waitFor(() => expect(screen.getByLabelText("내용")).toBeTruthy());
    await userEvent.type(screen.getByLabelText("내용"), "아직 적는 중");
    first.unmount();
    // 같은 회차로 다시 들어온다 — 새 트리, 새 캐시.
    renderSprint("/sprint?team=d-a&sprint=sp-now");
    await waitFor(() => expect(screen.getByLabelText("내용")).toHaveValue("아직 적는 중"));
  });

  it("적은 회의록이 목록에 남고, 완료 표시가 PATCH 를 부른다", async () => {
    renderSprint();
    await waitFor(() =>
      expect(screen.getByText("결제 모듈은 다음 회차로 미룹니다.")).toBeTruthy()
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: "결제 모듈은 다음 회차로 미룹니다. 완료 여부" })
    );
    await waitFor(() =>
      expect(
        apiMock.mock.calls.some(
          ([p, opts]) =>
            p === "/api/work/decisions/d-1" &&
            opts && opts.method === "PATCH" && opts.body.done === true
        )
      ).toBe(true)
    );
  });

  it("🔴 「범위 변경 기록이 없다」와 「안 바뀌었다」를 다르게 말한다", async () => {
    apiMock.mockImplementation((path) => {
      if (/\/api\/work\/sprints\/[^/]+\/meeting/.test(path)) {
        return Promise.resolve({ ...MEETING, scope: { tracked: false, added: 0, removed: 0 } });
      }
      return stub(path);
    });
    renderSprint();
    await waitFor(() => expect(screen.getByText(/얼마나 바뀌었는지 알 수 없습니다/)).toBeTruthy());
    expect(screen.queryByText(/0건이 들어오고/)).toBeNull();
  });

  it("담긴 티켓이 없는 회차의 건강은 0 이 아니라 「아직 재지 않음」이다", async () => {
    apiMock.mockImplementation((path) => {
      if (/\/api\/work\/sprints\/[^/]+\/meeting/.test(path)) {
        return Promise.resolve({ ...MEETING, health: null, summary: { ...MEETING.summary, total: 0 } });
      }
      return stub(path);
    });
    renderSprint();
    expect(await screen.findByText(/아직 재지 않았습니다/)).toBeTruthy();
    expect(screen.queryByText("62.5")).toBeNull();
  });

  it("건강 게이지가 점수와 밴드를 링 안에 말한다", async () => {
    renderSprint();
    await screen.findByText(/오늘 8\/27/);
    const center = document.querySelector("[data-gauge-center]");
    expect(center).toBeTruthy();
    expect(center.textContent).toContain("62.5");
    expect(center.textContent).toContain("주의");
  });
});

describe("스프린트 회의 — 견고성", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    apiMock.mockReset();
    apiMock.mockImplementation(stub);
  });

  it("🔴 부분 응답(sprint·today 만)에도 죽지 않는다 — 배포 사이의 옛 서버", async () => {
    apiMock.mockImplementation((path) => {
      if (/\/api\/work\/sprints\/[^/]+\/meeting/.test(path)) {
        return Promise.resolve({ sprint: SPRINTS.sprints[0], today: "2026-08-27" });
      }
      return stub(path);
    });
    renderSprint();
    expect(await screen.findByText(/오늘 8\/27/)).toBeTruthy();
    expect(screen.getByText("팀이 정해지지 않은 회차")).toBeTruthy();
  });

  it("🔴 지연 표식은 서버의 오늘로 판정한다 — 브라우저 시계가 아니라", async () => {
    const far = row({ id: "t-far", page_id: "pg-far", key: "ABC-7", title: "먼 마감", due: "2099-01-01" });
    apiMock.mockImplementation((path) => {
      if (/\/api\/work\/sprints\/[^/]+\/meeting/.test(path)) {
        return Promise.resolve({
          ...MEETING,
          today: "2099-02-01",
          discuss: { ...MEETING.discuss, overdue: { items: [far], total: 1, truncated: false } },
        });
      }
      return stub(path);
    });
    renderSprint();
    await screen.findByText("먼 마감");
    await waitFor(() =>
      expect(document.querySelector('[data-signal="overdue"]')).toBeTruthy(),
    );
  });

  it("팀 후보가 둘이면 팀 선택기가 서고, 팀을 바꾸면 회차 선택이 비워진다", async () => {
    const two = {
      selected: "d-a",
      options: [
        { id: "d-a", name: "A팀", path: [{ id: "d-a", name: "A팀" }], manageable: true },
        { id: "d-b", name: "B팀", path: [{ id: "d-b", name: "B팀" }], manageable: false },
      ],
      manageable: true,
    };
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/work/sprints?") || path === "/api/work/sprints") {
        const team = path.includes("d-b") ? { ...two, selected: "d-b", manageable: false } : two;
        return Promise.resolve({ sprints: path.includes("d-b") ? [] : SPRINTS.sprints, team });
      }
      return stub(path);
    });
    renderSprint();
    await screen.findByText(/오늘 8\/27/);
    await userEvent.click(screen.getByRole("combobox", { name: /^팀/ }));
    await userEvent.click(await screen.findByRole("option", { name: "B팀" }));
    await waitFor(() => expect(screen.getByTestId("here").textContent).toContain("team=d-b"));
    expect(screen.getByTestId("here").textContent).not.toContain("sprint=sp-now");
    expect(await screen.findByText("등록된 회차가 없습니다.")).toBeTruthy();
    // B 팀은 편성할 수 없다 — 「회차 추가」가 서지 않는다.
    expect(screen.queryByRole("button", { name: "회차 추가" })).toBeNull();
  });
});

describe("논의 갈래의 tablist 계약", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    apiMock.mockReset();
    apiMock.mockImplementation(stub);
  });

  it("화살표로 갈래를 옮기고, 패널이 tabpanel 로 이어진다", async () => {
    renderSprint();
    const first = await screen.findByRole("tab", { name: /지연/ });
    first.focus();
    await userEvent.keyboard("{ArrowRight}");
    await waitFor(() => {
      const next = screen.getByRole("tab", { name: /차단/ });
      expect(next.getAttribute("aria-selected")).toBe("true");
    });
    expect(screen.getByRole("tabpanel")).toBeTruthy();
    expect(screen.getByRole("tab", { name: /차단/ }).getAttribute("aria-controls")).toBe("discuss-panel");
  });
});

describe("회의록 확장 (UX3)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    apiMock.mockReset();
    apiMock.mockImplementation(stub);
  });

  it("종류가 「할 일」일 때만 담당자·마감 칸이 선다 — 결정에 마감은 뜻이 없다", async () => {
    renderSprint();
    await screen.findByText(/오늘 8\/27/);
    expect(screen.queryByRole("combobox", { name: /담당자/ })).toBeNull();
    const kindCombo = screen.getByRole("combobox", { name: /종류/ });
    await userEvent.click(kindCombo);
    await userEvent.click(await screen.findByRole("option", { name: "할 일" }));
    expect(screen.getByRole("combobox", { name: /담당자/ })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: /관련 티켓/ })).toBeTruthy();
  });

  it("관련 티켓 후보는 회차에 담긴 티켓이다", async () => {
    renderSprint();
    await screen.findByText(/오늘 8\/27/);
    await userEvent.click(screen.getByRole("combobox", { name: /관련 티켓/ }));
    const options = within(await screen.findByRole("listbox")).getAllByRole("option").map((o) => o.textContent);
    expect(options.some((o) => o.includes("ABC-1"))).toBe(true);
    expect(options.some((o) => o.includes("ABC-2"))).toBe(true);
  });

  it("🔴 적은 뒤에도 고칠 수 있다 — 「수정」이 PATCH 를 부른다", async () => {
    renderSprint();
    await userEvent.click(await screen.findByRole("button", { name: "수정" }));
    const dialog = await screen.findByRole("dialog");
    const bodyField = within(dialog).getByLabelText(/내용/);
    await userEvent.clear(bodyField);
    await userEvent.type(bodyField, "결제 모듈은 이번 회차에 붙입니다.");
    await userEvent.click(within(dialog).getByRole("button", { name: "저장" }));
    await waitFor(() => {
      const call = apiMock.mock.calls.find(([p, o]) => o && o.method === "PATCH");
      expect(call).toBeTruthy();
      expect(String(call[0])).toBe("/api/work/decisions/d-1");
      expect(call[1].body.body).toBe("결제 모듈은 이번 회차에 붙입니다.");
      expect(call[1].body).toHaveProperty("assignee_user_id");
    });
  });
});
