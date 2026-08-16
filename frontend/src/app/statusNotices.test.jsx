import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0016: 시스템 상태·공지를 헤더 칩 + CRITICAL 한 줄로 접은 것의 실제 동작.
 *
 * 여기서 못박는 것:
 *   - 활성 항목이 없으면 칩이 아예 안 그려진다(공간을 안 뺏는다).
 *   - 같은 심각도의 동기화 알림 여럿(티켓+문서 동시 정지 등)은 한 줄로 합쳐진다 — 원문
 *     매칭이 아니라 id 접두어("sync.") 기준.
 *   - 칩을 누르면 패널이 열려 전체 목록이 보인다.
 *   - 동기화류 닫기는 브라우저에만 기억되고(새로고침해도 유지), 심각도가 바뀌면 다시 뜬다.
 *   - 공지류 닫기는 서버로 실제 dismiss 요청을 보낸다(브라우저에만 숨기면 다른 기기에서
 *     다시 뜬다 — 기존 계약 그대로 유지).
 *   - CRITICAL 항목이 있을 때만 상시 노출 한 줄이 뜬다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { StatusChip, CriticalStatusLine, useStatusNotices } from "./StatusNotices.jsx";

const QUIET = {
  "/api/system/status": { notices: [], poll_seconds: 120 },
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

function Harness() {
  const notices = useStatusNotices();
  return (
    <>
      <StatusChip notices={notices} />
      <CriticalStatusLine notices={notices} />
    </>
  );
}

function renderHarness() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Harness />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  mockRoutes();
  window.localStorage.clear();
});

