import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* WF1 단독 결함(admin_policies, Low) — 상시 안내 배너(config.help)는 항상 기본(info) 톤의
 * Callout이었다. DataScreen.jsx의 다른 Callout(capWarning 등)은 이미 tone="warn"을 쓰는데,
 * 화면별로 위험도가 다른 안내(예: 정책의 "발행하면 즉시 실사용된다")를 구별할 방법이 없었다
 * — 능력은 있고 이 배너에는 안 쓰였다. config.helpTone으로 화면별 톤을 지정할 수 있게 한다.
 * Callout은 색만으로 톤을 나르지 않는다(WCAG 1.4.1, kit.jsx의 Callout 주석) — 그 단서는
 * 아이콘의 **접근 이름**이다: "주의"(warn) vs "안내"(기본 info)로 확인한다. 예전에는 그
 * 낱말이 상자의 제목 줄로도 섰는데, 그러면 한 줄짜리 안내의 높이가 두 배가 되고 진짜
 * 제목을 넣을 자리가 사라져서 접근 이름으로 옮겼다 — 계약은 그대로이고 자리만 옮겼다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderScreen(config) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={config} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const BASE_CONFIG = {
  key: "t", area: "테스트", title: "테스트 화면", endpoint: "/api/admin/t",
  columns: [{ key: "name", label: "이름" }],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], total: 0 });
});

describe("config.helpTone — 화면별 상시 배너 톤 (WF1 단독 결함)", () => {
  it("helpTone이 없으면(대다수 화면) 기본 안내 라벨('안내')을 쓴다", async () => {
    renderScreen({ ...BASE_CONFIG, help: "일반 안내 문구" });
    expect(await screen.findByText("일반 안내 문구")).toBeInTheDocument();
    expect(screen.getByLabelText("안내")).toBeInTheDocument();
    expect(screen.queryByLabelText("주의")).not.toBeInTheDocument();
    // 톤 낱말은 화면 글자로 서지 않는다 — 그 자리는 화면이 제목을 쓸 자리다.
    expect(screen.queryByText("안내")).not.toBeInTheDocument();
  });

  it("helpTone: 'warn'이면 배너가 '주의' 아이콘(warning 심각도)으로 뜬다", async () => {
    renderScreen({ ...BASE_CONFIG, help: "파급력이 큰 안내", helpTone: "warn" });
    expect(await screen.findByText("파급력이 큰 안내")).toBeInTheDocument();
    expect(screen.getByLabelText("주의")).toBeInTheDocument();
    expect(screen.queryByLabelText("안내")).not.toBeInTheDocument();
  });

  it("정책(admin_policies) 레지스트리는 실제로 helpTone: 'warn'을 쓴다", () => {
    expect(REGISTRY.policies.helpTone).toBe("warn");
  });

  it("프롬프트(admin_prompts) 레지스트리는 여전히 기본 톤이다(경고 아님)", () => {
    expect(REGISTRY.prompts.helpTone).toBeFalsy();
  });
});
