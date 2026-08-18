import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* CONC-02: maintenance_state는 서킷 브레이커(연속 실패 → degraded, 성공 → normal)와 관리자
 * 편집 폼이 같이 쓰는 필드였다 — 관리자 A가 '점검'으로 내려 배분을 멈춘 것을, 다른 칸만 고친
 * 관리자 B의 낡은 편집 폼 제출이 조용히 되돌릴 수 있었다(diffFields로 무관한 필드만 고친
 * 경우는 CONC-01이 막지만, 이 필드는 워낙 위험해 편집 폼에서 아예 빼고 확인 문구가 있는
 * 전용 액션으로만 바꾸게 한다).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { clickAction } from "../test-helpers/actions.js";

function renderScreen(key) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY[key]} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });
const confirmDialog = () => screen.findByRole("dialog", { name: "확인" }, WAIT);

const RUNNER = {
  id: "run-1", name: "기본 러너", enabled: true, maintenance_state: "degraded",
  last_health_status: "healthy", consecutive_failures: 2, config_version: 3,
  base_url: "http://127.0.0.1:8790", owner: "운영팀", version: "1.0",
  auth_type: "none", secret_ref: null, health_url: null, timeout_seconds: 60,
  concurrency_limit: 1, circuit_open_until: null, provider_type: "local_http",
  description: "", created_at: "2026-08-01T00:00:00Z",
};

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
  apiMock.mockImplementation((path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (String(path).startsWith("/api/admin/runners") && method === "GET") {
      return Promise.resolve({ items: [RUNNER] });
    }
    if (method === "PATCH") return Promise.resolve({ runner: { ...RUNNER, maintenance_state: "maintenance" } });
    return Promise.resolve({});
  });
});
afterEach(() => { window.location.hash = ""; });

async function openDrawer(user) {
  const cell = await screen.findByText("기본 러너", {}, WAIT);
  await user.click(cell.closest("tr"));
  return screen.findByRole("dialog", {}, WAIT);
}

describe("CONC-02 — 러너 점검 상태는 일반 편집 폼이 아니라 전용 액션으로만 바꾼다", () => {
  it("'수정' 폼에는 점검 상태 필드가 없다", async () => {
    const user = userEvent.setup();
    renderScreen("runners");
    const drawer = await openDrawer(user);
    await user.click(within(drawer).getByRole("button", { name: "수정" }));
    const dialogs = await screen.findAllByRole("dialog", {}, WAIT);
    const editDialog = dialogs[dialogs.length - 1];
    expect(within(editDialog).queryByRole("combobox", { name: /점검 상태/ })).not.toBeInTheDocument();
  });

  it("'점검 상태 변경' 액션은 확인을 먼저 받고, 고른 값만 PATCH된다", async () => {
    const user = userEvent.setup();
    renderScreen("runners");
    const drawer = await openDrawer(user);
    await clickAction(user, drawer, "점검 상태 변경");

    // 확인이 먼저 — 현재 상태를 말하고, 이 시점엔 아직 요청도 폼도 없다.
    const dlg = await confirmDialog();
    expect(dlg).toHaveTextContent(/성능 저하/);
    expect(apiMock.mock.calls.some((c) => c[1] && c[1].method === "PATCH")).toBe(false);
    expect(screen.queryByRole("combobox", { name: "점검 상태" })).not.toBeInTheDocument();

    await user.click(within(dlg).getByRole("button", { name: "점검 상태 변경" }));

    const formDialog = await screen.findByRole("dialog", { name: "점검 상태 변경" }, WAIT);
    await user.click(within(formDialog).getByRole("combobox", { name: "점검 상태" }));
    await user.click(await screen.findByRole("option", { name: "점검" }, WAIT));
    await user.click(within(formDialog).getByRole("button", { name: "점검 상태 변경" }));

    await waitFor(() => {
      const patchCall = apiMock.mock.calls.find((c) => c[0] === "/api/admin/runners/run-1" && c[1] && c[1].method === "PATCH");
      expect(patchCall).toBeTruthy();
      expect(patchCall[1].body).toEqual({ maintenance_state: "maintenance" });
    }, WAIT);
  });
});
