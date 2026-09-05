import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 정합성 화면 — 판은 정리할 것이 있는 항목에만 준다 (관리자 UI 정리 회차 · D-457).
 *
 * 못박는 것:
 *   ① 건수가 있는 항목은 판이고, 표와 공용 선택 열(체크박스 이름 = 대상 이름 + 「선택」)을 갖는다.
 *   ② 0건 항목은 판·표·체크박스 없이 이름·이유·「0건」 줄 하나다. 정리하는 법(remedy)은 거기 없다.
 *   ③ 선택 수가 지정 줄과 적용 버튼에 그대로 간다(전체 선택 포함).
 *   ④ 반례: 전부 0건이면 화면에 체크박스가 하나도 없고, 관리자 범위 표는 그대로 있다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { Integrity } from "./Integrity.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function finding(key, title, items, extra = {}) {
  return {
    key, title, why: `${title} 는 닫혀 있습니다.`, remedy: `${title} 를 지정하세요.`,
    count: items.length, items, fixable_here: false, ...extra,
  };
}

const OPEN = finding("users_without_membership", "소속이 지정되지 않은 사용자", [
  { id: "u1", display_name: "홍길동", email: "hong@goodmit.co.kr" },
  { id: "u2", display_name: "김철수", email: "kim@goodmit.co.kr" },
], { fixable_here: true });
const CLEAR_A = finding("tickets_multi_project", "프로젝트가 정확히 하나가 아닌 티켓", []);
const CLEAR_B = finding("spaces_without_owner", "소속이 지정되지 않은 지식 공간", []);

const ADMINS = {
  by_scope: { global: 2, org: 0, dept: 0 }, total: 2,
  items: [
    { id: "a1", display_name: "UI QA", role: "system_admin", admin_scope: "global", scope_path: [] },
    { id: "a2", display_name: "박민준", role: "admin", admin_scope: "global", scope_path: [] },
  ],
};

function payload(findings) {
  return { findings, total_issues: findings.reduce((n, f) => n + f.count, 0), admins: ADMINS };
}

let data;
beforeEach(() => {
  data = payload([OPEN, CLEAR_A, CLEAR_B]);
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path === "/api/admin/integrity") return Promise.resolve(data);
    if (path.startsWith("/api/admin/departments")) return Promise.resolve({ items: [{ id: "d1", name: "개발팀" }] });
    return Promise.resolve({});
  });
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Integrity />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("판은 정리할 것이 있는 항목에만 준다", () => {
  it("건수가 있는 항목은 h3 제목 + 표 + 공용 선택 열이다", async () => {
    renderScreen();
    expect(await screen.findByRole("heading", { level: 3, name: OPEN.title })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "홍길동 선택" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "전체 선택" })).toBeInTheDocument();
    expect(screen.getByText("2건")).toBeInTheDocument();
    expect(screen.getByText("0건 선택됨")).toBeInTheDocument();
    expect(screen.getByText(OPEN.remedy)).toBeInTheDocument();
  });

  it("0건 항목은 줄 하나다 — 제목 요소가 아니고 표도 체크박스도 없다", async () => {
    renderScreen();
    await screen.findByText(CLEAR_A.title);
    expect(screen.queryByRole("heading", { name: CLEAR_A.title })).toBeNull();
    expect(screen.getAllByText("0건").length).toBe(2);
    const row = screen.getByText(CLEAR_A.title).closest(".k-settingrow");
    expect(row).not.toBeNull();
    expect(within(row).queryByRole("checkbox")).toBeNull();
    expect(within(row).queryByRole("table")).toBeNull();
    // «왜 문제인가» 는 남는다 — 이름만 남기면 0건이 무엇을 뜻하는지 모른다.
    expect(within(row).getByText(CLEAR_A.why)).toBeInTheDocument();
    // 정리하는 법은 0건 줄에 없다 — 읽을 사람이 없는 안내다.
    expect(screen.queryByText(CLEAR_A.remedy)).toBeNull();
  });

  it("선택 수가 지정 줄과 적용 버튼에 그대로 간다 — 전체 선택 포함", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("checkbox", { name: "홍길동 선택" }));
    expect(screen.getByText("1건 선택됨")).toBeInTheDocument();
    // 소속을 아직 안 골랐으니 적용은 닫혀 있다.
    expect(screen.getByRole("button", { name: "선택한 1명에 적용" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "전체 선택" }));
    expect(screen.getByText("2건 선택됨")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "선택한 2명에 적용" })).toBeInTheDocument();
  });

  it("반례: 전부 0건이면 체크박스가 하나도 없고 관리자 범위 표는 그대로다", async () => {
    data = payload([{ ...OPEN, count: 0, items: [] }, CLEAR_A, CLEAR_B]);
    renderScreen();
    await screen.findByText(/정리할 것이 없습니다/);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getAllByText("0건").length).toBe(3);
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: "관리자 범위 현황" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "정리할 항목" })).toBeInTheDocument();
    expect(screen.getByText("박민준")).toBeInTheDocument();
  });
});
