/* 프로젝트 화면 — **숫자를 믿을 수 있게 그리는가**, 그리고 **포털에서 고칠 수 있는가**.
 *
 * 여기서 지키는 것:
 *
 *   1) 진행률이 **null 이면 0% 가 아니다.** 캐시가 비어 "아직 계산 안 함"인 것과, 세어 보니
 *      분모가 0이라 "작업이 아직 없음"인 것은 서로 다른 말이고 둘 다 0% 가 아니다.
 *   2) 🔴 **Notion 값과 비교하지 않는다**(사용자 지시). 포털이 계산한 값 하나만 크게 그리고,
 *      "두 값이 다릅니다" 같은 문구는 없다. 대신 계산 근거(계산식·표본·가중)는 남는다 -
 *      그건 "믿지 마라" 가 아니라 "이렇게 셌다" 라서 성격이 반대다.
 *   3) Health 는 점수 **옆에 이유 목록**이 있어야 한다. 47점만 본 팀장은 할 수 있는 일이 없다.
 *   4) 목록은 **표**다(카드 격자가 아니다). 열이 고정이라야 행끼리 비교가 된다.
 *   5) 요약 숫자는 **서버 응답을 그대로** 쓴다. 화면이 `items` 를 세면 20건씩 잘린 한 페이지만
 *      세게 되고, "총 22건인데 요약은 20건 기준" 이 된다.
 *   6) 생성·수정·마일스톤 CRUD 가 **실제로 API 를 부른다.** 버튼만 그려 놓고 배선이 없는
 *      상태가 이 저장소에서 여러 번 나왔다 - 그래서 나간 요청의 method 와 본문까지 본다.
 *   7) 저장 뒤 목록·요약·상세 캐시를 **전부** 무효화한다(하나만 하면 다른 화면이 옛 값을 본다).
 *
 * 오탐 방지를 위해 표본은 **값이 서로 다른 것**을 쓴다. 0 을 쓰면 "null 을 0으로 그렸다"를
 * 잡지 못하고, 요약 숫자를 목록 건수와 같게 두면 화면이 목록을 세도 통과한다.
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

/* 요약 표본. **목록 건수와 일부러 다르게** 둔다(총 22건, 목록은 한 페이지에 1건).
 * 화면이 목록을 세서 요약을 만들면 여기서 바로 갈라진다. */
const DASHBOARD = {
  today: "2026-08-07",
  total: 22,
  by_status: { planned: 2, active: 12, on_hold: 3, done: 5 },
  progress: { average_pct: 47.3, counted: 14, not_counted: 8 },
  health: {
    unscored: 5,
    trouble: {
      count: 4,
      items: [{
        project_id: "p-1", name: "배포 자동화", code: "DEP", status: "active",
        health_score: 45, progress_pct: 42.9, notion_status: "차질",
        reasons: ["노션 진행 상태가 차질"],
      }],
    },
  },
  milestones: {
    overdue: {
      count: 6,
      items: [{
        id: "m-9", project_id: "p-1", project_name: "배포 자동화",
        name: "지난 기한", due_on: "2026-07-01", status: "planned",
      }],
    },
  },
};

let listPayload = null;
let progressPayload = null;
let healthPayload = null;
let detailProject = null;
let milestonesPayload = null;

