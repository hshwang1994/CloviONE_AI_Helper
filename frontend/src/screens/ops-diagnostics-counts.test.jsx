/* qa-contract-change: 진단 화면의 «현재 리소스» 타일 셋 중 둘(활성 워크플로·추가된 러너)이 S11 로 사라졌다. 남은 하나(활성 스케줄)는 숫자뿐 아니라 **라벨까지** 단언하도록 바꿔, 줄어든 개수만큼 남은 것을 더 세게 못 박았다.
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
/* qa-contract-change: 「현재 리소스」 구획(값 하나를 든 전폭 판)이 「대시보드에서 보기」와 같은 주석 줄 한 문장으로 옮긴다(D-501). 크래시하지 않고 수를
   보인다는 단언은 그대로이고, 라벨 단언은 그 문장(「지금 활성화된 실행 일정은 5개입니다.」)과 실행 일정으로 가는 길로 잰다. 같은 회차의 진단 정리(디스크 두
   값은 속성 줄, 작업 지표는 24시간 측정만, 백로그는 판정 줄에서 거른 작업 큐로)를 재는 시험을 이 파일에 더한다.
   qa-contract-change: 주석 줄의 가는 길이 명사구 단추 이름 「실행 일정 보기 →」가 됐다(D-587, 「실패 작업 보기」와 같은 틀). 가는 곳(/schedules)은 그대로이고, 반례의
   부재 단언이 옛 문장(「켜져 있는 스케줄은」)을 찾아 늘 통과하던 것을 지금 문장으로 바꾼다. 판정 요약이 「확인할 항목 N건(위험 · 주의)」인지 새로 잰다. */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

/* 진단 화면 — '현재 리소스' 섹션(counts).
 *
 * Diagnostics.jsx가 ops/Diagnostics.jsx로 옮겨지면서 그 섹션의 판독 셋이 fmtNum()을
 * 쓰는데(활성 워크플로/활성 스케줄/등록된 러너), Dashboard.jsx에서 그 이름을 import하는 줄이
 * 빠졌다 — 다른 ops 테스트는 전부 counts: {}(빈 객체)만 써서 이 섹션 자체가 안 그려졌으므로
 * (Object.keys(counts).length===0) 지금까지 아무 테스트도 이 ReferenceError를 밟지 않았다.
 * 실제 배포에서는 진단 번들이 거의 항상 counts를 채워 보내므로, 이 화면을 열자마자
 * "fmtNum is not defined"로 전체가 깨진다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { Diagnostics } from "./Ops.jsx";
import { jobMeasures } from "./ops/JobQueuePanel.jsx";
import { healthVerdict, JOBS_BACKLOG_LINKS } from "./ops/opsHelpers.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname + location.search}</div>;
}

function renderDiagnostics() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/diagnostics"]}>
              <LocationProbe />
              <Diagnostics />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/* 백업 시각은 상대값이다 — 절대 날짜면 판정(7일)이 작성 다음 주부터 뒤집힌다(ops-service-status.test.jsx 와 같은 이유). */
const RECENT_BACKUP_AT = new Date(Date.now() - 24 * 3600 * 1000).toISOString().replace(/\.\d+Z$/, "");

const BASE_DASH = {
  integrations: {}, jobs_24h: {}, recent_critical_audit: [],
  disk: {}, memory: {}, cert_days_remaining: null,
  last_backup_at: RECENT_BACKUP_AT, last_backup_status: "succeeded",
  components: { web: "up", worker: "up", scheduler: "up" },
};

function withBundle(dashboard) {
  apiMock.mockImplementation((path) => {
    if (path === "/api/admin/diagnostics/bundle") {
      return Promise.resolve({
        generated_at: "2026-08-03T07:00:00",
        dashboard: { ...BASE_DASH, counts: {}, ...dashboard },
        recent_job_errors: [],
      });
    }
    return Promise.reject(new Error("unexpected api call: " + path));
  });
}

beforeEach(() => {
  apiMock.mockReset();
  Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
});

