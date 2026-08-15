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
    if (path === "/api/admin/departments") return Promise.resolve({ items: [{ id: "d-1", name: "개발팀", active: true }] });
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

describe("일괄 부서/직책 지정 — 적용 전 값 확인", () => {
  /* assignOptions(부서/직책 옵션)의 첫 항목은 항상 { value: "", label: "없음" }(Users.jsx의
   * useNameOptions)이다. assign.value를 ""로 초기화하면 관리자가 값을 건드리지 않아도 이미
   * '없음'이 골라진 것으로 취급돼, '적용'을 누르는 순간 선택한 전원의 부서/직책이 조용히
   * null로 지워진다. 자리표시자(선택 안 됨)와 '없음을 능동적으로 고름'을 구분해야 한다. */
  it("값을 실제로 고르기 전에는 '적용' 버튼이 눌리지 않는다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await selectAll(user);

    await user.click(screen.getByRole("combobox", { name: "일괄 지정" }));
    await user.click(await screen.findByRole("option", { name: "부서" }));

    // 값 드롭다운을 아직 건드리지 않았다 — 자리표시자 상태이므로 적용은 비활성이어야 한다.
    expect(screen.getByRole("button", { name: "적용" })).toBeDisabled();
  });

  it("'없음'을 능동적으로 고르면(자리표시자와 구분) 적용이 활성화되고 그대로 적용된다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await selectAll(user);

    await user.click(screen.getByRole("combobox", { name: "일괄 지정" }));
    await user.click(await screen.findByRole("option", { name: "부서" }));
    await user.click(screen.getByRole("combobox", { name: "값" }));
    await user.click(await screen.findByRole("option", { name: "없음" }));

    expect(screen.getByRole("button", { name: "적용" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "적용" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "확인" }));

    await waitFor(() => expect(lastBulkBody).not.toBeNull());
    expect(lastBulkBody.action).toBe("set_department");
    expect(lastBulkBody.value).toBeNull();
  });

  // Offboarding.jsx의 run()처럼, 확인창은 어떤 값이 실제로 적용될지 못박아야 한다 — 일반 문구
  // ("부서를 일괄 변경할까요?")만으론 관리자가 무슨 값이 들어가는지 모른 채 확인을 누른다.
  it("확인창에 실제로 적용될 값(선택한 부서명)이 그대로 보인다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await selectAll(user);

    await user.click(screen.getByRole("combobox", { name: "일괄 지정" }));
    await user.click(await screen.findByRole("option", { name: "부서" }));
    await user.click(screen.getByRole("combobox", { name: "값" }));
    await user.click(await screen.findByRole("option", { name: "개발팀" }));
    await user.click(screen.getByRole("button", { name: "적용" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/"개발팀"/)).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "확인" }));
    await waitFor(() => expect(lastBulkBody).not.toBeNull());
    expect(lastBulkBody.action).toBe("set_department");
    expect(lastBulkBody.value).toBe("d-1");
  });
});

describe("일괄 작업 확인창의 위험 스타일은 실제 위험도를 따른다", () => {
  // apply()가 예전엔 danger:true를 하드코딩해서, '활성화'처럼 되돌리기 쉬운 작업까지 확인
  // 버튼이 파괴적 작업(비활성화 등)과 똑같이 '위험' 스타일로 떴다. BULK_ACTIONS의 danger
  // 속성을 그대로 따라가야 한다.
  it("비파괴적 작업(활성화)의 확인 버튼은 위험 스타일이 아니다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await selectAll(user);
    await user.click(screen.getByRole("button", { name: "활성화" }));

    const dialog = await screen.findByRole("dialog");
    const confirmBtn = within(dialog).getByRole("button", { name: "확인" });
    expect(confirmBtn.className).not.toMatch(/containedError/);
  });

  it("파괴적 작업(비활성화)의 확인 버튼은 위험 스타일이다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await selectAll(user);
    await user.click(screen.getByRole("button", { name: "비활성화" }));

    const dialog = await screen.findByRole("dialog");
    const confirmBtn = within(dialog).getByRole("button", { name: "확인" });
    expect(confirmBtn.className).toMatch(/containedError/);
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

  it("미리 보기 전에는 추가 버튼이 눌리지 않는다", async () => {
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
    expect(await within(dialog).findByText(/추가 예정 1/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "1명 추가" })).toBeEnabled();
  });

  // 회귀: ImportModal의 '미리 보기'/'만들기' 두 버튼이 busy 불리언 하나를 공유했다.
  // BulkBar(같은 파일, 위쪽)는 이미 "busy === a.value"로 어떤 작업이 진행 중인지 액션별로
  // 구분하는데, ImportModal만 이 관례를 따르지 않아 '만들기'를 누르면 정작 실행 중이지 않은
  // '미리 보기' 버튼이 "확인 중…"으로 바뀌고, 실제로 요청이 나가는 '만들기' 버튼에는 아무
  // 진행 표시도 없었다 — 사용자에게 엉뚱한 동작이 진행 중이라고 말하는 셈이었다.
  it("'추가' 요청 중에는 '추가' 버튼에 진행 표시가 뜨고, '미리 보기' 버튼이 엉뚱하게 바뀌지 않는다", async () => {
    const user = userEvent.setup();
    let resolveCreate;
    apiMock.mockImplementation((path, opts) => {
      const method = (opts && opts.method) || "GET";
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: USERS, total: 3, page_size: 20 });
      if (path === "/api/admin/departments") return Promise.resolve({ items: [{ id: "d-1", name: "개발팀", active: true }] });
      if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
      if (path === "/api/admin/settings") return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
      if (path === "/api/admin/users/import/csv" && method === "POST") {
        if (opts.body.dry_run) {
          return Promise.resolve({
            dry_run: true, total: 1, created: 1, skipped: 0, failed: 0,
            results: [{ line: 2, email: "new@goodmit.co.kr", display_name: "신입", status: "ready", message: "새로 만들 계정입니다." }],
          });
        }
        // 실제 생성 요청은 테스트가 직접 resolve를 통제한다 — '진행 중'인 순간의 라벨을 봐야 한다.
        return new Promise((resolve) => { resolveCreate = resolve; });
      }
      return Promise.resolve({});
    });

    renderUsers();
    await user.click(await screen.findByRole("button", { name: "CSV 가져오기" }));
    const dialog = await screen.findByRole("dialog");
    const csv = within(dialog).getByLabelText("CSV 내용");
    await user.type(csv, "email,display_name{enter}new@goodmit.co.kr,신입");
    await user.click(within(dialog).getByRole("button", { name: "미리 보기" }));
    await within(dialog).findByText(/추가 예정 1/);

    await user.click(within(dialog).getByRole("button", { name: "1명 추가" }));

    expect(within(dialog).queryByText("확인 중…")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "미리 보기" })).toBeInTheDocument();

    resolveCreate({
      dry_run: false, total: 1, created: 1, skipped: 0, failed: 0,
      results: [{ line: 2, email: "new@goodmit.co.kr", display_name: "신입", status: "created", message: "생성됨" }],
    });
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "닫기" })).toBeInTheDocument());
  });
});