describe("StatusChip / CriticalStatusLine", () => {
  it("활성 항목이 없으면 칩이 안 그려진다", async () => {
    const { container } = renderHarness();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(container.textContent.trim()).toBe("");
  });

  it("WARNING 하나면 칩에 '주의 1'이 뜨고 CRITICAL 줄은 안 뜬다", async () => {
    mockRoutes({
      "/api/system/status": {
        notices: [{ id: "sync.tickets", level: "warning", message: "지금 티켓 동기화가 늦어지고 있습니다.", since: null }],
        poll_seconds: 120,
      },
    });
    renderHarness();
    expect(await screen.findByText(/주의 1/)).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("같은 심각도의 동기화 알림 둘은 칩·패널 모두에서 한 줄로 합쳐진다", async () => {
    mockRoutes({
      "/api/system/status": {
        notices: [
          { id: "sync.tickets", level: "critical", message: "지금 티켓 동기화가 멈춰 있습니다.", since: "2026-08-01T00:00:00" },
          { id: "sync.documents", level: "critical", message: "지금 문서 동기화가 멈춰 있습니다.", since: "2026-08-03T00:00:00" },
        ],
        poll_seconds: 120,
      },
    });
    renderHarness();
    // 칩: "장애 1" — 두 건이 아니라 합쳐진 한 건.
    expect(await screen.findByText(/장애 1/)).toBeInTheDocument();
    // CRITICAL 한 줄에도 "2개 항목"으로 합쳐 나온다.
    const line = await screen.findByRole("status");
    expect(line).toHaveTextContent("2개 항목");
    expect(line).not.toHaveTextContent("티켓 동기화가 멈춰 있습니다.지금"); // 원문 이어붙이기가 아니다.
  });

  it("심각도가 다른 동기화 알림은 합치지 않는다", async () => {
    mockRoutes({
      "/api/system/status": {
        notices: [
          { id: "sync.tickets", level: "critical", message: "지금 티켓 동기화가 멈춰 있습니다.", since: null },
          { id: "sync.documents", level: "warning", message: "지금 문서 동기화가 늦어지고 있습니다.", since: null },
        ],
        poll_seconds: 120,
      },
    });
    renderHarness();
    expect(await screen.findByText(/장애 1, 주의 1/)).toBeInTheDocument();
  });

  it("칩을 누르면 패널이 열려 항목이 보인다", async () => {
    mockRoutes({
      "/api/system/status": {
        notices: [{ id: "sync.tickets", level: "warning", message: "지금 티켓 동기화가 늦어지고 있습니다.", since: null }],
        poll_seconds: 120,
      },
    });
    renderHarness();
    const chip = await screen.findByText(/주의 1/);
    await userEvent.click(chip);
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText(/티켓 동기화가 늦어지고 있습니다/)).toBeInTheDocument();
  });

  it("동기화 알림을 닫으면 브라우저에만 기억되고, 다시 렌더해도 유지된다", async () => {
    mockRoutes({
      "/api/system/status": {
        notices: [{ id: "sync.tickets", level: "warning", message: "지금 티켓 동기화가 늦어지고 있습니다.", since: null }],
        poll_seconds: 120,
      },
    });
    const { unmount } = renderHarness();
    const chip = await screen.findByText(/주의 1/);
    await userEvent.click(chip);
    const panel = await screen.findByRole("dialog");
    await userEvent.click(within(panel).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.queryByText(/주의 1/)).not.toBeInTheDocument());
    // 서버로는 아무 POST도 안 나갔다 — 동기화 알림은 브라우저 기억이지 서버 dismiss가 아니다.
    expect(apiMock.mock.calls.some(([, opts]) => opts && opts.method === "POST")).toBe(false);

    unmount();
    // "새로고침" 흉내 — 같은 localStorage로 다시 마운트하면 여전히 닫혀 있어야 한다.
    renderHarness();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByText(/주의 1/)).not.toBeInTheDocument();
  });

  it("닫은 뒤 심각도가 올라가면 다시 뜬다", async () => {
    mockRoutes({
      "/api/system/status": {
        notices: [{ id: "sync.tickets", level: "warning", message: "지금 티켓 동기화가 늦어지고 있습니다.", since: null }],
        poll_seconds: 120,
      },
    });
    const { unmount } = renderHarness();
    const chip = await screen.findByText(/주의 1/);
    await userEvent.click(chip);
    const panel = await screen.findByRole("dialog");
    await userEvent.click(within(panel).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.queryByText(/주의 1/)).not.toBeInTheDocument());
    unmount();

    // 같은 id지만 이제 critical로 악화됐다.
    mockRoutes({
      "/api/system/status": {
        notices: [{ id: "sync.tickets", level: "critical", message: "지금 티켓 동기화가 멈춰 있습니다.", since: null }],
        poll_seconds: 120,
      },
    });
    renderHarness();
    expect(await screen.findByText(/장애 1/)).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("멈춰 있습니다");
  });

  it("공지를 닫으면 서버에 실제 dismiss 요청을 보낸다(브라우저에만 숨기지 않는다)", async () => {
    mockRoutes({
      "/api/announcements": {
        items: [{ id: "a-1", title: "정기 점검", body: "토요일 02:00~04:00", level: "warning", dismissible: true, link_url: null }],
      },
    });
    renderHarness();
    const chip = await screen.findByText(/주의 1/);
    await userEvent.click(chip);
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText(/정기 점검/)).toBeInTheDocument();

    const posted = [];
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") { posted.push(path); return Promise.resolve({ ok: true, dismissed: true }); }
      return Promise.resolve(QUIET[path] || { items: [] });
    });
    await userEvent.click(within(panel).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(posted).toContain("/api/announcements/a-1/dismiss"));
  });

  it("닫을 수 없는 공지에는 닫기 버튼이 없다", async () => {
    mockRoutes({
      "/api/announcements": {
        items: [{ id: "a-2", title: "필수 안내", body: "", level: "critical", dismissible: false }],
      },
    });
    renderHarness();
    const chip = await screen.findByText(/장애 1/);
    await userEvent.click(chip);
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText(/필수 안내/)).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "닫기" })).not.toBeInTheDocument();
  });

  it("앱 밖으로 나가는 공지 링크는 그리지 않는다", async () => {
    mockRoutes({
      "/api/announcements": {
        items: [{ id: "a-3", title: "안내", body: "", level: "info", dismissible: false, link_url: "javascript:alert(1)" }],
      },
    });
    renderHarness();
    const chip = await screen.findByText(/안내 1/);
    await userEvent.click(chip);
    const panel = await screen.findByRole("dialog");
    expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
  });

  it("시스템 상태 API가 죽어도 공지는 그대로 보인다(부분 실패를 통째 실패로 뭉개지 않는다)", async () => {
    mockRoutes({
      "/api/system/status": new Error("boom"),
      "/api/announcements": { items: [{ id: "a-4", title: "안내", body: "", level: "info", dismissible: false }] },
    });
    renderHarness();
    expect(await screen.findByText(/안내 1/)).toBeInTheDocument();
  });

  it("여러 CRITICAL이 있으면 한 줄만 뜨고 나머지 개수를 덧붙인다", async () => {
    mockRoutes({
      "/api/announcements": {
        items: [
          { id: "a-5", title: "장애 A", body: "", level: "critical", dismissible: false },
          { id: "a-6", title: "장애 B", body: "", level: "critical", dismissible: false },
        ],
      },
    });
    renderHarness();
    const line = await screen.findByRole("status");
    expect(line).toHaveTextContent("장애 A");
    expect(line).toHaveTextContent("그 외 장애 1건");
  });
});
