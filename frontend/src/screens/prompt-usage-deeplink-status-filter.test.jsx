import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* "이 프롬프트 버전 보기" 딥링크가 빈 목록으로 가던 문제 (UB-13/RG-08).
 *
 * qa-contract-change: 프롬프트 화면이 「발행됨」을 기본으로 스코프하지 않는다(D-518). 목록 첫머리가 사용처마다 기본 제공 지시문이라 그 기본값이 그 행들을 가렸다. 그래서 「빈 화면은 status=published 로 스코프한다」는 단언이 「빈 화면은 상태 조건을 싣지 않는다」로 바뀌었고, 이름 딥링크의 계약(이름만 싣는다)은 그대로다.
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
  /* 🔴 **목록 호출만** 고른다. 이 화면은 이름 후보를 별도 질의로 받는다
     (`/api/admin/prompts/slots` — 조건과 무관한 전량이라야 후보가 안 좁혀진다).
     접두사만 보면 그 호출이 마지막이 되어, 목록 조건을 재려던 단언이 엉뚱한 주소를 본다. */
  return apiMock.mock.calls
    .map((c) => c[0])
    .filter((p) => p.startsWith("/api/admin/prompts") && !p.includes("/usage/stats") && !p.includes("/slots"));
}

beforeEach(() => { apiMock.mockReset(); });
afterEach(() => { window.location.hash = ""; });

describe("프롬프트 사용 현황의 '버전 보기' 딥링크", () => {
  it("빈 화면으로 들어오면 상태 조건을 싣지 않는다(기본 제공 행이 보여야 한다)", async () => {
    window.location.hash = "#/prompts";
    renderPrompts();
    await waitFor(() => expect(promptCalls().length).toBeGreaterThan(0));
    for (const url of promptCalls()) {
      expect(url).not.toContain("status=");
    }
  });

  it("사용 통계의 딥링크(?id=)는 그 지시문의 상세를 곧바로 열고 목록은 좁히지 않는다", async () => {
    // 사용 통계는 이제 이름이 아니라 「지금 쓰는 지시문」의 id 로 건너온다(D-518) - 기본 제공 행도 같은 문이다.
    window.location.hash = "#/prompts?id=" + encodeURIComponent("builtin:answer");
    renderPrompts();
    await waitFor(() => expect(promptCalls()).toContain("/api/admin/prompts/builtin:answer"));
    for (const url of promptCalls().filter((u) => u !== "/api/admin/prompts/builtin:answer")) {
      expect(url).not.toContain("id=");
      expect(url).not.toContain("status=published");
    }
  });
});
