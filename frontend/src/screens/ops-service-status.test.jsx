import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 진단 화면 — 서비스 중단 상태 표시 + 재시작 안내, 백업 실패 표시, 수동 수집 액션.
 *
 * ops-maintenance.test.jsx/ops-tenant-config.test.jsx는 모든 컴포넌트가 "up"인 정상 경로만
 * 렌더했다 — 실패 상태(서비스 중단, 백업 실패)가 실제로 화면에 다른 톤·다른 배지·다른 안내로
 * 나타나는지는 어느 테스트도 확인하지 않았다. 이 파일은 그 gap을 메운다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { Diagnostics } from "./Ops.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderDiagnostics() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Diagnostics />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/* 백업 시각은 **상대값**이어야 한다. 예전엔 `"2026-08-01T00:00:00"` 이라고 절대 날짜를 박아
 * 두었는데, `opsHelpers.js` 의 판정은 `daysSince(...) > BACKUP_STALE_DAYS(=7)` 라는 **상대**
 * 기준이다. 그래서 이 픽스처는 작성 다음 날부터 조용히 썩었다 — 2026-08-07 에 통과하던
 * '시스템 정상' 단언이 2026-08-08 에 '마지막 백업이 오래됨(7일 전)' 으로 뒤집혀 프런트 스위트가
 * 깨졌고, `final_verify.sh` 가 막혀 배포까지 멈췄다. 시계를 고정(`vi.setSystemTime`)하는 방법도
 * 있지만 이 파일은 `userEvent` 와 `findBy*` 를 쓰므로 가짜 타이머가 오히려 부작용이 크다.
 * **기준일을 지금으로부터 재는 것이 이 픽스처가 원래 뜻하던 바다: "최근에 성공한 백업".** */
const RECENT_BACKUP_AT = new Date(Date.now() - 24 * 3600 * 1000)
  .toISOString().replace(/\.\d+Z$/, "");   // 백엔드와 같은 naive-UTC 표기(CLAUDE.md §2.9)

const BASE_DASH = {
  integrations: {}, counts: {}, jobs_24h: {}, recent_critical_audit: [],
  disk: {}, memory: {}, cert_days_remaining: null,
  last_backup_at: RECENT_BACKUP_AT, last_backup_status: "succeeded",
};

beforeEach(() => {
  apiMock.mockReset();
  // jsdom은 isSecureContext를 기본 제공하지 않는다(copyText()가 navigator.clipboard 경로를 타려면 필요).
  Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
});

describe("진단 — 서비스 중단 표시와 재시작 안내", () => {
  it("워커가 중단되면 상단 배너가 위험 톤으로, 서비스 타일은 '중단' 배지로 보인다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({
          generated_at: "2026-08-03T07:00:00",
          dashboard: { ...BASE_DASH, components: { web: "up", worker: "down", scheduler: "up" } },
          recent_job_errors: [],
        });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    renderDiagnostics();

    // 문제가 하나뿐이면 상단 배너 메시지는 그 문제 자체를 그대로 말한다(healthVerdict).
    expect(await screen.findByText("백그라운드 워커 중단")).toBeInTheDocument();
    // 배지도 같은 사실을 "중단"이라는 같은 한국어로 말한다(Badge의 statusText).
    expect(screen.getByText("중단")).toBeInTheDocument();
  });

  it("중단된 서비스가 있으면 담당 유닛의 journalctl 명령을 안내하고, '복사'를 누르면 클립보드에 복사한다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({
          generated_at: "2026-08-03T07:00:00",
          dashboard: { ...BASE_DASH, components: { web: "up", worker: "down", scheduler: "up" } },
          recent_job_errors: [],
        });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    // userEvent.setup()이 이 순간 navigator.clipboard를 자신의 스텁으로 통째로 교체한다
    // (@testing-library/user-event의 attachClipboardStubToView) — 그래서 스파이는 setup() *이후에*
    // 그 스텁 위에 건다. 미리 만든 mock 객체로 navigator.clipboard를 덮어써 두면 이 시점에 다시 덮여
    // 사라진다(직접 겪은 회귀: writeText가 "spy가 아니다"로 실패).
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText");
    renderDiagnostics();

    // worker만 죽었으므로 worker 전용 유닛만 안내한다(web과 다른 유닛이라 섞으면 엉뚱한 로그를 보게 된다).
    const guidance = await screen.findByText(/일부 서비스가 응답하지/);
    expect(guidance).toHaveTextContent("clovirassist-worker");
    expect(guidance).not.toHaveTextContent("clovirassist-web.service");

    const copyBtn = within(guidance).getByRole("button", { name: "복사" });
    await user.click(copyBtn);

    expect(writeTextSpy).toHaveBeenCalledWith("journalctl -u clovirassist-worker");
    expect(await screen.findByText("명령을 복사했습니다.")).toBeInTheDocument();
  });

  it("모든 서비스가 정상이면 재시작 안내를 그리지 않는다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({
          generated_at: "2026-08-03T07:00:00",
          dashboard: { ...BASE_DASH, components: { web: "up", worker: "up", scheduler: "up" } },
          recent_job_errors: [],
        });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    renderDiagnostics();

    expect(await screen.findByText("서비스 상태")).toBeInTheDocument();
    expect(screen.queryByText(/일부 서비스가 응답하지/)).toBeNull();
  });
});

