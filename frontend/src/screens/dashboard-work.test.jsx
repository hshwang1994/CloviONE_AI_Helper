import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 이번 주 업무 상태 묶음(`WorkSummary.jsx`).
 *
 * **이 묶음은 사용자 홈(`/me`) 오른쪽 레일에 산다** (0060 §3). 예전에는 관리자 대시보드
 * 하단에 있었는데, 여기 있는 숫자는 전부 개인 업무이거나 그 사람의 조회 범위 요약이고
 * 누르면 전부 사용자 콘솔로 나갔다. 관리자 콘솔은 Control Plane 이라 운영 정보만 둔다.
 *
 * 🔴 **티켓 축의 수는 여기서 뺐다.** `mine.open` 은 홈 상단 판독 줄의 「진행 중」과 같은
 * 함수가 센 값이고 `mine.overdue` 는 「지연」과 같은 값이다(app/home/work.py). 실측에서
 * 한 화면에 「지연 12」와 「지연 티켓 12」가 나란히 떠 있었다. 남는 것은 다른 축이다 —
 * 프로젝트와 마일스톤, 그리고 최근 완료 추이.
 *
 * 여기서 고정하는 계약은 넷이다.
 *
 *  1. **서버가 센 숫자를 그대로 그린다.** 화면이 다시 세면 같은 사실이 두 벌이 된다.
 *  2. **같은 수를 두 자리에서 말하지 않는다.** 판독 줄이 이미 말하는 티켓 수는 없다.
 *  3. **0 과 못 잼을 구별한다.** Health 를 아직 안 잰 프로젝트도 차질 0건에 섞이면 안 된다.
 *  4. **다른 질의가 죽어도 이 묶음은 뜬다.** 질의가 따로라 함께 죽을 이유가 없다.
 *
 * qa-contract-change: 프로젝트 축 줄을 손으로 그린 버튼 목록에서 대시보드와 같은 상태 줄 부품(StatusList, StatusTile — role=button 칸)으로 옮겼다(계획 B-6).
 * 네이티브 button 으로 찾던 단언을 role=button 칸으로 옮기고, 키보드로 닿는다(tabIndex 0)는 단언을 더한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "admin", id: "u-1" } }),
}));

import { WORK_UNKNOWN, WorkSection } from "./WorkSummary.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const WORK = {
  ok: true,
  today: "2026-08-03",
  window: { start: "2026-08-03", end_exclusive: "2026-08-10" },
  tickets: { configured: true, ok: true, mapped: true },
  mine: { open: 3, overdue: 1, due_this_week: 2, done_this_week: 1 },
  completion_trend: [
    { week_of: "2026-07-13", assigned: 0, done: 0 },
    { week_of: "2026-07-20", assigned: 0, done: 0 },
    { week_of: "2026-07-27", assigned: 2, done: 1 },
    { week_of: "2026-08-03", assigned: 2, done: 1 },
  ],
  projects: {
    in_scope: 4,
    unscored: 1,
    low_confidence: 2,
    truncated: false,
    troubled: {
      count: 2,
      items: [
        { project_id: "p1", name: "점수 낮음", code: "L1", status: "active",
          health_score: 30, progress_pct: null, notion_status: null,
          reasons: ["Health 점수 낮음"] },
        /* 예전에는 이 행이 `notion_status: "차질"` + "노션 진행 상태가 차질" 이었다.
           그 규칙은 얼어붙은 미러 컬럼으로 점수를 깎아 걷어냈으므로 서버가 이제 못 내는
           모양이다. 화면이 여러 건을 어떻게 그리는지는 그대로 지킨다. */
        { project_id: "p2", name: "점수 0점", code: null, status: "active",
          health_score: 0, progress_pct: 50, notion_status: null,
          reasons: ["Health 점수 낮음"] },
      ],
    },
  },
  milestones: {
    overdue: {
      count: 1,
      items: [{ id: "m1", project_id: "p1", project_name: "점수 낮음",
                name: "지난 기한", due_on: "2026-08-02", status: "planned" }],
    },
  },
};

function route(path) {
  if (path === "/api/home/work-dashboard") return Promise.resolve(WORK);
  return Promise.resolve({});
}

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <WorkSection />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(route);
});

