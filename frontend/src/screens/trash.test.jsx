import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 휴지통 계약 테스트.
 *
 * 이 화면의 두 동작은 되돌릴 수 있는 정도가 정반대다:
 *   - 복원: 무해하다. 확인 창 없이 곧바로 실행된다(한 번 더 묻는 건 방해일 뿐이다).
 *   - 영구 삭제: 노션 원본까지 보관처리된다. **반드시** 확인을 거치고, 취소하면 아무 요청도
 *     나가지 않아야 한다.
 * 두 버튼이 같은 행에 나란히 있어서, 재설계 중 mutation을 바꿔 달면 "복원을 눌렀는데 지워졌다"가
 * 조용히 성립한다 — 그래서 '어떤 URL로 갔는지'까지 본다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.

 * qa-contract-change: 정말 0건인 휴지통은 표를 그리지 않던 계약을 걷었다 — 목록의 0건은 다건과 같은 셸(표 머리 아래 띠)에 선다(D-588 · 계획 §4 22). 탭 줄을 그리지 않는다는 단언은 그대로다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Trash, urgentCount } from "./Trash.jsx";
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

const ITEM = {
  id: "t1", item_type: "document", type_label: "문서", title: "설계서 초안",
  deleted_by: "김운영", deleted_at: "2026-08-01T01:00:00", purge_after: "2026-08-08T01:00:00",
  can_manage: true, url: null,
};

