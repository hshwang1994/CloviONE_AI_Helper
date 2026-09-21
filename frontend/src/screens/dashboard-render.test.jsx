/* qa-contract-change: 실패 작업 경보의 단추가 「작업 큐 열기」에서 목적지를 말하는 「실패 작업 보기」가 됐다(실패로 거른 작업 큐로 간다). 권한 노출 판정은 그대로다. */
/* qa-contract-change: S11 이 대시보드의 «활성 워크플로» 타일을 걷어냈다(그 화면이 없어졌다). 줄어든 단언 하나가 정확히 그 타일이고, 나머지 지표 넷의 단언은 그대로다 — 값도 형태도 안 바뀌었다. */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

    // 섹션 뼈대는 그대로 선다.
    expect(await screen.findByText("필수 서비스")).toBeInTheDocument();
    expect(screen.getByText("외부 연동")).toBeInTheDocument();
    expect(screen.getByText("최근 24시간 작업")).toBeInTheDocument();
    expect(screen.getByText("백업")).toBeInTheDocument();
    expect(screen.getByText("파일 저장소")).toBeInTheDocument();
    expect(screen.queryByText("현재 큐 상태")).toBeNull();
    expect(screen.queryByText("인벤토리")).toBeNull();
    // 경보가 하나도 없으면 '조치 필요 없음'을 명시한다(빈 화면과 구분).
    expect(screen.getByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
    /* 🔴 연동이 하나도 없는 것은 **장애가 아니다.** 이 설치가 바깥으로 나가는 호출을 안
       쓴다는 정상 상태이고, 그렇게 말한다. */
    expect(screen.getByText(/추가된 외부 연동이 없습니다/)).toBeInTheDocument();
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

    expect(await screen.findByText("지금 상태")).toBeInTheDocument();
    expect(screen.getByText("마지막 백업")).toBeInTheDocument();
    // 경보 행의 값과 '백업' 구역의 값 둘 다 '없음'이다 — 같은 사실을 두 자리에서 말하는
    // 것이 아니라, 하나는 조치 목록이고 하나는 그 구역의 사실이다.
    expect(screen.getAllByText("없음").length).toBeGreaterThan(0);
    // 조치 목록의 기본 동작 버튼은 정확히 하나이고(이 경보 하나뿐이므로 primary), 백업
    // 구역의 버튼은 같은 화면의 두 번째 채운 버튼이 되지 않도록 outlined로 남는다
    // (PA-RC-0023 규범: 화면당 contained 정확히 1개).
    expect(screen.getAllByRole("button", { name: "백업 관리로 이동" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "백업 관리로 이동" }).className).toMatch(/containedPrimary/);
    /* 운영 자료 구역의 이동 수단은 **버튼이 아니라 링크**다 — 이 화면에서 버튼은 조치
       목록의 몫이라, 「지금 손대야 하는 것」과 「가서 보면 되는 것」이 같은 모양이 되지
       않는다. 그래서 이 화면의 채운 버튼은 여전히 정확히 하나다. */
    expect(screen.getByRole("button", { name: /백업 관리 →/ }).className).not.toMatch(/contained/);
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

    expect(await screen.findByText("지금 상태")).toBeInTheDocument();
    // 경보 행: 스케줄러 중단, 실패 2, 대기 4, 성공률 낮음(70%) — 넷 다 행으로 뜬다.
    expect(screen.getByText("2")).toBeInTheDocument(); // 실패 작업 값
    expect(screen.getByText("4")).toBeInTheDocument(); // 대기 작업 값
    expect(screen.getByText("70%")).toBeInTheDocument(); // 성공률 값
    // 기본 조치 버튼: 가장 급한(danger) 한 건만 primary, 나머지는 outlined.
    const primaryButtons = container.querySelectorAll(".MuiButton-containedPrimary");
    expect(primaryButtons.length).toBe(1);

    // 지금 경보 중인 값(대기 작업·성공률)은 정상 지표 스트립에 다시 나오지 않는다 —
    // 스케줄러가 중단이라 「필수 서비스 정상 N / M」도 빠지고, 스트립에 남는 건
    // 디스크(42%, 경보 임계값 80% 미만) 하나뿐이다.
    // within으로 스트립 영역만 좁혀 판정한다(경보 행에는 같은 라벨 "대기 작업"이
    // 존재해야 정상이므로 전체 문서에서 부재만 보면 안 된다). 라벨+값이 한 노드의
    // textContent로 합쳐지므로(예: "디스크 사용 42%") 정규식으로 부분일치를 본다.
    const strip = screen.getByText(/디스크 사용/).closest("div");
    expect(within(strip).queryByText(/대기 작업/)).toBeNull();
    expect(within(strip).queryByText(/24시간 성공률/)).toBeNull();
    expect(within(strip).getByText(/42%/)).toBeInTheDocument();
  });

  /* 🔴 필수 서비스는 「대응하는 경보가 없다」고 적혀 있었지만 사실이 아니었다 —
     buildAlerts 는 web 을 뺀 모든 필수 서비스에 `comp:<이름>` 경보를 만든다. 그래서 워커가
     응답 없음일 때 그 사실이 한 화면에 세 번 있었다(실측 2026-09-01): 조치 목록 한 줄,
     아래 「필수 서비스」 구역의 배지, 그리고 「지금 정상인」 줄의 「정상 1 / 3」. */
  it("필수 서비스가 경보 중이면 「필수 서비스 정상 N / M」이 정상 줄에서 빠진다", async () => {
    apiMock.mockResolvedValue({
      components: { web: "up", worker: "unknown", scheduler: "unknown" },
      jobs_24h: { total: 20, succeeded: 20, success_rate_pct: 100, queued: 0, failed_open: 0 },
      disk: { used_pct: 45 },
    });
    renderDashboard();

    expect(await screen.findByText(/디스크 사용 45%/)).toBeInTheDocument();
    const strip = screen.getByText(/디스크 사용/).closest("div");
    expect(within(strip).queryByText(/필수 서비스 정상/)).toBeNull();
    // 그 사실을 어디에서도 안 말하는 것이 아니다 — 아래 구역이 자기 분모로 말한다.
    expect(screen.getByText("정상 1 / 3")).toBeInTheDocument();
  });

  /* 「-」는 정상 지표가 아니라 **낼 수 없는 값**이다. 24시간 안에 끝난 작업이 없으면
     성공률에 분모가 없고, 그 사실은 아래 「최근 24시간 작업」 칸이 한 문장으로 말한다. */
  it("값이 없는 지표(성공률 「-」)는 정상 줄에 서지 않는다", async () => {
    apiMock.mockResolvedValue({
      components: { web: "up", worker: "up", scheduler: "up" },
      jobs_24h: { total: 0, succeeded: 0, success_rate_pct: null, queued: 0, failed_open: 0 },
      disk: { used_pct: 45 },
    });
    renderDashboard();

    expect(await screen.findByText(/디스크 사용 45%/)).toBeInTheDocument();
    const strip = screen.getByText(/디스크 사용/).closest("div");
    expect(within(strip).queryByText(/24시간 성공률/)).toBeNull();
    expect(screen.getByText("최근 24시간 동안 처리한 작업이 없습니다.")).toBeInTheDocument();
    // 대기 작업은 「미해결 실패」 다음, 「디스크」 앞이다 — 자리를 인덱스가 아니라 이웃으로 정한다.
    const labels = Array.from(strip.querySelectorAll("span"))
      .map((el) => el.textContent).filter((t) => /^(대기 작업|디스크 사용|미해결 실패)/.test(t));
    expect(labels.findIndex((t) => t.startsWith("대기 작업")))
      .toBeLessThan(labels.findIndex((t) => t.startsWith("디스크 사용")));
  });

  it("경보가 없는 지표는 스트립에 뜨고, 값이 조치 목록과 스트립 양쪽에 겹치지 않는다", async () => {
    apiMock.mockResolvedValue({
      components: { web: "up", worker: "up", scheduler: "up" },
      counts: {},
      jobs_24h: { total: 20, succeeded: 19, success_rate_pct: 99, queued: 0, failed_open: 0 },
      disk: { used_pct: 30 },
    });
    renderDashboard();

    expect(await screen.findByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
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
  it("진단에 갈 수 없는 역할(auditor)에게는 진단 경보 버튼이 비활성이고, 큐 경보는 활성이다", async () => {
    mockRole = "auditor";
    apiMock.mockResolvedValue({ jobs_24h: { failed_open: 3 }, cert_days_remaining: 3 });
    renderDashboard();

    expect(await screen.findByText("지금 상태")).toBeInTheDocument();
    // auditor는 /diagnostics 권한이 없다(SCREEN_ROLES) — 라벨에 "관리자 문의"가 붙고, 갈 곳이
    // 없으니 버튼도 "진단 열기"라고 거짓 약속하지 않고 "이동 불가"로 비활성 표시한다.
    expect(screen.getByText(/인증서 만료.*관리자 문의/)).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: "이동 불가" });
    expect(btn).toBeDisabled();
    // 작업 큐 읽기는 감사자에게 열렸다(app/jobs/router.py) — 실패 작업 경보는 큐로 간다.
    expect(screen.queryByText(/실패 작업.*관리자 문의/)).toBeNull();
    expect(screen.getByRole("button", { name: "실패 작업 보기" })).not.toBeDisabled();
  });

  it("작업 큐에 갈 수 있는 역할(operator)에게는 같은 경보 버튼이 활성이다", async () => {
    mockRole = "operator";
    apiMock.mockResolvedValue({ jobs_24h: { failed_open: 3 } });
    renderDashboard();

    expect(await screen.findByText("지금 상태")).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: "실패 작업 보기" });
    expect(btn).not.toBeDisabled();
  });
});

