import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 대시보드가 '비어 있는 응답'에도 무너지지 않는가 + PA-RC-0018(REBUILD) 이후의 계약을
 * 지키는가: 조치가 필요한 항목은 목록 행 + 버튼으로, 정상 지표는 한 줄 스트립으로, 같은
 * (값,라벨)은 화면에 한 번만.
 *
 * 대시보드 payload는 필드가 20개 가까이 되고, 필드마다 null이 될 수 있는 실제 이유가 있다
 * (비-Linux 호스트 → disk/memory null, nginx TLS 종단 → cert null, 신규 설치 → integrations {}).
 * 화면이 그중 하나라도 그냥 읽으면 ErrorBoundary가 대시보드를 통째로 잡아먹는다 —
 * 첫 화면이라 앱 전체가 고장 난 것처럼 보인다. 완전히 빈 객체({})로 그 최악을 고정한다.
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

    // 섹션 뼈대는 그대로 선다(현재 큐 상태·인벤토리·지금 상태는 PA-RC-0018로 없어졌다).
    expect(await screen.findByText("서비스 상태")).toBeInTheDocument();
    expect(screen.getByText("작업 지표 (최근 24시간)")).toBeInTheDocument();
    expect(screen.getByText("백업")).toBeInTheDocument();
    expect(screen.queryByText("현재 큐 상태")).toBeNull();
    expect(screen.queryByText("인벤토리")).toBeNull();
    expect(screen.queryByText("지금 상태")).toBeNull();
    // 경보가 하나도 없으면 '조치 필요 없음'을 명시한다(빈 화면과 구분).
    expect(screen.getByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
    // 감사 로그를 볼 수 있는 역할인데 목록이 비었으면 '정말 없다'고 말해 준다.
    expect(screen.getByText("최근 주요 변경 이력이 없습니다.")).toBeInTheDocument();
    // disk/memory/cert가 전부 없으면 '-' 죽은 타일 대신 섹션 자체가 사라진다.
    expect(screen.queryByText("시스템 리소스")).toBeNull();
    // 재구축의 성공 판정: 화면이 스스로 자기 구조를 설명하는 문장이 없어도 이해된다
    // (PA-RC-0018 acceptance criteria 7 — 삭제해도 이해되면 성공, 문구 자체가 없어야 통과).
    expect(screen.queryByText(/이 줄은 요약입니다/)).toBeNull();
  });

  it("정상 지표는 큰 숫자 카드가 아니라 한 줄 스트립 텍스트로 나온다(0이어도)", async () => {
    apiMock.mockResolvedValue({
      components: { web: "up", worker: "up", scheduler: "up" },
      jobs_24h: { total: 0, succeeded: 0, success_rate_pct: null, queued: 0, failed_open: 0 },
      disk: { used_pct: 40 },
    });
    renderDashboard();

    expect(await screen.findByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
    // 대기 작업이 0이어도 글자로 보인다 — 스트립 전체가 이미 "카드가 아닌 작은 텍스트"이므로
    // 큰 판독 칸(.k-readout)으로 그려지지 않는다(direction 4).
    const queuedText = screen.getByText("대기 작업 0");
    expect(queuedText.closest(".k-readout")).toBeNull();
  });

  // PA-RC-0028: 도넛 자체를 없앴다(제목 옆 'N / M' 요약으로 대체) — 이 테스트가 막던 문제는
  // 이제 "빈 도넛 그림"이 아니라 "'서비스 상태' 그리드가 타일 없이 조용히 비는 것"이다. 같은
  // 원칙(값이 없으면 빈 그림/빈 칸이 아니라 글로 '없다'고 쓴다)을 같은 문구로 이어간다.
  it("서비스 정보가 하나도 없으면 빈 그리드가 아니라 '없다'고 쓴다", async () => {
    apiMock.mockResolvedValue({});
    renderDashboard();

    expect(await screen.findByText("서비스 정보 없음")).toBeInTheDocument();
  });

  it("'마지막 백업 없음'은 백업을 실제로 실행할 수 있는 역할에게만 경보로 뜬다", async () => {
    // 조치할 수 없는 빨간 경보를 상시 띄우면 진짜 경보에 둔감해진다 — 이 경보만 system_admin 전용이다.
    mockRole = "system_admin";
    apiMock.mockResolvedValue({});
    renderDashboard();

    expect(await screen.findByText("확인이 필요한 항목")).toBeInTheDocument();
    expect(screen.getByText("마지막 백업")).toBeInTheDocument();
    expect(screen.getByText("없음")).toBeInTheDocument();
    // 조치 목록의 기본 동작 버튼은 정확히 하나이고(이 경보 하나뿐이므로 primary), 백업
    // 구역의 버튼은 같은 화면의 두 번째 채운 버튼이 되지 않도록 outlined로 남는다
    // (PA-RC-0023 규범: 화면당 contained 정확히 1개).
    expect(screen.getAllByRole("button", { name: "백업 관리로 이동" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "백업 관리로 이동" }).className).toMatch(/containedPrimary/);
    expect(screen.getByRole("button", { name: "백업 관리" }).className).not.toMatch(/contained/);
  });
});

