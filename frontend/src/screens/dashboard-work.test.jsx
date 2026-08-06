import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 업무 대시보드 구역 — 운영 지표만 있던 /dashboard 에 '내 일'을 더한 자리.
 *
 * 여기서 고정하는 계약은 세 가지다.
 *
 *  1. **서버가 센 숫자를 그대로 그린다.** 화면이 다시 세면 같은 사실이 두 벌이 되고,
 *     언젠가 서버와 화면이 다른 말을 한다.
 *  2. **0 과 '못 잼'을 구별한다.** 티켓 소스를 못 읽었을 때 0 을 그리면 "할 일이 없다"는
 *     거짓말이 된다. Health 를 아직 안 잰 프로젝트도 '차질 0건'에 섞이면 안 된다.
 *  3. **운영 지표가 죽어도 업무 구역은 뜬다.** 두 질의는 다른 소스라 함께 죽을 이유가 없다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "admin", id: "u-1" } }),
}));

import { Dashboard } from "./Dashboard.jsx";
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
    truncated: false,
    troubled: {
      count: 2,
      items: [
        { project_id: "p1", name: "점수 낮음", code: "L1", status: "active",
          health_score: 30, progress_pct: null, notion_status: null,
          reasons: ["Health 점수 낮음"] },
        { project_id: "p2", name: "노션 차질", code: null, status: "active",
          health_score: 100, progress_pct: 50, notion_status: "차질",
          reasons: ["노션 진행 상태가 차질"] },
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
              <Dashboard />
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

describe("대시보드 업무 구역", () => {
  it("내 몫과 프로젝트 지표를 서버가 센 그대로 그린다", async () => {
    renderDashboard();
    // 섹션 제목은 로딩 중에도 뜬다 - 값이 실린 타일을 기다려야 '로딩 화면을 검사'하지 않는다.
    expect(await screen.findByText("내 미완료")).toBeInTheDocument();

    // 라벨 옆의 값. StatCard 는 값과 라벨을 같은 카드 안 형제로 그린다.
    const tile = (label) => screen.getByText(label).parentElement;
    expect(tile("내 미완료")).toHaveTextContent("3");
    expect(tile("이번 주 마감")).toHaveTextContent("2");
    expect(tile("지연 티켓")).toHaveTextContent("1");
    // '차질 프로젝트'는 타일과 목록 제목에 각각 있다 - 타일 쪽만 고른다.
    expect(screen.getAllByText("차질 프로젝트")[0].parentElement).toHaveTextContent("2");
    expect(screen.getAllByText("지연 마일스톤")[0].parentElement).toHaveTextContent("1");
  });

  it("이번 주가 어느 주인지(KST 달력일)를 문장으로 말한다", async () => {
    renderDashboard();
    // 기준을 안 적으면 '이번 주'가 어느 주인지 몇 주 뒤에 아무도 답할 수 없다.
    // 끝은 **포함되는 마지막 날**로 보여준다(배타적 끝 08-10 을 그대로 보이면 반쯤은 틀리게 읽는다).
    expect(await screen.findByText(/2026-08-03 부터 2026-08-09 까지/)).toBeInTheDocument();
  });

  it("차질 프로젝트와 지연 마일스톤을 이유와 함께 나열한다", async () => {
    renderDashboard();
    expect(await screen.findByText("노션 차질")).toBeInTheDocument();
    expect(screen.getByText(/노션 진행 상태가 차질/)).toBeInTheDocument();
    expect(screen.getByText("지난 기한")).toBeInTheDocument();
    expect(screen.getByText(/2026-08-02/)).toBeInTheDocument();
  });

  it("아직 Health 를 재지 않은 프로젝트를 '차질 0건'에 섞지 않고 따로 말한다", async () => {
    renderDashboard();
    expect(await screen.findByText(/아직 Health 를 계산하지 않은 프로젝트 1건/)).toBeInTheDocument();
  });

  it("최근 완료 추이를 주별로 보여주고 기준을 밝힌다", async () => {
    renderDashboard();
    expect(await screen.findByText("최근 완료 추이")).toBeInTheDocument();
    expect(screen.getByText("2026-07-27")).toBeInTheDocument();
    // 완료 시각이 소스에 없다 - 마감일 기준이라는 사실을 화면이 그대로 말해야 한다.
    expect(screen.getByText(/마감일 기준/)).toBeInTheDocument();
  });
});

describe("대시보드 업무 구역 - 0 과 없음", () => {
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
    expect(await screen.findByText(/내 업무를 셀 수 없습니다/)).toBeInTheDocument();
    expect(screen.queryByText("내 미완료")).not.toBeInTheDocument();
    expect(screen.queryByText("이번 주 마감")).not.toBeInTheDocument();
    // 프로젝트 쪽은 다른 소스다 - 티켓이 죽었다고 함께 사라지면 안 된다(타일 + 목록 제목).
    expect(screen.getAllByText("차질 프로젝트")).toHaveLength(2);
  });

  it("운영 지표 질의가 실패해도 업무 구역은 그대로 뜬다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/home/work-dashboard") return Promise.resolve(WORK);
      return Promise.reject(new Error("운영 지표 실패"));
    });
    renderDashboard();
    expect(await screen.findByText("내 업무")).toBeInTheDocument();
  });
});
