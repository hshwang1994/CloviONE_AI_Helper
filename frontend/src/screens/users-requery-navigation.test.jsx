import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";

/* 회귀: 통합 검색(Ctrl+K)에서 사용자 결과를 고르면 `#/users?q=<이름>`으로 온다(Users.jsx
 * 상단 주석). 이미 /users 화면이 열려 있는 상태에서(예: 방금 다른 사람을 봤다가 팔레트를
 * 다시 열어 두 번째 사람을 고르는 경우) 같은 라우트("/users")로 쿼리 문자열만 바뀌어
 * 다시 내비게이트하면, react-router는 이미 마운트된 <Users/> 인스턴스를 재사용하고
 * 컴포넌트를 다시 마운트하지 않는다. 그런데 검색어 상태 q는
 * `useState(() => searchParams.get("q") || "")`로 **최초 마운트 시 한 번만** 주소를 읽으므로,
 * 두 번째 내비게이션에서 바뀐 q 파라미터가 검색창에도 목록 필터에도 반영되지 않는다 —
 * 화면은 첫 번째 사람 기준 결과를 계속 보여주면서 아무 일도 안 한 것처럼 보인다(주석이
 * 막으려던 바로 그 증상을 '이미 화면이 열려 있는' 경로에서는 놓치고 있었다). */

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
const BOB = { id: "u-bob", email: "bob@example.com", display_name: "Bob", role: "user", active: true };

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/admin/users?")) {
      const q = new URL("http://x" + path).searchParams.get("q") || "";
      const items = q === "Bob" ? [BOB] : q === "Alice" ? [ALICE] : [ALICE, BOB];
      return Promise.resolve({ items, total: items.length, page_size: 20 });
    }
    if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
    if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
    if (path === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
    return Promise.resolve({});
  });
});

function Harness() {
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate("/users?q=Bob")}>다른 사람으로(Bob)</button>
      <Routes>
        <Route path="/users" element={<Users />} />
      </Routes>
    </>
  );
}

function renderHarness() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/users?q=Alice"]}>
        <Harness />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Users 화면 — 이미 열린 채로 통합 검색 딥링크를 다시 받는 경우", () => {
  it("q=Alice로 처음 들어오면 검색창에 Alice가 채워진다", async () => {
    renderHarness();
    const box = await screen.findByRole("searchbox", { name: "사용자 검색" });
    await waitFor(() => expect(box).toHaveValue("Alice"));
  });

  it("같은 화면이 열린 채 q=Bob 딥링크를 다시 받으면 검색창과 목록이 Bob으로 갱신된다", async () => {
    const user = userEvent.setup();
    renderHarness();
    const box = await screen.findByRole("searchbox", { name: "사용자 검색" });
    await waitFor(() => expect(box).toHaveValue("Alice"));
    await screen.findByText("alice@example.com");

    await user.click(screen.getByRole("button", { name: "다른 사람으로(Bob)" }));

    // 주소는 바뀌었지만(컴포넌트가 재마운트되지 않으므로) 검색창은 여전히 Alice로 남아있으면 버그.
    await waitFor(() => expect(box).toHaveValue("Bob"));
    await screen.findByText("bob@example.com");
  });
});
