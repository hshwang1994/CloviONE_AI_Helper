import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* WF44 배경 조사(L축 재감사, 2026-08-13) — `Dashboard.jsx`의 `WorkSection`이 그리는 "차질
 * 프로젝트"/"지연 마일스톤"은 `["home","work-dashboard"]`(staleTime 60초)에서 온다. 그런데
 * `project-queries.js`의 모든 쓰기 훅이 공유하는 `invalidateProject()`는 `["projects",...]`만
 * 무효화하고 `["home"]`은 안 건드려, 마일스톤·프로젝트를 고쳐도 대시보드가 최소 60초(탭을 안
 * 벗어나면 그 이상) stale하게 남았다. 반대 방향(`ticket-views.js::TICKET_VIEW_KEYS`가 이미
 * `"projects"`를 포함해 티켓 편집은 프로젝트 캐시에 닿음)은 이미 돼 있던 것과 비교하면 이
 * 한 방향만 빠져 있었다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u1" } }),
}));

import { useUpdateMilestone } from "./project-queries.js";

function wrapper(qc) {
  return ({ children }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ milestone: { id: "m1" } });
});

describe("마일스톤 수정 → 프로젝트 캐시뿐 아니라 home(대시보드) 캐시도 무효화한다", () => {
  it("useUpdateMilestone 성공 시 ['home']이 무효화된다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["home", "work-dashboard"], {
      projects: { troubled: { count: 0, items: [] } },
      milestones: { overdue: { count: 0, items: [] } },
    });
    qc.setQueryData(["projects", "one", "p1"], { id: "p1" });
    expect(qc.getQueryState(["home", "work-dashboard"]).isInvalidated, "home").toBe(false);

    const { result } = renderHook(() => useUpdateMilestone("p1"), { wrapper: wrapper(qc) });
    await act(async () => {
      result.current.mutate({ id: "m1", body: { due_date: "2026-09-01" } });
    });

    await waitFor(() => {
      expect(qc.getQueryState(["home", "work-dashboard"]).isInvalidated, "home").toBe(true);
      // 기존 계약(프로젝트 캐시 자체)이 이번 수정으로 깨지지 않았는지도 함께 확인한다.
      expect(qc.getQueryState(["projects", "one", "p1"]).isInvalidated, "projects").toBe(true);
    });
  });
});