function mockList(items) {
  apiMock.mockImplementation((url, opts) => {
    // UA-10 확증 — 목록 조회는 이제 ?limit=을 붙여 나간다(그 값 자체는 이 계약 테스트의
    // 관심사가 아니라 접두어만 본다).
    if (url.startsWith("/api/trash?") && !opts) return Promise.resolve({ items, retention_days: 7, total: items.length });
    return Promise.resolve({ ok: true });
  });
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("영구 삭제는 확인을 거친다", () => {
  it("확인 창에서 취소하면 아무 요청도 나가지 않는다", async () => {
    mockList([ITEM]);
    const user = userEvent.setup();
    renderTrash();
    await screen.findByText("설계서 초안");
    const before = apiMock.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "영구 삭제" }));
    const dialog = await screen.findByRole("dialog");
    // 🔴 문구가 **되돌릴 수 없음**을 말해야 한다. 예전에는 「노션 휴지통에서 30일 내 복구
    // 가능」이라고 했는데 그 안전망은 S14 와 함께 사라졌다(D-284) — 지금은 행과 딸린
    // 댓글·첨부가 그대로 지워진다. 사용자는 이 한 줄을 읽고 누른다.
    expect(within(dialog).getByText(/되돌릴 수 없습니다/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/노션/)).toBeNull();

    await user.click(within(dialog).getByRole("button", { name: "취소" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const purged = apiMock.mock.calls.slice(before).filter((c) => String(c[0]).includes("/purge"));
    expect(purged).toHaveLength(0);
  });

  it("확인하면 그 항목의 purge 엔드포인트로만 요청한다", async () => {
    mockList([ITEM]);
    const user = userEvent.setup();
    renderTrash();
    await screen.findByText("설계서 초안");

    await user.click(screen.getByRole("button", { name: "영구 삭제" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "영구 삭제" }));

    await waitFor(() => {
      const writes = apiMock.mock.calls.filter((c) => c[1] && c[1].method === "POST");
      expect(writes.map((c) => String(c[0]))).toContain("/api/trash/t1/purge");
    });
  });
});

describe("복원은 확인 없이 곧바로 실행된다", () => {
  it("복원 버튼은 restore 엔드포인트를 부르고 purge는 부르지 않는다", async () => {
    mockList([ITEM]);
    const user = userEvent.setup();
    renderTrash();
    await screen.findByText("설계서 초안");

    await user.click(screen.getByRole("button", { name: "복원" }));

    await waitFor(() => {
      const writes = apiMock.mock.calls.filter((c) => c[1] && c[1].method === "POST").map((c) => String(c[0]));
      expect(writes).toContain("/api/trash/t1/restore");
      expect(writes.some((u) => u.includes("/purge"))).toBe(false);
    });
    // 확인 대화상자를 띄우지 않는다(무해한 동작에 확인을 붙이면 그냥 방해다).
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("권한과 빈 상태", () => {
  it("관리 권한이 없는 행에는 동작 버튼 대신 '권한 없음'이 뜬다", async () => {
    mockList([{ ...ITEM, can_manage: false }]);
    renderTrash();
    await screen.findByText("설계서 초안");
    expect(screen.getByText("권한 없음")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "복원" })).toBeNull();
    expect(screen.queryByRole("button", { name: "영구 삭제" })).toBeNull();
  });

  it("비어 있으면 탭 줄 없이 목록 판(표 머리 아래 띠)에 안내가 선다", async () => {
    mockList([]);
    renderTrash();
    const heading = await screen.findByRole("heading", { name: "휴지통이 비어 있습니다." });
    // 탭 줄은 그리지 않는다 — 「전체 0 / 티켓 0 / 문서 0」은 정보가 아니라 소음이다.
    // (조건이 걸려 0건인 경우는 **다른 사실**이라 탭 줄이 남는다 — trash-tabs.test.jsx.)
    expect(screen.queryByRole("tab")).toBeNull();
    // 목록의 0건은 다건과 같은 셸이다(D-588) — 판 없이 화면 가운데 큰 그림이 아니다.
    expect(heading.closest("[data-empty-layout='band']")).not.toBeNull();
  });

  /* WF1 R5 — 빈 상태 안내가 바로 위 상시 안내문("삭제한 티켓과 문서를 7일 동안 보관합니다...")
   * 과 거의 같은 문장을 또 말했다("삭제한 티켓과 문서가 7일 동안 여기 보관됩니다..."). 상시
   * 안내문은 빈 상태여도 사라지지 않으므로(항상 렌더) 같은 사실을 두 번 읽게 됐다. */
  it("빈 상태 안내가 바로 위 상시 안내문과 같은 사실(보관 일수)을 반복하지 않는다", async () => {
    mockList([]);
    renderTrash();
    await screen.findByRole("heading", { name: "휴지통이 비어 있습니다." });
    /* 상시 안내문(보관 일수 포함)은 여전히 있다 — 빈 상태에서도 사라지지 않는다.
       문구가 「티켓 7일, 문서 7일」로 갈라진 것은 두 정책이 실제로 다르기 때문이다(D-352):
       티켓 쪽은 원본을 보관처리하고, 문서 쪽은 행을 지운다. */
    expect(screen.getByText(/삭제한 티켓은 7일, 문서는 7일 동안 보관합니다/)).toBeInTheDocument();
    // 빈 상태 자체의 문구는 그 사실을 다시 말하지 않는다.
    expect(screen.queryByText(/7일 동안 여기 보관됩니다/)).not.toBeInTheDocument();
    // 그래도 되돌릴 수 있다는 재확인(이 화면의 핵심 안심 메시지)은 남아 있다.
    expect(screen.getByText(/이 화면에서 복원할 수 있습니다/)).toBeInTheDocument();
  });
});

describe("urgentCount", () => {
  it("24시간 안에 사라질 항목만 센다", () => {
    const now = Date.parse("2026-08-03T00:00:00Z");
    const items = [
      { purge_after: "2026-08-03T10:00:00" },   // 10시간 뒤 → 임박
      { purge_after: "2026-08-05T00:00:00" },   // 이틀 뒤 → 아님
      { purge_after: "2026-08-02T00:00:00" },   // 이미 지남 → 임박
      { purge_after: null },                     // 값 없음 → 세지 않는다
    ];
    expect(urgentCount(items, now)).toBe(2);
  });
});
