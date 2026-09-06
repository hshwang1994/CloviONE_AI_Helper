import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* qa-contract-change: 내려받기가 최상위 이동(window.location.href)에서 fetch+Blob 저장으로
 * 바뀌었다(xe-07·ops-03 — 404 응답이 관리 콘솔을 날 JSON 으로 덮던 결함). 그래서 「1.2초
 * 어림 타이머 뒤에 다시 읽는다」는 이 시험의 계약이 「받는 요청이 끝난 것을 알고 다시 읽는다」
 * 로 옮겨졌다. 재는 불변식(내려받은 뒤 목록을 다시 읽는가)은 그대로이고 단언은 늘어난다.
 *
 * 🔴 **내려받기는 행을 바꾼다** (2026-09-01).
 *
 * 백업 내려받기는 서버에 `downloaded_at` 을 남기고(`app/backups/service.py::mark_downloaded`),
 * 그 값이 **다음 행동의 조건**이다: 「서버에서 삭제」는 내려받은 적이 있는 행에만 뜬다
 * (D-204 — 브라우저가 받다 만 것과 다 받은 것을 서버는 구별하지 못하므로, 지우는 것은
 * 사람이 「받았다」고 답한 뒤여야 한다).
 *
 * 그런데 `DataScreen` 의 내려받기 갈래는 주소만 바꾸고 목록을 다시 받지 않은 채 빠져나갔다.
 * 그래서 받은 직후의 화면에는 그 단추가 **여전히 없었다** — 사람이 새로고침을 떠올리기
 * 전까지 D-204 의 두 번째 절반이 화면에서 존재하지 않았다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", email: "a@b.c" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const CONFIG = {
  key: "backup", area: "운영", title: "백업", endpoint: "/api/admin/backups",
  columns: [{ key: "path", label: "파일", identifier: true }],
  actions: [
    { label: "내려받기", download: (_qs, r) => "/api/admin/backups/" + r.id + "/download" },
  ],
};

let fetchMock;
let clickSpy;
let releaseFile;

beforeEach(() => {
  apiMock.mockReset();
  clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  globalThis.URL.createObjectURL = vi.fn(() => "blob:mock/1");
  globalThis.URL.revokeObjectURL = vi.fn();
  // 파일 응답을 **시험이 쥐고 있다** — 「받는 중에는 아직 다시 안 읽는다」를 재려면
  // 그 순간을 붙잡을 수 있어야 한다.
  fetchMock = vi.fn(() => new Promise((resolve) => {
    releaseFile = () => resolve({
      ok: true, status: 200,
      headers: { get: () => 'attachment; filename="db.dump"' },
      blob: () => Promise.resolve(new Blob(["dump"])),
    });
  }));
  globalThis.fetch = fetchMock;
});

afterEach(() => {
  clickSpy.mockRestore();
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <DataScreen config={CONFIG} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("행의 내려받기", () => {
  it("받은 뒤 목록을 다시 읽는다 — 그래야 서버가 남긴 값이 화면의 다음 단추를 켠다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [{ id: "b1", path: "/var/backups/backup-1" }], total: 1,
    }));
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("/var/backups/backup-1");
    const listCallsBefore = apiMock.mock.calls.length;

    await user.click(screen.getByText("/var/backups/backup-1"));
    await user.click(await screen.findByRole("button", { name: "내려받기" }));

    // 받는 요청이 실제로 나갔다.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/backups/b1/download");
    // 아직 안 끝났으면 다시 읽지 않는다 — 그 GET 보다 목록 질의가 먼저 닿으면 여전히 옛 값을 받는다.
    expect(apiMock.mock.calls.length).toBe(listCallsBefore);

    releaseFile();
    await waitFor(() => expect(apiMock.mock.calls.length).toBeGreaterThan(listCallsBefore));
  });
});
