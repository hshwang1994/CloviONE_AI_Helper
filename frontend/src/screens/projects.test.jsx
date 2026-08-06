/* 프로젝트 화면 — **숫자를 믿을 수 있게 그리는가**를 본다.
 *
 * 이 화면의 존재 이유는 숫자 하나를 크게 그리는 것이 아니라, 서로 다른 두 숫자를 나란히
 * 놓고 왜 다른지 말하는 것이다(app/projects/progress.py 가 그 판단을 기록한다). 그래서
 * 여기서 지키는 것도 표시 그 자체다.
 *
 *   1) 진행률이 **null 이면 0% 가 아니다.** 캐시가 비어 "아직 계산 안 함"인 것과, 세어 보니
 *      분모가 0이라 "작업이 아직 없음"인 것은 서로 다른 말이고 둘 다 0% 가 아니다.
 *   2) 앱 계산값과 Notion 값이 다르면 **둘 다** 보이고, 다르다고 말하고, 계산 근거를 적는다.
 *      한쪽만 보이면 사용자는 "포털이 틀렸다"고 결론 내리고 그 다음부터 둘 다 안 본다.
 *   3) Health 는 점수 **옆에 이유 목록**이 있어야 한다. 47점만 본 팀장은 할 수 있는 일이 없다.
 *   4) 필터는 주소에 남는다(티켓 화면과 같은 관용, `useQueryState`).
 *
 * 오탐 방지를 위해 표본을 고를 때 **값이 서로 다른 것**을 쓴다. 두 값이 같으면 한쪽만 그리는
 * 구현도 통과하고, 0 을 쓰면 "null 을 0으로 그렸다"를 잡지 못한다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

let authRole = "user";
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: authRole, id: "me-1" } }) }));

import { Projects } from "./Projects.jsx";
import { Project } from "./Project.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* ── 표본 ──────────────────────────────────────────────────────────────────── */

function project(over) {
  return {
    id: "p-1", name: "배포 자동화", code: "DEP", status: "active",
    dept_id: "d-1", owner_user_id: null,
    starts_on: "2026-07-01", ends_on: "2026-09-30",
    goal: "배포를 자동화한다", biz_type: null, product: null,
    progress_pct: 42.9, health_score: 63,
    archived_at: null,
    notion_page_id: "np-1",
    notion_progress_pct: 70, notion_status: "진행 중",
    notion_missing_at: null, notion_synced_at: "2026-08-06T00:00:00",
    notion_sync_error: null, notion_version: "v1",
    created_at: "2026-07-01T00:00:00", updated_at: "2026-08-06T00:00:00",
    ...over,
  };
}

/* 근거 표본. 합계가 진행률과 **실제로 맞는** 값을 쓴다 — 아무 숫자나 넣으면 화면이 근거를
 * 안 읽고 상수를 그려도 통과한다. 6 ÷ 14 = 42.86 → 42.9 */
const BASIS = {
  sample_tasks: 12, parent_tasks_excluded: 2, cancelled_excluded: 2,
  counted_tasks: 8, done_tasks: 4,
  weight_mode: "est_wd", est_wd_missing: 0,
  total_weight: 14, done_weight: 6,
};

const EMPTY_BASIS = {
  sample_tasks: 0, parent_tasks_excluded: 0, cancelled_excluded: 0,
  counted_tasks: 0, done_tasks: 0,
  weight_mode: "none", est_wd_missing: 0,
  total_weight: 0, done_weight: 0,
};

const HEALTH = {
  project_id: "p-1",
  score: 63,
  reasons: [
    {
      rule: "notion_trouble", label: "노션 진행 상태가 차질", penalty: 25,
      detail: "노션 진행 상태가 '차질' 로 표시돼 있습니다.",
    },
    {
      rule: "task_overdue", label: "지연 작업 비율", penalty: 12,
      detail: "기한이 적힌 열린 작업 10건 중 3건이 마감을 넘겼습니다(30%).",
    },
  ],
  checked: ["notion_trouble", "task_overdue"],
  unknown: [
    {
      rule: "milestone_overdue", label: "기한 지난 마일스톤",
      why: "기한이 적힌 마일스톤이 없어 일정 준수 여부를 판정할 수 없습니다.",
    },
  ],
};

