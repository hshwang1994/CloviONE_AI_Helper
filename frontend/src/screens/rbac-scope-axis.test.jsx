import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* RBAC 매트릭스 — 역할(role) 축만 있고 범위(scope) 축이 안 보인다.
 *
 * app/core/authz.py 의 rbac_matrix() 는 이미 `scopes`(전체/조직/부서 + 설명)를 함께
 * 돌려준다(SCOPE_LABELS) — "매트릭스가 역할만 보여 주면 '부서 관리자'가 왜 남의 부서를
 * 못 보는지 화면 어디에도 설명이 없다"는 주석이 그 이유를 말한다. 그런데 프런트
 * columnsFrom은 그 필드를 한 번도 읽지 않았다 — 응답에 있어도 화면엔 안 나온다.
 *
 * 이 테스트는 admin 열에 범위 설명(scopes 데이터)이 실제로 붙는지 확인한다. 기존
 * rbac-matrix.test.jsx의 "관리자" 열 이름 단정(정확 일치)은 깨지면 안 되므로, 열
 * 라벨 텍스트 자체는 그대로 두고(접근 가능한 이름 불변) 툴팁으로만 덧붙는지를 본다.
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
  ],
  scopes: [
    { value: "global", label: "전체", help: "조직, 부서 제한 없이 모든 대상을 관리한다." },
    { value: "org", label: "조직", help: "자기 조직(org_id)에 속한 대상만 보이고 관리할 수 있다." },
    { value: "dept", label: "부서", help: "자기 부서와 그 하위 부서에 속한 대상만 보인다." },
  ],
  scoped_role: "admin",
  source: "app/core/authz.py",
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(() => Promise.resolve(BODY));
});

describe("권한 매트릭스 — 범위(scope) 축", () => {
  it("서버가 돌려주는 scopes 데이터가 admin 열에 실제로 붙는다(고정 문구가 아니다)", async () => {
    renderMatrix();
    // 열 이름 자체(접근 가능한 이름)는 기존 회귀 테스트와 마찬가지로 그대로 '관리자' 여야 한다
    // — describeChild:true로 title이 aria-label을 덮어쓰지 않게 했다(그렇지 않으면 스크린
    // 리더가 "관리자" 대신 긴 설명 문장을 열 이름으로 읽어, 표를 훑을 때 오히려 방해가 된다).
    const adminHeader = await screen.findByRole("columnheader", { name: "관리자" });
    // 서버가 실제로 돌려준 부서 범위 설명 문구(app/core/authz.py SCOPE_LABELS)가 그대로
    // 붙어 있다 — 화면이 고정 문자열을 하드코딩했다면 이 값을 바꿔도 따라오지 않는다.
    const titled = adminHeader.querySelector("[title]");
    expect(titled).not.toBeNull();
    expect(titled.getAttribute("title")).toMatch(/자기 부서와 그 하위 부서에 속한 대상만 보인다/);
  });

  it("도움말에 admin 역할이 범위로 추가 제한될 수 있다는 안내가 있다", async () => {
    renderMatrix();
    await screen.findByRole("columnheader", { name: "관리자" });
    expect(screen.getByText(/범위로.*좁혀질 수 있습니다|추가로 좁혀질 수 있습니다/)).toBeInTheDocument();
  });
});