describe("진단 — 현재 리소스(counts) 섹션", () => {
  it("counts가 채워져 있으면 크래시하지 않고 인벤토리 숫자를 보여준다", async () => {
    withBundle({ counts: { active_schedules: 5 } });
    renderDiagnostics();

    // S11 이 워크플로·러너 타일을 걷어내 활성 스케줄 하나가 남았고, D-501 이 그 하나를 주석 줄 한 문장으로 옮겼다.
    expect(await screen.findByText("지금 활성화된 실행 일정은 5개입니다.")).toBeInTheDocument();
    // 값 하나를 든 전폭 판(「현재 리소스」 구획)은 없다.
    expect(screen.queryByText("현재 리소스")).toBeNull();
    expect(document.querySelector("[data-summary-single]")).toBeNull();
  });

  it("그 줄의 「실행 일정 보기 →」가 실행 일정으로 간다", async () => {
    withBundle({ counts: { active_schedules: 2 } });
    const user = userEvent.setup();
    renderDiagnostics();
    const line = (await screen.findByText("지금 활성화된 실행 일정은 2개입니다.")).closest("p");
    await user.click(within(line).getByRole("button", { name: "실행 일정 보기 →" }));
    expect(screen.getByTestId("location-probe")).toHaveTextContent("/schedules");
  });

  it("반례: 번들이 이 수를 안 주면 줄도 없다", async () => {
    withBundle({ counts: {} });
    renderDiagnostics();
    await screen.findByText("필수 서비스");
    expect(screen.queryByText(/활성화된 실행 일정은/)).toBeNull();
    expect(screen.queryByRole("button", { name: "실행 일정 보기 →" })).toBeNull();
  });
});

describe("진단 — 시스템 리소스는 값이 둘 이하이면 속성 줄이다 (D-501)", () => {
  it("디스크 여유 · 사용 두 값은 반폭 판 둘이 아니라 속성 줄 하나다", async () => {
    withBundle({ disk: { free_gb: 553.8, used_pct: 44.6 } });
    renderDiagnostics();
    const group = await screen.findByRole("group", { name: "시스템 리소스" });
    expect(group).toHaveClass("k-metabar");
    expect(within(group).getByText("디스크 여유")).toBeInTheDocument();
    expect(within(group).getByText("553.8GB")).toBeInTheDocument();
    expect(within(group).getByText("44.6%")).toBeInTheDocument();
  });

  it("반례: 값이 셋 이상이면 나란히 견주는 타일 줄이다", async () => {
    withBundle({ disk: { free_gb: 12, used_pct: 82 }, memory: { used_pct: 40 } });
    renderDiagnostics();
    const group = await screen.findByLabelText("시스템 리소스");
    expect(group).not.toHaveClass("k-metabar");
    expect(within(group).getByText("메모리 사용")).toBeInTheDocument();
  });
});

describe("진단 — 작업 지표는 24시간 측정만 든다 (D-501)", () => {
  it("백로그 누계(「대기 중(전체)」 · 「미해결 실패(전체)」)는 타일이 아니다", async () => {
    withBundle({ jobs_24h: { total: 12, success_rate_pct: 90, avg_processing_seconds: 4, queued: 7, failed_open: 3 } });
    renderDiagnostics();
    const group = await screen.findByLabelText("작업 지표");
    expect(within(group).getByText("처리 요청")).toBeInTheDocument();
    expect(within(group).getByText("성공률(종료된 작업 기준)")).toBeInTheDocument();
    expect(within(group).getByText("평균 처리 시간")).toBeInTheDocument();
    expect(within(group).queryByText(/\(전체\)/)).toBeNull();
    expect(screen.queryByText("대기 중(전체)")).toBeNull();
    expect(screen.queryByText("미해결 실패(전체)")).toBeNull();
  });

  it("잴 수 없는 값은 「-」 판이 아니라 빠지고, 남은 값이 둘 이하이면 속성 줄이다", async () => {
    withBundle({ jobs_24h: { total: 0, success_rate_pct: null, avg_processing_seconds: null, queued: 0, failed_open: 0 } });
    renderDiagnostics();
    const group = await screen.findByRole("group", { name: "작업 지표" });
    expect(group).toHaveClass("k-metabar");
    expect(within(group).getByText("처리 요청")).toBeInTheDocument();
    expect(within(group).queryByText("성공률(종료된 작업 기준)")).toBeNull();
    expect(within(group).queryByText("-")).toBeNull();
  });

  it("jobMeasures — 값이 없는 측정을 만들지 않는다", () => {
    expect(jobMeasures({}).map((m) => m.key)).toEqual([]);
    expect(jobMeasures({ total: 3, success_rate_pct: 100, avg_processing_seconds: 2 }).map((m) => m.key)).toEqual(["total", "rate", "avg"]);
    expect(jobMeasures({ total: 3, success_rate_pct: null, avg_processing_seconds: null }).map((m) => m.key)).toEqual(["total"]);
  });
});