/* 🔴 **실패한 새로고침을 성공이라고 알리지 않는다.**
 *
 * 이 화면은 30초마다 스스로 다시 읽고, 그것과 별개로 사람이 누르는 「새로고침」이 있다.
 * 누른 결과는 눈으로 보는 사람에게는 머리말의 「, 새로고침 실패」로, 스크린리더 사용자
 * 에게는 `role="status"` 한 줄로 간다 — 예전에는 그 한 줄이 결과를 안 보고 언제나
 * 「대시보드를 갱신했습니다」였고, 뒤에 붙는 시각은 **직전에 성공한** 조회의 것이었다.
 * 한 화면이 두 사람에게 반대로 말하고 있었다. */
describe("대시보드 — 수동 새로고침의 결과 알림", () => {
  it("새로고침이 실패하면 성공이 아니라 실패를 알린다", async () => {
    apiMock.mockResolvedValueOnce({
      components: { web: "up", worker: "up", scheduler: "up" },
      jobs_24h: { total: 5, succeeded: 5, success_rate_pct: 100, queued: 0, failed_open: 0 },
      disk: { used_pct: 30 },
    });
    renderDashboard();
    expect(await screen.findByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();

    apiMock.mockRejectedValue(new Error("네트워크 오류"));
    await userEvent.click(screen.getByRole("button", { name: "새로고침" }));

    // `retry: 1` 이라 한 번 더 시도한다 — 그 뒤에 결과가 나온다.
    expect(await screen.findByText(/갱신하지 못했습니다/, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByText(/대시보드를 갱신했습니다/)).toBeNull();
    // 마지막으로 성공한 값은 그대로 남는다 — 폴링 실패로 화면을 비우지 않는다.
    expect(screen.getByText("지금 조치가 필요한 문제가 없습니다.")).toBeInTheDocument();
    expect(screen.getByText(/새로고침 실패/)).toBeInTheDocument();
  }, 15000);   // `retry: 1` 의 재시도 대기(1초)가 기본 5초 예산 안에서 아슬아슬하다.
});