const WBS = {
  project_id: "p-1",
  roots: [{
    key: "np-t1", title: "설계", status: "진행", est_wd: 3, url: null,
    ticket_number: 101, depth: 0,
    progress: { percent: 50, basis: { ...BASIS, sample_tasks: 2, counted_tasks: 2, done_tasks: 1 } },
    children: [{
      key: "np-t2", title: "스키마 확정", status: "완료", est_wd: 1, url: null,
      ticket_number: 102, depth: 1,
      progress: { percent: 100, basis: { ...BASIS, sample_tasks: 1, counted_tasks: 1, done_tasks: 1 } },
      children: [],
    }],
  }],
  unplaced: [{ key: "np-t9", title: "순환에 걸린 작업", reason: "cycle" }],
  progress: { percent: 42.9, basis: BASIS },
};

const MILESTONES = {
  items: [
    { id: "m-1", project_id: "p-1", name: "설계 완료", due_on: "2026-07-15", status: "done", sort_order: 0, created_at: "2026-07-01T00:00:00", updated_at: "2026-07-15T00:00:00" },
    { id: "m-2", project_id: "p-1", name: "베타 배포", due_on: "2026-09-01", status: "planned", sort_order: 1, created_at: "2026-07-01T00:00:00", updated_at: "2026-07-01T00:00:00" },
  ],
  total: 2,
};

const WEEKLY = {
  project: { id: "p-1", name: "배포 자동화", code: "DEP", status: "active", progress_pct: 42.9, notion_page_id: "np-1" },
  window: {
    week_of: "2026-08-03", start: "2026-08-03", end_exclusive: "2026-08-10",
    prev_week: "2026-07-27", next_week: "2026-08-10",
  },
  done: { count: 1, items: [{ id: "t-1", tid: 101, title: "스키마 확정", status: "완료", due: "2026-08-05", est_wd: 1 }] },
  in_progress: { count: 0, items: [] },
  delayed: { count: 0, items: [] },
  issues: { count: 0, items: [] },
  next_week: { count: 0, items: [] },
  milestones: {
    changed: { count: 0, items: [] },
    due_this_week: { count: 0, items: [] },
    overdue: { count: 0, items: [] },
  },
  basis: { tickets_linked: true, sample_tickets: 12, sample_milestones: 2 },
  summary_md: "## 배포 자동화 주간 리포트\n기간: 2026-08-03 ~ 2026-08-09",
  source: "rule",
  llm_summary: null,
  // 서버(app/projects/service.py::_llm_notice)가 실제로 주는 키. 화면이 이걸 그려야
  // 사용자가 "AI 요약이 꺼진 것" 과 "고장 난 것" 을 구별할 수 있다.
  llm_notice: "AI 요약이 꺼져 있어 규칙 기반 요약을 보여 줍니다.",
  saved: null,
};

const TEAM_TICKETS = {
  configured: true, ok: true, mapped: true,
  items: [{
    id: "t-1", tid: 101, title: "스키마 확정", status: "완료", priority: "High",
    project: "배포 자동화", due: "2026-08-05", assignee_names: ["김하나"],
  }],
  total: 1, page: 1, page_size: 20,
};

let listPayload = null;
let progressPayload = null;
let healthPayload = null;
let detailProject = null;

beforeEach(() => {
  authRole = "user";
  listPayload = { items: [project()], total: 1, page: 1, page_size: 20 };
  progressPayload = { project_id: "p-1", percent: 42.9, basis: BASIS, notion_percent: 70 };
  healthPayload = HEALTH;
  detailProject = project();
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/projects/p-1/progress")) return Promise.resolve(progressPayload);
    if (p.startsWith("/api/projects/p-1/health")) return Promise.resolve(healthPayload);
    if (p.startsWith("/api/projects/p-1/wbs")) return Promise.resolve(WBS);
    if (p.startsWith("/api/projects/p-1/milestones")) return Promise.resolve(MILESTONES);
    if (p.startsWith("/api/projects/p-1/weekly-report")) return Promise.resolve(WEEKLY);
    if (p.startsWith("/api/projects/p-1")) return Promise.resolve({ project: detailProject });
    if (p.startsWith("/api/projects")) return Promise.resolve(listPayload);
    if (p.startsWith("/api/tickets/team")) return Promise.resolve(TEAM_TICKETS);
    if (p.startsWith("/api/tickets")) return Promise.resolve({ configured: true, ok: true, statuses: [], priorities: [], difficulties: [], projects: [], assignees: [] });
    if (p.startsWith("/api/admin/departments")) return Promise.resolve({ items: [] });
    return Promise.resolve({});
  });
});

