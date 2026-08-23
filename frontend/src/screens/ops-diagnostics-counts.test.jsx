/* qa-contract-change: 진단 화면의 «현재 리소스» 타일 셋 중 둘(활성 워크플로·추가된 러너)이 S11 로 사라졌다. 남은 하나(활성 스케줄)는 숫자뿐 아니라 **라벨까지** 단언하도록 바꿔, 줄어든 개수만큼 남은 것을 더 세게 못 박았다. */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

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
  integrations: {}, jobs_24h: {}, recent_critical_audit: [],
  disk: {}, memory: {}, cert_days_remaining: null,
  last_backup_at: "2026-08-01T00:00:00", last_backup_status: "succeeded",
  components: { web: "up", worker: "up", scheduler: "up" },
};

beforeEach(() => {
  apiMock.mockReset();
  Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
});

describe("진단 — 현재 리소스(counts) 섹션", () => {
  it("counts가 채워져 있으면 크래시하지 않고 인벤토리 숫자를 보여준다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({
          generated_at: "2026-08-03T07:00:00",
          dashboard: { ...BASE_DASH, counts: { active_schedules: 5 } },
          recent_job_errors: [],
        });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    renderDiagnostics();

    expect(await screen.findByText("현재 리소스")).toBeInTheDocument();
    // S11 이 워크플로·러너 타일을 걷어내 활성 스케줄 하나가 남았다.
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("활성 스케줄")).toBeInTheDocument();
  });
});
