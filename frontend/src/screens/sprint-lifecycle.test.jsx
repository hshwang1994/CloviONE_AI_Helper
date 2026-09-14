import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* qa-contract-change: 회차가 팀의 것이 되어(D-482) 이월 후보의 축이 「같은 프로젝트 또는 팀 전체 회차」에서 「같은 팀의 열린 회차」로 바뀌었고, 닫은 회차의 수정 폼은 이름만 남기며(목표는 기록), 편성 가능 여부를 부르는 화면이 `canPlan` 으로 넘긴다(관리 범위). 팀 미정 회차에 팀을 정해 주는 칸이 새로 붙었다. 단언 수는 늘었다.
 *
 * 회차의 한 바퀴(SprintLifecycle) — 보드·회의가 공유하는 부품.
 *
 *  1) 이월 대화상자의 선택은 **열리는 순간에만** 기본값을 받는다.
 *  2) 이월 후보는 서버 규칙과 같은 축이다 — 같은 팀의 열린 회차만.
 *  3) 회차 수정·삭제가 실제 API 를 부른다 — 삭제 항목은 planned 에만 뜬다.
 *  4) 편성할 수 없는 사람에게는 아무것도 안 그린다(서버 게이트의 화면 쪽 그림자).
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

import { SprintLifecycle, sprintEditFields } from "./SprintLifecycle.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function sprint(over) {
  return {
    id: "sp-1", name: "이번 회차", department_id: "d-a",
    starts_on: "2026-08-24", ends_on: "2026-08-30", state: "active", goal: null,
    ...over,
  };
}

const OTHERS = [
  sprint(),
  sprint({ id: "sp-next", name: "다음 회차", state: "planned" }),
  sprint({ id: "sp-done", name: "지난 회차", state: "closed" }),
  sprint({ id: "sp-other", name: "이웃 팀 회차", state: "planned", department_id: "d-b" }),
  sprint({ id: "sp-none", name: "팀 미정 회차", state: "planned", department_id: null }),
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
    expect(screen.queryByRole("button", { name: "회차 닫기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "회차 열기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "회차 관리" })).toBeNull();
  });

  it("🔴 관리 범위 밖이면(canPlan=false) 운영군이어도 안 그린다 — 보이는 것과 고치는 것은 다른 문이다", () => {
    renderLife({ canPlan: false });
    expect(screen.queryByRole("button", { name: "회차 닫기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "회차 관리" })).toBeNull();
  });

  it("🔴 이월 후보는 같은 팀의 열린 회차뿐이다 — 닫힌 회차·다른 팀·팀 미정 회차는 없다", async () => {
    renderLife();
    await userEvent.click(screen.getByRole("button", { name: "회차 닫기" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("combobox", { name: /안 끝난 티켓/ }));
    const labels = within(await screen.findByRole("listbox"))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(labels.some((l) => l.includes("다음 회차"))).toBe(true);
    expect(labels.some((l) => l.includes("백로그로 되돌림"))).toBe(true);
    expect(labels.some((l) => l.includes("지난 회차"))).toBe(false);
    expect(labels.some((l) => l.includes("이웃 팀 회차"))).toBe(false);
    expect(labels.some((l) => l.includes("팀 미정 회차"))).toBe(false);
  });

  it("같은 팀에 열린 회차가 없으면 백로그가 기본값이다 — 그래도 닫을 수 있다", async () => {
    renderLife({ sprints: [sprint(), sprint({ id: "sp-done", name: "지난 회차", state: "closed" })] });
    await userEvent.click(screen.getByRole("button", { name: "회차 닫기" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("combobox", { name: /안 끝난 티켓/ }).textContent).toContain("백로그로 되돌림");
    await userEvent.click(within(dialog).getByRole("button", { name: "회차 닫기" }));
    await waitFor(() => {
      const call = apiMock.mock.calls.find(([p]) => String(p).includes("/close"));
      expect(call).toBeTruthy();
      expect(call[1].body).toEqual({ target_sprint_id: null });
    });
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
      // 이미 팀이 있는 회차의 팀은 보내지 않는다.
      expect(call[1].body).not.toHaveProperty("department_id");
    });
  });

  it("🔴 닫은 회차의 수정 폼은 이름만이다 — 기간과 목표는 기록이다", () => {
    const closed = sprintEditFields(sprint({ state: "closed" }), []);
    expect(closed.map((f) => f.name)).toEqual(["name"]);
    const open = sprintEditFields(sprint(), []);
    expect(open.map((f) => f.name)).toEqual(["name", "starts_on", "ends_on", "goal"]);
  });

  it("팀 미정 회차의 수정 폼에는 팀을 정하는 칸이 선다", () => {
    const teams = [{ value: "d-a", label: "A팀" }];
    const fields = sprintEditFields(sprint({ department_id: null, state: "planned" }), teams);
    expect(fields.map((f) => f.name)).toEqual(["name", "department_id", "starts_on", "ends_on", "goal"]);
    expect(fields[1].options).toBe(teams);
  });

  it("삭제는 planned 회차에만 뜨고, 확인 뒤 DELETE 를 부른다", async () => {
    const { unmount } = renderLife();
    await userEvent.click(screen.getByRole("button", { name: "회차 관리" }));
    expect(screen.queryByRole("menuitem", { name: "회차 삭제" })).toBeNull();
    await userEvent.keyboard("{Escape}");
    unmount();

    renderLife({ sprint: sprint({ state: "planned" }) });
    await userEvent.click(screen.getByRole("button", { name: "회차 관리" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "회차 삭제" }));
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
