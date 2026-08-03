import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 화면 위쪽 띠 3종(PLAN Phase 6).
 *
 * 여기서 못박는 것은 "예쁘게 그려지는가"가 아니라 **거짓말을 하지 않는가**다:
 *   - 정상일 때는 아무 띠도 뜨지 않는다(늘 떠 있으면 아무도 안 읽는다).
 *   - 임퍼소네이션 중이면 닫을 수 없는 띠가 뜨고, 종료 버튼이 실제로 stop 을 부른다.
 *   - 공지를 닫으면 서버에 dismiss 를 보낸다(브라우저에만 숨기지 않는다 — 그러면 다른 PC
 *     에서 다시 뜬다).
 *   - 배너 API 가 실패해도 화면에 오류가 뜨지 않는다(본문은 멀쩡한데 앱이 고장 난 것처럼
 *     보이는 것이 가장 나쁜 결과다).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Banners } from "./Banners.jsx";

const QUIET = {
  "/api/admin/impersonation/state": { impersonating: false },
  "/api/system/status": { notices: [], checked_at: "2026-08-03T00:00:00", poll_seconds: 120 },
  "/api/announcements": { items: [] },
};

function mockRoutes(overrides = {}) {
  const table = { ...QUIET, ...overrides };
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

function renderBanners() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Banners />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  mockRoutes();
});

describe("화면 위쪽 띠", () => {
  it("전부 정상이면 아무 띠도 그리지 않는다", async () => {
    const { container } = renderBanners();
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
    renderBanners();
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("홍길동");
    expect(banner).toHaveTextContent("읽기 전용");
    expect(banner).toHaveTextContent("차단된 변경 시도 2건");
    // 닫기(X)가 없어야 한다 — 임퍼소네이션 배너는 끌 수 없다.
    expect(screen.queryByRole("button", { name: /^닫기$/ })).not.toBeInTheDocument();

    const stopCalls = [];
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") { stopCalls.push(path); return Promise.resolve({ ok: true }); }
      return Promise.resolve(QUIET[path] || {});
    });
    await userEvent.click(screen.getByRole("button", { name: /대리 보기 종료/ }));
    await waitFor(() => expect(stopCalls).toContain("/api/admin/impersonation/stop"));
  });

  it("동기화가 늦으면 사실만 담백하게 알린다", async () => {
    mockRoutes({
      "/api/system/status": {
        notices: [{
          id: "sync.tickets",
          level: "warning",
          message: "지금 티켓 동기화가 늦어지고 있습니다. 마지막으로 정상 갱신된 지 22분 지났습니다 — 최근 변경이 아직 안 보일 수 있습니다.",
          since: "2026-08-03T00:00:00",
        }],
        poll_seconds: 120,
      },
    });
    renderBanners();
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("티켓 동기화가 늦어지고");
    expect(banner).toHaveTextContent("마지막 정상");
  });

  it("공지를 닫으면 서버에 dismiss 를 보낸다", async () => {
    mockRoutes({
      "/api/announcements": {
        items: [{
          id: "a-1", title: "정기 점검", body: "토요일 02:00~04:00",
          level: "warning", dismissible: true, link_url: null, link_label: null,
        }],
      },
    });
    renderBanners();
    expect(await screen.findByText("정기 점검")).toBeInTheDocument();

    const posted = [];
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") { posted.push(path); return Promise.resolve({ ok: true, dismissed: true }); }
      return Promise.resolve(QUIET[path] || { items: [] });
    });
    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() => expect(posted).toContain("/api/announcements/a-1/dismiss"));
  });

  it("닫을 수 없는 공지에는 닫기 버튼이 없다", async () => {
    mockRoutes({
      "/api/announcements": {
        items: [{ id: "a-2", title: "필수 안내", body: "", level: "critical", dismissible: false }],
      },
    });
    renderBanners();
    expect(await screen.findByText("필수 안내")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /close/i })).not.toBeInTheDocument();
  });

  it("배너 API 가 죽어도 화면에 오류를 띄우지 않는다", async () => {
    mockRoutes({
      "/api/system/status": new Error("boom"),
      "/api/announcements": new Error("boom"),
      "/api/admin/impersonation/state": new Error("boom"),
    });
    const { container } = renderBanners();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(container.textContent).not.toMatch(/오류|실패|boom/);
  });
});
