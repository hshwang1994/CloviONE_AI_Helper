import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 조직 관리 개선(계획 3.6 · D-510)으로 고른 대상의 「더 보기」와 주 동작(부서 추가 · 하위 부서 추가)이 상세 판 머리에서 페이지 머리로 옮겨 갔다(판 안의 30px 주 동작이 머리의 34px 보조 단추보다 작아 위계가 거꾸로 읽혔다). 판 머리에는 「수정」 하나가 남는다 — 판 안에서 단추를 찾던 단언을 페이지 머리(`.k-page-actions`)로 옮겼다.
 *
 * qa-contract-change: 조직 관리 IA 재설계(P6)로 활성화 · 비활성화가 판 머리 단추에서 「더 보기」 메뉴 항목으로 옮겨 갔고, 수정 · 상태 변경이 서버가 주는 can_edit 을 따르게 됐다 — 단추를 찾던 단언을 메뉴 항목 단언으로 옮기고 can_edit 의 음성 · 양성 사례를 더했다.
 *
 * **자기 조직 비활성화는 시스템 관리자만 할 수 있다**(org-09).
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
 *
 * **조직 이름 · 상태를 바꾸는 것 자체는 전체 관리자만 할 수 있다**(`require_global_management`). 서버가 그 답을
 * 조직 응답의 `can_edit` 로 싣는다 — 아무도 안 읽던 동안 범위 관리자는 「수정」을 눌러 저장할 때 403 을 봤다.
 * 서버 값이 화면의 추정보다 앞선다: `can_edit:false` 면 전역 관리자로 보여도 안 세우고, `true` 면 세운다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
