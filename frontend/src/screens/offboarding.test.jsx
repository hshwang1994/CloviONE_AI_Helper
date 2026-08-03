import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 온보딩·오프보딩 화면 (PLAN Phase 6).
 *
 * 여기서 못박는 것은 "화면이 그려진다"가 아니라 **되돌릴 수 있고 거짓말하지 않는다**이다:
 *   1) 실행 전에 보유 티켓을 **먼저 보여 준다**(조용한 일괄 실행 금지).
 *   2) 실행 요청에는 **사용자가 화면에서 확인한 목록 그대로** 실린다(서버가 알아서 고르지 않는다).
 *   3) 12건 중 3건이 실패하면 **성공 토스트로 덮지 않고** 그 숫자를 말한다.
 *   4) 되돌리기 버튼이 이력 상세 안에 실제로 있다 — 되돌릴 방법이 화면에 없으면 아무도 실행을 못 누른다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Offboarding } from "./Offboarding.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const LEAVER = {
  id: "u-leaver", email: "leaver@goodmit.co.kr", display_name: "퇴사자", role: "user",
  active: true, archived_at: null, department: "개발팀", department_id: "d-1",
  title: "팀원", notion_mapping_status: "verified", locked: false,
  must_change_password: false, last_login_at: null, created_at: "2026-07-01T00:00:00",
};

const PREVIEW = {
  user: { ...LEAVER },
  onboarding: [
    { key: "department", label: "부서 배정", ok: true, value: "개발팀" },
    { key: "notion", label: "Notion 사용자 연결", ok: true, value: "verified" },
  ],
  notion_mapped: true,
  tickets: [
    { id: "page-1", tid: 101, title: "혼자 담당 A", status: "진행", due: "2026-09-01", assignee_names: ["퇴사자"] },
    { id: "page-2", tid: 102, title: "공동 담당", status: "진행", due: "2026-09-02", assignee_names: ["퇴사자", "동료"] },
  ],
  ticket_count: 2,
  tickets_error: null,
  successor_candidates: [
    { user_id: "u-succ", display_name: "후임", email: "succ@goodmit.co.kr", department: "개발팀" },
  ],
  max_tickets_per_run: 100,
  open_run: null,
};

const RUN_ROW = {
  id: "run-1", user_id: "u-leaver", user_name: "퇴사자", actor_user_id: "actor-1",
  actor_name: "관리자", successor_user_id: "u-succ", successor_name: "후임",
  status: "partial", deactivated: true, archived: false, note: null,
  ticket_total: 2, ticket_moved: 1, ticket_failed: 1, undone_at: null,
  undone_by_user_id: null, undo_error: null, created_at: "2026-08-03T01:00:00",
};

let runs = [];
let lastRunBody = null;

beforeEach(() => {
  runs = [];
  lastRunBody = null;
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (path.startsWith("/api/admin/users?")) {
      return Promise.resolve({ items: [LEAVER], total: 1, page_size: 20 });
    }
    if (path.startsWith("/api/admin/offboarding/preview/")) return Promise.resolve(PREVIEW);
    if (path.startsWith("/api/admin/offboarding/run/") && method === "POST") {
      lastRunBody = opts.body;
      runs = [RUN_ROW];
      return Promise.resolve({
        run: RUN_ROW,
        moves: [
          { id: "m1", ticket_page_id: "page-1", tid: 101, title: "혼자 담당 A", status: "moved", error: null },
          { id: "m2", ticket_page_id: "page-2", tid: 102, title: "공동 담당", status: "failed", error: "Notion 오류" },
        ],
      });
    }
    if (path.startsWith("/api/admin/offboarding?")) {
      return Promise.resolve({ items: runs, total: runs.length, page: 1, page_size: 20 });
    }
    if (path === "/api/admin/offboarding/run-1") {
      return Promise.resolve({ run: { ...RUN_ROW, moves: [] } });
    }
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
              <Offboarding />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

async function pickLeaverAndRun(user) {
  await user.click(await screen.findByRole("button", { name: /상세 보기/ }));
  // 미리보기 — 실행 전에 보유 티켓이 화면에 있어야 한다.
  expect(await screen.findByText("혼자 담당 A")).toBeInTheDocument();
  expect(screen.getByText(/보유 티켓 2건/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "오프보딩 실행" }));
  // 확인 대화상자에서 무엇이 바뀌는지 먼저 말한다.
  const confirmDialog = await screen.findByRole("dialog");
  expect(within(confirmDialog).getByText(/티켓 2건을/)).toBeInTheDocument();
  await user.click(within(confirmDialog).getByRole("button", { name: "실행" }));
}

describe("오프보딩 화면", () => {
  it("실행 요청에는 화면에서 확인한 티켓 목록이 그대로 실린다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await pickLeaverAndRun(user);

    await waitFor(() => expect(lastRunBody).not.toBeNull());
    // 서버가 알아서 전부 옮기지 않는다 — 화면이 보낸 목록만 대상이다.
    expect(lastRunBody.ticket_page_ids).toEqual(["page-1", "page-2"]);
    expect(lastRunBody.deactivate).toBe(true);
  });

  it("부분 실패를 성공 토스트로 덮지 않는다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await pickLeaverAndRun(user);

    // 12건 중 3건 실패를 '완료'라고 말하면 그 3건은 영영 아무도 안 본다.
    expect(await screen.findByText(/1건은 실패했습니다/)).toBeInTheDocument();
    expect(await screen.findByText("Notion 오류")).toBeInTheDocument();
  });

  it("체크를 풀면 그 티켓은 요청에서 빠진다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("button", { name: /상세 보기/ }));
    await screen.findByText("혼자 담당 A");

    const boxes = screen.getAllByRole("checkbox", { name: "이 항목 선택" });
    await user.click(boxes[0]);
    await waitFor(() => expect(screen.getByText(/선택 1건/)).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "오프보딩 실행" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "실행" }));
    await waitFor(() => expect(lastRunBody).not.toBeNull());
    expect(lastRunBody.ticket_page_ids).toEqual(["page-2"]);
  });

  it("이력 상세에 되돌리기 버튼이 있다", async () => {
    runs = [RUN_ROW];
    const user = userEvent.setup();
    renderScreen();
    // 대상 고르기 표의 첫 열은 render가 없어 라벨이 '상세 보기: 퇴사자'가 되고, 이력 표의 첫
    // 열은 render(날짜 포맷)가 있어 라벨이 정확히 '상세 보기'다(kit.jsx rowOpenLabel) — 정확 일치로 고른다.
    const openRun = await screen.findByRole("button", { name: "상세 보기" });
    await user.click(openRun);
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByRole("button", { name: "되돌리기" })).toBeInTheDocument();
  });
});
