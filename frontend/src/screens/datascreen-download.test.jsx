import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 내려받기 — **머리에서도 되고, 실패해도 화면을 잃지 않는다** (audit-01 · xe-07 · ops-03).
 *
 * 두 결함이 같은 갈래에 있었다.
 *
 *   1) 머리 액션에는 `download` 가지가 아예 없었다. registry 가 감사 로그의 「CSV 내보내기」를
 *      그렇게 선언했는데, 그 버튼은 맨 아래 쓰기 가지까지 떨어져 `a.path()` 를 불렀고 —
 *      내려받기 액션에는 `path` 가 없으므로 — 그 자리에서 TypeError 가 났다. 화면에는
 *      «s.path is not a function» 이 토스트로 떴고 **요청은 한 건도 안 나갔다**.
 *
 *   2) 내려받기가 `window.location.href` 로 최상위 이동을 했다. 성공 응답은 첨부 헤더 덕에
 *      문서가 유지되지만, 404 는 브라우저가 그대로 그려서 관리 콘솔이 통째로 사라지고 날
 *      JSON 한 줄이 화면을 대체했다(백업 파일이 디스크에서 사라진 흔한 사건에서 실측).
 *
 * 여기서 고정하는 것: 머리와 행이 같은 갈래를 타고, 성공은 파일로 저장되고, 실패는 서버 문구
 * 토스트로 끝나며 화면은 그대로 남는다. 반례로 쓰기 액션이 여전히 `api()` 로 나가는 것도 본다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AUDIT = {
  key: "audit", area: "감사", title: "감사 로그", endpoint: "/api/admin/audit",
  columns: [{ key: "action", label: "동작", identifier: true }],
  filters: [{ key: "result", label: "결과", type: "select", options: [{ value: "failure", label: "실패" }] }],
  headerActions: [
    { label: "CSV 내보내기", download: (qs) => "/api/admin/audit/export.csv" + (qs ? "?" + qs : "") },
  ],
};

const BACKUP = {
  key: "backup", area: "운영", title: "백업", endpoint: "/api/admin/backups",
  columns: [{ key: "path", label: "파일", identifier: true }],
  actions: [{ label: "내려받기", download: (_qs, r) => "/api/admin/backups/" + r.id + "/download" }],
};

let fetchMock;
let anchorClicks;
let clickSpy;
let hrefBefore;

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
  anchorClicks = [];
  hrefBefore = null;
  // 저장은 임시 <a download> 클릭이다 — jsdom 은 실제 저장을 못 하므로 무엇을 눌렀는지만 잡는다.
  clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function capture() {
    anchorClicks.push({ href: this.href, download: this.download });
  });
  globalThis.URL.createObjectURL = vi.fn(() => "blob:mock/1");
  globalThis.URL.revokeObjectURL = vi.fn();
  fetchMock = vi.fn();
  globalThis.fetch = fetchMock;
});

afterEach(() => {
  clickSpy.mockRestore();
  window.location.hash = "";
});

function okFile(body, disposition) {
  return Promise.resolve({
    ok: true, status: 200,
    headers: { get: (k) => (k.toLowerCase() === "content-disposition" ? disposition : null) },
    blob: () => Promise.resolve(new Blob([body], { type: "text/csv" })),
    json: () => Promise.reject(new Error("본문은 파일이다")),
  });
}

