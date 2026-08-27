import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
});
