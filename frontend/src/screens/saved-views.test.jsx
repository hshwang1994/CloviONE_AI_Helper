import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 저장된 뷰 + 주소 복원 (계획서 Phase 6 사용자).
 *
 * 이 두 기능은 같은 뿌리에서 나온다: **지금 보고 있는 뷰가 주소에 실려 있다.**
 * 그래서 여기서 확인하는 것도 둘이다:
 *   1) 주소에 필터가 실려 오면 그대로 복원된다 → 링크 공유가 동작한다.
 *   2) 필터를 바꾸면 주소가 따라 바뀌고, 저장은 그 문자열을 그대로 보낸다 →
 *      저장된 뷰를 부르는 일이 곧 그 링크를 여는 일이 된다.
 *
 * jsdom 의 window.location.hash 를 실제로 읽고 쓴다(MemoryRouter 는 해시를 안 쓰지만,
 * DataScreen 의 뷰 동기화는 HashRouter 규약대로 window.location 을 직접 본다).
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
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const CONFIG = {
  key: "audit",
  area: "운영",
  title: "감사 로그",
  endpoint: "/api/admin/audit",
  columns: [{ key: "action", label: "동작" }],
  filters: [
    { key: "result", type: "select", label: "결과", options: [{ value: "failure", label: "실패" }] },
  ],
};

function renderScreen(config = CONFIG) {
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

function routeApi(overrides = {}) {
  return (path, options) => {
    if (path.startsWith("/api/me/views")) {
      if (options && options.method === "POST") return Promise.resolve({ view: { id: "v-1", ...options.body } });
      if (options && options.method === "DELETE") return Promise.resolve({ ok: true });
      return Promise.resolve({ items: overrides.views || [] });
    }
    return Promise.resolve({ items: [], total: 0 });
  };
}

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "#/audit";
});
afterEach(() => { window.location.hash = ""; });

describe("주소로 뷰 복원", () => {
  it("주소에 실린 필터로 첫 조회를 한다 — 기본값으로 한 번 더 조회하지 않는다", async () => {
    window.location.hash = "#/audit?result=failure";
    apiMock.mockImplementation(routeApi());
    renderScreen();

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/audit?result=failure"));
    // 필터 없는 첫 조회가 섞여 나가면 목록이 두 번 깜빡이고 링크와 다른 화면을 보게 된다.
    const listCalls = apiMock.mock.calls
      .map((c) => c[0])
      .filter((p) => p.startsWith("/api/admin/audit"));
    expect(listCalls).toEqual(["/api/admin/audit?result=failure"]);
  });

  it("필터를 바꾸면 주소가 따라 바뀐다(링크 공유가 공짜로 따라온다)", async () => {
    apiMock.mockImplementation(routeApi());
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("감사 로그");

    await user.click(screen.getByRole("combobox", { name: /결과/ }));
    await user.click(await screen.findByRole("option", { name: "실패" }));

    await waitFor(() => expect(window.location.hash).toBe("#/audit?result=failure"));
  });

  it("필터를 지우면 주소도 깨끗해진다", async () => {
    window.location.hash = "#/audit?result=failure";
    apiMock.mockImplementation(routeApi());
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("감사 로그");

    await user.click(await screen.findByRole("button", { name: "필터 지우기" }));
    await waitFor(() => expect(window.location.hash).toBe("#/audit"));
  });
});

describe("저장된 뷰", () => {
  it("저장 시 지금 주소의 쿼리 문자열을 그대로 보낸다", async () => {
    window.location.hash = "#/audit?result=failure";
    apiMock.mockImplementation(routeApi());
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("감사 로그");

    await user.click(await screen.findByRole("button", { name: /저장된 뷰/ }));
    await user.click(await screen.findByText("지금 필터를 뷰로 저장…"));
    await user.type(screen.getByLabelText("뷰 이름"), "실패만");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith("/api/me/views", {
        method: "POST",
        body: { screen_key: "audit", name: "실패만", query: "result=failure", overwrite: false },
      })
    );
  });

  it("이름이 겹치면(409) 조용히 덮어쓰지 않고 물어본다", async () => {
    apiMock.mockImplementation((path, options) => {
      if (path === "/api/me/views" && options && options.method === "POST") {
        return Promise.reject(Object.assign(new Error("같은 이름의 뷰가 이미 있습니다."), { status: 409 }));
      }
      return routeApi()(path, options);
    });
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("감사 로그");

    await user.click(await screen.findByRole("button", { name: /저장된 뷰/ }));
    await user.click(await screen.findByText("지금 필터를 뷰로 저장…"));
    await user.type(screen.getByLabelText("뷰 이름"), "중복");
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText(/같은 이름의 뷰가 이미 있습니다/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "덮어쓰기" })).toBeInTheDocument();
  });

  it("저장된 뷰를 고르면 그 조건으로 화면이 되돌아간다", async () => {
    apiMock.mockImplementation(routeApi({
      views: [{ id: "v-1", screen_key: "audit", name: "실패만", query: "result=failure", created_at: "", updated_at: "" }],
    }));
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("감사 로그");

    await user.click(await screen.findByRole("button", { name: /저장된 뷰 \(1\)/ }));
    await user.click(await screen.findByText("실패만"));

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/audit?result=failure"));
    await waitFor(() => expect(window.location.hash).toBe("#/audit?result=failure"));
  });

  it("뷰 목록 옆에 실제 조건을 요약해 보여 준다(석 달 뒤에도 무슨 뷰인지 알게)", async () => {
    apiMock.mockImplementation(routeApi({
      views: [{ id: "v-1", screen_key: "audit", name: "실패만", query: "result=failure", created_at: "", updated_at: "" }],
    }));
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("감사 로그");

    await user.click(await screen.findByRole("button", { name: /저장된 뷰 \(1\)/ }));
    expect(await screen.findByText("결과: 실패")).toBeInTheDocument();
  });

  it("저장된 뷰가 없으면 무엇을 하면 되는지 알려 준다", async () => {
    apiMock.mockImplementation(routeApi());
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("감사 로그");

    await user.click(await screen.findByRole("button", { name: /저장된 뷰/ }));
    expect(await screen.findByText(/저장된 뷰가 없습니다/)).toBeInTheDocument();
  });
});
