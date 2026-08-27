import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* qa-contract-replaced-by: frontend/src/screens/sprint-redesign.test.jsx
 *
 * 스프린트 회의가 **회차를 아는가** (지시 4).
 *
 * 예전 이 화면은 「이번 주 월요일부터 다음 주 월요일까지 마감인 티켓」을 스프린트라고
 * 불렀고, 스스로 「날짜 범위 기준입니다」라는 사과 문구를 달고 있었다. 지금은 회차가
 * 실체이고(`sprints` 표) 화면은 `/api/work/sprints/{id}/meeting` 하나를 읽는다.
 *
 * 이 파일이 지키는 것 넷:
 *
 *  1) 회차를 안 골랐으면 **열려 있는 회차**를 고른다. 회의를 여는 사람이 매번 목록에서
 *     같은 것을 다시 고르게 하지 않는다.
 *  2) 「오늘 논의할 항목」이 **유형별**이다. 탭마다 건수가 붙고, 줄을 누르면 그 티켓으로
 *     간다 — 「관련 티켓으로 바로 이동」이 요구다.
 *  3) 후보의 「추가」가 실제로 편입 API 를 부른다. 안 부르면 이 화면은 읽기 전용 대시보드로
 *     되돌아간다.
 *  4) 회의록이 **저장된다.** 이 화면의 유일한 쓰기이고, 이 표가 생긴 이유다.
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

