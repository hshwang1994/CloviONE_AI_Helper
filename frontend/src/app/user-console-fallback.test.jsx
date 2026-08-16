import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0024 acceptance_criteria (4)/(4-b) — 일반 사용자가 관리자 전용 주소로 들어오면
 * /me로 조용히 튕기지 않는다.
 *
 * App.jsx는 role==="user"면 AdminRoutes를 아예 마운트하지 않는다(App.jsx:82의
 * useUserConsole = isUser || userSeg — isUser 하나만으로 이미 true) — 그래서 /rbac 같은
 * 관리자 주소로 들어온 user 역할의 요청은 항상 이 UserRoutes의 catch-all로 떨어진다.
 * 그 catch-all이 예전엔 <Navigate to="/me" replace />였다 — 무슨 일이 있었는지 설명이
 * 전혀 없었다(Handoff PA-F-072).
 *
 * 이제 두 경우를 가른다: navConfig.js의 관리자 NAV에 있는 주소(존재는 하지만 이 역할이
 * 못 쓰는 화면)면 "권한이 없습니다", 정말 모르는 주소(오타 등)면 "찾을 수 없습니다".
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import UserRoutes from "./UserRoutes.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockResolvedValue({ items: [], total: 0 });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <UserRoutes />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("사용자 콘솔 — 모르는 경로 (PA-RC-0024)", () => {
  it("관리자 전용 주소(/rbac)는 '권한이 없습니다'를 보여준다(홈으로 조용히 안 튕김)", async () => {
    renderAt("/rbac");
    expect(await screen.findByText("권한이 없습니다")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "오늘" })).not.toBeInTheDocument();
  });

  it("관리자 전용 주소(/users, /backup, /impersonation)도 같은 안내를 보여준다", async () => {
    for (const path of ["/users", "/backup", "/impersonation"]) {
      const { unmount } = renderAt(path);
      expect(await screen.findByText("권한이 없습니다")).toBeInTheDocument();
      unmount();
    }
  });

  it("정말 모르는 주소(오타)는 '찾을 수 없습니다'를 보여준다", async () => {
    renderAt("/totally-made-up-path-xyz");
    expect(await screen.findByText("찾을 수 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("권한이 없습니다")).not.toBeInTheDocument();
  });
});
