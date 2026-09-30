import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 조직 관리 개선(계획 3.6 · D-510)으로 고른 대상의 「더 보기」와 주 동작(부서 추가 · 하위 부서 추가)이 상세 판 머리에서 페이지 머리로 옮겨 갔다(판 안의 30px 주 동작이 머리의 34px 보조 단추보다 작아 위계가 거꾸로 읽혔다). 판 머리에는 「수정」 하나가 남는다 — 판 안에서 단추를 찾던 단언을 페이지 머리(`.k-page-actions`)로 옮겼다.
 *
 * qa-contract-change: 조직 관리 IA 재설계(P6)로 부서 삭제가 판 머리 단추에서 「더 보기」 메뉴 항목으로 옮겨 갔고, 막힌 이유 문장 옆에 막는 것(소속 사용자 · 보관된 계정)으로 가는 링크가 붙었다 — 단추 단언을 메뉴 항목 단언으로 옮기고 링크 주소 단언을 더했다. 서버 이유 문장은 한 글자도 바뀌지 않는다.
 *
 * 부서 상세의 **삭제 안내와 확인 문구가 서버 판정과 같은 말을 하는가**(org-02 · xc-01 · xc-04).
 *
 * 실측(2026-09-06 · 자기 서버): 하위 부서 하나를 가진 부서의 상세 판이 「삭제하면 하위 부서
 * 1개가 최상위 부서로 올라갑니다」라고 적고 삭제 단추를 세웠다. 확인 창은 「되돌릴 수
 * 없습니다」를 붙여 같은 약속을 되풀이했고, 실제 응답은
 * `DELETE /api/admin/departments/{id}` → 409 «이 부서에 하위 부서 1건이(가) 연결되어 있어
 * 삭제할 수 없습니다» 였다. 승격은 FK 가 `SET NULL` 이던 시절의 사실이고, 지금 서버는
 * 하위 부서를 차단 사유로 센다 — 화면이 서버와 **정반대**를 약속하고 있었다.
 *
 * 그래서 여기서 지키는 성질은 「화면이 스스로 세지 않는다」다. 판정도 문장도 상세 응답의
 * `delete_precheck` 에서 오고(app/org/service.py), 화면은 그것을 그리기만 한다. 표본은
 * 서버가 실제로 싣는 모양 그대로다. 막는 갈래 중 이 콘솔에 **갈 곳이 있는 것**(소속 사용자)만 링크를 단다.
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
    active: true, user_count: 0, child_count: 5, subtree_user_count: 3, created_at: AT },
  { id: "dep-parent", kind: "department", name: "본부", depth: 1, path: "클로비원 › 본부",
    org_id: "org-1", active: true, user_count: 0, child_count: 1, subtree_user_count: 0, created_at: AT },
  { id: "dep-free", kind: "department", name: "빈부서", depth: 1, path: "클로비원 › 빈부서",
    org_id: "org-1", active: true, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
  { id: "dep-rooms", kind: "department", name: "방있는부서", depth: 1, path: "클로비원 › 방있는부서",
    org_id: "org-1", active: true, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
  { id: "dep-archived", kind: "department", name: "보관프로젝트부서", depth: 1,
    path: "클로비원 › 보관프로젝트부서", org_id: "org-1", active: true, user_count: 0,
    child_count: 0, subtree_user_count: 0, created_at: AT },
  { id: "dep-people", kind: "department", name: "사람있는부서", depth: 1, path: "클로비원 › 사람있는부서",
    org_id: "org-1", active: true, user_count: 3, child_count: 0, subtree_user_count: 3, created_at: AT },
];

const ORGS = [{ id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
  department_count: 5, user_count: 3, created_at: AT }];

const base = (id, name, extra) => ({
  id, name, active: true, parent_id: null, org_id: "org-1", org_name: "클로비원",
  user_count: 0, created_at: AT, ...extra,
});

/* 서버가 실제로 내는 다섯 가지 답. 문장은 `app/org/service.py::_blocked_message` 와
   `detached_message` 가 만드는 그대로다 — 409 와 같은 함수라 눌러 보기 전과 뒤가 같은 말이다. */
const DEPT_ITEMS = {
  // 하위 부서가 막는다 — 예전 화면이 「최상위로 올라갑니다」라고 약속하던 바로 그 경우다.
  "dep-parent": base("dep-parent", "본부", {
    child_department_count: 1,
    delete_precheck: {
      deletable: false,
      blockers: [{ kind: "child_departments", label: "하위 부서", count: 1, archived_count: 0 }],
      detachables: [],
      reason: "이 부서에 하위 부서 1건이 연결되어 있어 삭제할 수 없습니다."
        + " 먼저 다른 부서로 옮기거나, '비활성'으로 두면 새로 고를 수는 없지만 기존 연결은"
        + " 그대로 유지됩니다.",
    },
  }),
  // 반례 — 아무것도 안 매달린 부서는 예전과 똑같이 지울 수 있어야 한다.
  "dep-free": base("dep-free", "빈부서", {
    child_department_count: 0,
    delete_precheck: { deletable: true, blockers: [], detachables: [], reason: null },
  }),
  // 막지 않고 연결만 끊는 갈래 — 지워지지는 않지만 부서 표시를 잃는다.
  "dep-rooms": base("dep-rooms", "방있는부서", {
    child_department_count: 0,
    delete_precheck: {
      deletable: true,
      blockers: [],
      detachables: [{ kind: "chat_rooms", label: "팀 채팅방", count: 1 }],
      reason: "팀 채팅방 1건은 부서 연결만 끊고 그대로 두었습니다.",
    },
  }),
  // 보관되어 **목록에 안 보이는** 프로젝트가 막는다(xc-04).
  "dep-archived": base("dep-archived", "보관프로젝트부서", {
    child_department_count: 0,
    delete_precheck: {
      deletable: false,
      blockers: [{ kind: "projects", label: "프로젝트", count: 1, archived_count: 1 }],
      detachables: [],
      reason: "이 부서에 프로젝트 1건이 연결되어 있어 삭제할 수 없습니다."
        + " 그중 보관된 프로젝트 1건은 목록에 보이지 않으니 보관함을 함께 확인해 주세요."
        + " 먼저 다른 부서로 옮기거나, '비활성'으로 두면 새로 고를 수는 없지만 기존 연결은"
        + " 그대로 유지됩니다.",
    },
  }),
  // 사람이 막는다 — 그중 한 명은 보관된 계정이라 사용자 목록 기본 화면에 안 보인다(org-08).
  "dep-people": base("dep-people", "사람있는부서", {
    user_count: 3,
    child_department_count: 0,
    delete_precheck: {
      deletable: false,
      blockers: [{ kind: "users", label: "소속 사용자", count: 3, archived_count: 1 }],
      detachables: [],
      reason: "이 부서에 소속 사용자 3명이 연결되어 있어 삭제할 수 없습니다."
        + " 그중 보관된 계정 1명은 목록에 보이지 않으니 보관함을 함께 확인해 주세요."
        + " 먼저 다른 부서로 옮기거나, '비활성'으로 두면 새로 고를 수는 없지만 기존 연결은"
        + " 그대로 유지됩니다.",
    },
  }),
};

function mockApi() {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
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

function renderDept(id) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/departments/" + id]}>
          <Routes>
            <Route path="/departments/:id" element={<OrgConsole />} />
            <Route path="/organizations" element={<OrgConsole />} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });
