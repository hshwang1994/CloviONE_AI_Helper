import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 🔴 **주 동작은 «...» 뒤에 숨지 않는다** (2026-09-01).
 *
 * `DataScreen` 은 머리 액션을 「위험한 것」과 「아닌 것」으로 갈라 앞의 것을 «...» 넘침
 * 메뉴에 빨간 글씨로 넣는다. 그 판정이 `variant === "danger" || !!confirm` 이었다 —
 * **「확인을 한 번 묻는다」를 「파괴적이다」로 읽었다.**
 *
 * 그래서 백업 화면의 «백업 실행» 이 사라졌다. 그 액션은 `primary: true` 로 선언된 그
 * 화면의 존재 이유인데(`registry/platform.js`), 확인 문구를 갖고 있다는 이유만으로
 * 머리에서 빠지고 «...» 메뉴 안에 위험 항목으로 들어가 있었다. 관리자가 「지금 백업」을
 * 누르려면 먼저 그 메뉴를 열 생각을 해야 했다.
 *
 * 여기서 고정하는 것 둘:
 *   1) `primary` 액션은 확인 문구가 있어도 **머리에 버튼으로** 선다.
 *   2) 그래도 `danger`/`confirm` 인 **다른** 액션은 그대로 넘침 메뉴로 간다(회귀 방지).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", email: "a@b.c" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROWS = [{ id: "1", name: "백업 하나" }];

const CONFIG = {
  key: "backup", area: "운영", title: "백업", endpoint: "/api/admin/backups",
  columns: [{ key: "name", label: "이름", identifier: true }],
  headerActions: [
    { label: "복원 안내", method: "GET", path: () => "/api/admin/backups/restore-instructions" },
    {
      label: "백업 실행", variant: "primary", primary: true,
      path: () => "/api/admin/backups", confirm: "지금 데이터베이스 백업을 실행할까요?",
    },
    { label: "전부 지우기", variant: "danger", path: () => "/x", confirm: "정말요?" },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(() => Promise.resolve({ items: ROWS, total: ROWS.length }));
});

function renderScreen(cfg) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <DataScreen config={cfg} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("머리의 주 동작", () => {
  it("확인 문구가 있어도 머리에 버튼으로 선다 — «...» 메뉴 안이 아니다", async () => {
    renderScreen(CONFIG);
    await screen.findByText("백업 하나");
    expect(screen.getByRole("button", { name: "백업 실행" })).toBeInTheDocument();
  });

  it("주 동작이 아닌 위험한 액션은 그대로 넘침 메뉴로 간다", async () => {
    renderScreen(CONFIG);
    await screen.findByText("백업 하나");
    // 메뉴를 열기 전에는 DOM 에 없다 — 즉 머리에 버튼으로 서 있지 않다.
    expect(screen.queryByRole("button", { name: "전부 지우기" })).toBeNull();
    expect(screen.getByRole("button", { name: "백업 화면 작업 더 보기" })).toBeInTheDocument();
  });
});

/* 주 동작에 `when(ctx)` 가 걸린 화면 — 관리 알림의 「모두 읽음」 모양이다. 읽을 것이 있으면
 * 머리에 버튼으로 서고(넘침 메뉴가 아니다), 없으면 아예 없다. 예전에는 `primary` 선언이
 * 빠져 있어 확인 문구 때문에 «...» 메뉴 안 위험 항목으로 들어가 있었다. */
const NOTIF_CONFIG = {
  key: "admin-notifications", area: "운영", title: "관리 알림", endpoint: "/api/notifications",
  unreadCountKey: "unread",
  columns: [{ key: "title", label: "제목", identifier: true }],
  headerActions: [
    { label: "모두 읽음", variant: "primary", primary: true, when: (ctx) => ctx.unreadCount > 0,
      path: () => "/api/notifications/read-all", confirm: "관리 알림을 모두 읽음 처리할까요?" },
  ],
};

describe("when 이 걸린 주 동작", () => {
  it("읽을 것이 있으면 머리에 버튼으로 선다 — 넘침 메뉴가 아니다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({ items: [{ id: "n1", title: "알림 하나" }], total: 1, unread: 3 }));
    renderScreen(NOTIF_CONFIG);
    await screen.findByText("알림 하나");
    expect(screen.getByRole("button", { name: "모두 읽음" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "관리 알림 화면 작업 더 보기" })).toBeNull();
  });

  it("읽을 것이 없으면 버튼이 없다(반례)", async () => {
    apiMock.mockImplementation(() => Promise.resolve({ items: [{ id: "n1", title: "알림 하나" }], total: 1, unread: 0 }));
    renderScreen(NOTIF_CONFIG);
    await screen.findByText("알림 하나");
    expect(screen.queryByRole("button", { name: "모두 읽음" })).toBeNull();
    expect(screen.queryByRole("button", { name: "관리 알림 화면 작업 더 보기" })).toBeNull();
  });
});
