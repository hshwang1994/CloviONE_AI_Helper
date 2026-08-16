import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0017: 시스템 설정·유지보수·Notion 관리·AI 관리는 화면이 아니라 /settings의 탭이
 * 됐다(SettingsShell.jsx) — 옛 주소 네 개(/system, /maintenance, /notion-console,
 * /llm-console)가 죽은 링크나 대시보드로 튕기지 않고, 정확히 자기 몫의 탭으로 떨어지는가를
 * 지킨다(Handoff 수용 기준: "39개 기존 URL은 새 위치로 리다이렉트해야 한다 — 404도, 뭉뚱그린
 * 대시보드 튕김도 안 된다"). 나머지 35개 URL은 경로 자체가 안 바뀌었으므로(사이드바 그룹만
 * 재편됐다) 여기서 따로 볼 게 없다 — AdminRoutes.jsx의 <Route>가 그대로다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

let currentRole = "system_admin";
vi.mock("./auth.jsx", () => ({
  useAuth: () => ({ data: { role: currentRole, id: "a1" } }),
}));

import AdminRoutes from "./AdminRoutes.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const WAIT = { timeout: 8000 };

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(() => Promise.resolve({}));
  currentRole = "system_admin";
});

function renderRoute(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <AdminRoutes />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("옛 설정류 주소 → /settings 탭 리다이렉트", () => {
  it.each([
    ["/system", "OS와 서비스 동작"],
    ["/notion-console", "연동"],
    ["/llm-console", "AI"],
    ["/maintenance", "시스템 정책"],
  ])("%s 는 대시보드가 아니라 '%s' 탭으로 간다", async (path, tabLabel) => {
    renderRoute(path);
    expect(await screen.findByRole("tab", { name: tabLabel, selected: true }, WAIT)).toBeInTheDocument();
    // 대시보드로 뭉뚱그려 튕기지 않았다는 것도 명시적으로 못박는다(Dashboard.jsx의 h1 제목).
    expect(screen.queryByRole("heading", { name: "대시보드" })).not.toBeInTheDocument();
  });

  it("system_admin이 아니면 /system도 결국 '시스템 정책' 탭(모두가 보는 기본 탭)에 떨어진다", async () => {
    currentRole = "operator";
    renderRoute("/system");
    expect(await screen.findByRole("tab", { name: "시스템 정책", selected: true }, WAIT)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "OS와 서비스 동작" })).not.toBeInTheDocument();
  });
});
