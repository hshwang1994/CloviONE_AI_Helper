/* qa-contract-change: 서버가 깎기 전 admin_scope 열이 아니라 /api/me 가 실어 보내는 파생 관리 범위(management.kind)로 판정 축을 옮겼다 — 고정값과 when 이 받는 맥락 이름도 같이 바꿈. */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 관리 **범위**도 단추를 가른다 (xa-07).
 *
 * `role` 은 「무엇을 할 수 있는가」이고 관리 범위는 「누구에게 할 수 있는가」다. 서버는
 * 공지·전체 AI 상한·조직 정지처럼 **포털 전체가 주인인 자원**을 이미 범위로 거절하는데
 * (`app.core.scope.require_global_management`) 이 셸은 역할 축만 봤다 — 부서 범위 관리자에게
 * 전역 자원의 '추가'·'수정'이 그대로 그려졌고, 눌러 403 을 받고 나서야 못 한다는 것을 알았다
 * (실측: `POST /api/admin/announcements` → 403 「공지는 전체 범위 관리자만 만들고 바꿀 수
 * 있습니다」).
 *
 * 🔴 판정 축은 `admin_scope` **열이 아니다** (R7-02). 서버는 그 열을 그대로 안 쓴다 —
 * `management_scope()` 가 운영자·감사자의 기본값 'global' 을 조직 범위로 내리고, 관리할
 * 부서가 없는 'dept' 를 아무것도 관리 못 하는 범위로 내린다. 열을 그대로 읽으면 그 둘이
 * 전부 「전역」이 되어, 이 게이트를 붙여 놓고도 운영자는 여전히 단추를 보고 403 을 받는다.
 * `/api/me` 는 서버의 판정을 `user.management.kind` 로 이미 싣는다 — 그 값을 읽는다.
 *
 * 여기서 고정하는 것 셋:
 *   1) 선언이 `requiresGlobalScope: true` 라고 말하면 부서 범위 관리자에게 그 단추가 없다.
 *   2) 그보다 세밀한 조건을 위해 `when` 이 받는 맥락에 범위가 실려 있다 — 「행의 범위가
 *      '전체'인 것만 못 고친다」 같은 판단은 registry 가 스스로 한다.
 *   3) 열과 서버의 답이 갈리면 **서버의 답을 따른다**(운영자의 'global' 열).
 * 반례는 같은 화면을 **전역 범위 관리자**로 여는 것이다. 단추가 사라지면 안 된다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
let authData;
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: authData }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROWS = [
  { id: "q-global", name: "전체 상한", scope: "global" },
  { id: "q-dept", name: "서비스운영팀 상한", scope: "dept" },
];

const seenScopes = [];

const CONFIG = {
  key: "ai-quotas", area: "AI", title: "AI 상한", endpoint: "/api/admin/ai-quotas",
  columns: [{ key: "name", label: "이름", identifier: true }],
  // 공지처럼 **전체 범위 관리자만** 만들 수 있는 자원.
  create: { roles: ["admin", "system_admin"], requiresGlobalScope: true, fields: [{ name: "name", label: "이름" }] },
  createLabel: "상한 추가",
  // 역할을 안 적은 머리 동작 — 역할 축은 통과하고 **범위 축만** 남는 자리다.
  headerActions: [{ label: "전체 상한 초기화", requiresGlobalScope: true, path: () => "/api/admin/ai-quotas/reset" }],
  actions: [
    {
      label: "수정",
      // 행의 범위와 내 범위를 **함께** 봐야 정해지는 게이트.
      when: (row, ctx) => { seenScopes.push(ctx.managementScope); return row.scope !== "global" || ctx.isGlobalAdmin; },
      path: (r) => "/api/admin/ai-quotas/" + r.id,
    },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: ROWS, total: ROWS.length });
  seenScopes.length = 0;
  window.location.hash = "";
});

