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
 *
 * qa-contract-change: 부서 조건을 말하던 안내 상자(「부서가 지정되지 않은 사용자만 보고 있습니다 · 부서 필터 해제」)를 걷었다(D-501) — 같은 조건을
 * 조건 줄의 칩이 이미 말했다. 「센티널이 뜻으로 말해진다」는 단언은 그 상자 대신 부서 칸의 값과 칩(「부서: 미지정」)으로 재고, 상자가 없다는 단언과
 * 부서 칸(wide · 맨 앞 · 「미지정」 후보 · 고르면 같은 주소 키)을 재는 시험을 더한다.
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
  it("?role=admin 으로 마운트하면 그 조건으로 첫 묶음을 조회한다", async () => {
    renderAt("/users?role=admin");
    await screen.findByText("bob@example.com");

    const call = apiMock.mock.calls.find((c) => String(c[0]).startsWith("/api/admin/users?"));
    expect(call, "목록 조회 자체가 안 나갔다").toBeTruthy();
    const params = new URL("http://x" + call[0]).searchParams;
    expect(params.get("role")).toBe("admin");
    /* 쪽 번호는 조건이 아니다 — 첫 묶음 요청에 실리지 않는다. */
    expect(params.get("page")).toBeNull();
  });

  it("옛 링크의 ?page=3 이 첫 요청을 오염시키지 않는다", async () => {
    /* 북마크와 저장된 뷰가 여전히 이 값을 들고 온다. 화면은 그것을 「미리 받아 둘 묶음 수」로만
       읽고(`useInfiniteList` 의 `resume` — 그 동작은 `lib/use-infinite-list.test.jsx` 가 잰다)
       조건에는 안 섞는다. 더 받을 것이 없으면 첫 묶음에서 그대로 멈춘다. */
    renderAt("/users?page=3");
    await screen.findByText("bob@example.com");
    const first = apiMock.mock.calls
      .map((c) => String(c[0]))
      .find((u) => u.startsWith("/api/admin/users?"));
    expect(new URL("http://x" + first).searchParams.get("page")).toBeNull();
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

  it("「부서 없음」 센티널(?department_id=none)은 서버로 그대로 가고 칸과 칩이 그 뜻을 말한다 (P-61)", async () => {
    /* 조직 콘솔의 「부서 미지정 N명」 링크가 이 주소로 온다. 서버가 `none` 을 IS NULL 로
       읽으므로 화면은 값을 바꾸지 않고 넘기고, 부서 이름 대신 뜻을 적는다. */
    renderAt("/users?department_id=none");
    await screen.findByText("alice@example.com");
    const call = apiMock.mock.calls.find((c) => String(c[0]).startsWith("/api/admin/users?"));
    expect(new URL("http://x" + call[0]).searchParams.get("department_id")).toBe("none");
    // 뜻은 부서 칸의 값(「미지정」)과 조건 칩(「부서: 미지정」)이 말한다 — 같은 조건을 되풀이하던 안내 상자는 없다(D-501).
    expect(screen.getByRole("combobox", { name: "부서" })).toHaveValue("미지정");
    expect(screen.getByText("부서: 미지정")).toBeInTheDocument();
    expect(screen.queryByText(/부서가 지정되지 않은 사용자만 보고 있습니다/)).toBeNull();
    expect(screen.queryByRole("button", { name: "부서 필터 해제" })).toBeNull();
    // 서버 센티널 글자는 화면 어디에도 서지 않는다.
    expect(screen.queryByText(/none/)).toBeNull();
  });
});

/* 부서 칸 (D-501) — 표에 「부서」 열이 있는데 부서로 거를 칸이 없었다. 부서 조건은 조직 콘솔에서 넘어올 때만 걸렸고, 그 사실을 칩과
   안내 상자가 두 번 말했다. 칸이 조건을 걸고 풀며 주소 키는 칩 · 딥링크와 같은 `department_id` 다. */
describe("/users 부서 칸 (D-501)", () => {
  function withDepartments() {
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: [ALICE, ADMIN_BOB], total: 2, page_size: 20 });
      if (path === "/api/admin/departments") {
        return Promise.resolve({ items: [
          { id: "d-1", name: "플랫폼개발팀", active: true, org_name: "굿딧" },
          { id: "d-2", name: "옛 운영팀", active: false, org_name: "굿딧" },
        ] });
      }
      if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
      if (path === "/api/admin/settings") return Promise.resolve({ settings: {} });
      return Promise.resolve({});
    });
  }

  it("부서 칸은 필터 바의 wide 칸이고 조건 칸의 맨 앞이다(범위가 먼저)", async () => {
    withDepartments();
    renderAt("/users");
    const cell = await screen.findByRole("combobox", { name: "부서" });
    const root = cell.closest("[data-filter-kind]");
    expect(root).toHaveAttribute("data-filter-kind", "entity");
    expect(root).toHaveAttribute("data-filter-size", "wide");
    const kinds = [...document.querySelectorAll("[data-filter-row] > [data-filter-kind]")].map((n) => n.getAttribute("data-filter-kind"));
    expect(kinds[0]).toBe("search");
    expect(kinds[1]).toBe("entity");
  });

  it("후보는 「미지정」이 맨 앞이고, 비활성 부서도 표시와 함께 남는다", async () => {
    withDepartments();
    const user = userEvent.setup();
    renderAt("/users");
    const cell = await screen.findByRole("combobox", { name: "부서" });
    await user.click(cell);
    const names = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(names[0]).toMatch(/전체/);
    expect(names[1]).toBe("미지정");
    expect(names.join("|")).toMatch(/플랫폼개발팀/);
    expect(names.join("|")).toMatch(/옛 운영팀 \(비활성\)/);
  });

  it("부서를 고르면 그 조건으로 다시 받고, 주소와 조건 칩이 같은 키 · 같은 이름을 말한다", async () => {
    withDepartments();
    window.location.hash = "#/users";
    const user = userEvent.setup();
    renderAt("/users");
    const cell = await screen.findByRole("combobox", { name: "부서" });
    await user.click(cell);
    await user.click(await screen.findByRole("option", { name: /플랫폼개발팀/ }));
    await waitFor(() => {
      const last = apiMock.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith("/api/admin/users?")).pop();
      expect(new URL("http://x" + last).searchParams.get("department_id")).toBe("d-1");
    });
    await waitFor(() => expect(window.location.hash).toContain("department_id=d-1"));
    expect(screen.getByText("부서: 플랫폼개발팀")).toBeInTheDocument();
  });
});
