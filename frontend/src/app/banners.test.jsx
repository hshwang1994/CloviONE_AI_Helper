import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 화면 위쪽 띠 — **임퍼소네이션 하나만 남는다** (지시 1·55·67).
 *
 * 지시 1 로 상단의 `안내`·`장애` 알림 영역을 걷어냈다. 그래서 이 파일의 계약이 바뀌었다:
 * 예전에는 "CRITICAL 이면 한 줄이 뜬다"를 못박았는데, 지금은 **어떤 시스템 알림도 여기
 * 뜨지 않는다**는 것을 못박는다. 그 정보는 사라진 게 아니라 종(NotificationBell) 안의
 * "시스템 상태" 묶음으로 갔다 — notification-bell-system-notices.test.jsx 가 그쪽을 덮는다.
 *
 * **임퍼소네이션은 남는다.** 알림이 아니라 보안 상태 표시이기 때문이다(지시 55) — 지금
 * 남의 눈으로 보고 있다는 사실은 접혀 있으면 안 된다.
 *
 * 여기서 못박는 것:
 *   - 임퍼소네이션이 아니면 아무 띠도 뜨지 않는다(장애가 있어도).
 *   - 임퍼소네이션 중이면 닫을 수 없는 띠가 뜨고, 종료가 실제 API를 부른다.
 *   - 임퍼소네이션 API가 죽어도 화면에 오류가 뜨지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Banners } from "./Banners.jsx";

const QUIET_IMPERSONATION = { "/api/admin/impersonation/state": { impersonating: false } };

function mockRoutes(overrides = {}) {
  const table = { ...QUIET_IMPERSONATION, ...overrides };
  apiMock.mockImplementation((path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (method !== "GET") return Promise.resolve({ ok: true });
    if (path in table) {
      const value = table[path];
      return value instanceof Error ? Promise.reject(value) : Promise.resolve(value);
    }
    return Promise.resolve({});
  });
}

// useStatusNotices()가 실제로 돌려주는 모양을 손으로 흉내 낸다 — Banners는 이 값을 그대로
// CriticalStatusLine에 넘기기만 하므로, 여기서는 그 껍데기(prop 계약)만 검증하면 된다.
function fakeNotices(visible) {
  const counts = { critical: 0, warning: 0, info: 0 };
  for (const n of visible) counts[n.level] = (counts[n.level] || 0) + 1;
  return { isLoading: false, isError: false, all: visible, visible, counts, dismiss: vi.fn() };
}

function renderBanners(notices, overrides) {
  if (overrides) mockRoutes(overrides);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Banners notices={notices} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  mockRoutes();
});

describe("화면 위쪽 띠", () => {
  it("임퍼소네이션도 CRITICAL 항목도 없으면 아무 띠도 그리지 않는다", async () => {
    const { container } = renderBanners(fakeNotices([]));
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(container.textContent.trim()).toBe("");
  });

  it("임퍼소네이션 중이면 읽기 전용이라고 말하고, 종료가 실제 API를 부른다", async () => {
    mockRoutes({
      "/api/admin/impersonation/state": {
        impersonating: true,
        actor_name: "관리자 A",
        target_id: "u-9",
        target_name: "홍길동",
        target_email: "hong@goodmit.co.kr",
        blocked_write_count: 2,
      },
    });
    renderBanners(fakeNotices([]));
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("홍길동");
    expect(banner).toHaveTextContent("읽기 전용");
    expect(banner).toHaveTextContent("차단된 변경 시도 2건");
    // 닫기(X)가 없어야 한다 — 임퍼소네이션 배너는 끌 수 없다.
    expect(screen.queryByRole("button", { name: /^닫기$/ })).not.toBeInTheDocument();

    const stopCalls = [];
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") { stopCalls.push(path); return Promise.resolve({ ok: true }); }
      return Promise.resolve(QUIET_IMPERSONATION[path] || {});
    });
    await userEvent.click(screen.getByRole("button", { name: /대리 보기 종료/ }));
    await waitFor(() => expect(stopCalls).toContain("/api/admin/impersonation/stop"));
  });

  it("임퍼소네이션 API가 죽어도 화면에 오류를 띄우지 않는다", async () => {
    mockRoutes({ "/api/admin/impersonation/state": new Error("boom") });
    const { container } = renderBanners(fakeNotices([]));
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(container.textContent).not.toMatch(/오류|실패|boom/);
  });

  it("CRITICAL 장애가 있어도 상단에 띠를 그리지 않는다 (지시 1 — 종이 단일 진입점)", async () => {
    const { container } = renderBanners(fakeNotices([
      { id: "sync.tickets", level: "critical", message: "지금 티켓 동기화가 멈춰 있습니다.", kind: "sync" },
    ]));
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/멈춰 있습니다/);
  });

  it("WARNING/INFO 도 마찬가지로 상단에 뜨지 않는다", async () => {
    const { container } = renderBanners(fakeNotices([
      { id: "sync.tickets", level: "warning", message: "지금 티켓 동기화가 늦어지고 있습니다.", kind: "sync" },
    ]));
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/늦어지고 있습니다/);
  });

  it("장애 중이어도 임퍼소네이션 띠는 그대로 뜬다 (보안 상태는 접히지 않는다)", async () => {
    renderBanners(fakeNotices([
      { id: "sync.tickets", level: "critical", message: "지금 티켓 동기화가 멈춰 있습니다.", kind: "sync" },
    ]), {
      "/api/admin/impersonation/state": {
        impersonating: true, target_name: "김지혜", actor_name: "UI QA", blocked_write_count: 0,
      },
    });
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("읽기 전용");
    expect(banner).not.toHaveTextContent("멈춰 있습니다");
  });

  it("notices가 아직 없으면(로딩 중 등) 크래시하지 않는다", () => {
    expect(() => renderBanners(undefined)).not.toThrow();
  });
});
