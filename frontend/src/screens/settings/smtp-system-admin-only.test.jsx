import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/* 메일 서버 설정은 설정 표에서 고치지 않는다 (D-545 · D-548).
 *
 * qa-contract-change: 예전에는 설정 표가 메일 서버 설정(`smtp`) 줄을 전역 관리자에게 열람 전용으로 열었다. 이제 메일 서버 설정은 메일 화면의
 * 설정 탭이 전용 API 로 다루고 범용 설정 API 는 그 키를 거절한다 - 그래서 설정 표는 그 줄을 그리지 않고, 옛 주소(`?setting=smtp`)는 메일 화면으로
 * 보낸다. 「시스템 관리자가 아니면 바꿀 수 없다」는 성질은 서버(`tests/integration/test_mail_settings_api.py`)와 메일 화면 시험
 * (`screens/mail/mail-screen.test.jsx`)이 잰다. 반례(다른 키는 관리자가 그대로 고친다)는 그대로다. */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
let role = "admin";
vi.mock("../../app/auth.jsx", () => ({ useAuth: () => ({ data: { role } }) }));

import { Settings } from "../Settings.jsx";

const PAYLOAD = {
  settings: {
    smtp: {
      value: { enabled: false, host: "", port: 587, security: "starttls", from_address: "", from_name: "", username: "", timeout_seconds: 20 },
      type: "object", description: "메일 발송에 쓸 서버 정보", restart_required: false, is_default: true,
    },
    conversation_retention_days: { value: 90, type: "int", description: "대화 보존", restart_required: false, is_default: true },
  },
};

beforeEach(() => {
  window.location.hash = "";
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) return Promise.resolve(PAYLOAD);
    return Promise.resolve({});
  });
});

function renderSettings(path = "/settings") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/mail" element={<div>메일 화면</div>} />
          <Route path="*" element={<Settings />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("메일 서버 설정 — 설정 표에 없다 (D-548)", () => {
  it("설정 표는 메일 서버 설정 줄을 그리지 않는다", async () => {
    role = "system_admin";
    renderSettings();
    await screen.findByRole("row", { name: "상세 보기: 대화 보존 기간(일)" });
    expect(screen.queryByRole("row", { name: "상세 보기: 메일(SMTP) 발송" })).toBeNull();
  });

  it("옛 주소(?setting=smtp)는 메일 화면의 설정 탭으로 간다", async () => {
    role = "system_admin";
    window.location.hash = "#/settings?setting=smtp";
    renderSettings("/settings?setting=smtp");
    expect(await screen.findByText("메일 화면")).toBeInTheDocument();
  });

  it("반례: 다른 키는 관리자가 그대로 고친다", async () => {
    role = "admin";
    const user = userEvent.setup();
    renderSettings();
    const row = await screen.findByRole("row", { name: "상세 보기: 대화 보존 기간(일)" });
    await user.click(row);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText(/열람 전용입니다/)).toBeNull();
  });
});
