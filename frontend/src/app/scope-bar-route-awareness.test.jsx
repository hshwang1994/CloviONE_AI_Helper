/* 스코프 바 — 범위가 실제로 걸리는 화면에서만 "이 범위 밖은 안 보인다"고 말한다.
 *
 * 예전에는 라우트를 안 가리고 모든 화면에 그 문장을 띄웠다. 그런데 게시판·놀이·알림은
 * 부서 범위를 안 건다(`app/board/repository.py` 가 명시) - 부서가 배정된 사용자가
 * `/board` 를 열면 그 자리에서 거짓말이 됐다. 배지(관리 범위: OO팀) 자체는 로그인 사실이라
 * 어느 화면에서나 유효해 계속 뜨지만, 뒤의 캐비어트 문장은 범위가 실제로 걸리는 화면
 * (navConfig.js::SCOPE_ENFORCED_PATHS)에서만 떠야 한다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));

import { AuthProvider } from "./auth.jsx";
import { ScopeBar } from "./ScopeBar.jsx";

const DEPT_ADMIN = {
  user: {
    id: "u1", email: "a@b.c", display_name: "관리자", role: "admin",
    admin_scope: "dept", scope_dept_name: "브로드컴사업본부",
  },
  features: {}, branding: {}, csrf_token: "t",
};

function renderAt(pathname) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <MemoryRouter initialEntries={[pathname]}>
          <ScopeBar />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

describe("ScopeBar 라우트 인지", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue(DEPT_ADMIN);
  });

  it("범위가 실제로 걸리는 화면(/team-docs)에서는 캐비어트 문장이 뜬다", async () => {
    renderAt("/team-docs");
    await waitFor(() => expect(screen.getByText("브로드컴사업본부")).toBeTruthy());
    expect(screen.queryByText("이 범위 밖의 항목은 목록에 나오지 않습니다.")).toBeTruthy();
  });

  it("범위를 안 거는 화면(/board)에서는 캐비어트 문장이 없다 — 배지는 그대로 뜬다", async () => {
    renderAt("/board");
    await waitFor(() => expect(screen.getByText("브로드컴사업본부")).toBeTruthy());
    expect(screen.queryByText("이 범위 밖의 항목은 목록에 나오지 않습니다.")).toBeNull();
  });
});
