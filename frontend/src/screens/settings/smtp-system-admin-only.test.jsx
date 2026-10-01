import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 메일 서버 설정은 시스템 관리자만 바꾼다(D-545). 서버가 그 키를 다른 역할에게 403 으로 막으므로, 설정 표는 전역
 * 관리자에게도 편집기를 열람 전용으로 열고 까닭을 말한다 — 편집기를 열어 두면 저장에서 403 을 받는 막다른 길이다.
 * 반례: 시스템 관리자는 그대로 저장할 수 있다. 다른 키는 관리자가 그대로 고친다. */

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
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) return Promise.resolve(PAYLOAD);
    if (path === "/api/admin/secrets") return Promise.resolve({ items: [{ name: "smtp.password", label: "메일 비밀번호", stored: false }] });
    return Promise.resolve({});
  });
});

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openRow(user, name) {
  const row = await screen.findByRole("row", { name: `상세 보기: ${name}` });
  await user.click(row);
  return screen.findByRole("dialog");
}

describe("메일 서버 설정 — 시스템 관리자 전용 (D-545)", () => {
  it("전역 관리자에게는 열람 전용으로 열리고 까닭을 말한다", async () => {
    role = "admin";
    const user = userEvent.setup();
    renderSettings();
    const dialog = await openRow(user, "메일(SMTP) 발송");
    expect(within(dialog).getByText("열람 전용입니다. 이 설정은 시스템 관리자만 바꿀 수 있습니다.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "저장" })).toBeDisabled();
  });

  it("반례: 시스템 관리자에게는 잠금 문구가 없다", async () => {
    role = "system_admin";
    const user = userEvent.setup();
    renderSettings();
    const dialog = await openRow(user, "메일(SMTP) 발송");
    expect(within(dialog).queryByText(/열람 전용입니다/)).toBeNull();
  });

  it("반례: 다른 키는 관리자가 그대로 고친다", async () => {
    role = "admin";
    const user = userEvent.setup();
    renderSettings();
    const dialog = await openRow(user, "대화 보존 기간(일)");
    expect(within(dialog).queryByText(/열람 전용입니다/)).toBeNull();
  });
});