const actor = vi.hoisted(() => ({ role: "admin", org_id: "org-1", kind: "global" }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({
    data: { id: "actor-1", role: actor.role, org_id: actor.org_id, management: { kind: actor.kind } },
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
  { id: "org-3", kind: "organization", name: "묵은회사", depth: 0, path: "묵은회사",
    active: false, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
];
const ORGS = [
  { id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
    department_count: 0, user_count: 15, created_at: AT },
  { id: "org-2", name: "자회사", slug: "subsidiary", status: "active",
    department_count: 0, user_count: 3, created_at: AT },
  { id: "org-3", name: "묵은회사", slug: "old-co", status: "suspended",
    department_count: 0, user_count: 0, created_at: AT },
];

function mockApi({ canEdit } = {}) {
  const orgs = canEdit === undefined ? ORGS : ORGS.map((o) => ({ ...o, can_edit: canEdit }));
  apiMock.mockImplementation((url) => {
    const u = String(url);
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: orgs });
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

async function openOrg(orgId, name, opts) {
  mockApi(opts);
  renderOrg(orgId);
  await within(await screen.findByTestId("org-console-panel", {}, WAIT))
    .findByRole("heading", { name }, WAIT);
  return screen.getByTestId("org-console-panel");
}

/** 「더 보기」 메뉴의 항목 이름. 메뉴를 열고 읽은 뒤 닫는다(열린 메뉴는 판을 가린다). */
async function menuItems(panel, name) {
  await userEvent.click(within(document.querySelector(".k-page-actions")).getByRole("button", { name: `${name} 작업 더 보기` }));
  const menu = await screen.findByRole("menu", {}, WAIT);
  const names = within(menu).getAllByRole("menuitem").map((m) => m.textContent);
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull(), WAIT);
  return names;
}

beforeEach(() => {
  apiMock.mockReset();
  actor.role = "admin";
  actor.org_id = "org-1";
  actor.kind = "global";
});

describe("자기 조직 비활성화", () => {
  it("전역 admin 의 자기 조직 메뉴에는 비활성화가 없고, 판이 이유를 말한다", async () => {
    const panel = await openOrg("org-1", "클로비원");
    expect(await menuItems(panel, "클로비원")).toEqual(["감사 로그에서 보기"]);
    expect(within(panel).queryByRole("button", { name: "비활성화" })).toBeNull();
    expect(within(panel).getByText(/자기 조직 비활성화는 시스템 관리자만 할 수 있습니다\./))
      .toBeInTheDocument();
    // 남는 것은 여전히 있다 — 이름 수정은 이 게이트와 무관하다.
    expect(within(panel).getByRole("button", { name: "수정" })).toBeInTheDocument();
  });

  it("시스템 관리자는 자기 조직도 비활성화할 수 있다(반례)", async () => {
    actor.role = "system_admin";
    const panel = await openOrg("org-1", "클로비원");
    expect(await menuItems(panel, "클로비원")).toContain("비활성화");
    expect(within(panel).queryByText(/자기 조직 비활성화는/)).toBeNull();
  });

  it("전역 admin 도 남의 조직은 비활성화할 수 있다(반례 — 서버가 200 을 준다)", async () => {
    const panel = await openOrg("org-2", "자회사");
    expect(await menuItems(panel, "자회사")).toEqual(["감사 로그에서 보기", "비활성화"]);
    expect(within(panel).queryByText(/자기 조직 비활성화는/)).toBeNull();
  });

  it("이미 정지된 조직의 「활성화」는 그대로 있다 — 푸는 것은 막히지 않는다", async () => {
    actor.org_id = "org-3";
    const panel = await openOrg("org-3", "묵은회사");
    expect(await menuItems(panel, "묵은회사")).toEqual(["감사 로그에서 보기", "활성화"]);
    expect(within(panel).queryByText(/자기 조직 비활성화는/)).toBeNull();
  });
});

describe("조직을 바꾸는 권한 — 서버의 can_edit", () => {
  it("can_edit:false 면 전역 판정과 무관하게 수정 · 상태 변경을 세우지 않고, 이유를 한 줄로 말한다(음성)", async () => {
    const panel = await openOrg("org-2", "자회사", { canEdit: false });
    expect(within(panel).queryByRole("button", { name: "수정" })).toBeNull();
    const names = await menuItems(panel, "자회사");
    expect(names).not.toContain("비활성화");
    expect(names).not.toContain("활성화");
    expect(within(panel).getByText("조직 이름과 상태는 전체 관리자만 바꿀 수 있습니다.")).toBeInTheDocument();
    // 부서를 만드는 것은 조직을 바꾸는 일이 아니다 — 그 입구는 그대로 선다.
    expect(within(document.querySelector(".k-page-actions")).getByRole("button", { name: "부서 추가" })).toBeInTheDocument();
  });

  it("can_edit:false 인 정지 조직도 활성화를 세우지 않는다(음성)", async () => {
    const panel = await openOrg("org-3", "묵은회사", { canEdit: false });
    expect(await menuItems(panel, "묵은회사")).toEqual(["감사 로그에서 보기"]);
    // 권한이 없는데 자기 조직 안내를 따로 세우지 않는다 — 이유는 권한 줄 하나다.
    expect(within(panel).queryByText(/자기 조직 비활성화는/)).toBeNull();
  });

  it("can_edit:true 면 범위 관리자로 보이는 계정에도 수정과 상태 변경이 선다(양성 — 서버 값이 앞선다)", async () => {
    actor.kind = "org";
    const panel = await openOrg("org-2", "자회사", { canEdit: true });
    expect(within(panel).getByRole("button", { name: "수정" })).toBeInTheDocument();
    expect(await menuItems(panel, "자회사")).toContain("비활성화");
    expect(within(panel).queryByText("조직 이름과 상태는 전체 관리자만 바꿀 수 있습니다.")).toBeNull();
  });

  it("can_edit 을 모르는 옛 응답이면 이 화면의 전역 판정으로 떨어진다 — 범위 관리자에게는 안 세운다", async () => {
    actor.kind = "dept";
    const panel = await openOrg("org-2", "자회사");
    expect(within(panel).queryByRole("button", { name: "수정" })).toBeNull();
    expect(await menuItems(panel, "자회사")).toEqual(["감사 로그에서 보기"]);
  });
});
