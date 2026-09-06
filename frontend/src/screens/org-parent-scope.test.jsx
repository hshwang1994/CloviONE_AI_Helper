import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 부서 폼의 **상위 부서 후보는 그 부서가 들어갈 조직의 부서뿐이다**(org-03), 그리고
 * **정지된 조직은 후보 라벨이 그 상태를 말한다**(org-17).
 *
 * 실측(2026-09-06 · 자기 서버, 조직 넷): 「부서 추가」의 상위 후보에 다른 조직의 부서
 * (P11타조직부서)가 그대로 서 있었고, 그것을 고르고 조직을 굿모닝아이텍으로 두면
 * `POST /api/admin/departments` → 422 «알 수 없는 상위 부서입니다» 였다. 서버는 상위 부서가
 * 이 행과 같은 조직일 것을 요구한다(app/org/tree.py::validate_parent · service.py::create_item).
 * 같은 목록에 정지된 조직의 부서(P11정지부서)도, 정지된 조직 자체(P11조직)도 아무 표시 없이
 * 섞여 있었다.
 *
 * 반례를 함께 잰다: 같은 조직의 부서는 그대로 후보이고 고른 값이 그대로 실려 나간다.
 * 후보를 조건에 따라 좁히는 것과, **없는 조합을 권하지 않는 것**은 다른 일이다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({
    data: { role: "system_admin", id: "actor-1", org_id: "org-1", management: { kind: "global" } },
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
    department_count: 2, user_count: 4, created_at: AT },
  { id: "org-2", name: "자회사", slug: "subsidiary", status: "active",
    department_count: 1, user_count: 0, created_at: AT },
  { id: "org-3", name: "묵은회사", slug: "old-co", status: "suspended",
    department_count: 0, user_count: 0, created_at: AT },
];
/* 조직마다 부서가 있어야 「좁혀졌다」를 실제로 잴 수 있다 — 전부 한 조직이면 좁히는 코드가
   없어도 이 시험이 우연히 통과한다. */
const DEPTS = [
  { id: "dep-sales", name: "영업팀", org_id: "org-1", active: true, user_count: 4, created_at: AT },
  { id: "dep-dev", name: "개발팀", org_id: "org-1", active: true, user_count: 3, created_at: AT },
  { id: "dep-sub", name: "자회사기획팀", org_id: "org-2", active: true, user_count: 1, created_at: AT },
];

function mockApi() {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (options && options.method === "POST") return Promise.resolve({ department: { id: "made-1" } });
    if (options && options.method === "PATCH") return Promise.resolve({ ok: true });
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single) {
      return Promise.resolve({ department: {
        id: single[1], name: "영업팀", active: true, parent_id: null, org_id: "org-1",
        org_name: "클로비원", user_count: 4, child_department_count: 0, created_at: AT,
        delete_precheck: { deletable: true, blockers: [], detachables: [], reason: null },
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

/** 열린 대화상자에서 select 를 열고 후보 이름을 읽은 뒤 원래대로 닫는다. */
async function optionNames(dlg, label) {
  await userEvent.click(within(dlg).getByLabelText(label));
  const list = await screen.findByRole("listbox", {}, WAIT);
  const names = within(list).getAllByRole("option").map((o) => o.textContent);
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull(), WAIT);
  return names;
}

async function openCreate() {
  mockApi();
  renderAt();
  await userEvent.click(await screen.findByRole("button", { name: "부서 추가" }, WAIT));
  return screen.findByRole("dialog", {}, WAIT);
}

beforeEach(() => { apiMock.mockReset(); });

describe("부서 추가의 상위 부서 후보", () => {
  it("조직 칸을 비우면 내 조직의 부서만 후보다 — 남의 조직 부서는 없다", async () => {
    const dlg = await openCreate();
    const names = await optionNames(dlg, /상위 부서/);
    expect(names).toEqual(["(최상위)", "영업팀", "개발팀"]);
  });

  it("조직을 바꾸면 후보도 그 조직 것으로 바뀐다(반례: 그 조직 부서는 남는다)", async () => {
    const dlg = await openCreate();
    await userEvent.click(within(dlg).getByLabelText(/^조직/));
    await userEvent.click(await screen.findByRole("option", { name: "자회사" }, WAIT));
    const names = await optionNames(dlg, /상위 부서/);
    expect(names).toEqual(["(최상위)", "자회사기획팀"]);
  });

  it("먼저 고른 상위 부서가 조직을 바꿔 후보 밖이 되면 요청에 안 실린다", async () => {
    const dlg = await openCreate();
    // 내 조직의 부서를 고른다 — 이때는 유효한 조합이다.
    await userEvent.click(within(dlg).getByLabelText(/상위 부서/));
    await userEvent.click(await screen.findByRole("option", { name: "영업팀" }, WAIT));
    // 조직을 자회사로 바꾸면 그 조합은 서버가 422 로 거절하는 조합이 된다.
    await userEvent.click(within(dlg).getByLabelText(/^조직/));
    await userEvent.click(await screen.findByRole("option", { name: "자회사" }, WAIT));

    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/departments" && o && o.method === "POST");
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.parent_id).toBeNull();
      expect(post[1].body.org_id).toBe("org-2");
    }, WAIT);
  });

  it("같은 조직 안에서 고른 상위 부서는 그대로 실려 나간다(반례)", async () => {
    const dlg = await openCreate();
    await userEvent.click(within(dlg).getByLabelText(/상위 부서/));
    await userEvent.click(await screen.findByRole("option", { name: "개발팀" }, WAIT));
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/departments" && o && o.method === "POST");
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.parent_id).toBe("dep-dev");
    }, WAIT);
  });
});

describe("부서 수정의 상위 부서 후보", () => {
  it("이 부서가 속한 조직의 부서만 후보다(자기 자신은 여전히 빠진다)", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const panel = await screen.findByTestId("org-console-panel", {}, WAIT);
    await userEvent.click(await within(panel).findByRole("button", { name: "수정" }, WAIT));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    const names = await optionNames(dlg, /상위 부서/);
    expect(names).toEqual(["(최상위)", "개발팀"]);
  });
});

describe("조직 후보의 라벨", () => {
  it("정지된 조직은 그 상태를 달고 선다 — 활성 조직은 이름 그대로다(org-17)", async () => {
    const dlg = await openCreate();
    const names = await optionNames(dlg, /^조직/);
    expect(names).toEqual(["선택 안 함", "클로비원", "자회사", "묵은회사 (미사용)"]);
  });
});
