import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 목록 화면의 자리 규칙 (D-501) — 관리자 화면을 사용자 화면과 같은 질서로.
 *
 *   ① 상세의 빈 값은 한 줄이다. 작업 큐의 상세는 열여덟 줄 중 열 줄이 「-」였다 — 값이 있는 줄 사이에 빈 줄이 끼어
 *      있으면 읽을 것을 찾으려고 「-」 열 개를 다 지나야 한다. 빈 줄들은 마지막 한 줄 「값 없음」이 이름만 나열한다.
 *   ② 「지금 할 일」 문장(요약의 경고)은 요약 **위**다 — 머리 → 지금 할 일 → 요약 → 필터 바 → 목록.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "a1" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { dateCol } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderScreen(config) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter><DataScreen config={config} /></MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
});

const JOB = {
  id: "j1", job_type: "chat_message", status: "queued", attempt_count: 1,
  started_at: null, last_error: null, idempotency_key: "", message_id: null, user_id: "u-1",
};

const CONFIG = {
  key: "jobs", area: "운영", title: "작업 큐", endpoint: "/api/admin/jobs",
  columns: [
    { key: "job_type", label: "유형", type: "enum", render: (r) => (r.job_type === "chat_message" ? "채팅 메시지" : r.job_type) },
    { key: "attempt_count", label: "시도", type: "count" },
    { key: "last_error", label: "오류", type: "text", render: (r) => r.last_error || "-" },
  ],
  detailFields: [
    { key: "id", label: "작업 ID" },
    { key: "idempotency_key", label: "중복 방지 키" },
    { key: "user_id", label: "요청자 계정 ID" },
    { key: "message_id", label: "메시지 ID" },
    dateCol("started_at", "시작"),
  ],
};

async function openDetail() {
  apiMock.mockImplementation(() => Promise.resolve({ items: [JOB], total: 1 }));
  renderScreen(CONFIG);
  const cell = await screen.findByText("채팅 메시지");
  await userEvent.click(cell.closest("tr"));
  return screen.findByRole("dialog");
}

describe("상세의 빈 값은 한 줄이다 (D-501)", () => {
  it("값이 있는 줄만 차례대로 서고, 빈 줄은 마지막 「값 없음」 한 줄이 이름만 나열한다", async () => {
    const dialog = await openDetail();
    // 값 없는 넷(오류 · 중복 방지 키 · 메시지 ID · 시작)은 각자 줄을 갖지 않는다.
    expect(within(dialog).queryAllByText("-")).toHaveLength(0);
    const empty = dialog.querySelector("[data-detail-empty]");
    expect(empty).not.toBeNull();
    expect(empty).toHaveTextContent("오류, 중복 방지 키, 메시지 ID, 시작");
    // 「값 없음」은 마지막 줄이다 — 값이 있는 줄(유형 · 시도 · 작업 ID · 요청자)이 모두 그 앞이다.
    const text = dialog.textContent;
    expect(text.indexOf("값 없음")).toBeGreaterThan(text.indexOf("요청자 계정 ID"));
    expect(within(dialog).getByText("u-1")).toBeInTheDocument();
    expect(within(dialog).getByText("j1")).toBeInTheDocument();
  });

  it("반례 — 빈 값이 없으면 「값 없음」 줄도 없다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [{ ...JOB, started_at: "2026-08-24T03:00:00Z", last_error: "연결 시간 초과", idempotency_key: "k-1", message_id: "m-1" }],
      total: 1,
    }));
    renderScreen(CONFIG);
    const cell = await screen.findByText("채팅 메시지");
    await userEvent.click(cell.closest("tr"));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.querySelector("[data-detail-empty]")).toBeNull();
    expect(within(dialog).queryByText("값 없음")).toBeNull();
    expect(within(dialog).getByText("k-1")).toBeInTheDocument();
  });
});

describe("「지금 할 일」 문장은 요약 위다 (D-501)", () => {
  it("요약의 경고 문장이 요약 줄보다 먼저 선다", async () => {
    apiMock.mockImplementation((url) => {
      if (String(url).includes("/schedule")) {
        return Promise.resolve({ schedule: { enabled: false, keep: 14, keep_days: 7 }, warnings: ["백업이 앱과 같은 디스크에만 있습니다."] });
      }
      return Promise.resolve({ items: [{ id: "b1", name: "백업 하나" }], total: 1 });
    });
    const { container } = renderScreen({
      key: "backup", area: "운영", title: "백업", endpoint: "/api/admin/backups",
      columns: [{ key: "name", label: "이름", type: "identifier" }],
      summary: {
        endpoint: "/api/admin/backups/schedule",
        kind: "meta",
        cards: (d) => [{ value: String(d.schedule.keep), label: "보관 개수" }],
        notes: (d) => d.warnings,
      },
    });
    const warning = await screen.findByText("백업이 앱과 같은 디스크에만 있습니다.");
    const summary = await screen.findByRole("group", { name: "요약" });
    // DOCUMENT_POSITION_FOLLOWING(4) — 요약이 경고 **뒤**에 있다.
    expect(warning.compareDocumentPosition(summary) & 4).toBe(4);
    expect(container.querySelector(".k-metabar")).toBe(summary);
  });
});