describe("이번 주 업무 상태 묶음", () => {
  it("프로젝트 축 두 값을 서버가 센 그대로 그린다", async () => {
    renderDashboard();
    expect(await screen.findByText("차질 프로젝트")).toBeInTheDocument();

    const row = (label) => screen.getByText(label).closest('[role="button"], button');
    expect(row("차질 프로젝트")).toHaveTextContent("2건");
    expect(row("지연 마일스톤")).toHaveTextContent("1건");
    // 줄은 키보드로도 닿는다 — 누를 수 있는 칸이 탭 순서에 선다.
    expect(row("차질 프로젝트")).toHaveAttribute("tabindex", "0");
  });

  /* 🔴 판독 줄이 이미 말하는 티켓 수를 여기서 되풀이하지 않는다. 세 라벨은 각각 홈 상단의
     「진행 중」·「지연」과 오른쪽 도넛의 모수와 같은 값이었다. */
  it("판독 줄과 같은 값을 다시 말하지 않는다", async () => {
    renderDashboard();
    await screen.findByText("차질 프로젝트");
    for (const gone of ["내 미완료", "지연 티켓", "이번 주 마감"]) {
      expect(screen.queryByText(gone), gone).toBeNull();
    }
  });

  it("차질 프로젝트·지연 마일스톤 줄을 누르면 /projects로 간다(이름·사유 상세는 거기에 있다)", async () => {
    renderDashboard();
    const row = await screen.findByText("차질 프로젝트");
    expect(row.closest('[role="button"], button')).toBeInTheDocument();
    expect(row.closest('[role="button"], button')).toHaveAttribute("aria-label", "차질 프로젝트 목록 열기");
    expect(screen.queryByText("노션 차질")).not.toBeInTheDocument();
  });

  /* 빠진 것이 있으면 빠졌다고 말하되, 읽어도 사용자가 할 수 있는 일이 없는 문장은 접어 둔다
     (사용자 지시: 내부 진단성 문구는 단순화하거나 상세 도움말로 옮긴다). 접힘 자체가 화면에
     남아 있어야 「빠진 것이 없다」와 구별된다. */
  it("판정에서 빠진 프로젝트가 있으면 접힌 도움말로 말한다", async () => {
    renderDashboard();
    const summary = await screen.findByText("이 수에 안 들어간 프로젝트가 있습니다");
    expect(summary).toBeInTheDocument();
    // 진단 문구 자체는 지우지 않는다 — 접힌 안쪽에 그대로 있다.
    expect(screen.getByText(/Health 점수가 없는 프로젝트 1건/)).toBeInTheDocument();
    expect(screen.getByText(/일부 항목만으로 계산한 프로젝트 2건/)).toBeInTheDocument();
    // 예전 문구(내부 용어 그대로)는 화면 본문에 없다.
    expect(screen.queryByText(/Health 를 계산하지 않은/)).toBeNull();
    expect(screen.queryByText(/점수의 신뢰도가 낮을 수 있습니다/)).toBeNull();
  });

  it("최근 완료 추이는 네 주가 모두 같은 모양이고, 마감이 없던 주를 0% 로 그리지 않는다", async () => {
    renderDashboard();
    expect(await screen.findByText("최근 완료 추이")).toBeInTheDocument();

    /* 넉 주가 **전부** 「기간」 한 줄을 갖는다. 예전에는 부연(`그 주 마감 N건`)이 마감이
       있던 주에만 한 줄 더 붙어 행 높이가 들쭉날쭉했다. 연도는 넉 주 내내 같은 값이라 뺀다. */
    for (const label of ["7월 13일 주간", "7월 20일 주간", "7월 27일 주간", "8월 3일 주간"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }

    /* 🔴 막대는 «그 주 마감 대상 가운데 얼마나 끝냈는가» 다. 상대 축소를 쓰면 완료 1건짜리
       주가 꽉 찬 막대가 되어 규모를 부풀린다 — 그래서 화면에 상대 비교 안내가 없다. */
    expect(screen.queryByText(/100%로 본 상대 비교/)).toBeNull();
    expect(screen.getAllByText("마감 2건 중 1건 완료")).toHaveLength(2);

    // 마감이 0건인 주는 0% 가 아니라 **분모가 없는 주**다.
    expect(screen.getAllByText("마감 없음")).toHaveLength(2);

    /* 집계 기준은 본문에 상시로 두지 않는다 — 접힘은 남아 있고(사실을 지우지 않는다)
       그 안에 문장이 있다. */
    expect(screen.getByText("집계 기준")).toBeInTheDocument();
    expect(screen.getByText(/마감일이 그 주에 든 티켓만 셉니다/)).toBeInTheDocument();
  });
});

describe("이번 주 업무 상태 묶음 - 0 과 없음", () => {
  it("티켓 소스를 못 읽으면 0 이 아니라 '셀 수 없다'고 말한다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/home/work-dashboard") {
        return Promise.resolve({
          ...WORK,
          tickets: { configured: true, ok: false, mapped: true, error: "노션 오류" },
          mine: null,
          completion_trend: null,
        });
      }
      return Promise.resolve({});
    });
    renderDashboard();
    expect(await screen.findByText(WORK_UNKNOWN)).toBeInTheDocument();
    // 못 세는 것을 0 으로 그리지 않는다 — 그림 자체가 없다.
    expect(screen.queryByText("7월 27일 주간")).not.toBeInTheDocument();
    // 프로젝트 쪽은 다른 소스다 - 티켓이 죽었다고 함께 사라지면 안 된다.
    expect(screen.getByText("차질 프로젝트")).toBeInTheDocument();
  });

  it("다른 질의가 실패해도 이 묶음은 그대로 뜬다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/home/work-dashboard") return Promise.resolve(WORK);
      return Promise.reject(new Error("운영 지표 실패"));
    });
    renderDashboard();
    expect(await screen.findByText("차질 프로젝트")).toBeInTheDocument();
  });
});
