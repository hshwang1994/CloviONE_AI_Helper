import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0014 acceptance_criteria (3) — /users 생성 폼의 필드가 서버 상한
 * (app/users/schemas.py UserCreateRequest)과 같은 maxLength를 갖는다.
 *
 * Users.jsx는 registry 화면이 아니라서 PA-RC-0005가 만든 maxLength 배선(FORM_SCHEMAS →
 * fieldLimits.json → FormField)이 자동으로 닿지 않았다 — 이 RC 전에는 두 칸 다 무제한(-1)이라,
 * 500자를 넣어야 서버 왕복 뒤에야 영문 422로 걸렸다(probe_limits.py 결함 재현).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Users } from "./Users.jsx";

function renderUsers() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Users />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("사용자 생성 폼 — 서버 상한과 같은 maxLength", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: [], total: 0, page_size: 20 });
      if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
      if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
      if (path === "/api/admin/organizations") return Promise.resolve({ items: [], total: 0 });
      if (path === "/api/admin/settings") {
        return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
      }
      return Promise.resolve({});
    });
  });

  it("이메일 255자, 이름 120자 — 서버 스키마와 일치한다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await user.click(await screen.findByRole("button", { name: "사용자 추가" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/이메일/)).toHaveProperty("maxLength", 255);
    expect(within(dialog).getByLabelText(/이름/)).toHaveProperty("maxLength", 120);
  });
});
