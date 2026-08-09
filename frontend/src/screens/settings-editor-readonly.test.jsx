import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 읽기 전용 역할(operator)에게 SettingEditor 의 버튼이 **사라지지 않고 비활성으로 남는지** 본다.
 *
 * 예전엔 `{canWrite ? <Button>…</Button> : null}` 로 통째로 안 그렸다 — 같은 실수를
 * Maintenance.jsx 가 먼저 겪고 "비활성 + 이유 문구(aria-describedby)"로 고쳤는데
 * SettingEditor 는 그 관례를 못 받았다. 버튼이 사라지면 스크린리더 사용자는 그 기능이
 * 아예 없는 화면으로 인식한다 — '있지만 지금은 못 누른다'와 다른 경험이다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "operator" } }),
}));

import { Settings } from "./Settings.jsx";

const PAYLOAD = {
  settings: {
    conversation_retention_days: { value: 90, type: "int", description: "대화 보존", restart_required: false, is_default: true },
  },
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) {
      return Promise.resolve(PAYLOAD);
    }
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

describe("SettingEditor — 읽기 전용 역할(operator)", () => {
  it("'미리 검증'·'저장' 버튼이 사라지지 않고 비활성으로 남으며, 이유와 연결된다", async () => {
    const user = userEvent.setup();
    renderSettings();
    const btn = await screen.findByRole("button", { name: "상세 보기: 대화 보존 기간(일)" });
    await user.click(btn);

    const check = await screen.findByRole("button", { name: "미리 검증" });
    const save = screen.getByRole("button", { name: "저장" });
    expect(check).toBeDisabled();
    expect(save).toBeDisabled();
    expect(check).toHaveAttribute("aria-describedby", "setting-locked-reason");
    expect(save).toHaveAttribute("aria-describedby", "setting-locked-reason");
    expect(screen.getByText(/열람 전용입니다/)).toHaveAttribute("id", "setting-locked-reason");
  });
});
