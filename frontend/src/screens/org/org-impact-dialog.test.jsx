import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 영향 확인 창 (O1 · D-533) — 창 하나하나가 서버 답을 어떻게 그리는가.
 *
 * 화면 단위 흐름(메뉴 → 창 → 요청)은 `org-console-actions` · `org-delete-precheck` 가 본다. 여기서는 창의 상태를 본다:
 *   ① 창이 열려 있을 때만 묻는다(닫힌 창은 질의를 만들지 않는다).
 *   ② 답을 받기 전에는 확정 단추를 누를 수 없고, 못 받으면 창 안에서 다시 시도한다 — 모르는 상태로 「삭제」를 세우지 않는다.
 *   ③ 0 인 갈래는 줄을 세우지 않는다(시스템 관리자 0명이면 그 문장이 없다).
 *   ④ 「상세 정보」는 ID 를 복사하고, 복사가 막히면 직접 고르라고 말한다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { DeptDeleteDialog, OrgDetailsDialog, OrgSuspendDialog } from "./orgImpact.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const DEPT = { id: "dep-1", name: "플랫폼개발팀", active: true, org_id: "org-1", parent_id: null };
const ORG = { id: "org-1", name: "굿모닝아이텍", status: "active" };

function ui(node) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>{node}</ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}
const impactCalls = () => apiMock.mock.calls.filter(([p]) => String(p).endsWith("/impact"));

beforeEach(() => { apiMock.mockReset(); });

describe("부서 삭제 창", () => {
  it("닫힌 창은 묻지 않는다", async () => {
    apiMock.mockResolvedValue({});
    ui(<DeptDeleteDialog dept={DEPT} open={false} onClose={() => {}} />);
    await new Promise((r) => { setTimeout(r, 20); });
    expect(impactCalls()).toHaveLength(0);
  });

  it("답을 받기 전에는 「삭제」가 없고, 지울 수 있다는 답이 오면 「플랫폼개발팀을 삭제하시겠습니까?」로 바뀐다", async () => {
    let resolve;
    apiMock.mockImplementation(() => new Promise((r) => { resolve = r; }));
    ui(<DeptDeleteDialog dept={DEPT} open onClose={() => {}} />);
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).queryByRole("button", { name: "삭제" })).toBeNull();
    expect(impactCalls().map(([p]) => p)).toEqual(["/api/admin/departments/dep-1/impact"]);
    resolve({ delete: { deletable: true, blockers: [], detachables: [] }, deactivate: {} });
    expect(await screen.findByRole("dialog", { name: "플랫폼개발팀을 삭제하시겠습니까?" })).toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "삭제" })).toBeEnabled();
  });

  it("답을 못 받으면 창 안에서 다시 시도하고, 확정 단추는 서지 않는다", async () => {
    apiMock.mockRejectedValueOnce(Object.assign(new Error("boom"), { status: 500 }));
    apiMock.mockResolvedValueOnce({ delete: { deletable: false, blockers: [{ kind: "users", label: "소속 사용자", count: 2, unit: "명" }] }, deactivate: {} });
    ui(<DeptDeleteDialog dept={DEPT} open onClose={() => {}} />);
    const dlg = await screen.findByRole("dialog");
    const retry = await within(dlg).findByRole("button", { name: /다시 시도/ });
    expect(within(dlg).queryByRole("button", { name: "삭제" })).toBeNull();
    await userEvent.click(retry);
    expect(await screen.findByRole("dialog", { name: "이 부서는 삭제할 수 없습니다." })).toBeInTheDocument();
    expect(impactCalls()).toHaveLength(2);
  });
});

describe("조직 비활성화 창", () => {
  it("빠지는 시스템 관리자가 없으면 그 문장을 세우지 않고, 답을 받기 전에는 확정을 누를 수 없다", async () => {
    let resolve;
    apiMock.mockImplementation(() => new Promise((r) => { resolve = r; }));
    ui(<OrgSuspendDialog org={ORG} open onClose={() => {}} />);
    const dlg = await screen.findByRole("dialog", { name: "굿모닝아이텍을 비활성화하시겠습니까?" });
    expect(within(dlg).getByRole("button", { name: "비활성화" })).toBeDisabled();
    resolve({ suspend: { signed_out_users: 12, exempt_system_admins: 0, inactive_users: 0, archived_users: 0 } });
    await waitFor(() => expect(within(dlg).getByRole("button", { name: "비활성화" })).toBeEnabled());
    expect(dlg.textContent).toContain("12명");
    expect(dlg.textContent).not.toContain("시스템 관리자");
  });
});

describe("상세 정보 창", () => {
  it("ID 를 복사하고, 복사가 막히면 직접 고르라고 말한다", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    ui(<OrgDetailsDialog open onClose={() => {}} kind="department" item={{ id: "dep-1", name: "플랫폼개발팀", created_at: "2026-01-02T03:04:05Z" }} childCount={0} />);
    const dlg = await screen.findByRole("dialog", { name: "상세 정보" });
    expect(within(dlg).getByText("부서 ID")).toBeInTheDocument();
    expect(within(dlg).getByText("없음")).toBeInTheDocument();
    await userEvent.click(within(dlg).getByRole("button", { name: "복사" }));
    expect(writeText).toHaveBeenCalledWith("dep-1");
    expect(await screen.findByText("복사하지 못했습니다. ID를 직접 골라 복사하세요.")).toBeInTheDocument();
  });
});