function failEnvelope(status, message) {
  return Promise.resolve({
    ok: false, status,
    headers: { get: () => null },
    json: () => Promise.resolve({ error: { code: "not_found", message } }),
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

describe("머리의 내려받기 (audit-01)", () => {
  it("누르면 지금 화면의 필터가 붙은 주소로 요청이 나가고 파일로 저장된다", async () => {
    window.location.hash = "#/audit?result=failure";
    apiMock.mockResolvedValue({ items: [{ id: "1", action: "user.login" }], total: 1 });
    fetchMock.mockImplementation(() => okFile("동작,결과\n", 'attachment; filename="audit-log.csv"'));
    const user = userEvent.setup();
    renderScreen(AUDIT);
    await screen.findByText("user.login");

    hrefBefore = window.location.href;
    await user.click(screen.getByRole("button", { name: "CSV 내보내기" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/audit/export.csv?result=failure");
    // 세션 쿠키를 실어야 한다 — 이 주소는 로그인한 사람만 받을 수 있다.
    expect(fetchMock.mock.calls[0][1].credentials).toBe("same-origin");
    await waitFor(() => expect(anchorClicks).toHaveLength(1));
    // 파일 이름은 서버가 Content-Disposition 에 실어 준 것을 그대로 쓴다.
    expect(anchorClicks[0].download).toBe("audit-log.csv");
    expect(anchorClicks[0].href).toBe("blob:mock/1");
    // 예전 증상: 요청 0건 + 원시 예외 토스트.
    expect(screen.queryByText(/is not a function/)).toBeNull();
    expect(window.location.href).toBe(hrefBefore);
  });

  it("반례 — 머리의 쓰기 액션은 그대로 api() 로 나간다(내려받기 갈래가 삼키지 않는다)", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") return Promise.resolve({ ok: true });
      return Promise.resolve({ items: [{ id: "1", action: "user.login" }], total: 1 });
    });
    const user = userEvent.setup();
    renderScreen({ ...AUDIT, headerActions: [{ label: "정리", path: () => "/api/admin/audit/purge" }] });
    await screen.findByText("user.login");

    await user.click(screen.getByRole("button", { name: "정리" }));

    await waitFor(() => {
      const posts = apiMock.mock.calls.filter((c) => c[1] && c[1].method === "POST");
      expect(posts).toHaveLength(1);
      expect(posts[0][0]).toBe("/api/admin/audit/purge");
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("내려받기가 실패해도 관리 콘솔이 남는다 (xe-07 · ops-03)", () => {
  it("404 면 서버 문구를 토스트로 내고 화면은 그대로다 — 파일도 저장하지 않는다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "b1", path: "/var/backups/backup-1" }], total: 1 });
    fetchMock.mockImplementation(() => failEnvelope(404, "백업 파일이 서버에 없습니다."));
    const user = userEvent.setup();
    renderScreen(BACKUP);
    await screen.findByText("/var/backups/backup-1");
    const listCallsBefore = apiMock.mock.calls.length;

    await user.click(screen.getByText("/var/backups/backup-1"));
    hrefBefore = window.location.href;
    await user.click(await screen.findByRole("button", { name: "내려받기" }));

    expect(await screen.findByText("백업 파일이 서버에 없습니다.")).toBeInTheDocument();
    // 화면이 살아 있다 — 목록도 주소도 그대로다(예전에는 날 JSON 한 줄이 문서를 대체했다).
    expect(screen.getAllByText("/var/backups/backup-1").length).toBeGreaterThan(0);
    expect(window.location.href).toBe(hrefBefore);
    expect(anchorClicks).toHaveLength(0);
    // 받지 못했으니 목록을 다시 읽을 이유도 없다.
    expect(apiMock.mock.calls.length).toBe(listCallsBefore);
  });

  it("연결 자체가 끊겨도 사람의 말로 알린다 — 브라우저의 영어 문구를 그대로 올리지 않는다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "b1", path: "/var/backups/backup-1" }], total: 1 });
    fetchMock.mockImplementation(() => Promise.reject(new TypeError("Failed to fetch")));
    const user = userEvent.setup();
    renderScreen(BACKUP);
    await screen.findByText("/var/backups/backup-1");

    await user.click(screen.getByText("/var/backups/backup-1"));
    await user.click(await screen.findByRole("button", { name: "내려받기" }));

    expect(await screen.findByText(/서버에 연결할 수 없습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/Failed to fetch/)).toBeNull();
  });

  it("반례 — 200 이면 파일이 저장되고 오류 토스트가 없다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "b1", path: "/var/backups/backup-1" }], total: 1 });
    fetchMock.mockImplementation(() => okFile("dump", 'attachment; filename="db.dump"'));
    const user = userEvent.setup();
    renderScreen(BACKUP);
    await screen.findByText("/var/backups/backup-1");

    await user.click(screen.getByText("/var/backups/backup-1"));
    await user.click(await screen.findByRole("button", { name: "내려받기" }));

    await waitFor(() => expect(anchorClicks).toHaveLength(1));
    expect(anchorClicks[0].download).toBe("db.dump");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/backups/b1/download");
    expect(screen.queryByText("백업 파일이 서버에 없습니다.")).toBeNull();
  });
});
