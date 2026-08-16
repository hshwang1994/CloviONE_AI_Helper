import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

/* PA-RC-0013: /users만 검색·필터·페이지를 URL에 안 실어서 새로고침·공유에 견디지 못했다
 * (대조군 /team-docs·/board·/team-tickets·/audit은 이미 견딘다, Handoff 실측
 * probe_deeplink2.json). DataScreen.jsx가 이미 쓰는 datascreen-view.js 순수 함수를
 * 그대로 가져다 raw history.replaceState로 되쓴다.
 *
 * window.location.hash 를 직접 건드리므로(HashRouter가 실제로 보는 자리) 파일 전역에서
 * 매 시험 전후로 반드시 비운다 — datascreen.test.jsx/data-screen-edit-diff.test.jsx의
 * 기존 관용과 같다(안 비우면 한 시험의 필터가 다음 시험으로 샌다).
 */

beforeEach(() => { window.location.hash = ""; });
afterEach(() => { window.location.hash = ""; });

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Users } from "./Users.jsx";

const ALICE = { id: "u-alice", email: "alice@example.com", display_name: "Alice", role: "user", active: true };
const ADMIN_BOB = { id: "u-bob", email: "bob@example.com", display_name: "Bob", role: "admin", active: true };

function mockApi() {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/admin/users?")) {
      const params = new URL("http://x" + path).searchParams;
      const role = params.get("role");
      const items = role === "admin" ? [ADMIN_BOB] : [ALICE, ADMIN_BOB];
      return Promise.resolve({ items, total: items.length, page_size: 20 });
    }
    if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
    if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
    if (path === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
    return Promise.resolve({});
  });
}

beforeEach(mockApi);

function renderAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path="/users" element={<Users />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("/users 목록 상태 → URL (쓰기 방향, PA-RC-0013)", () => {
  it("검색어를 넣으면 hash가 #/users?q=... 형태로 바뀐다", async () => {
    // MemoryRouter(시험 전용)는 window.location.hash를 실제로 안 건드린다 — 실제 앱의
    // HashRouter는 마운트 시점에 이미 "#/users"를 써 둔 상태다. 여기서 그 전제를 흉내
    // 낸다(안 하면 이 효과가 처음 읽는 hashPath가 빈 문자열이라 "#/users" 대신 "#"만
    // 남는다 — 실제 앱에서는 재현되지 않는 시험 전용 아티팩트).
    window.location.hash = "#/users";
    const user = userEvent.setup();
    renderAt("/users");
    const box = await screen.findByRole("searchbox", { name: "사용자 검색" });
    await user.type(box, "Alice");

    await waitFor(() => expect(window.location.hash).toBe("#/users?q=Alice"), { timeout: 2000 });
  });

  it("기본값(빈 필터, 1쪽)은 주소에 나타나지 않는다", async () => {
    renderAt("/users");
    await screen.findByText("alice@example.com");

    expect(window.location.hash).not.toMatch(/page=1/);
    expect(window.location.hash).not.toMatch(/[?&](role|active|locked|archived)=(&|$)/);
  });

  it("history.pushState가 아니라 replaceState만 쓴다 — 필터를 여러 번 바꿔도 뒤로가기 이력이 안 쌓인다", async () => {
    const pushSpy = vi.spyOn(window.history, "pushState");
    const user = userEvent.setup();
    renderAt("/users");
    const box = await screen.findByRole("searchbox", { name: "사용자 검색" });
    await user.type(box, "A");
    await user.type(box, "l");
    await user.type(box, "i");

    await waitFor(() => expect(window.location.hash).toContain("q=Ali"), { timeout: 2000 });
    expect(pushSpy).not.toHaveBeenCalled();
    pushSpy.mockRestore();
  });
});

describe("/users 목록 상태 ← URL (읽기 방향/새로고침 복원, PA-RC-0013)", () => {
  it("?role=admin&page=2로 마운트하면 그 필터·페이지로 목록을 조회한다", async () => {
    renderAt("/users?role=admin&page=2");
    await screen.findByText("bob@example.com");

    const call = apiMock.mock.calls.find((c) => String(c[0]).startsWith("/api/admin/users?"));
    expect(call, "목록 조회 자체가 안 나갔다").toBeTruthy();
    const params = new URL("http://x" + call[0]).searchParams;
    expect(params.get("role")).toBe("admin");
    expect(params.get("page")).toBe("2");
  });

  it("기존 인바운드 딥링크(?q=)는 여전히 동작한다(회귀 방지)", async () => {
    renderAt("/users?q=Alice");
    const box = await screen.findByRole("searchbox", { name: "사용자 검색" });
    await waitFor(() => expect(box).toHaveValue("Alice"));
  });

  it("기존 인바운드 딥링크(?department_id=)는 여전히 동작한다(회귀 방지)", async () => {
    renderAt("/users?department_id=d-1");
    await screen.findByText("alice@example.com");
    const call = apiMock.mock.calls.find((c) => String(c[0]).startsWith("/api/admin/users?"));
    const params = new URL("http://x" + call[0]).searchParams;
    expect(params.get("department_id")).toBe("d-1");
  });
});