describe("진단 — 백로그는 판정 줄 한 곳이 말하고 그 줄에서 거른 작업 큐로 간다", () => {
  it("대기 · 미해결 실패 줄마다 그 상태로 거른 작업 큐 링크가 선다", async () => {
    withBundle({ jobs_24h: { total: 1, queued: 7, failed_open: 3 } });
    const user = userEvent.setup();
    renderDiagnostics();
    const queued = (await screen.findByText("대기 작업 7건")).closest("li");
    await user.click(within(queued).getByRole("button", { name: "대기 작업 보기" }));
    expect(screen.getByTestId("location-probe")).toHaveTextContent("/jobs?status=queued");
  });

  it("줄이 하나뿐이어도 그 줄에서 간다", async () => {
    withBundle({ jobs_24h: { total: 1, failed_open: 2 } });
    const user = userEvent.setup();
    renderDiagnostics();
    expect(await screen.findByText(/미해결 실패 작업 2건/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "실패 작업 보기" }));
    expect(screen.getByTestId("location-probe")).toHaveTextContent("/jobs?status=failed");
  });

  it("healthVerdict — 백로그 줄만 갈 곳을 든다(대시보드 경보와 같은 곳 · 같은 이름)", () => {
    const hv = healthVerdict({ web: "down" }, {}, {}, null, { queued: 2, failed_open: 1 }, {}, null, null);
    const byMsg = Object.fromEntries(hv.problems.map((p) => [p.msg, p]));
    expect(byMsg["대기 작업 2건"].link).toEqual({ to: "/jobs?status=queued", label: "대기 작업 보기" });
    expect(byMsg["미해결 실패 작업 1건"].link).toEqual({ to: "/jobs?status=failed", label: "실패 작업 보기" });
    expect(byMsg["웹 서버 중단"].link).toBeUndefined();
    expect(JOBS_BACKLOG_LINKS.failed.to).toBe("/jobs?status=failed");
  });
});

/* 판정 요약은 심각도 하나를 대표로 세우지 않는다 — 예전 「주의 5건」 아래에 「위험」 줄 둘이 섞여 제목과 목록이 다른 말을 했다. */
describe("진단 — 판정 요약은 전체 건수이고 두 심각도가 섞이면 갈라 말한다", () => {
  it("위험과 주의가 섞이면 「확인할 항목 N건(위험 D건, 주의 W건)」이다", () => {
    // 위험 둘(웹 서버 중단 · 미해결 실패) + 주의 둘(대기 · 디스크 80%).
    const hv = healthVerdict({ web: "down" }, { used_pct: 81 }, {}, null, { queued: 2, failed_open: 1 }, {}, null, null);
    expect(hv.tone).toBe("danger");
    expect(hv.msg).toBe("확인할 항목 4건(위험 2건, 주의 2건)");
  });

  it("한 심각도뿐이면 괄호를 붙이지 않는다 — 줄마다의 표지가 이미 말한다", () => {
    const hv = healthVerdict({}, { used_pct: 81 }, { used_pct: 82 }, null, { queued: 2 }, {}, null, null);
    expect(hv.tone).toBe("warn");
    expect(hv.msg).toBe("확인할 항목 3건");
    expect(hv.msg).not.toMatch(/^주의/);
  });

  it("화면 머리 상자가 그 요약을 제목으로 쓰고 줄마다 위험 · 주의 표지를 단다", async () => {
    withBundle({ components: { web: "up", worker: "down" }, jobs_24h: { total: 1, queued: 7, failed_open: 3 } });
    renderDiagnostics();
    expect(await screen.findByText("확인할 항목 3건(위험 2건, 주의 1건)")).toBeInTheDocument();
    expect(screen.queryByText(/^주의 \d+건$/)).toBeNull();
  });
});