const SPRINTS = {
  sprints: [
    { id: "sp-old", name: "8월 셋째 주", project_id: "p-1", starts_on: "2026-08-17", ends_on: "2026-08-23", state: "closed", goal: null },
    { id: "sp-now", name: "8월 넷째 주", project_id: "p-1", starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active", goal: "결제 모듈을 붙입니다." },
  ],
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

const MEETING = {
  sprint: SPRINTS.sprints[1],
  neighbours: { prev: SPRINTS.sprints[0], next: null },
  today: "2026-08-27",
  summary: {
    total: 4, done: 1, in_progress: 2, canceled: 0,
    overdue: 1, issue: 0, blocked: 1, remaining_wd: 6, planned_wd: 7,
  },
  health: { score: 62.5, progress_pct: 25, elapsed_pct: 50 },
  burndown: {
    total_est_wd: 7,
    points: [
      { date: "2026-08-24", planned: 7, open: 6 },
      { date: "2026-08-25", planned: 5, open: 4 },
      { date: "2026-08-26", planned: 3, open: 3 },
    ],
  },
  workload: [
    { user_id: "u-2", display_name: "개발자", avatar_url: null, avatar_default_key: null, remaining_wd: 6, open: 3, unestimated: 1 },
  ],
  scope: { tracked: true, added: 1, removed: 0 },
  discuss: {
    overdue: { items: [row()], total: 1, truncated: false },
    blocked: { items: [row({ id: "t-stuck", page_id: "pg-stuck", key: "ABC-2", title: "막힌 일", blocked: true, due: null })], total: 1, truncated: false },
    unassigned: { items: [], total: 0, truncated: false },
    due_soon: { items: [], total: 0, truncated: false },
    scope_changes: { items: [], total: 0, truncated: false },
  },
  candidates: [
    row({ id: "t-cand", page_id: "pg-cand", key: "ABC-9", title: "아직 안 담은 일", due: null, version: 4 }),
  ],
  decisions: [
    {
      id: "d-1", kind: "decision", body: "결제 모듈은 다음 회차로 미룹니다.",
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

function stub(path) {
  if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [{ id: "p-1", name: "포털" }] });
  if (path.startsWith("/api/work/statuses")) return Promise.resolve(STATUSES);
  if (path.startsWith("/api/work/sprints?") || path === "/api/work/sprints") return Promise.resolve(SPRINTS);
  if (/\/api\/work\/sprints\/[^/]+\/meeting/.test(path)) return Promise.resolve(MEETING);
  return Promise.resolve({});
}

function renderSprint() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Sprint />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("스프린트 회의", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(stub);
  });

  it("🔴 회차를 안 골랐으면 열려 있는 회차를 스스로 고른다", async () => {
    renderSprint();
    await waitFor(() =>
      expect(
        apiMock.mock.calls.some(([p]) => p === "/api/work/sprints/sp-now/meeting")
      ).toBe(true)
    );
    // 닫힌 회차를 고르지 않는다 — 목록의 첫 줄이라는 이유로 지난 회의를 열면 안 된다.
    expect(apiMock.mock.calls.some(([p]) => p === "/api/work/sprints/sp-old/meeting")).toBe(false);
  });

  it("회차 기간과 오늘을 화면이 말한다", async () => {
    renderSprint();
    // 이 화면은 이제 ECharts 차트 여러 개(번다운·건강·Workload)를 함께 그린다(§15.2) —
    // 그 자체는 이 문장과 무관하지만, 전체 표적 검증처럼 차트가 많은 시험 파일 여럿이
    // 동시에 도는 동안에는 동적 import 의 시스템 부하가 늘어 기본 시간 제한(1000ms)을
    // 넘길 수 있다. 넉넉히 준다.
    await waitFor(() => expect(screen.getByText(/2026-08-24부터/)).toBeTruthy(), { timeout: 5000 });
    expect(screen.getByText(/오늘은 2026-08-27입니다/)).toBeTruthy();
  });

  it("🔴 논의 항목은 유형별이고 각 탭이 건수를 말한다", async () => {
    renderSprint();
    // 위 시험과 같은 이유(§15.2 차트 여럿 + §15.5 `DateField` 지연 로드) — 전량 실행처럼
    // 동적 import 부하가 큰 상황에서 기본 1000ms 를 넘길 수 있어 넉넉히 준다.
    await waitFor(() => expect(screen.getByRole("tab", { name: "지연 1" })).toBeTruthy(), { timeout: 5000 });
    for (const name of ["차단 1", "미할당 0", "마감 임박 0", "범위 변경 0"]) {
      expect(screen.getByRole("tab", { name })).toBeTruthy();
    }
    // 기본 탭은 지연이다 — 회의에서 가장 먼저 말하는 것이다.
    expect(screen.getByText("늦은 일")).toBeTruthy();
    expect(screen.queryByText("막힌 일")).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: "차단 1" }));
    await waitFor(() => expect(screen.getByText("막힌 일")).toBeTruthy());
  });

  it("🔴 후보의 「추가」가 실제로 편입 API 를 부른다", async () => {
    renderSprint();
    await waitFor(() => expect(screen.getByText("아직 안 담은 일")).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: "추가" }));
    await waitFor(() =>
      expect(
        apiMock.mock.calls.some(
          ([p, opts]) =>
            p === "/api/work/board/t-cand/move" &&
            opts &&
            opts.method === "POST" &&
            opts.body.set_sprint === true &&
            opts.body.sprint_id === "sp-now" &&
            // 버전을 함께 보낸다 — 두 사람이 같은 후보를 동시에 담으면 뒤엣것이
            // 앞엣것을 덮어쓰는데 둘 다 성공한 것처럼 보인다.
            opts.body.base_version === 4
        )
      ).toBe(true)
    );
  });

  it("🔴 회의록을 적으면 저장 API 를 부른다", async () => {
    renderSprint();
    await waitFor(() => expect(screen.getByLabelText("내용")).toBeTruthy());
    await userEvent.type(screen.getByLabelText("내용"), "다음 회차에서 다시 봅니다.");
    await userEvent.click(screen.getByRole("button", { name: "적기" }));
    await waitFor(() =>
      expect(
        apiMock.mock.calls.some(
          ([p, opts]) =>
            p === "/api/work/sprints/sp-now/decisions" &&
            opts &&
            opts.method === "POST" &&
            opts.body.kind === "decision" &&
            opts.body.body === "다음 회차에서 다시 봅니다."
        )
      ).toBe(true)
    );
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
        return Promise.resolve({
          ...MEETING,
          scope: { tracked: false, added: 0, removed: 0 },
        });
      }
      return stub(path);
    });
    renderSprint();
    await waitFor(() => expect(screen.getByText(/얼마나 바뀌었는지 알 수 없습니다/)).toBeTruthy());
    // 0 으로 적으면 화면이 「안정된 회차」라고 말하는데, 실은 아무것도 모르는 것이다.
    expect(screen.queryByText(/0건이 들어오고/)).toBeNull();
  });

  it("담긴 티켓이 없는 회차의 건강은 0 이 아니라 「아직 재지 않음」이다", async () => {
    apiMock.mockImplementation((path) => {
      if (/\/api\/work\/sprints\/[^/]+\/meeting/.test(path)) {
        return Promise.resolve({
          ...MEETING,
          health: null,
          summary: { ...MEETING.summary, total: 0 },
        });
      }
      return stub(path);
    });
    renderSprint();
    // `null` 은 0 이 아니다 — 안 잰 점수를 0 으로 그리면 아무 일도 안 담긴 회차가
    // 화면에서 가장 나쁜 회차가 된다.
    expect(await screen.findByText(/아직 재지 않았습니다/)).toBeTruthy();
    expect(screen.queryByText("62.5")).toBeNull();
  });
});
