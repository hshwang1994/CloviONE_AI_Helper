import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* **자기 조직 비활성화는 시스템 관리자만 할 수 있다**(org-09).
 *
 * 실측(2026-09-06 · 자기 서버, park.minjun = 전역 admin): 조직 상세 판의 「비활성화」가
 * 그대로 서 있고, 누르면 «소속 사용자 15명이 지금 즉시 로그아웃되고 다시 로그인할 수 없게
 * 됩니다» 라는 확인 창이 떴다. 확인을 누른 뒤에야
 * `PATCH /api/admin/organizations/{id} {status:"suspended"}` → 403 «자기 조직은 시스템
 * 관리자만 정지할 수 있습니다» 가 돌아왔다. 조직 상태는 그대로 active 였다.
 *
 * 되돌릴 수 없는 결과를 예고하는 확인 창은 **실제로 일어날 수 있는 일**에만 떠야 한다.
 * 서버 판정(app/org/service.py::ensure_may_suspend_org)은 역할과 조직 id 둘만 보는 조건이라
 * 화면이 그대로 재현할 수 있다 — 같은 콘솔이 「조직 추가」에 대해서는 이미 그렇게 한다.
 *
 * 반례를 둘 둔다: 시스템 관리자는 자기 조직도 비활성화할 수 있고, 전역 admin 도 **남의**
 * 조직은 비활성화할 수 있다(그 요청은 실측에서 200 이었다). 하나라도 함께 감추면 이 수정은
 * 결함을 다른 결함으로 바꾸는 것이 된다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
const actor = vi.hoisted(() => ({ role: "admin", org_id: "org-1" }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({
    data: { id: "actor-1", role: actor.role, org_id: actor.org_id, management: { kind: "global" } },
  }),
}));

import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원",
    active: true, user_count: 2, child_count: 0, subtree_user_count: 15, created_at: AT },
  { id: "org-2", kind: "organization", name: "자회사", depth: 0, path: "자회사",
    active: true, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
];
const ORGS = [
  { id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
    department_count: 0, user_count: 15, created_at: AT },
  { id: "org-2", name: "자회사", slug: "subsidiary", status: "active",
    department_count: 0, user_count: 3, created_at: AT },
  { id: "org-3", name: "묵은회사", slug: "old-co", status: "suspended",
    department_count: 0, user_count: 0, created_at: AT },
];

function mockApi() {
  apiMock.mockImplementation((url) => {
    const u = String(url);
    if (u.startsWith("/api/admin/departments/tree")) {
      return Promise.resolve({ items: TREE.concat([
        { id: "org-3", kind: "organization", name: "묵은회사", depth: 0, path: "묵은회사",
          active: false, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
      ]) });
    }
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: [] });
    if (u.startsWith("/api/admin/users")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({ items: [] });
  });
}

function renderOrg(orgId) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/organizations?org=" + orgId]}>
          <Routes><Route path="/organizations" element={<OrgConsole />} /></Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });

async function openOrg(orgId, name) {
  mockApi();
  renderOrg(orgId);
  await within(await screen.findByTestId("org-console-panel", {}, WAIT))
    .findByRole("heading", { name }, WAIT);
  return screen.getByTestId("org-console-panel");
}

beforeEach(() => {
  apiMock.mockReset();
  actor.role = "admin";
  actor.org_id = "org-1";
});

describe("자기 조직 비활성화", () => {
  it("전역 admin 의 자기 조직에는 단추가 없고, 판이 이유를 말한다", async () => {
    const panel = await openOrg("org-1", "클로비원");
    expect(within(panel).queryByRole("button", { name: "비활성화" })).toBeNull();
    expect(within(panel).getByText(/자기 조직 비활성화는 시스템 관리자만 할 수 있습니다\./))
      .toBeInTheDocument();
    // 남는 것은 여전히 있다 — 이름 수정은 이 게이트와 무관하다.
    expect(within(panel).getByRole("button", { name: "수정" })).toBeInTheDocument();
  });

  it("시스템 관리자는 자기 조직도 비활성화할 수 있다(반례)", async () => {
    actor.role = "system_admin";
    const panel = await openOrg("org-1", "클로비원");
    expect(within(panel).getByRole("button", { name: "비활성화" })).toBeInTheDocument();
    expect(within(panel).queryByText(/자기 조직 비활성화는/)).toBeNull();
  });

  it("전역 admin 도 남의 조직은 비활성화할 수 있다(반례 — 서버가 200 을 준다)", async () => {
    const panel = await openOrg("org-2", "자회사");
    expect(within(panel).getByRole("button", { name: "비활성화" })).toBeInTheDocument();
    expect(within(panel).queryByText(/자기 조직 비활성화는/)).toBeNull();
  });

  it("이미 정지된 조직의 「활성화」는 그대로 있다 — 푸는 것은 막히지 않는다", async () => {
    actor.org_id = "org-3";
    const panel = await openOrg("org-3", "묵은회사");
    expect(within(panel).getByRole("button", { name: "활성화" })).toBeInTheDocument();
    expect(within(panel).queryByText(/자기 조직 비활성화는/)).toBeNull();
  });
});
