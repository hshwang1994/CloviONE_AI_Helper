import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 진단 화면의 '설치처 설정' 섹션.
 *
 * 왜 이 테스트가 있는가: 예전엔 노션 DB id 와 이메일 도메인의 기본값이 개발 워크스페이스를
 * 가리켜서, 다른 고객사에 설치해도 아무 설정 없이 '되는 것처럼' 보였다. 기본값을 비운 뒤에도
 * 화면이 그냥 빈 목록을 보여 주면 "설정을 안 했다"와 "결과가 없다"가 구별되지 않는다.
 * 그 구분이 화면에 실제로 **글자로** 나타나는지 못 박는다.
 *
 * 값이 달라지는 표본을 쓴다: 채운 항목과 안 채운 항목을 한 응답에 섞어, 화면이 상수를
 * 그리는 것이 아니라 응답을 읽는다는 것을 보인다.
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

const BASE_BUNDLE = {
  generated_at: "2026-08-06T00:00:00",
  dashboard: {
    components: { web: "up", worker: "up", scheduler: "up" },
    integrations: {},
    counts: {},
    jobs_24h: {},
    recent_critical_audit: [],
    disk: {},
    memory: {},
  },
  settings: {},
  recent_job_errors: [],
};

function bundleWith(tenantConfig) {
  return { ...BASE_BUNDLE, tenant_config: tenantConfig };
}

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
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("진단 화면의 설치처 설정", () => {
  it("안 채운 항목을 '설정 안 됨'으로 구분해 말하고, 무슨 일이 벌어지는지 함께 보여준다", async () => {
    apiMock.mockResolvedValue(bundleWith({
      configured: false,
      unset_count: 1,
      items: [
        { key: "notion_tasks_database_id", label: "노션 작업 데이터베이스", env_var: "NOTION_TASKS_DATABASE_ID", source: "env", state: "set", when_unset: "티켓 목록이 채워지지 않습니다." },
        { key: "notion_documents_database_id", label: "노션 문서 데이터베이스", env_var: "NOTION_DOCUMENTS_DATABASE_ID", source: "env", state: "unset", when_unset: "문서 목록이 채워지지 않습니다." },
      ],
    }));
    renderDiagnostics();

    // 안 채운 것이 몇 개인지 상단에서 먼저 말한다.
    expect(await screen.findByText(/아직 설정하지 않은 항목이 1개 있습니다/)).toBeInTheDocument();
    // 화면 맨 아래 '원본 자료'가 번들 JSON을 통째로 인쇄하므로, 같은 문자열이 거기에도 있다.
    // 섹션 안으로 범위를 좁히지 않으면 이 테스트는 JSON 덤프를 보고 통과해 버린다.
    const section = within(screen.getByText("설치처 설정").closest("section"));
    // 항목별로 채웠는지 아닌지가 글자로 남는다(색이나 아이콘만으로 구분하지 않는다).
    expect(section.getByText("설정됨")).toBeInTheDocument();
    expect(section.getByText("설정 안 됨")).toBeInTheDocument();
    // 안 채운 항목만 결과와 고칠 자리(환경 변수 이름)를 덧붙인다.
    expect(section.getByText(/문서 목록이 채워지지 않습니다\..*NOTION_DOCUMENTS_DATABASE_ID/)).toBeInTheDocument();
    // 채운 항목의 설명까지 달면 경고가 묻힌다.
    expect(section.queryByText(/티켓 목록이 채워지지 않습니다/)).toBeNull();
  });

  it("모두 채웠으면 경고 대신 채웠다고 말한다", async () => {
    apiMock.mockResolvedValue(bundleWith({
      configured: true,
      unset_count: 0,
      items: [
        { key: "notion_tasks_database_id", label: "노션 작업 데이터베이스", env_var: "NOTION_TASKS_DATABASE_ID", source: "env", state: "set", when_unset: "티켓 목록이 채워지지 않습니다." },
      ],
    }));
    renderDiagnostics();

    expect(await screen.findByText(/설치처 고유 설정을 모두 채웠습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/아직 설정하지 않은 항목/)).toBeNull();
  });

  it("서버가 이 정보를 안 주면 섹션을 그리지 않는다", async () => {
    // 없는 것을 있는 척 그리지 않는다. '0개 미설정'으로 보이면 확인했다는 거짓 신호가 된다.
    apiMock.mockResolvedValue({ ...BASE_BUNDLE });
    renderDiagnostics();

    expect(await screen.findByText("외부 연동")).toBeInTheDocument();
    expect(screen.queryByText("설치처 설정")).toBeNull();
  });
});
