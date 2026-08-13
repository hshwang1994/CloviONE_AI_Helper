import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* UA-25 — 휴지통 일괄 복원/영구삭제 실패 토스트가 실제 사유(이미 처리됨·권한 없음·Notion
 * 보관 실패)와 무관하게 항상 "권한이 없어 건너뛰었습니다"였다. 백엔드(service.py의
 * restore_bulk/purge_bulk)는 이미 건별 실제 사유를 failed[].error로 돌려준다 — 화면이
 * 그 사유를 안 보고 뭉갠 것뿐이었다. Notion 장애 때 관리자가 이 문구만 보고 "내 권한이
 * 부족한가" 하고 다른(더 높은 권한의) 계정으로 재시도하는 헛수고를 하게 만들었다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Trash } from "./Trash.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderTrash() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Trash />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const ITEMS = [
  { id: "t1", item_type: "ticket", type_label: "티켓", title: "정상 티켓",
    deleted_by: "김운영", deleted_at: "2026-08-01T01:00:00", purge_after: "2026-08-08T01:00:00",
    can_manage: true, url: null },
  { id: "t2", item_type: "ticket", type_label: "티켓", title: "실패할 티켓",
    deleted_by: "김운영", deleted_at: "2026-08-01T01:00:00", purge_after: "2026-08-08T01:00:00",
    can_manage: true, url: null },
];

beforeEach(() => {
  apiMock.mockReset();
});

async function selectBoth() {
  await screen.findByText("정상 티켓");
  fireEvent.click(screen.getByRole("checkbox", { name: "정상 티켓 선택" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "실패할 티켓 선택" }));
}

describe("휴지통 일괄 실패 사유 (UA-25)", () => {
  it("일괄 복원 — '이미 처리된 항목'은 권한 문구가 아니라 실제 사유를 보여준다", async () => {
    apiMock.mockImplementation((url, opts) => {
      if (url.startsWith("/api/trash?") && !opts) {
        return Promise.resolve({ items: ITEMS, retention_days: 7, total: 2 });
      }
      if (url === "/api/trash/restore-bulk") {
        return Promise.resolve({
          restored: [{ id: "t1", title: "정상 티켓", item_type: "ticket", notion_page_id: "p1" }],
          failed: [{ id: "t2", error: "이미 처리된 항목입니다." }],
        });
      }
      return Promise.resolve({ ok: true });
    });
    renderTrash();
    await selectBoth();

    fireEvent.click(screen.getByRole("button", { name: "선택 복원" }));

    await screen.findByText(/이미 처리된 항목입니다/);
    expect(screen.queryByText(/권한이 없/)).toBeNull();
  });

  it("일괄 영구삭제 — Notion 보관처리 실패도 권한 문구가 아니라 실제 사유를 보여준다", async () => {
    apiMock.mockImplementation((url, opts) => {
      if (url.startsWith("/api/trash?") && !opts) {
        return Promise.resolve({ items: ITEMS, retention_days: 7, total: 2 });
      }
      if (url === "/api/trash/purge-bulk") {
        return Promise.resolve({
          purged: [{ id: "t1", title: "정상 티켓", item_type: "ticket", notion_page_id: "p1" }],
          failed: [{ id: "t2", error: "노션 보관처리에 실패했습니다. 잠시 후 다시 시도하세요." }],
        });
      }
      return Promise.resolve({ ok: true });
    });
    renderTrash();
    await selectBoth();

    fireEvent.click(screen.getByRole("button", { name: "선택 영구 삭제" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "영구 삭제" }));

    await screen.findByText(/노션 보관처리에 실패했습니다/);
    expect(screen.queryByText(/권한이 없/)).toBeNull();
  });
});
