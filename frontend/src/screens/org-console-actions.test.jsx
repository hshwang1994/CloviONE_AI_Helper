import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 콘솔의 **행동** — 확인 문구와 게이트 (admin-uiux 에서 이관 · 재설계 후 정본).
 *
 * 1) 조직 비활성화 확인 문구는 이 버튼이 실제로 하는 일을 말한다: 몇 명이 **지금 즉시
 *    로그아웃**되고 다시 로그인할 수 없게 되는지, 그리고 되돌릴 수 있다는 사실.
 *    "기존 데이터는 그대로"라고만 적으면 아무 일도 안 일어나는 것처럼 읽힌다.
 * 2) 부서 비활성화도 인원수를 말한다 — 0명과 200명이 같은 경고를 받지 않는다.
 * 3) 사용 중(소속 인원>0)인 부서에는 삭제 버튼 자체가 없다 — 눌러도 항상 409 인 버튼을
 *    그리지 않는다.
 * 4) 상세 판의 primary 는 「수정」 하나다(화면/판당 primary 하나 원칙).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1", management: { kind: "global" } } }),
}));

import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원",
    active: true, user_count: 0, child_count: 2, subtree_user_count: 9, created_at: AT },
  { id: "dep-sales", kind: "department", name: "영업팀", depth: 1, path: "클로비원 › 영업팀",
    org_id: "org-1", active: true, user_count: 4, child_count: 0, subtree_user_count: 4, created_at: AT },
  { id: "dep-empty", kind: "department", name: "빈부서", depth: 1, path: "클로비원 › 빈부서",
    org_id: "org-1", active: true, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
];
const ORGS = [{ id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
  department_count: 2, user_count: 9, created_at: AT }];
const DEPT_ITEMS = {
  "dep-sales": { id: "dep-sales", name: "영업팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 4, child_department_count: 0, created_at: AT },
  "dep-empty": { id: "dep-empty", name: "빈부서", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 0, child_department_count: 0, created_at: AT },
};

function mockApi(overrides) {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (overrides) {
      const hit = overrides(u, options);
      if (hit !== undefined) return hit;
    }
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single && (!options || !options.method)) {
      return Promise.resolve({ department: DEPT_ITEMS[single[1]] || null });
    }
    if (single) return Promise.resolve({ ok: true });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: [] });
    if (u.startsWith("/api/admin/users")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({ items: [] });
  });
}

function renderAt(path) {
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
const panel = () => screen.getByTestId("org-console-panel");

beforeEach(() => { apiMock.mockReset(); });

describe("조직 비활성화", () => {
  it("🔴 확인 문구가 로그아웃 사실과 인원수, 되돌리는 길을 말한다", async () => {
    mockApi();
    renderAt("/organizations");
    const off = await within(await screen.findByTestId("org-console-panel", {}, WAIT))
      .findByRole("button", { name: "비활성화" }, WAIT);
    await userEvent.click(off);

    const text = (await screen.findByText(/즉시 로그아웃/, {}, WAIT)).textContent;
    expect(text).toContain("9명");
    expect(text).toContain("다시 로그인할 수 없게");
    expect(text).toContain("되돌릴 수 있습니다");

    // 확인 대화상자의 확정 버튼도 「비활성화」라 대화상자 안에서 고른다.
    const dialogs = screen.getAllByRole("dialog");
    await userEvent.click(
      within(dialogs[dialogs.length - 1]).getByRole("button", { name: "비활성화" }),
    );
    await waitFor(() => {
      const patch = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/organizations/org-1" && o && o.method === "PATCH");
      expect(patch, "비활성화 요청이 안 나갔다").toBeTruthy();
      expect(patch[1].body.status).toBe("suspended");
    }, WAIT);
  });
});

describe("부서 액션", () => {
  it("비활성화 확인 문구에 인원수가 실린다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const off = await within(await screen.findByTestId("org-console-panel", {}, WAIT))
      .findByRole("button", { name: "비활성화" }, WAIT);
    await userEvent.click(off);
    expect((await screen.findByText(/사용자 4명/, {}, WAIT))).toBeInTheDocument();
  });

  it("🔴 사용 중인 부서에는 삭제 버튼이 없고, 빈 부서에는 있다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    await within(await screen.findByTestId("org-console-panel", {}, WAIT))
      .findByRole("heading", { name: "영업팀" }, WAIT);
    expect(within(panel()).queryByRole("button", { name: "삭제" })).toBeNull();
    // 이유는 버튼이 사라진 자리 대신 삭제 안내가 말한다.
    expect(within(panel()).getByText(/삭제할 수 없습니다/)).toBeInTheDocument();
  });

  it("빈 부서는 삭제할 수 있고, 확인 뒤 DELETE 가 나간다", async () => {
    mockApi();
    renderAt("/departments/dep-empty");
    const del = await within(await screen.findByTestId("org-console-panel", {}, WAIT))
      .findByRole("button", { name: "삭제" }, WAIT);
    await userEvent.click(del);
    expect(await screen.findByText(/되돌릴 수 없습니다/, {}, WAIT)).toBeInTheDocument();
    // 확인 대화상자의 확정 버튼(「삭제」) — 판의 버튼과 이름이 같아 대화상자 안에서 고른다.
    const dialogs = screen.getAllByRole("dialog");
    const confirmDialog = dialogs[dialogs.length - 1];
    await userEvent.click(within(confirmDialog).getByRole("button", { name: "삭제" }));
    await waitFor(() => {
      expect(apiMock.mock.calls.some(([p, o]) =>
        String(p) === "/api/admin/departments/dep-empty" && o && o.method === "DELETE")).toBe(true);
    }, WAIT);
  });

  it("서버가 409 로 거절하면 그 문장이 그대로 보인다", async () => {
    mockApi((u, options) => {
      if (u === "/api/admin/departments/dep-empty" && options && options.method === "DELETE") {
        const err = new Error("이 부서를 참조하는 프로젝트 2건이 있어 지울 수 없습니다.");
        err.status = 409;
        return Promise.reject(err);
      }
      return undefined;
    });
    renderAt("/departments/dep-empty");
    const del = await within(await screen.findByTestId("org-console-panel", {}, WAIT))
      .findByRole("button", { name: "삭제" }, WAIT);
    await userEvent.click(del);
    const dialogs = await screen.findAllByRole("dialog", {}, WAIT);
    await userEvent.click(within(dialogs[dialogs.length - 1]).getByRole("button", { name: "삭제" }));
    expect(await screen.findByText(/참조하는 프로젝트 2건/, {}, WAIT)).toBeInTheDocument();
  });

  it("감사 로그 딥링크가 그 부서를 가리킨다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const link = await within(await screen.findByTestId("org-console-panel", {}, WAIT))
      .findByRole("link", { name: "감사 로그에서 보기" }, WAIT);
    expect(link.getAttribute("href")).toBe("#/audit?object_type=department&object_id=dep-sales");
  });
});
