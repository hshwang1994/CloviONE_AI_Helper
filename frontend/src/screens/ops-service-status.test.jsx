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

const BASE_DASH = {
  integrations: {}, counts: {}, jobs_24h: {}, recent_critical_audit: [],
  disk: {}, memory: {}, cert_days_remaining: null,
  last_backup_at: "2026-08-01T00:00:00", last_backup_status: "succeeded",
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
    const guidance = await screen.findByText(/일부 서비스가 중단/);
    expect(guidance).toHaveTextContent("clovirone-web-worker");
    expect(guidance).not.toHaveTextContent("clovirone-web-assistant.service");

    const copyBtn = within(guidance).getByRole("button", { name: "복사" });
    await user.click(copyBtn);

    expect(writeTextSpy).toHaveBeenCalledWith("journalctl -u clovirone-web-worker");
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
    expect(screen.queryByText(/일부 서비스가 중단/)).toBeNull();
  });
});

describe("진단 — 백업 실패 표시", () => {
  it("마지막 백업이 실패했으면 배지와 상단 배너 모두 실패를 말한다", async () => {
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
    expect(screen.getByText("실패")).toBeInTheDocument(); // 백업 카드 배지
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
