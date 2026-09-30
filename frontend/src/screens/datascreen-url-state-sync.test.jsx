import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Routes, Route, Link } from "react-router-dom";

/* **주소가 이 화면 뷰의 정본이다** — 주소가 바뀌면 화면도 바뀐다 (audit-03).
 *
 * 지금까지 읽기는 마운트 한 번뿐이고 그 뒤로는 화면 → 주소 한 방향으로만 되썼다. 그래서
 * 사이드바에서 같은 메뉴를 다시 누르면(react-router 가 같은 라우트를 리마운트하지 않는다)
 * **주소만 비고 화면은 앞 조건을 그대로** 들고 있었다 — 실브라우저 실측: 주소 `#/audit`,
 * 화면 「조건 1개에 맞는 결과가 22건입니다.」, 새 요청 0건. 그 상태에서 주소를 복사해 주면 상대는 다른
 * 화면을 보고, 새로고침 한 번이면 조사 중이던 조건이 사라진다.
 *
 * 여기서 고정하는 것: 같은 경로의 조건 없는 주소로 다시 들어오면 조건이 처음 상태로 돌아가고
 * 목록을 다시 받는다. 반례 둘 — 화면 기본값이 있는 화면은 그 기본값으로 돌아가고(빈 조건이
 * 아니다), 조건이 실린 주소로 들어오면 그 조건이 그대로 선다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AUDIT = {
  key: "audit", area: "감사", title: "감사 로그", endpoint: "/api/admin/audit",
  columns: [{ key: "action", label: "동작", identifier: true }],
  filters: [{
    key: "result", label: "결과", type: "select",
    options: [{ value: "success", label: "성공" }, { value: "failure", label: "실패" }],
  }],
};

/* 상태 필터의 **기본값**이 있는 화면(프롬프트·정책이 그렇다). 되돌아가는 자리가 「빈 조건」이
   아니라 「첫 방문과 같은 상태」임을 이 설정으로 가른다. */
const PROMPTS = {
  key: "prompts", area: "AI", title: "프롬프트", endpoint: "/api/admin/prompts",
  columns: [{ key: "name", label: "이름", identifier: true }],
  filters: [{
    key: "status", label: "상태", type: "select", value: "published",
    options: [{ value: "draft", label: "초안" }, { value: "published", label: "발행됨" }],
  }],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const url = String(path);
    if (url.startsWith("/api/admin/audit")) {
      return Promise.resolve({ items: [{ id: "1", action: "user.login" }], total: 1 });
    }
    if (url.startsWith("/api/admin/prompts")) {
      return Promise.resolve({ items: [{ id: "p1", name: "티켓 요약" }], total: 1 });
    }
    return Promise.resolve({ items: [], total: 0 });
  });
});

afterEach(() => { window.location.hash = ""; });

function renderApp(config, path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <HashRouter>
              {/* 사이드바 대역 — 실제 메뉴와 같은 react-router 이동이다. */}
              <Link to={path}>메뉴로 다시 들어가기</Link>
              <Routes>
                <Route path={path} element={<DataScreen config={config} />} />
              </Routes>
            </HashRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

/** 목록 조회만 — 저장된 뷰(/api/me/views) 같은 곁가지는 세지 않는다. */
function listUrls(prefix) {
  return apiMock.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith(prefix));
}

describe("같은 화면으로 다시 들어오기 (audit-03)", () => {
  it("조건 없는 주소로 다시 들어오면 조건이 풀리고 목록을 다시 받는다", async () => {
    window.location.hash = "#/audit";
    const user = userEvent.setup();
    renderApp(AUDIT, "/audit");
    await screen.findByText("user.login");

    await user.click(screen.getByLabelText("결과"));
    await user.click(await screen.findByRole("option", { name: "실패" }));
    await waitFor(() => expect(window.location.hash).toBe("#/audit?result=failure"));
    await waitFor(() => expect(listUrls("/api/admin/audit").some((u) => u.includes("result=failure"))).toBe(true));

    await user.click(screen.getByRole("link", { name: "메뉴로 다시 들어가기" }));

    // 주소가 조건을 잃었으면 화면도 잃어야 한다 — 둘이 다른 말을 하면 안 된다.
    await waitFor(() => expect(window.location.hash).toBe("#/audit"));
    await waitFor(() => expect(screen.getByLabelText("결과")).toHaveTextContent("전체"));
    const after = listUrls("/api/admin/audit");
    expect(after[after.length - 1]).toBe("/api/admin/audit");
  });

  it("반례 — 기본 조건이 있는 화면은 그 기본값으로 돌아간다(빈 조건이 아니다)", async () => {
    window.location.hash = "#/prompts?status=draft";
    const user = userEvent.setup();
    renderApp(PROMPTS, "/prompts");
    await screen.findByText("티켓 요약");
    await waitFor(() => expect(listUrls("/api/admin/prompts").some((u) => u.includes("status=draft"))).toBe(true));

    await user.click(screen.getByRole("link", { name: "메뉴로 다시 들어가기" }));

    await waitFor(() => expect(screen.getByLabelText("상태")).toHaveTextContent("발행됨"));
    await waitFor(() => expect(window.location.hash).toBe("#/prompts?status=published"));
    const after = listUrls("/api/admin/prompts");
    expect(after[after.length - 1]).toBe("/api/admin/prompts?status=published");
  });

  it("반례 — 사람이 고른 조건은 자기 주소 되쓰기에 지워지지 않는다(되돌림 고리가 없다)", async () => {
    window.location.hash = "#/audit";
    const user = userEvent.setup();
    renderApp(AUDIT, "/audit");
    await screen.findByText("user.login");

    await user.click(screen.getByLabelText("결과"));
    await user.click(await screen.findByRole("option", { name: "성공" }));

    await waitFor(() => expect(window.location.hash).toBe("#/audit?result=success"));
    // 되쓰기가 다시 읽기를 깨우면 여기서 조건이 스스로 풀린다 — 그러지 않는지 잠시 지켜본다.
    await new Promise((r) => setTimeout(r, 300));
    expect(window.location.hash).toBe("#/audit?result=success");
    expect(screen.getByLabelText("결과")).toHaveTextContent("성공");
  });
});
