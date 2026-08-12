import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* CONC-01: DataScreen.jsx의 공용 수정 폼이 화면에 보이는 모든 필드를 매번 재전송했다 — 두
 * 관리자가 같은 행을 열면 나중 저장이 앞사람의 변경을 조용히 되돌렸다(config_version은 존재·
 * 증가·응답까지 다 되는데 왕복도 검사도 안 함). Users.jsx만 diffFields로 이 문제를 피했고,
 * 나머지 27개 등록 화면(DataScreen.jsx의 공용 edit 경로)은 그대로였다 — 같은 diffFields를
 * 그 공용 경로에도 적용한다.
 *
 * departments(edit.fields: 이름 + 상위 부서 2개)로 대표 검증한다: 이름만 고쳐도 상위 부서가
 * PATCH body에 안 실리는지, 아무것도 안 바꾸면 서버 왕복 자체가 없는지 확인한다.
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
// MUI 화면 하나를 jsdom에서 그리는 데 1초 가까이 걸린다(admin-uiux.test.jsx와 같은 이유) — 기본
// 테스트 제한(5초)이 위 대기 상한보다 짧으면 실패가 항상 "Test timed out"으로 뭉개져 실제
// 어긋난 값이 보고서에 안 남는다.
vi.setConfig({ testTimeout: 20000 });

const DEPT = {
  id: "dep-1", name: "영업팀", org_name: "클로비원", org_id: "org-1",
  active: true, user_count: 0, created_at: "2026-08-01T00:00:00Z", parent_id: null,
};

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
  apiMock.mockImplementation((path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (String(path).startsWith("/api/admin/departments") && method === "GET") {
      return Promise.resolve({ items: [DEPT], total: 1 });
    }
    if (method === "PATCH") return Promise.resolve({ department: { ...DEPT, name: "영업2팀" } });
    return Promise.resolve({});
  });
});
afterEach(() => { window.location.hash = ""; });

async function openEditForm(user) {
  const cell = await screen.findByText("영업팀", {}, WAIT);
  await user.click(within(cell.closest("tr")).getByRole("button", { name: /상세/ }));
  const drawer = await screen.findByRole("dialog", {}, WAIT);
  await user.click(within(drawer).getByRole("button", { name: "수정" }));
  const dialogs = await screen.findAllByRole("dialog", {}, WAIT);
  return dialogs[dialogs.length - 1];
}

describe("CONC-01 — DataScreen 공용 수정 폼이 바뀐 필드만 보낸다", () => {
  it("이름만 고치면 PATCH body에 이름만 실린다(건드리지 않은 상위 부서는 안 실린다)", async () => {
    const user = userEvent.setup();
    renderScreen("departments");
    const dialog = await openEditForm(user);

    const nameField = within(dialog).getByRole("textbox", { name: /부서 이름/ });
    await user.clear(nameField);
    await user.type(nameField, "영업2팀");
    await user.click(within(dialog).getByRole("button", { name: "저장" }));

    await waitFor(() => {
      const patchCall = apiMock.mock.calls.find((c) => c[0] === "/api/admin/departments/dep-1" && c[1] && c[1].method === "PATCH");
      expect(patchCall).toBeTruthy();
      expect(patchCall[1].body).toEqual({ name: "영업2팀" });
    }, WAIT);
  });

  it("아무것도 안 바꾸고 저장하면 PATCH 요청 자체가 안 나가고 안내만 뜬다", async () => {
    const user = userEvent.setup();
    renderScreen("departments");
    const dialog = await openEditForm(user);

    await user.click(within(dialog).getByRole("button", { name: "저장" }));

    await screen.findByText("변경된 내용이 없습니다.", {}, WAIT);
    expect(apiMock.mock.calls.some((c) => c[1] && c[1].method === "PATCH")).toBe(false);
  });
});