describe("대시보드 — 경보와 정상 지표의 중복 없음(PA-RC-0018 acceptance criteria 3)", () => {
  it("경보 중인 지표는 조치 목록에만 뜨고, 정상 지표 스트립에는 다시 뜨지 않는다", async () => {
    apiMock.mockResolvedValue({
      components: { web: "up", worker: "up", scheduler: "down" },
      integrations: { n8n: { enabled: true, last_health: "up" } },
      counts: { runners: 2, active_workflows: 1, active_schedules: 0 },
      jobs_24h: { total: 10, succeeded: 7, success_rate_pct: 70, queued: 4, failed_open: 2 },
      recent_critical_audit: [],
      disk: { used_pct: 42 }, memory: {},
      cert_days_remaining: null, last_backup_at: null, last_backup_status: null,
    });
    const { container } = renderDashboard();

    expect(await screen.findByText("확인이 필요한 항목")).toBeInTheDocument();
    // 경보 행: 스케줄러 중단, 실패 2, 대기 4, 성공률 낮음(70%) — 넷 다 행으로 뜬다.
    expect(screen.getByText("2")).toBeInTheDocument(); // 실패 작업 값
    expect(screen.getByText("4")).toBeInTheDocument(); // 대기 작업 값
    expect(screen.getByText("70%")).toBeInTheDocument(); // 성공률 값
    // 기본 조치 버튼: 가장 급한(danger) 한 건만 primary, 나머지는 outlined.
    const primaryButtons = container.querySelectorAll(".MuiButton-containedPrimary");
    expect(primaryButtons.length).toBe(1);

    // 지금 경보 중인 값(대기 작업·성공률)은 정상 지표 스트립에 다시 나오지 않는다 —
    // 스트립에 남는 건 서비스 정상 요약과 디스크(42%, 경보 임계값 80% 미만)뿐이다.
    // within으로 스트립 영역만 좁혀 판정한다(경보 행에는 같은 라벨 "대기 작업"이
    // 존재해야 정상이므로 전체 문서에서 부재만 보면 안 된다). 라벨+값이 한 노드의
    // textContent로 합쳐지므로(예: "디스크 사용 42%") 정규식으로 부분일치를 본다.
    const strip = screen.getByText(/디스크 사용/).closest("div");
    expect(within(strip).queryByText(/대기 작업/)).toBeNull();
    expect(within(strip).queryByText(/24시간 성공률/)).toBeNull();
    expect(within(strip).getByText(/42%/)).toBeInTheDocument();
  });

  it("경보가 없는 지표는 스트립에 뜨고, 값이 조치 목록과 스트립 양쪽에 겹치지 않는다", async () => {
    apiMock.mockResolvedValue({
      components: { web: "up", worker: "up", scheduler: "up" },
      counts: { active_workflows: 3 },
      jobs_24h: { total: 20, succeeded: 19, success_rate_pct: 99, queued: 0, failed_open: 0 },
      disk: { used_pct: 30 },
    });
    renderDashboard();

    expect(await screen.findByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("활성 워크플로 3")).toBeInTheDocument();
    expect(screen.getByText(/24시간 성공률 99%/)).toBeInTheDocument();
    expect(screen.getByText("디스크 사용 30%")).toBeInTheDocument();
    expect(screen.getByText("대기 작업 0")).toBeInTheDocument();
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
    expect(screen.getByText("활성")).toBeInTheDocument();
    expect(screen.queryByText("지금 조치가 필요한 문제가 없습니다.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "유지보수 설정 열기" })).toBeInTheDocument();
  });

  it("점검 중이 아니면 경보를 만들지 않는다", async () => {
    apiMock.mockResolvedValue({ maintenance: false });
    renderDashboard();

    expect(await screen.findByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText("유지보수 모드")).not.toBeInTheDocument();
  });
});

describe("대시보드 — 조치 버튼의 권한 노출(PA-RC-0018 acceptance criteria 12)", () => {
  it("작업 큐에 갈 수 없는 역할(auditor)에게는 실패 작업 경보 버튼이 비활성이다", async () => {
    mockRole = "auditor";
    apiMock.mockResolvedValue({ jobs_24h: { failed_open: 3 } });
    renderDashboard();

    expect(await screen.findByText("확인이 필요한 항목")).toBeInTheDocument();
    // auditor는 /jobs 권한이 없다(NAV_ROLES) — 라벨에 "관리자 문의"가 붙고, 갈 곳이 없으니
    // 버튼도 "작업 큐 열기"라고 거짓 약속하지 않고 "이동 불가"로 비활성 표시한다.
    expect(screen.getByText(/실패 작업.*관리자 문의/)).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: "이동 불가" });
    expect(btn).toBeDisabled();
  });

  it("작업 큐에 갈 수 있는 역할(operator)에게는 같은 경보 버튼이 활성이다", async () => {
    mockRole = "operator";
    apiMock.mockResolvedValue({ jobs_24h: { failed_open: 3 } });
    renderDashboard();

    expect(await screen.findByText("확인이 필요한 항목")).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: "작업 큐 열기" });
    expect(btn).not.toBeDisabled();
  });
});
