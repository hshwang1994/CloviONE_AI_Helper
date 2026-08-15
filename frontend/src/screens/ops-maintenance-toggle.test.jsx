import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 유지보수 모드 전환의 실제 확인/전송 흐름.
 *
 * ops-maintenance.test.jsx는 쓰기 권한이 없을 때 버튼이 "보이되 비활성"인지만 확인한다 —
 * 쓰기 권한이 있는 관리자가 실제로 버튼을 눌렀을 때 확인 대화상자가 뜨고, 취소하면 아무 일도
 * 일어나지 않고, 확인하면 정확한 값으로 PUT이 나가는지는 어느 테스트도 거치지 않았다.
 * 점검 공지의 '미리 검증' 실패 표시도 마찬가지로 비어 있었다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "admin", id: "u-1" } }),
}));

import { Maintenance } from "./Ops.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderMaintenance() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Maintenance />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

let mmValue;
function mockSettingsApi() {
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) {
      return Promise.resolve({
        settings: {
          maintenance_mode: { value: mmValue },
          maintenance_message: { value: "점검 중입니다." },
        },
      });
    }
    if (path === "/api/admin/settings/maintenance_mode" && opts && opts.method === "PUT") {
      mmValue = opts.body.value;
      return Promise.resolve({});
    }
    return Promise.reject(new Error("unexpected api call: " + path + " " + (opts && opts.method)));
  });
}

beforeEach(() => {
  apiMock.mockReset();
  mmValue = false;
  mockSettingsApi();
});

describe("유지보수 모드 전환 — 확인 대화상자", () => {
  it("활성화할까요? 확인 후 승인하면 PUT이 나가고, 배너·버튼 라벨이 활성으로 바뀐다", async () => {
    const user = userEvent.setup();
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 활성화" });
    await user.click(toggleBtn);

    const dialog = await screen.findByRole("dialog", { name: "확인" });
    expect(dialog).toHaveTextContent(/유지보수 모드를 활성화할까요\?/);
    await user.click(within(dialog).getByRole("button", { name: "유지보수 모드 활성화" }));

    expect(await screen.findByText("유지보수 모드를 전환했습니다.")).toBeInTheDocument();
    // 낙관적으로 먼저 바뀌지 않는다 — 서버 값(무효화 후 재조회)을 따라 배너/버튼이 뒤늦게 활성으로 바뀐다.
    expect(await screen.findByRole("button", { name: "유지보수 모드 비활성화" })).toBeInTheDocument();
    expect(screen.getByText(/현재 유지보수 모드가 활성화되어 있습니다/)).toBeInTheDocument();

    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/maintenance_mode" && o && o.method === "PUT");
    expect(putCall[1].body).toEqual({ value: true });
  });

  it("취소하면 PUT이 나가지 않고 상태가 그대로다", async () => {
    const user = userEvent.setup();
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 활성화" });
    await user.click(toggleBtn);

    const dialog = await screen.findByRole("dialog", { name: "확인" });
    await user.click(within(dialog).getByRole("button", { name: "취소" }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "확인" })).toBeNull());
    expect(screen.getByRole("button", { name: "유지보수 모드 활성화" })).toBeInTheDocument();
    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/maintenance_mode" && o && o.method === "PUT");
    expect(putCall).toBeUndefined();
  });

  it("이미 활성화된 상태에서는 비활성화하는 문구로 확인한다", async () => {
    mmValue = true;
    const user = userEvent.setup();
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 비활성화" });
    await user.click(toggleBtn);

    const dialog = await screen.findByRole("dialog", { name: "확인" });
    expect(dialog).toHaveTextContent("유지보수 모드를 비활성화할까요?");
    await user.click(within(dialog).getByRole("button", { name: "유지보수 모드 비활성화" }));

    expect(await screen.findByRole("button", { name: "유지보수 모드 활성화" })).toBeInTheDocument();
    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/maintenance_mode" && o && o.method === "PUT");
    expect(putCall[1].body).toEqual({ value: false });
  });
});

describe("점검 공지 — 미리 검증 실패 표시", () => {
  it("검증이 실패하면 필드 옆에 오류가 남고, 토스트도 함께 뜬다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) {
        return Promise.resolve({
          settings: {
            maintenance_mode: { value: false },
            maintenance_message: { value: "점검 중입니다." },
          },
        });
      }
      if (path === "/api/admin/settings/maintenance_message/dry-run" && opts && opts.method === "POST") {
        return Promise.reject(new Error("공지 문구가 너무 깁니다."));
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderMaintenance();

    await user.click(await screen.findByRole("button", { name: "미리 검증" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("공지 문구가 너무 깁니다.");
    expect(await screen.findByText("공지 문구가 너무 깁니다.")).toBeInTheDocument(); // 토스트
  });
});
