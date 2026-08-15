import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 회귀: 유지보수 모드 on/off, 점검 공지 저장이 '버전 기록' 캐시를 낡게 뒀다.
 *
 * SettingVersions.jsx는 ["settings", key, "versions"]를 캐시 키로 쓰고, SettingsMain.jsx의
 * onSaved는 저장 후 그 키를 함께 무효화한다(주석: "SettingVersions.doRollback과 동일한 이유").
 * ops/Maintenance.jsx의 toggle·saveMsg 뮤테이션은 ["settings"]만 무효화하고 저 키는 빠뜨렸다 —
 * 그래서 저장 직후 "변경 기록"/"버전 기록" 드로어를 열면 기본 staleTime(30초) 안에는 방금 만든
 * 행이 빠진 캐시를 그대로 보여줬다.
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
    if (path === "/api/admin/settings/maintenance_message" && opts && opts.method === "PUT") {
      return Promise.resolve({});
    }
    return Promise.reject(new Error("unexpected api call: " + path + " " + (opts && opts.method)));
  });
}

function renderMaintenance(qc) {
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

beforeEach(() => {
  apiMock.mockReset();
  mmValue = false;
  mockSettingsApi();
});

describe("유지보수 — 버전 기록 캐시 무효화", () => {
  it("모드를 켜면 ['settings','maintenance_mode','versions'] 캐시도 함께 무효화된다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["settings", "maintenance_mode", "versions"], { items: [] });
    expect(qc.getQueryState(["settings", "maintenance_mode", "versions"]).isInvalidated).toBe(false);

    const user = userEvent.setup();
    renderMaintenance(qc);

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 활성화" });
    await user.click(toggleBtn);
    const dialog = await screen.findByRole("dialog", { name: "확인" });
    await user.click(within(dialog).getByRole("button", { name: "유지보수 모드 활성화" }));

    await waitFor(() => {
      expect(qc.getQueryState(["settings", "maintenance_mode", "versions"]).isInvalidated, "모드 변경 기록").toBe(true);
    }, { timeout: 3000 });
  });

  it("점검 공지를 저장하면 ['settings','maintenance_message','versions'] 캐시도 함께 무효화된다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["settings", "maintenance_message", "versions"], { items: [] });
    expect(qc.getQueryState(["settings", "maintenance_message", "versions"]).isInvalidated).toBe(false);

    const user = userEvent.setup();
    renderMaintenance(qc);

    const box = await screen.findByLabelText("점검 공지");
    await user.clear(box);
    await user.type(box, "새 점검 공지입니다.");
    await user.click(await screen.findByRole("button", { name: "공지 저장" }));

    await waitFor(() => {
      expect(qc.getQueryState(["settings", "maintenance_message", "versions"]).isInvalidated, "공지 버전 기록").toBe(true);
    }, { timeout: 3000 });
  });
});
