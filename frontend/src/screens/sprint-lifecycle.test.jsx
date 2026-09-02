import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 회차의 한 바퀴(SprintLifecycle) — 보드·회의가 공유하는 부품인데 전용 시험이 없었다.
 *
 * 여기서 못박는 것 넷:
 *  1) 이월 대화상자의 선택은 **열리는 순간에만** 기본값을 받는다 — 열려 있는 동안 회차
 *     목록이 재조회돼 배열 신원이 바뀌어도 사용자의 선택을 덮지 않는다(닫기는 되돌릴
 *     수 없는 동작이다).
 *  2) 이월 후보는 서버 규칙과 같은 축이다 — 닫힌 회차·다른 프로젝트 회차는 후보에
 *     없고, 팀 전체 회차는 언제나 있다(고르면 서버 거절만 보는 후보를 안 보여 준다).
 *  3) 회차 수정·삭제가 실제 API 를 부른다 — 삭제 항목은 planned 에만 뜬다.
 *  4) 일반 사용자에게는 아무것도 안 그린다(서버 게이트의 화면 쪽 그림자).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
let role = "system_admin";
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role, id: "u-1" } }),
}));

import { SprintLifecycle } from "./SprintLifecycle.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function sprint(over) {
  return {
    id: "sp-1", name: "이번 회차", project_id: "p-1",
    starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active", goal: null,
    ...over,
  };
}

const OTHERS = [
  sprint(),
  sprint({ id: "sp-next", name: "다음 회차", state: "planned" }),
  sprint({ id: "sp-done", name: "지난 회차", state: "closed" }),
  sprint({ id: "sp-other", name: "이웃 회차", state: "planned", project_id: "p-2" }),
  sprint({ id: "sp-team", name: "팀 전체 회차", state: "planned", project_id: null }),
];

function renderLife(props) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <SprintLifecycle sprint={sprint()} sprints={OTHERS} {...props} />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("SprintLifecycle", () => {
  beforeEach(() => {
    role = "system_admin";
    apiMock.mockReset();
    apiMock.mockResolvedValue({});
  });

  it("일반 사용자에게는 아무것도 안 그린다", () => {
    role = "user";
    renderLife();
    // 서버가 PROJECT_WRITE 로 막는다 — 여기서는 누를 수 없는 단추를 안 보여 준다.
    expect(screen.queryByRole("button", { name: "회차 닫기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "회차 열기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "회차 관리" })).toBeNull();
  });

  it("이월 후보에 닫힌 회차와 다른 프로젝트 회차가 없다 — 팀 전체 회차는 있다", async () => {
    renderLife();
    await userEvent.click(screen.getByRole("button", { name: "회차 닫기" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("combobox", { name: /안 끝난 티켓/ }));
    const labels = within(await screen.findByRole("listbox"))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(labels.some((l) => l.includes("다음 회차"))).toBe(true);
    expect(labels.some((l) => l.includes("팀 전체 회차"))).toBe(true);
    // 고르면 서버 거절만 보는 후보는 애초에 안 보여 준다.
    expect(labels.some((l) => l.includes("지난 회차"))).toBe(false);
    expect(labels.some((l) => l.includes("이웃 회차"))).toBe(false);
  });

  it("🔴 회차 목록의 신원이 바뀌어도 고른 이월 대상을 덮지 않는다", async () => {
    const { rerender } = renderLife();
    await userEvent.click(screen.getByRole("button", { name: "회차 닫기" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("combobox", { name: /안 끝난 티켓/ }));
    await userEvent.click(await screen.findByRole("option", { name: "백로그로 되돌림" }));
    expect(
      within(dialog).getByRole("combobox", { name: /안 끝난 티켓/ }).textContent
    ).toContain("백로그로 되돌림");

    // 폴링·무효화가 준 「내용은 같고 신원만 새」 배열 — 예전에는 이 순간 선택이
    // 첫 항목으로 조용히 리셋됐다.
    const qcWrap = (
      <QueryClientProvider client={new QueryClient()}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <SprintLifecycle sprint={sprint()} sprints={OTHERS.map((s) => ({ ...s }))} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    );
    rerender(qcWrap);
    expect(
      within(screen.getByRole("dialog")).getByRole("combobox", { name: /안 끝난 티켓/ }).textContent
    ).toContain("백로그로 되돌림");
  });

  it("회차 수정이 PATCH 를 부른다", async () => {
    renderLife();
    await userEvent.click(screen.getByRole("button", { name: "회차 관리" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "회차 수정" }));
    const dialog = await screen.findByRole("dialog");
    const name = within(dialog).getByLabelText(/이름/);
    await userEvent.clear(name);
    await userEvent.type(name, "고친 회차");
    await userEvent.click(within(dialog).getByRole("button", { name: "저장" }));
    await waitFor(() => {
      const call = apiMock.mock.calls.find(([p, o]) => o && o.method === "PATCH");
      expect(call).toBeTruthy();
      expect(String(call[0])).toBe("/api/work/sprints/sp-1");
      expect(call[1].body.name).toBe("고친 회차");
    });
  });

  it("삭제는 planned 회차에만 뜨고, 확인 뒤 DELETE 를 부른다", async () => {
    // active 에는 삭제 항목이 없다.
    const { unmount } = renderLife();
    await userEvent.click(screen.getByRole("button", { name: "회차 관리" }));
    expect(screen.queryByRole("menuitem", { name: "회차 삭제" })).toBeNull();
    await userEvent.keyboard("{Escape}");
    unmount();

    renderLife({ sprint: sprint({ state: "planned" }) });
    await userEvent.click(screen.getByRole("button", { name: "회차 관리" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "회차 삭제" }));
    // 확인 대화상자 — 되돌릴 수 없는 동작이다.
    const confirmDialog = await screen.findByRole("dialog");
    await userEvent.click(within(confirmDialog).getByRole("button", { name: "삭제" }));
    await waitFor(() => {
      const call = apiMock.mock.calls.find(([p, o]) => o && o.method === "DELETE");
      expect(call).toBeTruthy();
      expect(String(call[0])).toBe("/api/work/sprints/sp-1");
    });
  });

  it("회차 열기가 state API 를 부른다", async () => {
    renderLife({ sprint: sprint({ state: "planned" }) });
    await userEvent.click(screen.getByRole("button", { name: "회차 열기" }));
    await waitFor(() => {
      const call = apiMock.mock.calls.find(([p]) => String(p).includes("/state"));
      expect(call).toBeTruthy();
      expect(call[1].body).toEqual({ state: "active" });
    });
  });
});