function renderAs(data) {
  authData = data;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <DataScreen config={CONFIG} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// 고정값은 `/api/me` 가 실제로 보내는 모양 그대로다 — 열(admin_scope)과 서버의 답
// (management.kind)을 **둘 다** 싣는다. 화면이 어느 쪽을 읽는지가 여기서 갈린다.
const DEPT_ADMIN = { role: "admin", id: "u-dept", admin_scope: "dept", management: { kind: "dept" } };
const GLOBAL_ADMIN = { role: "admin", id: "u-global", admin_scope: "global", management: { kind: "global" } };
/* 운영자는 `admin_scope` 열이 'global' 이다(0024 마이그레이션이 전부 그렇게 채웠다).
   서버는 그 값을 조직 범위로 깎아 내리고 전역 자원의 쓰기를 403 으로 막는다. */
const OPERATOR = { role: "operator", id: "u-op", admin_scope: "global", management: { kind: "org" } };
/* 관리할 부서가 하나도 없는 부서 범위 관리자 — 서버는 아무것도 관리하지 못하는 범위로 읽는다. */
const EMPTY_SUBTREE_ADMIN = { role: "admin", id: "u-empty", admin_scope: "dept", management: { kind: "none" } };

describe("전역 자원의 쓰기 단추 (xa-07)", () => {
  it("부서 범위 관리자에게는 '추가'도 전역 머리 동작도 그리지 않는다", async () => {
    renderAs(DEPT_ADMIN);
    await screen.findByText("전체 상한");

    expect(screen.queryByRole("button", { name: "상한 추가" })).toBeNull();
    expect(screen.queryByRole("button", { name: "전체 상한 초기화" })).toBeNull();
  });

  it("반례 — 전역 범위 관리자에게는 둘 다 그대로 있다", async () => {
    renderAs(GLOBAL_ADMIN);
    await screen.findByText("전체 상한");

    expect(screen.getByRole("button", { name: "상한 추가" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "전체 상한 초기화" })).toBeInTheDocument();
  });

  it("행 액션의 when 이 내 범위를 받는다 — 전역 행의 '수정'은 부서 범위 관리자에게 없다", async () => {
    const user = userEvent.setup();
    renderAs(DEPT_ADMIN);
    await screen.findByText("전체 상한");

    await user.click(screen.getByText("전체 상한"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "수정" })).toBeNull();
    expect(seenScopes).toContain("dept");
  });

  it("반례 — 같은 관리자도 자기 부서 범위 행은 고칠 수 있다", async () => {
    const user = userEvent.setup();
    renderAs(DEPT_ADMIN);
    await screen.findByText("서비스운영팀 상한");

    await user.click(screen.getByText("서비스운영팀 상한"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "수정" })).toBeInTheDocument();
  });

  it("반례 — 범위를 안 싣는 계정(management 없음)은 전역으로 본다(OrgConsole.jsx 와 같은 판정)", async () => {
    renderAs({ role: "system_admin", id: "u-sys" });
    await screen.findByText("전체 상한");

    expect(screen.getByRole("button", { name: "상한 추가" })).toBeInTheDocument();
  });
});

describe("판정 축은 admin_scope 열이 아니라 서버가 깎아 낸 관리 범위다 (R7-02)", () => {
  it("운영자의 admin_scope 는 'global' 이지만 전역 머리 동작은 그리지 않는다", async () => {
    renderAs(OPERATOR);
    await screen.findByText("전체 상한");

    // 열을 그대로 읽으면 이 단추가 선다 — 그리고 누르면 서버가 403 을 낸다.
    expect(screen.queryByRole("button", { name: "전체 상한 초기화" })).toBeNull();
  });

  it("운영자의 when 맥락에도 파생 범위('org')가 실린다 — 열의 'global' 이 아니다", async () => {
    const user = userEvent.setup();
    renderAs(OPERATOR);
    await screen.findByText("전체 상한");

    await user.click(screen.getByText("전체 상한"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(seenScopes).toContain("org");
    expect(seenScopes).not.toContain("global");
  });

  it("관리할 부서가 없는 부서 범위 관리자에게도 전역 쓰기 단추가 없다", async () => {
    renderAs(EMPTY_SUBTREE_ADMIN);
    await screen.findByText("전체 상한");

    expect(screen.queryByRole("button", { name: "상한 추가" })).toBeNull();
    expect(screen.queryByRole("button", { name: "전체 상한 초기화" })).toBeNull();
  });
});