const panel = () => screen.getByTestId("org-console-panel");
/* 고른 대상의 「더 보기」와 주 동작은 페이지 머리에 선다(D-510). */
const pageActions = () => document.querySelector(".k-page-actions");

async function openPanel(id, name) {
  mockApi();
  renderDept(id);
  await within(await screen.findByTestId("org-console-panel", {}, WAIT))
    .findByRole("heading", { name }, WAIT);
}

/** 「더 보기」를 열어 항목 이름을 읽는다. `keepOpen` 이면 열린 메뉴를 돌려준다(항목을 누를 때). */
async function openMenu(name, { keepOpen = false } = {}) {
  await userEvent.click(within(pageActions()).getByRole("button", { name: `${name} 작업 더 보기` }));
  const menu = await screen.findByRole("menu", {}, WAIT);
  if (keepOpen) return menu;
  const names = within(menu).getAllByRole("menuitem").map((m) => m.textContent);
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull(), WAIT);
  return names;
}

describe("서버가 막는 부서", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("하위 부서가 있으면 메뉴에 삭제가 없고, 안내는 서버가 낸 이유를 그대로 말한다", async () => {
    await openPanel("dep-parent", "본부");
    expect(await openMenu("본부")).not.toContain("삭제");
    expect(within(panel()).queryByRole("button", { name: "삭제" })).toBeNull();
    expect(within(panel()).getByText(DEPT_ITEMS["dep-parent"].delete_precheck.reason))
      .toBeInTheDocument();
    // 🔴 서버와 정반대였던 약속은 화면 어디에도 없다 — 이것이 이 시험의 핵심이다.
    expect(panel().textContent).not.toContain("최상위 부서로 올라갑니다");
    // 하위 부서는 바로 왼쪽 트리가 그 목록이다 — 따로 갈 곳이 없어 링크를 만들지 않는다.
    expect(within(panel()).queryByRole("link", { name: "소속 사용자 보기" })).toBeNull();
  });

  it("보관되어 목록에 안 보이는 것이 막고 있으면 그 사실까지 말한다(xc-04)", async () => {
    await openPanel("dep-archived", "보관프로젝트부서");
    expect(await openMenu("보관프로젝트부서")).not.toContain("삭제");
    expect(panel().textContent).toContain("보관된 프로젝트 1건은 목록에 보이지 않으니");
    expect(within(panel()).getByText(DEPT_ITEMS["dep-archived"].delete_precheck.reason))
      .toBeInTheDocument();
  });

  it("사람이 막으면 이유 문장 옆에 그 사람들 · 보관된 계정으로 가는 링크가 선다", async () => {
    await openPanel("dep-people", "사람있는부서");
    expect(await openMenu("사람있는부서")).not.toContain("삭제");
    expect(within(panel()).getByText(DEPT_ITEMS["dep-people"].delete_precheck.reason))
      .toBeInTheDocument();
    expect(within(panel()).getByRole("link", { name: "소속 사용자 보기" }).getAttribute("href"))
      .toBe("#/users?department_id=dep-people");
    expect(within(panel()).getByRole("link", { name: "보관된 계정 보기" }).getAttribute("href"))
      .toBe("#/users?department_id=dep-people&archived=true");
  });
});

