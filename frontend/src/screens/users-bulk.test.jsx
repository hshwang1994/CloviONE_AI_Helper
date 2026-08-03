import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 사용자 대량 작업 + CSV (PLAN Phase 6).
 *
 * 못박는 것:
 *   1) **부분 실패를 성공으로 덮지 않는다** — 3명 중 1명이 막히면 그 사실과 사유를 말한다.
 *   2) **가져오기는 미리보기가 먼저다** — 미리 보기 전에는 '만들기' 버튼이 눌리지 않는다.
 *   3) **내보내기는 지금 걸린 필터 그대로** 나간다(목록과 다른 결과가 나가면 파일을 열기 전까지 아무도 모른다).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Users } from "./Users.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const mkUser = (n) => ({
  id: "u-" + n, email: `m${n}@goodmit.co.kr`, display_name: "사람" + n, role: "user",
  active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
  department: null, department_id: null, title: null, title_id: null,
  last_login_at: null, created_at: "2026-07-01T00:00:00", archived_at: null,
});
const USERS = [mkUser(1), mkUser(2), mkUser(3)];

let lastBulkBody = null;

beforeEach(() => {
  lastBulkBody = null;
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (path.startsWith("/api/admin/users?")) {
      return Promise.resolve({ items: USERS, total: 3, page_size: 20 });
    }
    if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
    if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
    if (path === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
    if (path === "/api/admin/users/bulk/apply" && method === "POST") {
      lastBulkBody = opts.body;
      return Promise.resolve({
        action: "disable", action_label: "비활성화", requested: 3,
        applied: [
          { id: "u-1", email: "m1@goodmit.co.kr", display_name: "사람1", changed: true },
          { id: "u-2", email: "m2@goodmit.co.kr", display_name: "사람2", changed: true },
        ],
        failed: [{ id: "u-3", error: "마지막 system_admin 계정은 비활성화할 수 없습니다." }],
      });
    }
    if (path === "/api/admin/users/import/csv" && method === "POST") {
      return Promise.resolve({
        dry_run: !!opts.body.dry_run, total: 1,
        created: opts.body.dry_run ? 1 : 1, skipped: 0, failed: 0,
        results: [{ line: 2, email: "new@goodmit.co.kr", display_name: "신입",
                    status: opts.body.dry_run ? "ready" : "created", message: "새로 만들 계정입니다." }],
      });
    }
    return Promise.resolve({});
  });
});

function renderUsers() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Users />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

async function selectAll(user) {
  const all = await screen.findByRole("checkbox", { name: "전체 선택" });
  await user.click(all);
  return screen.findByText("3명 선택");
}

describe("사용자 대량 작업", () => {
  it("선택한 id 목록이 그대로 요청에 실린다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await selectAll(user);
    await user.click(screen.getByRole("button", { name: "비활성화" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /확인|비활성화|계속/ }));

    await waitFor(() => expect(lastBulkBody).not.toBeNull());
    expect(lastBulkBody.user_ids).toEqual(["u-1", "u-2", "u-3"]);
    expect(lastBulkBody.action).toBe("disable");
  });

  it("부분 실패를 성공 토스트로 덮지 않는다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await selectAll(user);
    await user.click(screen.getByRole("button", { name: "비활성화" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /확인|비활성화|계속/ }));

    expect(await screen.findByText(/1명 실패/)).toBeInTheDocument();
    expect(screen.getByText(/마지막 system_admin/)).toBeInTheDocument();
  });

  it("선택이 없으면 대량 작업 막대 자체가 없다", async () => {
    renderUsers();
    await screen.findByText("m1@goodmit.co.kr");
    expect(screen.queryByText(/명 선택$/)).not.toBeInTheDocument();
  });
});

describe("CSV", () => {
  it("내보내기 링크에 지금 걸린 검색어가 붙는다", async () => {
    const user = userEvent.setup();
    renderUsers();
    const link = await screen.findByRole("link", { name: "CSV 내보내기" });
    expect(link.getAttribute("href")).toBe("/api/admin/users/export/csv");

    // 화면에 필터를 걸었는데 내보낸 파일에 전 직원이 담기면, 그 사실은 파일을 열기 전까지
    // 아무도 모른다 — 목록과 같은 필터 문자열을 쓰는지 링크로 확인한다(검색어는 250ms 디바운스).
    await user.type(screen.getByLabelText("사용자 검색"), "사람2");
    await waitFor(() => expect(
      screen.getByRole("link", { name: "CSV 내보내기" }).getAttribute("href"),
    ).toBe("/api/admin/users/export/csv?q=" + encodeURIComponent("사람2")));
  });

  it("미리 보기 전에는 만들기 버튼이 눌리지 않는다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await user.click(await screen.findByRole("button", { name: "CSV 가져오기" }));
    const dialog = await screen.findByRole("dialog");
    const csv = within(dialog).getByLabelText("CSV 내용");
    await user.type(csv, "email,display_name{enter}new@goodmit.co.kr,신입");

    // 미리 보기를 하기 전에는 '만들기'가 아니라 안내 라벨이고 비활성이다.
    const gate = within(dialog).getByRole("button", { name: "미리 보기를 먼저 하세요" });
    expect(gate).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: "미리 보기" }));
    expect(await within(dialog).findByText(/생성 예정 1/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "1명 만들기" })).toBeEnabled();
  });
});
