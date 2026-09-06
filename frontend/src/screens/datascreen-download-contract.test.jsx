import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 내려받기의 나머지 절반 — **크기**와 **오류의 모양** (R7-03 · R7-04).
 *
 * xe-07 이 최상위 이동을 없애면서 모든 내려받기가 `fetch` → `res.blob()` 을 지나게 됐다.
 * 감사 CSV 에는 옳다(그래야 404·403 을 화면 안에서 말한다). 그런데 백업 덤프는 데이터베이스
 * 전체다 — 본문이 전부 도착할 때까지 탭이 들고 있어야 하고, 그동안 진행률을 볼 자리가 없고,
 * 탭을 닫으면 받던 것이 통째로 사라진다. 브라우저의 내려받기 관리자는 그 셋을 다 해 준다.
 *
 * 여기서 고정하는 것:
 *   1) 행이 자기 크기를 말하고 그 값이 임계를 넘으면 요청을 **탭이 버퍼링하지 않는다** —
 *      `<a download>` 로 브라우저에게 넘긴다(문서는 그대로 남는다, 최상위 이동이 아니다).
 *   2) 반례 둘: 작은 행과 크기를 말하지 않는 머리 동작(감사 CSV)은 지금까지 그대로 —
 *      받아서 상태를 보고 Blob 으로 저장한다.
 *   3) 실패한 내려받기의 오류는 `lib/api.js` 를 지나는 오류와 **같은 모양**이다 — 상관
 *      id(`requestId`)를 봉투에서, 봉투가 없으면 `X-Request-ID` 헤더에서 싣는다(Z8).
 *
 * 3) 은 화면에 그리는 자리가 아직 없어서(토스트는 문구만 받는다) 오류 객체를 받는 공용
 * 처리기를 목으로 잡아 그 모양을 직접 본다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }) }));
const handled = [];
vi.mock("./data-screen/apiError.js", () => ({
  handleApiError: (e) => { handled.push(e); },
}));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const BACKUP = {
  key: "backup", area: "운영", title: "백업", endpoint: "/api/admin/backups",
  columns: [{ key: "path", label: "파일", identifier: true }],
  actions: [{ label: "내려받기", download: (_qs, r) => "/api/admin/backups/" + r.id + "/download" }],
};

const AUDIT = {
  key: "audit", area: "감사", title: "감사 로그", endpoint: "/api/admin/audit",
  columns: [{ key: "action", label: "동작", identifier: true }],
  headerActions: [{ label: "CSV 내보내기", download: () => "/api/admin/audit/export.csv" }],
};

const GB = 1024 * 1024 * 1024;
const BIG_ROW = { id: "b-big", path: "/var/backups/full", size_bytes: 5 * GB };
const SMALL_ROW = { id: "b-small", path: "/var/backups/tiny", size_bytes: 4096 };

let fetchMock;
let anchorClicks;
let clickSpy;

beforeEach(() => {
  apiMock.mockReset();
  handled.length = 0;
  window.location.hash = "";
  anchorClicks = [];
  clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function capture() {
    anchorClicks.push({ href: this.href, download: this.download });
  });
  globalThis.URL.createObjectURL = vi.fn(() => "blob:mock/1");
  globalThis.URL.revokeObjectURL = vi.fn();
  fetchMock = vi.fn();
  globalThis.fetch = fetchMock;
});

afterEach(() => { clickSpy.mockRestore(); window.location.hash = ""; });

function okFile(body, disposition) {
  return Promise.resolve({
    ok: true, status: 200,
    headers: { get: (k) => (k.toLowerCase() === "content-disposition" ? disposition : null) },
    blob: () => Promise.resolve(new Blob([body], { type: "application/octet-stream" })),
    json: () => Promise.reject(new Error("본문은 파일이다")),
  });
}

function failWith(status, body, headers) {
  const table = headers || {};
  return Promise.resolve({
    ok: false, status,
    headers: { get: (k) => (table[k] != null ? table[k] : null) },
    json: () => (body ? Promise.resolve(body) : Promise.reject(new Error("봉투가 아니다"))),
    blob: () => Promise.reject(new Error("실패 응답에는 파일이 없다")),
  });
}

function renderScreen(config) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <DataScreen config={config} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function pressDownload(row) {
  const user = userEvent.setup();
  await screen.findByText(row.path);
  await user.click(screen.getByText(row.path));
  await user.click(await screen.findByRole("button", { name: "내려받기" }));
}

