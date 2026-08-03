import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 권한 매트릭스 화면 — **열이 서버 응답에서 나온다** (PLAN Phase 6).
 *
 * 요구는 "표의 출처는 app/core/authz.py 하나여야 한다"였다. 화면이 역할 배열을 한 벌 더 들면
 * 백엔드에서 규칙을 고쳐도 표는 옛 열을 계속 보여 주고, 그때 사람은 화면을 믿는다.
 *
 * 그래서 여기서는 **서버가 새 역할을 하나 더 돌려주면 열이 저절로 하나 는다**를 못박는다.
 * 화면에 역할이 적혀 있으면 이 테스트는 통과할 수 없다(모르는 역할의 열이 안 생긴다).
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

function renderMatrix() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY.rbac} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const BODY = {
  roles: [
    { value: "user", label: "일반 사용자" },
    { value: "admin", label: "관리자" },
  ],
  items: [
    { id: "console.read", capability: "관리 콘솔 조회", area: "콘솔", note: "", allowed: ["admin"] },
    { id: "console.write", capability: "설정 변경", area: "콘솔", note: "", allowed: ["admin"] },
  ],
  scopes: [],
  source: "app/core/authz.py",
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(() => Promise.resolve(BODY));
});

describe("권한 매트릭스", () => {
  it("역할 열을 서버 응답에서 만든다", async () => {
    renderMatrix();
    expect(await screen.findByRole("columnheader", { name: "일반 사용자" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "관리자" })).toBeInTheDocument();
    expect(screen.getByText("관리 콘솔 조회")).toBeInTheDocument();
  });

  it("서버가 역할을 하나 더 주면 열이 저절로 는다(화면에 역할 목록이 없다는 증거)", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      ...BODY,
      roles: [...BODY.roles, { value: "future_role", label: "새로 생긴 역할" }],
      items: [{ id: "x", capability: "새 권한", area: "콘솔", note: "", allowed: ["future_role"] }],
    }));
    renderMatrix();
    // 화면이 자기 역할 표를 들고 있었다면 이 열은 절대 생기지 않는다.
    expect(await screen.findByRole("columnheader", { name: "새로 생긴 역할" })).toBeInTheDocument();
    expect(screen.getAllByText("허용").length).toBe(1);
  });

  it("허용되지 않은 칸은 빈칸이 아니라 '허용 안 됨'으로 읽힌다", async () => {
    renderMatrix();
    // 색·기호만으로 구분하면 스크린리더 사용자에게는 아무 정보가 없다.
    expect((await screen.findAllByLabelText("허용 안 됨")).length).toBe(2);
  });
});