describe("서버가 막지 않는 부서(반례)", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("아무것도 안 매달렸으면 메뉴에서 삭제할 수 있고, 확인 뒤 DELETE 가 나간다", async () => {
    await openPanel("dep-free", "빈부서");
    expect(within(panel()).getByText("이 부서는 지금 삭제할 수 있습니다.")).toBeInTheDocument();
    expect(within(panel()).queryByRole("link", { name: "소속 사용자 보기" })).toBeNull();
    const menu = await openMenu("빈부서", { keepOpen: true });
    await userEvent.click(within(menu).getByRole("menuitem", { name: "삭제" }));
    const dialogs = await screen.findAllByRole("dialog", {}, WAIT);
    const dlg = dialogs[dialogs.length - 1];
    expect(dlg.textContent).toContain("이 부서를 지울까요? 되돌릴 수 없습니다.");
    await userEvent.click(within(dlg).getByRole("button", { name: "삭제" }));
    await waitFor(() => {
      expect(apiMock.mock.calls.some(([p, o]) =>
        String(p) === "/api/admin/departments/dep-free" && o && o.method === "DELETE")).toBe(true);
    }, WAIT);
  });

  it("연결만 끊는 갈래가 있으면 안내와 확인 창이 그것을 미리 말한다", async () => {
    await openPanel("dep-rooms", "방있는부서");
    expect(within(panel()).getByText(
      "이 부서는 지금 삭제할 수 있습니다. 삭제하면 팀 채팅방 1건은 부서 연결만 끊고 그대로 남습니다.",
    )).toBeInTheDocument();
    const menu = await openMenu("방있는부서", { keepOpen: true });
    await userEvent.click(within(menu).getByRole("menuitem", { name: "삭제" }));
    const dialogs = await screen.findAllByRole("dialog", {}, WAIT);
    const dlg = dialogs[dialogs.length - 1];
    expect(dlg.textContent).toContain(
      "이 부서를 지우면 팀 채팅방 1건은 부서 연결만 끊고 그대로 남습니다.",
    );
    // 「그대로 두었습니다」는 지운 **뒤**의 문장이다 — 누르기 전에 과거형으로 말하지 않는다.
    expect(dlg.textContent).not.toContain("그대로 두었습니다");
  });
});