describe("큰 산출물은 브라우저 내려받기 관리자가 받는다 (R7-03)", () => {
  it("5GB 덤프는 탭이 버퍼링하지 않는다 — 그 주소를 그대로 브라우저에 넘긴다", async () => {
    apiMock.mockResolvedValue({ items: [BIG_ROW], total: 1 });
    renderScreen(BACKUP);
    const hrefBefore = window.location.href;

    await pressDownload(BIG_ROW);

    await waitFor(() => expect(anchorClicks).toHaveLength(1));
    // Blob 주소가 아니라 API 주소 그대로다 — 본문이 탭을 지나지 않았다는 뜻이다.
    expect(anchorClicks[0].href).toContain("/api/admin/backups/b-big/download");
    expect(anchorClicks[0].href).not.toContain("blob:");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(globalThis.URL.createObjectURL).not.toHaveBeenCalled();
    // 최상위 이동이 아니다 — 콘솔은 그 자리에 남는다(xe-07 이 없앤 증상은 안 돌아온다).
    expect(window.location.href).toBe(hrefBefore);
    expect(screen.getAllByText("/var/backups/full").length).toBeGreaterThan(0);
  });

  it("반례 — 작은 행은 그대로 받아서 상태를 보고 Blob 으로 저장한다", async () => {
    apiMock.mockResolvedValue({ items: [SMALL_ROW], total: 1 });
    fetchMock.mockImplementation(() => okFile("dump", 'attachment; filename="db.dump"'));
    renderScreen(BACKUP);

    await pressDownload(SMALL_ROW);

    await waitFor(() => expect(anchorClicks).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/backups/b-small/download");
    expect(anchorClicks[0].href).toBe("blob:mock/1");
    expect(anchorClicks[0].download).toBe("db.dump");
  });

  it("반례 — 크기를 말하지 않는 머리 동작(감사 CSV)도 그대로 받아서 저장한다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "1", action: "user.login" }], total: 1 });
    fetchMock.mockImplementation(() => okFile("동작\n", 'attachment; filename="audit-log.csv"'));
    const user = userEvent.setup();
    renderScreen(AUDIT);
    await screen.findByText("user.login");

    await user.click(screen.getByRole("button", { name: "CSV 내보내기" }));

    await waitFor(() => expect(anchorClicks).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(anchorClicks[0].download).toBe("audit-log.csv");
  });
});

describe("내려받기 오류도 다른 오류와 같은 모양이다 (R7-04 · Z8)", () => {
  it("봉투의 request_id 를 오류에 싣는다", async () => {
    apiMock.mockResolvedValue({ items: [SMALL_ROW], total: 1 });
    fetchMock.mockImplementation(() => failWith(404, {
      error: { code: "not_found", message: "백업 파일이 서버에 없습니다.", request_id: "req-envelope-1" },
    }));
    renderScreen(BACKUP);

    await pressDownload(SMALL_ROW);

    await waitFor(() => expect(handled).toHaveLength(1));
    expect(handled[0].status).toBe(404);
    expect(handled[0].message).toBe("백업 파일이 서버에 없습니다.");
    expect(handled[0].requestId).toBe("req-envelope-1");
  });

  it("봉투가 없는 실패(프록시의 HTML 403)는 X-Request-ID 헤더에서 싣는다", async () => {
    apiMock.mockResolvedValue({ items: [SMALL_ROW], total: 1 });
    fetchMock.mockImplementation(() => failWith(403, null, { "X-Request-ID": "req-header-9" }));
    renderScreen(BACKUP);

    await pressDownload(SMALL_ROW);

    await waitFor(() => expect(handled).toHaveLength(1));
    expect(handled[0].status).toBe(403);
    expect(handled[0].requestId).toBe("req-header-9");
  });

  it("반례 — 서버가 id 를 안 주면 null 이다(없는 값을 지어내지 않는다)", async () => {
    apiMock.mockResolvedValue({ items: [SMALL_ROW], total: 1 });
    fetchMock.mockImplementation(() => failWith(500, null, {}));
    renderScreen(BACKUP);

    await pressDownload(SMALL_ROW);

    await waitFor(() => expect(handled).toHaveLength(1));
    expect(handled[0].requestId).toBeNull();
  });
});