describe("진단 — 백업 실패 표시", () => {
  // PA-RC-0028: 진단 화면 본문의 '백업' 카드(배지 포함)는 제거됐다 — /dashboard가 이미 같은
  // 사실을 상시 보여주므로 두 화면에 같은 실패를 중복 표시하지 않는다(데이터는 번들에 그대로
  // 남고, 이 화면은 대시보드로 가는 링크만 남긴다). 실패는 이제 상단 healthVerdict 배너
  // 하나로만 말한다 — 예전엔 배지가 더 있어 "실패를 두 번 말한다"가 이 테스트의 요지였다.
  it("마지막 백업이 실패했으면 상단 배너가 실패를 말한다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({
          generated_at: "2026-08-03T07:00:00",
          dashboard: {
            ...BASE_DASH,
            components: { web: "up", worker: "up", scheduler: "up" },
            last_backup_status: "failed",
          },
          recent_job_errors: [],
        });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    renderDiagnostics();

    expect(await screen.findByText("최근 백업 실패")).toBeInTheDocument(); // 상단 배너
    expect(screen.getByRole("button", { name: "대시보드에서 보기 →" })).toBeInTheDocument();
  });
});

// PA-RC-0028 required_tests (3) — Diagnostics.jsx가 '최근 주요 변경'·'백업' 섹션을 렌더하지
// 않는다는 컴포넌트 테스트. 데이터를 일부러 채워서 확인한다 — "목록이 비어서 안 보인다"가 아니라
// "섹션 자체가 없다"를 증명해야, 언젠가 recent_critical_audit/last_backup_at이 다시 채워져도
// 예전 중복 렌더가 조용히 되살아나지 않는다.
describe("진단 — 대시보드와 중복이던 섹션 제거(PA-RC-0028)", () => {
  it("'최근 주요 변경'·'백업' 섹션은 데이터가 있어도 더는 렌더되지 않고 대시보드로 가는 링크만 남는다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({
          generated_at: "2026-08-03T07:00:00",
          dashboard: {
            ...BASE_DASH,
            components: { web: "up", worker: "up", scheduler: "up" },
            recent_critical_audit: [
              { created_at: "2026-08-02T00:00:00", action: "user.role_change", actor: "admin@example.com", object_type: "user", object_id: "u-9" },
            ],
          },
          recent_job_errors: [],
        });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    renderDiagnostics();

    await screen.findByText("서비스 상태");
    expect(screen.queryByText("최근 주요 변경")).toBeNull();
    expect(screen.queryByText("백업")).toBeNull();
    expect(screen.queryByText("백업 관리")).toBeNull(); // 예전 백업 카드의 CTA 버튼
    expect(screen.getByText(/백업 상태와 최근 주요 변경은 대시보드에서/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "대시보드에서 보기 →" })).toBeInTheDocument();
  });
});

describe("진단 — 수동 수집 액션", () => {
  it("'진단 수집'을 누르면 다시 수집하고, 완료되면 성공 토스트를 띄운다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({
          generated_at: "2026-08-03T07:00:00",
          dashboard: { ...BASE_DASH, components: { web: "up", worker: "up", scheduler: "up" } },
          recent_job_errors: [],
        });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderDiagnostics();

    await screen.findByText("시스템 정상, 지금 확인이 필요한 항목이 없습니다.");
    const before = apiMock.mock.calls.filter(([p]) => p === "/api/admin/diagnostics/bundle").length;

    await user.click(screen.getByRole("button", { name: "진단 수집" }));

    expect(await screen.findByText("진단을 수집했습니다.")).toBeInTheDocument();
    const after = apiMock.mock.calls.filter(([p]) => p === "/api/admin/diagnostics/bundle").length;
    expect(after).toBe(before + 1); // 자동 최초 수집(1) + 수동 재수집(1개 더)
  });
});
