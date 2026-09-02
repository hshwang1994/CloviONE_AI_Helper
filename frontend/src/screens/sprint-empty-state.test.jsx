import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

/* 스프린트 회의 — 회차 0건일 때의 빈 상태 (A2 재검수).
 *
 * 실측: 운영에 회차가 0건인데 `EmptyState` 에 없는 prop `hint` 를 넘겨서 안내 문장
 * 자체가 안 나왔다("아직 만든 스프린트가 없습니다." 한 줄뿐). §8.3 은 이 빈 상태가
 * layout="page" 로 서고 「스프린트 만들기」·「백로그 보기」 둘을 준다고 못 박는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { Sprint } from "./Sprint.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function stub(path) {
  if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
  if (path.startsWith("/api/work/statuses")) return Promise.resolve({ statuses: [] });
  if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: [] });
  return Promise.resolve({});
}

function renderSprint() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Sprint />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("스프린트 회의 — 회차 0건", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(stub);
  });

  it("안내 문장이 실제로 보이고, 만들기/백로그 두 행동이 있다", async () => {
    renderSprint();
    await waitFor(() =>
      expect(screen.getByText("아직 만든 스프린트가 없습니다.")).toBeTruthy(),
    );
    // 예전엔 EmptyState 가 모르는 prop(hint)을 조용히 버려서 이 문장 자체가 없었다.
    expect(screen.getByText(/번다운과 건강, 담당자별 남은 일/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "스프린트 추가" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "백로그 보기" })).toBeTruthy();
  });

  it("스프린트 만들기를 누르면 만들기 대화상자가 열린다", async () => {
    renderSprint();
    const btn = await screen.findByRole("button", { name: "스프린트 추가" });
    btn.click();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    expect(screen.getByRole("heading", { name: "새 스프린트" })).toBeTruthy();
  });

  it("만들기 폼에 프로젝트 칸이 보인다 — 현재 필터값을 조용히 쓰지 않는다", async () => {
    renderSprint();
    (await screen.findByRole("button", { name: "스프린트 추가" })).click();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    // 칸이 안 보이던 시절에는 필터가 「전체」인 채 만들면 모르는 사이 팀 전체 회차가
    // 됐다 — 팀 전체 회차는 조직에 하나만 열 수 있어 동작이 완전히 다르다.
    expect(within(screen.getByRole("dialog")).getByText("프로젝트")).toBeTruthy();
  });
});

describe("스프린트 회의 — 회차는 있는데 열린 것이 없다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/work/sprints")) {
        return Promise.resolve({
          sprints: [{
            id: "sp-9", name: "지난 회차", project_id: "",
            starts_on: "2026-08-01", ends_on: "2026-08-07", state: "closed",
          }],
        });
      }
      return stub(path);
    });
  });

  it("🔴 자동 선택 대신 「회차를 고르세요」 안내가 선다 — 백지가 아니다", async () => {
    renderSprint();
    await screen.findByText("회의할 회차를 고르세요.");
    // 예전에는 이 조합(회차 있음 + 미선택)이 머리+필터만 남는 백지였다 — 폴백 자동
    // 선택은 닫힌 회차의 빈 번다운으로 데려갔고, 빈 상태 조건(회차 0건)도 안 맞았다.
    expect(screen.getByRole("button", { name: "가장 최근 회차 열기" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "스프린트 추가" })).toBeTruthy();
  });
});
