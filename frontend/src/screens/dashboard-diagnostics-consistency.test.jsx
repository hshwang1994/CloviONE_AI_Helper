import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* PA-RC-0028 required_tests (4) — "서비스 분류 어휘가 두 화면에서 같은 소스를 쓴다".
 *
 * /dashboard와 /diagnostics는 같은 8개 서비스(내부 컴포넌트+외부 연동)를 각자 따로 그린다.
 * 예전엔 opsHelpers.js가 COMP_LABELS(컴포넌트 4종)와 SERVICE_LABELS(8종)를 별개 상수로
 * 들고 있어 한쪽만 고치면 두 화면이 말없이 다른 이름을 보여줄 수 있었다 — 이 파일은 그 회귀를
 * "두 화면을 같은 fixture로 각각 렌더해 타일 텍스트를 직접 대조"하는 방식으로 막는다(값이 같다는
 * 것을 증명하지, serviceLabel을 같이 호출한다는 구현 세부사항을 증명하지 않는다 — 화면이 실제로
 * 같은 말을 하는지가 사용자에게 중요한 사실이다). */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { Dashboard } from "./Dashboard.jsx";
import { Diagnostics } from "./Ops.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wrap(children) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>{children}</MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

// 두 화면이 각각 "internal 컴포넌트"와 "external 연동"으로 나누는 것은 이미 의도된 분류다
// (target_design) — 여기서 대조하는 것은 그 분류의 옳고 그름이 아니라, 같은 키가 두 화면에서
// 같은 한국어 이름으로 나오는가다.
const COMPONENTS = { web: "up", worker: "down" };
const INTEGRATIONS = { n8n: { enabled: true, last_health: "up" } };

const BASE = {
  components: COMPONENTS, integrations: INTEGRATIONS,
  counts: {}, jobs_24h: {}, recent_critical_audit: [],
  disk: {}, memory: {}, cert_days_remaining: null,
  last_backup_at: null, last_backup_status: null,
};

beforeEach(() => {
  apiMock.mockReset();
  Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
});

describe("서비스 이름 어휘 일관성 — /dashboard vs /diagnostics (PA-RC-0028)", () => {
  it("같은 컴포넌트/연동 키가 두 화면에서 같은 한국어 이름의 타일로 나온다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/dashboard") return Promise.resolve({ ...BASE });
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const dashboardRender = render(wrap(<Dashboard />));
    await within(dashboardRender.container).findByText("서비스 상태");
    /* 2026-08-19: 상단 경보도 `serviceLabel` 을 쓰게 하면서 같은 이름이 한 화면에 두 번
       나올 수 있게 됐다(경보 + 서비스 타일). 그게 **이 시험이 원하던 상태**다 — 예전에는
       경보만 "워커"라고 짧게 부르고 타일은 "백그라운드 워커"라고 불렀다. 그러니 여기서
       재는 것은 "한 번만 나오는가"가 아니라 "두 화면이 같은 이름을 쓰는가"이므로 첫 번째
       것을 집는다. */
    const first = (t) => within(dashboardRender.container).getAllByText(t)[0];
    const dashboardWeb = first("웹 서버");
    const dashboardWorker = first("백그라운드 워커");
    const dashboardN8n = first("n8n 엔진");
    dashboardRender.unmount();

    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({ generated_at: "2026-08-03T07:00:00", dashboard: { ...BASE }, recent_job_errors: [] });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const diagnosticsRender = render(wrap(<Diagnostics />));
    await within(diagnosticsRender.container).findByText("서비스 상태");
    // 같은 문자열이 두 번째 화면에도 그대로 있어야 한다 — 렌더 자체가 실패하면(다른 이름이면)
    // getByText가 여기서 던진다. 첫 화면에서 읽은 텍스트를 그대로 다시 찾는 것 자체가 대조다.
    for (const el of [dashboardWeb, dashboardWorker, dashboardN8n]) {
      expect(within(diagnosticsRender.container).getAllByText(el.textContent).length).toBeGreaterThan(0);
    }
  });
});
