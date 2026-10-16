import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 조직 관리 작업 공간(O1 · D-533)으로 판의 「정보」 구획이 사라졌다 — 할 수 없는 동작의 까닭(자기 조직 비활성화 · 변경 권한)은 판에 늘 서는 줄이 아니라 「더 보기」의 **비활성 항목과 그 설명**이 말한다. 「수정」은 판 머리 단추에서 메뉴 첫 항목으로, 「활성화」는 「다시 사용」으로, 동작 단추는 페이지 머리에서 판 머리로 옮겼다. 음성 · 양성 사례는 하나도 걷지 않았다.
 *
 * **자기 조직 비활성화는 시스템 관리자만 할 수 있다**(org-09).
 *
 * 실측(2026-09-06 · 자기 서버, 전역 admin): 조직 판의 「비활성화」가 그대로 서 있고, 누르면 «소속 사용자 15명이 지금 즉시
 * 로그아웃되고 다시 로그인할 수 없게 됩니다» 라는 확인 창이 떴다. 확인을 누른 뒤에야 403 «자기 조직은 시스템 관리자만 정지할 수
 * 있습니다» 가 돌아왔다. 되돌릴 수 없는 결과를 예고하는 창은 **실제로 일어날 수 있는 일**에만 떠야 한다 — 그래서 항목을 누를 수
 * 없게 두고 까닭을 설명으로 단다. 서버 판정(`ensure_may_suspend_org`)은 역할과 조직 id 둘만 보는 조건이라 화면이 그대로 재현한다.
 *
 * **조직 이름 · 상태를 바꾸는 것 자체는 전체 관리자만 할 수 있다**(`require_global_management`). 서버가 그 답을 `can_edit` 로
 * 싣는다 — 서버 값이 화면의 추정보다 앞선다. 값을 모르는 옛 응답이면 전역 판정(`management.kind`)으로 떨어진다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
const actor = vi.hoisted(() => ({ role: "admin", org_id: "org-1", kind: "global" }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { id: "actor-1", role: actor.role, org_id: actor.org_id, management: { kind: actor.kind } } }),
}));

import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원", active: true, child_count: 0, subtree_user_count: 15, created_at: AT },
  { id: "org-2", kind: "organization", name: "자회사", depth: 0, path: "자회사", active: true, child_count: 0, subtree_user_count: 0, created_at: AT },
  { id: "org-3", kind: "organization", name: "묵은회사", depth: 0, path: "묵은회사", active: false, child_count: 0, subtree_user_count: 0, created_at: AT },
];
const ORGS = [
  { id: "org-1", name: "클로비원", slug: "clovirone", status: "active", department_count: 0, user_count: 15, created_at: AT },
  { id: "org-2", name: "자회사", slug: "subsidiary", status: "active", department_count: 0, user_count: 3, created_at: AT },
  { id: "org-3", name: "묵은회사", slug: "old-co", status: "suspended", department_count: 0, user_count: 0, created_at: AT },
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
  await within(await screen.findByTestId("org-console-panel", {}, WAIT)).findByRole("heading", { level: 2, name }, WAIT);
  return screen.getByTestId("org-console-panel");
}

/** 「더 보기」 메뉴의 항목 — `{ name, disabled, help }`. 메뉴를 열고 읽은 뒤 닫는다(열린 메뉴는 판을 가린다). */
async function menuItems(panel, name) {
  await userEvent.click(within(panel.querySelector("[data-pane-head]")).getByRole("button", { name: `${name} 작업 더 보기` }));
  const menu = await screen.findByRole("menu", {}, WAIT);
  const out = within(menu).getAllByRole("menuitem").map((m) => {
    const helpId = m.getAttribute("aria-describedby");
    const help = helpId ? (document.getElementById(helpId) || {}).textContent || "" : "";
    return { name: m.getAttribute("aria-label") || m.textContent, disabled: m.getAttribute("aria-disabled") === "true", help };
  });
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull(), WAIT);
  return out;
}
const pick = (items, name) => items.find((i) => i.name === name);

beforeEach(() => {
  apiMock.mockReset();
  actor.role = "admin";
  actor.org_id = "org-1";
  actor.kind = "global";
});