beforeEach(() => {
  authRole = "user";
  listPayload = { items: [project()], total: 1, page: 1, page_size: 20 };
  progressPayload = { project_id: "p-1", percent: 42.9, basis: BASIS, notion_percent: 70 };
  healthPayload = HEALTH;
  detailProject = project();
  milestonesPayload = MILESTONES;
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/projects/dashboard")) return Promise.resolve(DASHBOARD);
    if (p.startsWith("/api/projects/p-1/progress")) return Promise.resolve(progressPayload);
    if (p.startsWith("/api/projects/p-1/health")) return Promise.resolve(healthPayload);
    if (p.startsWith("/api/projects/p-1/wbs")) return Promise.resolve(WBS);
    if (p.startsWith("/api/projects/p-1/milestones")) return Promise.resolve(milestonesPayload);
    if (p.startsWith("/api/projects/p-1/weekly-report")) return Promise.resolve(WEEKLY);
    if (p.startsWith("/api/projects/p-1")) return Promise.resolve({ project: detailProject });
    if (p.startsWith("/api/projects")) return Promise.resolve(listPayload);
    if (p.startsWith("/api/tickets/team")) return Promise.resolve(TEAM_TICKETS);
    if (p.startsWith("/api/tickets")) return Promise.resolve({ configured: true, ok: true, statuses: [], priorities: [], difficulties: [], projects: [], assignees: [] });
    if (p.startsWith("/api/admin/departments")) return Promise.resolve({ items: [] });
    return Promise.resolve({});
  });
});

/** 마지막으로 그 경로에 나간 쓰기 요청(method + body). 없으면 null. */
function lastWrite(prefix, method) {
  const calls = apiMock.mock.calls.filter(([p, opt]) =>
    String(p).startsWith(prefix) && opt && opt.method === method);
  const last = calls[calls.length - 1];
  return last ? { path: String(last[0]), ...last[1] } : null;
}

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

/** 마지막으로 **그 경로**로 나간 요청의 쿼리스트링.
 *
 * 접두사가 아니라 경로가 정확히 맞는 것만 본다. 접두사로 보면 `/api/projects` 가
 * `/api/projects/dashboard` 까지 잡아서, 조건이 목록에 실렸는지 묻는 검사가 요약 요청을
 * 보고 "조건이 없다" 고 답한다(그러면 조건을 안 보내는 구현도 통과한다). */
function lastQuery(path) {
  const calls = apiMock.mock.calls
    .map(([p]) => String(p))
    .filter((p) => p === path || p.startsWith(path + "?"));
  const last = calls[calls.length - 1];
  return new URLSearchParams(last && last.includes("?") ? last.slice(last.indexOf("?") + 1) : "");
}

/** 요약 타일 {라벨: 값}. 라벨 뒤의 심각도 표시('위험'/'주의')는 떼어 낸다(kit.jsx::StatCard). */
function summaryTiles() {
  const out = {};
  for (const el of document.querySelectorAll(".k-stat")) {
    const kids = Array.from(el.children);
    const value = kids[0] ? kids[0].textContent.trim() : "";
    const label = kids[1] ? kids[1].textContent.trim().replace(/(위험|주의)$/, "").trim() : "";
    out[label] = value;
  }
  return out;
}

/* ── 목록 ──────────────────────────────────────────────────────────────────── */

