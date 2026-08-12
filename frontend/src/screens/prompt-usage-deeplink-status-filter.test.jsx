import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* "이 프롬프트 버전 보기" 딥링크가 빈 목록으로 가던 문제 (UB-13/RG-08).
 *
 * `#/prompts?name=X`로 가면 `name` 필터만 실리는데, 프롬프트 화면은 `status`를
 * `published`로 기본 스코프한다(`registry/authoring.js`). 예전 `DataScreen.jsx`는
 * 필터를 **키 단위**로 병합해서(주소에 없는 키는 화면 기본값이 채움), 발행 버전이
 * 없는 이름(=이 딥링크가 원래 보여주려는, 가장 유력한 정리 대상)을 클릭하면
 * `name=X&status=published`로 좁혀져 0건이 됐다 — 실제로는 그 이름의 버전들이
 * 있는데 "없는 프롬프트"로 보였다.
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

function renderPrompts() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/me/views")) return Promise.resolve({ items: [] });
    return Promise.resolve({ items: [], total: 0, page: 1, page_size: 500 });
  });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY.prompts} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function promptCalls() {
  return apiMock.mock.calls.map((c) => c[0]).filter((p) => p.startsWith("/api/admin/prompts"));
}

beforeEach(() => { apiMock.mockReset(); });
afterEach(() => { window.location.hash = ""; });

describe("프롬프트 사용 현황의 '버전 보기' 딥링크", () => {
  it("빈 화면으로 들어오면 여전히 기본 status=published로 스코프한다(회귀 방지)", async () => {
    window.location.hash = "#/prompts";
    renderPrompts();
    await waitFor(() => expect(promptCalls().length).toBeGreaterThan(0));
    for (const url of promptCalls()) {
      expect(url).toContain("status=published");
    }
  });

  it("name만 실린 딥링크로 들어오면 status 기본값이 안 붙는다(발행 버전 없는 이름도 나온다)", async () => {
    window.location.hash = "#/prompts?name=" + encodeURIComponent("초안뿐인 프롬프트");
    renderPrompts();
    await waitFor(() => expect(promptCalls().length).toBeGreaterThan(0));
    for (const url of promptCalls()) {
      expect(url).toContain("name=");
      expect(url).not.toContain("status=published");
    }
  });
});