describe("자기 조직 비활성화", () => {
  it("전역 admin 의 자기 조직에서 「비활성화」는 누를 수 없고, 설명이 까닭을 말한다", async () => {
    const panel = await openOrg("org-1", "클로비원");
    const items = await menuItems(panel, "클로비원");
    expect(pick(items, "비활성화")).toEqual({
      name: "비활성화", disabled: true, help: "자기 조직 비활성화는 시스템 관리자만 할 수 있습니다.",
    });
    // 이름 수정은 이 게이트와 무관하다.
    expect(pick(items, "수정").disabled).toBe(false);
    // 판에 까닭을 늘 세우던 「정보」 구획은 없다.
    expect(within(panel).queryByText(/자기 조직 비활성화는/)).toBeNull();
  });

  it("시스템 관리자는 자기 조직도 비활성화할 수 있다(반례)", async () => {
    actor.role = "system_admin";
    const panel = await openOrg("org-1", "클로비원");
    expect(pick(await menuItems(panel, "클로비원"), "비활성화").disabled).toBe(false);
  });

  it("전역 admin 도 남의 조직은 비활성화할 수 있다(반례 — 서버가 200 을 준다)", async () => {
    const panel = await openOrg("org-2", "자회사");
    expect(pick(await menuItems(panel, "자회사"), "비활성화")).toEqual({ name: "비활성화", disabled: false, help: "" });
  });

  it("이미 정지된 조직의 「다시 사용」은 그대로 있다 — 푸는 것은 막히지 않는다", async () => {
    actor.org_id = "org-3";
    const panel = await openOrg("org-3", "묵은회사");
    const items = await menuItems(panel, "묵은회사");
    expect(pick(items, "활성화").disabled).toBe(false);
    expect(pick(items, "비활성화")).toBeUndefined();
  });
});

describe("조직을 바꾸는 권한 — 서버의 can_edit", () => {
  it("can_edit:false 면 전역 판정과 무관하게 「수정」을 누를 수 없고 상태 변경이 없다 — 까닭은 설명이다(음성)", async () => {
    const panel = await openOrg("org-2", "자회사", { canEdit: false });
    const items = await menuItems(panel, "자회사");
    expect(pick(items, "수정")).toEqual({ name: "수정", disabled: true, help: "조직 이름과 상태는 전체 관리자만 바꿀 수 있습니다." });
    expect(pick(items, "비활성화")).toBeUndefined();
    expect(pick(items, "활성화")).toBeUndefined();
    // 부서를 만드는 것은 조직을 바꾸는 일이 아니다 — 그 입구는 그대로 선다.
    expect(within(panel.querySelector("[data-pane-head]")).getByRole("button", { name: "부서 추가" })).toBeInTheDocument();
  });

  it("can_edit:false 인 정지 조직도 「다시 사용」을 세우지 않는다(음성)", async () => {
    const panel = await openOrg("org-3", "묵은회사", { canEdit: false });
    const items = await menuItems(panel, "묵은회사");
    expect(pick(items, "활성화")).toBeUndefined();
    expect(pick(items, "수정").disabled).toBe(true);
  });

  it("can_edit:true 면 범위 관리자로 보이는 계정에도 수정과 상태 변경이 선다(양성 — 서버 값이 앞선다)", async () => {
    actor.kind = "org";
    const panel = await openOrg("org-2", "자회사", { canEdit: true });
    const items = await menuItems(panel, "자회사");
    expect(pick(items, "수정").disabled).toBe(false);
    expect(pick(items, "비활성화").disabled).toBe(false);
  });

  it("can_edit 을 모르는 옛 응답이면 이 화면의 전역 판정으로 떨어진다 — 범위 관리자에게는 상태 변경이 없다", async () => {
    actor.kind = "dept";
    const panel = await openOrg("org-2", "자회사");
    const items = await menuItems(panel, "자회사");
    expect(pick(items, "수정").disabled).toBe(true);
    expect(pick(items, "비활성화")).toBeUndefined();
  });

  it("조직 삭제는 누구에게나 까닭과 함께 비활성이다 — 지우는 대신 비활성화로 새 사용을 막는다", async () => {
    actor.role = "system_admin";
    const panel = await openOrg("org-2", "자회사");
    expect(pick(await menuItems(panel, "자회사"), "삭제")).toEqual({
      name: "삭제", disabled: true, help: "조직은 삭제할 수 없습니다. 대신 비활성화할 수 있습니다.",
    });
  });
});