describe("프로젝트 목록 — 표", () => {
  it("카드가 아니라 표로 그린다 - 열이 고정이라야 행끼리 비교가 된다", async () => {
    listPayload = {
      items: [project(), project({ id: "p-2", name: "사내 포털", code: "POR", status: "on_hold" })],
      total: 2, page: 1, page_size: 20,
    };
    renderAt("/projects");
    expect(await screen.findByText("배포 자동화")).toBeInTheDocument();

    const table = screen.getByRole("table");
    for (const label of ["이름", "상태", "부서", "기간", "진행률", "Health"]) {
      expect(within(table).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    // 행이 두 개(머리행 제외)여야 한다. 예전 카드 격자는 role=table 자체가 없었다.
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("사내 포털")).toBeInTheDocument();
  });

  it("행을 누르면 상세로 간다", async () => {
    const user = userEvent.setup();
    renderAt("/projects");
    await screen.findByText("배포 자동화");

    await user.click(screen.getByRole("button", { name: "상세 보기: 배포 자동화" }));

    await waitFor(() => expect(addr()).toBe("/projects/p-1"));
  });

  it("진행률 캐시가 비어 있으면 0% 라고 하지 않는다", async () => {
    listPayload = {
      items: [project({ progress_pct: null, notion_progress_pct: null, health_score: null })],
      total: 1, page: 1, page_size: 20,
    };
    renderAt("/projects");
    expect(await screen.findByText("배포 자동화")).toBeInTheDocument();

    const table = screen.getByRole("table");
    // 0% 는 "세어 봤더니 0" 이라는 뜻이라, 한 번도 안 센 것에 붙이면 거짓말이다.
    expect(within(table).queryByText("0%")).toBeNull();
    expect(within(table).getByText("아직 계산하지 않았습니다")).toBeInTheDocument();
    expect(within(table).getByText("Health 를 아직 계산하지 않았습니다")).toBeInTheDocument();
  });

  it("🔴 Notion 값을 나란히 그리지 않고, 다르다고 말하지도 않는다", async () => {
    // 표본의 두 값은 서로 다르다(42.9 vs 70). 예전 화면은 여기서 '70%' 와 "다릅니다" 를 그렸다.
    renderAt("/projects");
    await screen.findByText("배포 자동화");

    const table = screen.getByRole("table");
    expect(within(table).getByText("42.9%")).toBeInTheDocument();
    expect(within(table).queryByText("70%")).toBeNull();
    expect(screen.queryByText(/다릅니다/)).toBeNull();
    expect(screen.queryByText(/Notion 값/)).toBeNull();
  });

  it("설명문이 Notion 과 비교한다고 말하지 않는다", async () => {
    renderAt("/projects");
    await screen.findByText("배포 자동화");

    expect(screen.queryByText(/Notion 값을 나란히/)).toBeNull();
    expect(screen.getByText(/포털이 작업을 다시 세어 계산한 값/)).toBeInTheDocument();
  });
});

describe("프로젝트 목록 — 요약", () => {
  it("🔴 요약 숫자는 서버 응답을 그대로 쓴다 (목록을 세지 않는다)", async () => {
    // 목록은 한 페이지에 1건인데 요약은 22건이다. 화면이 items 를 세면 여기서 갈라진다.
    renderAt("/projects");
    await screen.findByText("배포 자동화");

    // 통째로 비교한다. 타일 하나씩 보면 화면이 새 타일을 몰래 더해도 안 걸린다.
    expect(summaryTiles()).toEqual({
      "전체": "22",
      "진행": "12",
      "완료": "5",
      "보류": "3",
      "계획": "2",
      "평균 진행률": "47.3%",
      "Health 하위": "4",
      "지연 마일스톤": "6",
    });
  });

  it("요약은 목록과 다른 경로를 부르고, 페이지 조건을 싣지 않는다", async () => {
    renderAt("/projects?page=2");
    await screen.findByText("배포 자동화");

    const calls = apiMock.mock.calls.map(([p]) => String(p));
    expect(calls).toContain("/api/projects/dashboard");
    // 요약이 보고 있는 페이지를 따라가면 그건 이미 잘린 표본이다.
    expect(calls.some((p) => p.startsWith("/api/projects/dashboard?"))).toBe(false);
  });

  it("못 잰 것을 감추지 않는다", async () => {
    // "Health 하위 0건" 이 '다 건강하다' 인지 '아무것도 안 쟀다' 인지는 다른 사실이다.
    renderAt("/projects");
    await screen.findByText("배포 자동화");

    expect(screen.getByText(/계산이 끝난 14건만 셌습니다/)).toBeInTheDocument();
    expect(screen.getByText(/8건은 아직 계산하지 않았습니다/)).toBeInTheDocument();
    expect(screen.getByText(/Health 는 5건을 아직 재지 않았습니다/)).toBeInTheDocument();
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

describe("프로젝트 상세 — 진행률", () => {
  it("🔴 포털 값 하나만 그리고, 계산 근거는 남긴다", async () => {
    // 응답에는 notion_percent(70)가 있다. 화면이 그걸 그리면 안 된다.
    renderAt("/projects/p-1");
    expect(await screen.findByText("42.9%")).toBeInTheDocument();

    expect(screen.queryByText("70%")).toBeNull();
    expect(screen.queryByText(/다릅니다/)).toBeNull();
    expect(screen.queryByText("Notion 값")).toBeNull();

    // 근거는 "믿지 마라" 가 아니라 "이렇게 셌다" 라서 남긴다.
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
    // 저쪽 값이 있다고 그것으로 대신 채우지 않는다 - 그건 포털이 센 값이 아니다.
    expect(screen.queryByText("55%")).toBeNull();
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

  it("티켓 탭은 완료·취소를 기본으로 숨기고, 스위치로 포함시킬 수 있다", async () => {
    // TeamTickets 는 '완료, 취소 포함' 스위치가 있어 끝난 티켓도 볼 수 있다. 이 탭이 같은
    // /api/tickets/team 을 재사용하면서 그 스위치를 안 그리면, 서버 기본값(active=true)에
    // 조용히 갇혀 이 프로젝트의 완료·취소 티켓을 영영 볼 방법이 없어진다 - "총 N건"이
    // 사실은 활성 티켓 수인데 전체인 것처럼 보인다.
    const user = userEvent.setup();
    renderAt("/projects/p-1");
    await screen.findByText("63점");

    await user.click(screen.getByRole("tab", { name: "티켓" }));
    await screen.findByText("스키마 확정");

    // 서버 기본값에 기대지 않고 명시적으로 활성만 요청한다(화면이 무엇을 요청하는지 보인다).
    expect(lastQuery("/api/tickets/team").get("active")).toBe("true");

    await user.click(screen.getByRole("switch", { name: "완료, 취소 포함" }));

    await waitFor(() => expect(lastQuery("/api/tickets/team").get("active")).toBe("false"));
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

/* ── 포털에서 만들고 고친다 ────────────────────────────────────────────────────
 *
 * 백엔드에는 처음부터 다 있었는데(create/update/마일스톤 CRUD) 화면에 버튼이 하나도
 * 없었다. 그래서 여기서 보는 것은 "버튼이 있는가" 가 아니라 **나간 요청**이다 - 버튼만
 * 그려 놓고 배선이 없는 상태가 이 저장소에서 여러 번 나왔다. */

/** 폼 모달의 칸을 채운다. 라벨로 찾는다(placeholder 는 화면 문구가 아니다). */
async function fill(user, label, value) {
  const input = screen.getByLabelText(new RegExp("^" + label));
  await user.clear(input);
  await user.type(input, value);
}

describe("프로젝트 생성", () => {
  beforeEach(() => { authRole = "admin"; });

  it("🔴 새 프로젝트 폼이 실제로 POST 를 부른다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opt) => {
      const p = String(path);
      if (p === "/api/projects" && opt && opt.method === "POST") {
        return Promise.resolve({ project: { ...project(), id: "p-new", name: "새 사업" } });
      }
      if (p.startsWith("/api/projects/dashboard")) return Promise.resolve(DASHBOARD);
      if (p.startsWith("/api/projects/p-1")) return Promise.resolve({ project: detailProject });
      if (p.startsWith("/api/projects")) return Promise.resolve(listPayload);
      if (p.startsWith("/api/admin/departments")) return Promise.resolve({ items: [] });
      return Promise.resolve({});
    });

    renderAt("/projects");
    await screen.findByText("배포 자동화");

    await user.click(screen.getByRole("button", { name: "+ 새 프로젝트" }));
    await fill(user, "이름", "새 사업");
    await fill(user, "시작일", "2026-09-01");
    await user.click(screen.getByRole("button", { name: "만들기" }));

    await waitFor(() => expect(lastWrite("/api/projects", "POST")).not.toBeNull());
    const sent = lastWrite("/api/projects", "POST");
    expect(sent.path).toBe("/api/projects");
    expect(sent.body.name).toBe("새 사업");
    // 날짜는 서버가 이미 받는 필드다(EDITABLE_FIELDS). 폼이 그 칸을 안 그리면 사용자는
    // 노션에서만 기간을 정할 수 있다 - 그게 사용자가 없애라고 한 상태다.
    expect(sent.body.starts_on).toBe("2026-09-01");
    expect(sent.body.status).toBe("active");
  });

  it("쓰기 권한이 없으면 버튼을 그리지 않는다", async () => {
    authRole = "user";
    renderAt("/projects");
    await screen.findByText("배포 자동화");

    expect(screen.queryByRole("button", { name: "+ 새 프로젝트" })).toBeNull();
  });
});

describe("프로젝트 수정", () => {
  beforeEach(() => { authRole = "admin"; });

  it("🔴 수정 폼이 PATCH 를 부르고, 편집 시작 시점의 지문을 함께 보낸다", async () => {
    const user = userEvent.setup();
    renderAt("/projects/p-1");
    await screen.findByText("63점");

    await user.click(screen.getByRole("button", { name: "수정" }));
    await fill(user, "종료일", "2026-12-31");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(lastWrite("/api/projects/p-1", "PATCH")).not.toBeNull());
    const sent = lastWrite("/api/projects/p-1", "PATCH");
    expect(sent.body.ends_on).toBe("2026-12-31");
    // 폼은 열려 있던 값을 그대로 되보낸다 - 이름이 빠지면 서버가 지우기로 읽을 수 있다.
    expect(sent.body.name).toBe("배포 자동화");
    // 지문을 안 보내면 두 사람이 같은 폼을 열었을 때 나중 사람이 조용히 덮어쓴다.
    expect(sent.body.base_notion_version).toBe("v1");
  });

  it("🔴 저장 뒤 목록·요약·상세 캐시를 전부 무효화한다", async () => {
    // 하나만 하면 저장은 됐는데 다른 화면이 옛 값을 계속 보여 준다(E6 에서 겪은 그 실수).
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, "invalidateQueries");
    render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <MemoryRouter initialEntries={["/projects/p-1"]}>
                <Routes><Route path="/projects/:id" element={<Project />} /></Routes>
              </MemoryRouter>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("63점");

    await user.click(screen.getByRole("button", { name: "수정" }));
    await fill(user, "이름", "이름 바꿈");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(lastWrite("/api/projects/p-1", "PATCH")).not.toBeNull());
    await waitFor(() => {
      const keys = spy.mock.calls.map(([a]) => JSON.stringify(a && a.queryKey));
      expect(keys).toContain(JSON.stringify(["projects", "list"]));
      expect(keys).toContain(JSON.stringify(["projects", "dashboard"]));
      expect(keys).toContain(JSON.stringify(["projects", "one", "p-1"]));
    });
  });
});

describe("프로젝트 보관 (FN-04)", () => {
  beforeEach(() => { authRole = "admin"; });

  it("🔴 '보관' 버튼이 확인 후 DELETE /api/projects/{id}를 부른다", async () => {
    const user = userEvent.setup();
    renderAt("/projects/p-1");
    await screen.findByText("63점");

    await user.click(screen.getByRole("button", { name: "보관" }));
    // ConfirmProvider 다이얼로그의 확인 버튼은 confirmLabel("프로젝트 보관")을 쓴다 —
    // 트리거 버튼("보관")과 라벨이 겹치지 않아야 어느 쪽을 눌렀는지 테스트가 분명히 안다.
    await user.click(await screen.findByRole("button", { name: "프로젝트 보관" }));

    await waitFor(() => expect(lastWrite("/api/projects/p-1", "DELETE")).not.toBeNull());
  });

  it("이미 보관된 프로젝트에는 '보관' 버튼이 다시 뜨지 않는다(되돌리는 API가 없다)", async () => {
    detailProject = project({ archived_at: "2026-08-01T00:00:00" });
    renderAt("/projects/p-1");
    await screen.findByText("배포 자동화");

    expect(screen.queryByRole("button", { name: "보관" })).toBeNull();
    expect(screen.getByText("보관됨")).toBeInTheDocument();
  });
});

describe("마일스톤 CRUD", () => {
  beforeEach(() => { authRole = "admin"; });

  async function openMilestones(user) {
    renderAt("/projects/p-1");
    await screen.findByText("63점");
    await user.click(screen.getByRole("tab", { name: "마일스톤" }));
    await screen.findByText("설계 완료");
  }

  it("🔴 추가가 실제로 POST 를 부른다", async () => {
    const user = userEvent.setup();
    await openMilestones(user);

    await user.click(screen.getByRole("button", { name: "+ 마일스톤 추가" }));
    await fill(user, "이름", "정식 오픈");
    await fill(user, "기한", "2026-10-01");
    await user.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => expect(lastWrite("/api/projects/p-1/milestones", "POST")).not.toBeNull());
    const sent = lastWrite("/api/projects/p-1/milestones", "POST");
    expect(sent.body.name).toBe("정식 오픈");
    expect(sent.body.due_on).toBe("2026-10-01");
  });

  it("🔴 수정이 그 행의 id 로 PATCH 를 부른다", async () => {
    const user = userEvent.setup();
    await openMilestones(user);

    // 행마다 다른 접근 이름이 있어야 어느 줄을 고치는지 알 수 있다.
    await user.click(screen.getByRole("button", { name: "마일스톤 수정: 베타 배포" }));
    await fill(user, "기한", "2026-09-15");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(lastWrite("/api/projects/p-1/milestones/m-2", "PATCH")).not.toBeNull());
    const sent = lastWrite("/api/projects/p-1/milestones/m-2", "PATCH");
    expect(sent.body.due_on).toBe("2026-09-15");
    expect(sent.body.name).toBe("베타 배포");
  });

  it("🔴 삭제는 확인을 받은 뒤에만 부른다", async () => {
    const user = userEvent.setup();
    await openMilestones(user);

    await user.click(screen.getByRole("button", { name: "마일스톤 삭제: 베타 배포" }));
    // 확인 대화상자가 뜨기 전에는 아무것도 안 나간다 - 되돌릴 수 없는 삭제다.
    expect(lastWrite("/api/projects/p-1/milestones/m-2", "DELETE")).toBeNull();

    await screen.findByText(/되돌릴 수 없습니다/);
    await user.click(screen.getByRole("button", { name: "삭제" }));

    await waitFor(() =>
      expect(lastWrite("/api/projects/p-1/milestones/m-2", "DELETE")).not.toBeNull());
  });

  it("취소하면 삭제하지 않는다", async () => {
    const user = userEvent.setup();
    await openMilestones(user);

    await user.click(screen.getByRole("button", { name: "마일스톤 삭제: 베타 배포" }));
    await screen.findByText(/되돌릴 수 없습니다/);
    await user.click(screen.getByRole("button", { name: "취소" }));

    await waitFor(() => expect(screen.queryByText(/되돌릴 수 없습니다/)).toBeNull());
    expect(lastWrite("/api/projects/p-1/milestones/m-2", "DELETE")).toBeNull();
  });

  it("마일스톤이 하나도 없어도 추가할 수 있다", async () => {
    // 빈 상태에서 버튼이 사라지면 첫 마일스톤을 영원히 못 만든다.
    const user = userEvent.setup();
    milestonesPayload = { items: [], total: 0 };
    renderAt("/projects/p-1");
    await screen.findByText("63점");
    await user.click(screen.getByRole("tab", { name: "마일스톤" }));

    expect(await screen.findByText("마일스톤이 없습니다")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ 마일스톤 추가" })).toBeInTheDocument();
  });

  it("쓰기 권한이 없으면 수정·삭제 버튼을 그리지 않는다", async () => {
    const user = userEvent.setup();
    authRole = "user";
    await openMilestones(user);

    expect(screen.queryByRole("button", { name: "+ 마일스톤 추가" })).toBeNull();
    expect(screen.queryByRole("button", { name: "마일스톤 삭제: 베타 배포" })).toBeNull();
  });
});