/* 주소를 검사에서 읽는 유일한 방법. 화면이 무엇을 주소에 실었는지 본다. */
function AddressProbe() {
  const loc = useLocation();
  return <div data-testid="addr">{loc.pathname + loc.search}</div>;
}

function renderAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <AddressProbe />
              <Routes>
                <Route path="/projects" element={<Projects />} />
                <Route path="/projects/:id" element={<Project />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const addr = () => screen.getByTestId("addr").textContent;

function addrParam(key) {
  const s = addr();
  return new URLSearchParams(s.includes("?") ? s.slice(s.indexOf("?") + 1) : "").get(key);
}

/** 마지막으로 그 접두사로 나간 요청의 쿼리스트링. */
function lastQuery(prefix) {
  const calls = apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith(prefix));
  const last = calls[calls.length - 1];
  return new URLSearchParams(last && last.includes("?") ? last.slice(last.indexOf("?") + 1) : "");
}

/* ── 목록 ──────────────────────────────────────────────────────────────────── */

describe("프로젝트 목록 — 진행률", () => {
  it("진행률 캐시가 비어 있으면 0% 라고 하지 않는다", async () => {
    listPayload = {
      items: [project({ progress_pct: null, notion_progress_pct: null, health_score: null })],
      total: 1, page: 1, page_size: 20,
    };
    renderAt("/projects");
    expect(await screen.findByText("배포 자동화")).toBeInTheDocument();

    // 0% 는 "세어 봤더니 0" 이라는 뜻이라, 한 번도 안 센 것에 붙이면 거짓말이다.
    expect(screen.queryByText("0%")).toBeNull();
    expect(screen.getByText("아직 계산하지 않았습니다")).toBeInTheDocument();
  });

  it("앱 값과 Notion 값이 다르면 둘 다 보여 주고 다르다고 말한다", async () => {
    renderAt("/projects");
    const card = (await screen.findByText("배포 자동화")).closest("article");

    expect(within(card).getByText("42.9%")).toBeInTheDocument();
    expect(within(card).getByText("70%")).toBeInTheDocument();
    expect(within(card).getByText(/다릅니다/)).toBeInTheDocument();
  });

  it("두 값이 같으면 다르다고 말하지 않는다", async () => {
    listPayload = {
      items: [project({ progress_pct: 70, notion_progress_pct: 70 })],
      total: 1, page: 1, page_size: 20,
    };
    renderAt("/projects");
    const card = (await screen.findByText("배포 자동화")).closest("article");

    expect(within(card).queryByText(/다릅니다/)).toBeNull();
  });
});

describe("프로젝트 목록 — 조건이 주소에 남는다", () => {
  it("아무것도 안 고르면 주소가 깨끗하고 서버에도 조건을 안 보낸다", async () => {
    renderAt("/projects");
    await screen.findByText("배포 자동화");
    expect(addr()).toBe("/projects");
    expect(lastQuery("/api/projects").toString()).toBe("");
  });

  it("보관 포함을 켜면 주소에 남고 같은 조건이 서버로 나간다", async () => {
    const user = userEvent.setup();
    renderAt("/projects");
    await screen.findByText("배포 자동화");

    await user.click(screen.getByRole("switch", { name: "보관한 프로젝트 포함" }));

    await waitFor(() => expect(addrParam("archived")).toBe("1"));
    await waitFor(() => expect(lastQuery("/api/projects").get("include_archived")).toBe("true"));
  });

  it("주소에 실린 조건으로 시작한다 (새로고침, 링크 공유)", async () => {
    renderAt("/projects?archived=1");
    await screen.findByText("배포 자동화");
    expect(lastQuery("/api/projects").get("include_archived")).toBe("true");
    expect(screen.getByRole("switch", { name: "보관한 프로젝트 포함" })).toBeChecked();
  });

  it("페이지를 넘겨도 걸어 둔 조건은 그대로 간다", async () => {
    const user = userEvent.setup();
    listPayload = { items: [project()], total: 45, page: 1, page_size: 20 };
    renderAt("/projects?archived=1");
    await screen.findByText("배포 자동화");

    await user.click(await screen.findByRole("button", { name: "다음" }));

    await waitFor(() => {
      const sent = lastQuery("/api/projects");
      expect(sent.get("page")).toBe("2");
      expect(sent.get("include_archived")).toBe("true");
    });
    expect(addrParam("page")).toBe("2");
  });
});

