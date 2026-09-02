import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 콘솔의 폼 모달 — 만든 값이 그대로 실려 나가고, 수정은 바뀐 것만 보낸다.
 *
 * 1) 조직 추가는 **전역 관리자만** 본다(서버가 403 으로 막는 것과 같은 선 — 감춤은 안내다).
 * 2) 부서 추가의 상위 후보는 조건 무관 전량이고, 비우면 최상위(null)로 나간다.
 * 3) 수정은 diff 만 PATCH 한다 — 무변경 저장은 요청 없이 「변경된 내용이 없습니다.」
 * 4) 부서 수정의 상위 후보에서 자기 자신은 빠진다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
const authState = vi.hoisted(() => ({ kind: "global" }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({
    data: { role: "system_admin", id: "actor-1", management: { kind: authState.kind } },
  }),
}));

import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원",
    active: true, user_count: 0, child_count: 1, subtree_user_count: 4, created_at: AT },
  { id: "dep-sales", kind: "department", name: "영업팀", depth: 1, path: "클로비원 › 영업팀",
    org_id: "org-1", active: true, user_count: 4, child_count: 0, subtree_user_count: 4, created_at: AT },
];
const ORGS = [
  { id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
    department_count: 1, user_count: 4, created_at: AT },
  { id: "org-2", name: "자회사", slug: "subsidiary", status: "active",
    department_count: 0, user_count: 0, created_at: AT },
];
const DEPTS = [
  { id: "dep-sales", name: "영업팀", org_id: "org-1", active: true, user_count: 4, created_at: AT },
  { id: "dep-dev", name: "개발팀", org_id: "org-1", active: true, user_count: 3, created_at: AT },
];

function mockApi() {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (options && options.method === "POST") return Promise.resolve({ id: "made-1" });
    if (options && options.method === "PATCH") return Promise.resolve({ ok: true });
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single) {
      return Promise.resolve({ department: {
        id: single[1], name: "영업팀", active: true, parent_id: null,
        org_id: "org-1", org_name: "클로비원", user_count: 4, child_department_count: 0,
        created_at: AT,
      } });
    }
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: DEPTS });
    if (u.startsWith("/api/admin/users")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({ items: [] });
  });
}

function renderAt(path = "/organizations") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/organizations" element={<OrgConsole />} />
            <Route path="/departments/:id" element={<OrgConsole />} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });

beforeEach(() => { apiMock.mockReset(); authState.kind = "global"; });

describe("조직 추가", () => {
  it("전역 관리자에게만 입구가 보이고, 이름과 식별자가 그대로 실려 나간다", async () => {
    mockApi();
    renderAt();
    await userEvent.click(await screen.findByRole("button", { name: "조직 추가" }, WAIT));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    await userEvent.type(within(dlg).getByLabelText(/조직 이름/), "새회사");
    await userEvent.type(within(dlg).getByLabelText(/식별자/), "new-co");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/organizations" && o && o.method === "POST");
      expect(post, "조직 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body).toEqual({ name: "새회사", slug: "new-co" });
    }, WAIT);
  });

  it("부서 범위 관리자에게는 입구가 없다(서버 403 과 같은 선의 안내)", async () => {
    authState.kind = "dept";
    mockApi();
    renderAt();
    await screen.findByTestId("org-console-tree", {}, WAIT);
    expect(screen.queryByRole("button", { name: "조직 추가" })).toBeNull();
    expect(screen.getByRole("button", { name: "부서 추가" })).toBeInTheDocument();
  });
});

describe("부서 추가", () => {
  it("상위 후보는 전량이고, 비우면 최상위(null)로 나간다 — 조직 칸은 조직이 둘일 때 선다", async () => {
    mockApi();
    renderAt();
    await userEvent.click(await screen.findByRole("button", { name: "부서 추가" }, WAIT));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    // 후보 전량 — 지금 화면 조건과 무관하게 두 부서가 다 선다.
    await userEvent.click(within(dlg).getByLabelText(/상위 부서/));
    expect(await screen.findByRole("option", { name: "영업팀" }, WAIT)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "개발팀" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: "(최상위)" }));
    // 전역 관리자 + 조직 둘 — 조직 칸이 선다.
    expect(within(dlg).getByLabelText(/조직/)).toBeInTheDocument();

    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/departments" && o && o.method === "POST");
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.name).toBe("품질팀");
      expect(post[1].body.parent_id ?? null).toBeNull();
    }, WAIT);
  });
});

describe("수정은 바뀐 것만 보낸다(diff)", () => {
  it("무변경 저장은 요청 없이 「변경된 내용이 없습니다.」", async () => {
    mockApi();
    renderAt();
    const panel = await screen.findByTestId("org-console-panel", {}, WAIT);
    await userEvent.click(await within(panel).findByRole("button", { name: "수정" }, WAIT));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    await userEvent.click(within(dlg).getByRole("button", { name: "저장" }));
    expect(await screen.findByText("변경된 내용이 없습니다.", {}, WAIT)).toBeInTheDocument();
    expect(apiMock.mock.calls.some(([, o]) => o && o.method === "PATCH")).toBe(false);
  });

  it("조직 이름을 바꾸면 그 필드만 PATCH 로 나간다", async () => {
    mockApi();
    renderAt();
    const panel = await screen.findByTestId("org-console-panel", {}, WAIT);
    await userEvent.click(await within(panel).findByRole("button", { name: "수정" }, WAIT));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    const box = within(dlg).getByLabelText(/조직 이름/);
    await userEvent.clear(box);
    await userEvent.type(box, "클로비원 주식회사");
    await userEvent.click(within(dlg).getByRole("button", { name: "저장" }));
    await waitFor(() => {
      const patch = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/organizations/org-1" && o && o.method === "PATCH");
      expect(patch, "수정 요청이 안 나갔다").toBeTruthy();
      expect(patch[1].body).toEqual({ name: "클로비원 주식회사" });
    }, WAIT);
  });

  it("부서 수정의 상위 후보에서 자기 자신은 빠진다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const panel = await screen.findByTestId("org-console-panel", {}, WAIT);
    await userEvent.click(await within(panel).findByRole("button", { name: "수정" }, WAIT));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    await userEvent.click(within(dlg).getByLabelText(/상위 부서/));
    expect(await screen.findByRole("option", { name: "개발팀" }, WAIT)).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "영업팀" })).toBeNull();
  });
});
