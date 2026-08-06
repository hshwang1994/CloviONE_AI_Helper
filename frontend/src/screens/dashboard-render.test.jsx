import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 대시보드가 '비어 있는 응답'에도 무너지지 않는가 + 차트가 그림 없이도 읽히는가.
 *
 * 대시보드 payload는 필드가 20개 가까이 되고, 필드마다 null이 될 수 있는 실제 이유가 있다
 * (비-Linux 호스트 → disk/memory null, nginx TLS 종단 → cert null, 신규 설치 → integrations {}).
 * 화면이 그중 하나라도 그냥 읽으면 ErrorBoundary가 대시보드를 통째로 잡아먹는다 —
 * 첫 화면이라 앱 전체가 고장 난 것처럼 보인다. 완전히 빈 객체({})로 그 최악을 고정한다.
 *
 * 함께 확인하는 것: 새로 들인 SVG 차트 두 종의 계약.
 *   - 값이 하나도 없으면 빈 그림이 아니라 '없다'는 글자를 낸다(도넛).
 *   - 값이 0이어도 숫자는 항상 글자로 나간다(막대) — 그림을 못 보는 사람도 같은 정보를 얻는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
// 역할은 테스트마다 바꾼다(경보 일부는 '그 문제를 실제로 조치할 수 있는 역할'에게만 뜬다).
let mockRole = "admin";
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: mockRole, id: "u-1" } }),
}));

import { Dashboard } from "./Dashboard.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

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
  mockRole = "admin";
});

describe("대시보드 — 빈 payload", () => {
  it("모든 하위 객체가 없는 응답({})에도 크래시 없이 그린다", async () => {
    apiMock.mockResolvedValue({});
    renderDashboard();

    // 섹션 뼈대는 그대로 선다.
    expect(await screen.findByText("서비스 상태")).toBeInTheDocument();
    expect(screen.getByText("현재 큐 상태")).toBeInTheDocument();
    expect(screen.getByText("작업 지표 (최근 24시간)")).toBeInTheDocument();
    // 경보가 하나도 없으면 '조치 필요 없음'을 명시한다(빈 화면과 구분).
    expect(screen.getByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
    // 감사 로그를 볼 수 있는 역할인데 목록이 비었으면 '정말 없다'고 말해 준다.
    expect(screen.getByText("최근 주요 변경 이력이 없습니다.")).toBeInTheDocument();
    // disk/memory/cert가 전부 없으면 '-' 죽은 타일 대신 섹션 자체가 사라진다.
    expect(screen.queryByText("시스템 리소스")).toBeNull();
  });

  it("차트는 값이 없으면 '없다'고 쓰고, 0이어도 숫자를 글자로 낸다", async () => {
    apiMock.mockResolvedValue({});
    renderDashboard();

    // 도넛: 서비스가 한 건도 없으면 빈 원이 아니라 이유를 쓴다.
    expect(await screen.findByText("서비스 정보 없음")).toBeInTheDocument();
    // 막대: 대기/미해결 실패가 0이어도 두 값 모두 숫자로 읽힌다(그림에만 의존하지 않는다).
    expect(screen.getAllByText("0건")).toHaveLength(2);
  });

  it("'마지막 백업 없음'은 백업을 실제로 실행할 수 있는 역할에게만 경보로 뜬다", async () => {
    // 조치할 수 없는 빨간 경보를 상시 띄우면 진짜 경보에 둔감해진다 — 이 경보만 system_admin 전용이다.
    mockRole = "system_admin";
    apiMock.mockResolvedValue({});
    renderDashboard();

    expect(await screen.findByText("확인이 필요한 항목")).toBeInTheDocument();
    expect(screen.getByText("마지막 백업")).toBeInTheDocument();
    expect(screen.getByText("없음")).toBeInTheDocument();
  });
});

describe("대시보드 — 경보와 큐 구성", () => {
  it("실패·대기 작업이 있으면 경보 타일과 막대 값이 같은 수치를 말한다", async () => {
    apiMock.mockResolvedValue({
      components: { web: "up", worker: "up", scheduler: "down" },
      integrations: { n8n: { enabled: true, last_health: "up" } },
      counts: { runners: 2, active_workflows: 1, active_schedules: 0 },
      jobs_24h: { total: 10, succeeded: 7, success_rate_pct: 70, queued: 4, failed_open: 2 },
      recent_critical_audit: [],
      disk: {}, memory: {},
      cert_days_remaining: null, last_backup_at: null, last_backup_status: null,
    });
    renderDashboard();

    // 경보 줄(스케줄러 중단 / 실패 / 대기 / 성공률). '중단'은 경보 타일·서비스 배지·도넛 범례에
    // 동시에 나온다 — 셋이 같은 말을 쓰는 것이 이 화면의 규칙이라 개수로 세지 않고 존재만 본다.
    expect(await screen.findByText("확인이 필요한 항목")).toBeInTheDocument();
    expect(screen.getAllByText("중단").length).toBeGreaterThan(0);

    // 막대 차트의 값은 타일과 같은 수치를 글자로 낸다(타일은 '4'/'2', 막대는 '4건'/'2건').
    expect(screen.getByText("4건")).toBeInTheDocument();
    expect(screen.getByText("2건")).toBeInTheDocument();

    // 도넛 범례도 글자로 구성을 말한다(정상 3 = web/worker/n8n, 중단 1 = scheduler).
    expect(screen.getByText("3개")).toBeInTheDocument();
  });
});

describe("대시보드 — 유지보수 모드", () => {
  /* 8단계 전수 점검에서 찾은 결함: 서버는 `maintenance` 를 매 폴링마다 실어 보내는데
   * (app/health/service.py, 주석은 "화면이 상단 배너/경보로 띄운다"고 적혀 있었다)
   * 화면이 그 필드를 한 번도 읽지 않았다. 그래서 **전체 사용자 쓰기가 막힌 동안에도**
   * 이 화면은 초록색 '문제 없음' 배너를 띄웠다 — 운영자는 그 배너를 믿고 사용자 신고를
   * 다른 장애로 오해한다. 이 화면에서 가장 조용한 거짓말이라 테스트로 못 박는다. */
  it("점검 중이면 초록색 '문제 없음' 대신 경보로 뜬다", async () => {
    apiMock.mockResolvedValue({ maintenance: true });
    renderDashboard();

    expect(await screen.findByText("유지보수 모드")).toBeInTheDocument();
    expect(screen.getByText("켜짐")).toBeInTheDocument();
    expect(screen.queryByText("지금 조치가 필요한 문제가 없습니다.")).not.toBeInTheDocument();
  });

  it("점검 중이 아니면 경보를 만들지 않는다", async () => {
    apiMock.mockResolvedValue({ maintenance: false });
    renderDashboard();

    expect(await screen.findByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText("유지보수 모드")).not.toBeInTheDocument();
  });
});