/* ── 상세 ──────────────────────────────────────────────────────────────────── */

describe("프로젝트 상세 — 진행률 두 값", () => {
  it("두 값이 다르면 둘 다 보이고, 계산식과 표본 수를 적는다", async () => {
    renderAt("/projects/p-1");
    expect(await screen.findByText("42.9%")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText(/다릅니다/)).toBeInTheDocument();

    // 근거가 없으면 두 숫자는 그냥 서로를 부정하는 두 주장일 뿐이다.
    expect(screen.getByText(/작업 12건 중 8건/)).toBeInTheDocument();
    expect(screen.getByText(/부모 작업 2건/)).toBeInTheDocument();
    expect(screen.getByText(/취소 2건/)).toBeInTheDocument();
    expect(screen.getByText(/완료 가중 6/)).toBeInTheDocument();
    expect(screen.getByText(/전체 가중 14/)).toBeInTheDocument();
  });

  it("셀 작업이 없으면 0% 가 아니라 작업이 없다고 말한다", async () => {
    progressPayload = { project_id: "p-1", percent: null, basis: EMPTY_BASIS, notion_percent: 55 };
    renderAt("/projects/p-1");
    expect(await screen.findByText("작업이 아직 없습니다")).toBeInTheDocument();

    expect(screen.queryByText("0%")).toBeNull();
    // 저쪽 값이 있다고 그것으로 대신 채우지 않는다 — 그건 앱이 센 값이 아니다.
    expect(screen.getByText("55%")).toBeInTheDocument();
  });
});

describe("프로젝트 상세 — Health", () => {
  it("점수 옆에 이유 목록을 그린다", async () => {
    renderAt("/projects/p-1");
    expect(await screen.findByText("63점")).toBeInTheDocument();

    expect(screen.getByText("노션 진행 상태가 차질")).toBeInTheDocument();
    expect(screen.getByText(/차질' 로 표시돼 있습니다/)).toBeInTheDocument();
    expect(screen.getByText("-25점")).toBeInTheDocument();

    expect(screen.getByText("지연 작업 비율")).toBeInTheDocument();
    expect(screen.getByText(/10건 중 3건이 마감을 넘겼습니다/)).toBeInTheDocument();
    expect(screen.getByText("-12점")).toBeInTheDocument();

    // 못 잰 것을 감추면 가장 정보가 없는 프로젝트가 가장 건강해 보인다.
    expect(screen.getByText("기한 지난 마일스톤")).toBeInTheDocument();
    expect(screen.getByText(/판정할 수 없습니다/)).toBeInTheDocument();
  });

  it("잴 것이 없으면 0점이라고 하지 않는다", async () => {
    healthPayload = { project_id: "p-1", score: null, reasons: [], checked: [], unknown: HEALTH.unknown };
    renderAt("/projects/p-1");
    expect(await screen.findByText("점수를 낼 수 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("0점")).toBeNull();
  });
});

describe("프로젝트 상세 — 탭", () => {
  it("고른 탭이 주소에 남고, WBS 트리와 못 그린 작업을 보여 준다", async () => {
    const user = userEvent.setup();
    renderAt("/projects/p-1");
    await screen.findByText("63점");

    await user.click(screen.getByRole("tab", { name: "WBS" }));

    await waitFor(() => expect(addrParam("tab")).toBe("wbs"));
    expect(await screen.findByText("설계")).toBeInTheDocument();
    expect(screen.getByText("스키마 확정")).toBeInTheDocument();
    // 못 그린 작업을 조용히 빼면 사용자는 자기 일이 사라진 줄 안다.
    expect(screen.getByText("순환에 걸린 작업")).toBeInTheDocument();
  });

  /* 아래 두 개는 **배선 검사**다. 부품을 재사용한다고 적어 놓고 실제로는 이어져 있지 않은
     상태가 이 저장소에서 여러 번 나왔다 - 순수 함수는 옳은데 입력이 비어 있었다. 그러니
     탭을 실제로 열어 보고, 서버로 나간 조건까지 본다. */
  it("티켓 탭은 이 프로젝트의 노션 page id 로 걸러 기존 목록을 재사용한다", async () => {
    const user = userEvent.setup();
    renderAt("/projects/p-1");
    await screen.findByText("63점");

    await user.click(screen.getByRole("tab", { name: "티켓" }));

    expect(await screen.findByText("스키마 확정")).toBeInTheDocument();
    // 조건은 서버가 건다. 화면에서 거르면 서버가 자른 한 페이지 안에서만 걸러진다.
    expect(lastQuery("/api/tickets/team").get("project_id")).toBe("np-1");
  });

  it("노션 짝이 없는 프로젝트는 티켓 목록을 부르지 않는다", async () => {
    const user = userEvent.setup();
    detailProject = project({ notion_page_id: null });
    renderAt("/projects/p-1");
    await screen.findByText("63점");

    await user.click(screen.getByRole("tab", { name: "티켓" }));

    expect(await screen.findByText("연결된 노션 작업이 없습니다")).toBeInTheDocument();
    // 조건 없이 부르면 회사의 모든 티켓이 이 프로젝트의 목록으로 뜬다.
    const calls = apiMock.mock.calls.map(([p]) => String(p));
    expect(calls.some((p) => p.startsWith("/api/tickets/team"))).toBe(false);
  });

  it("주간 리포트 탭은 서버가 준 주로 이동하고, 저장본이 없으면 없다고 말한다", async () => {
    const user = userEvent.setup();
    renderAt("/projects/p-1");
    await screen.findByText("63점");

    await user.click(screen.getByRole("tab", { name: "주간 리포트" }));

    // 창의 끝은 배타적이지만 사람에게는 포함으로 보여야 한다(2026-08-10 이 아니라 08-09).
    // 문구를 통째로 맞춘다 - 요약문에도 같은 기간이 적혀 있어서 날짜만으로는 무엇을 본 것인지 모른다.
    expect(await screen.findByText(/2026-08-03 ~ 2026-08-09 \(마감일 기준/)).toBeInTheDocument();
    expect(screen.getByText(/저장본이 아직 없습니다/)).toBeInTheDocument();

    // 주 경계를 화면이 다시 계산하지 않는다 - 서버가 준 prev_week 를 그대로 되돌려 보낸다.
    await user.click(screen.getByRole("button", { name: "이전 주" }));
    await waitFor(() => expect(addrParam("week")).toBe("2026-07-27"));
    await waitFor(() => expect(lastQuery("/api/projects/p-1/weekly-report").get("week")).toBe("2026-07-27"));
  });

  it("🔴 규칙 요약이면 **왜** 규칙 요약인지까지 말한다", async () => {
    // 서버에만 `llm_notice` 를 넣고 화면을 안 고친 채 "배선했다" 고 적어 뒀던 자리다.
    // 이유를 안 주면 사용자는 AI 요약이 꺼져 있는지 고장 났는지 화면에서 구분할 수 없다.
    const user = userEvent.setup();
    renderAt("/projects/p-1");
    await screen.findByText("63점");
    await user.click(screen.getByRole("tab", { name: "주간 리포트" }));

    expect(await screen.findByText(/규칙으로 만든 요약입니다/)).toBeInTheDocument();
    expect(screen.getByText(/AI 요약이 꺼져 있어/)).toBeInTheDocument();
  });

  it("마일스톤 탭은 기한과 상태를 사람 말로 적는다", async () => {
    const user = userEvent.setup();
    renderAt("/projects/p-1");
    await screen.findByText("63점");

    await user.click(screen.getByRole("tab", { name: "마일스톤" }));

    expect(await screen.findByText("설계 완료")).toBeInTheDocument();
    expect(screen.getByText("베타 배포")).toBeInTheDocument();
    // 계약은 영어 열거값이지만 화면은 그것을 그대로 보여 주지 않는다.
    expect(screen.queryByText("planned")).toBeNull();
  });
});
