import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 관리의 구성원 표는 **그 사람이 올린 사진 · 고른 그림**을 그린다(D-556).
 *
 * 예전에는 `/api/admin/users` 행에 `avatar_url` · `avatar_default_key` 가 없어 표가 사용자 id 로 배정한 DiceBear 그림을
 * 그렸고, 그래서 같은 사람이 프로필 화면과 조직 관리에서 다른 얼굴을 가졌다. 서버가 두 칸을 싣고 표는 그것을 그대로 쓴다. */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { OrgMembersPane } from "./OrgMembersPane.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const PEOPLE = [
  { id: "u-photo", display_name: "사진있음", email: "photo@example.com", title: "과장", role: "user", active: true,
    department: "영업팀", avatar_url: "/api/profile/avatar/u-photo?v=77", avatar_default_key: null },
  { id: "u-picked", display_name: "그림고름", email: "picked@example.com", title: null, role: "user", active: true,
    department: "영업팀", avatar_url: null, avatar_default_key: "thumbs:4" },
  { id: "u-none", display_name: "아무것도", email: "none@example.com", title: null, role: "user", active: true,
    department: "영업팀", avatar_url: null, avatar_default_key: null },
];

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: PEOPLE, total: PEOPLE.length, page: 1, page_size: 50 });
});

function renderPane() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <MemoryRouter>
          <OrgMembersPane label="영업팀" scope={{ kind: "dept", deptId: "d-1", hasChildren: false }} />
        </MemoryRouter>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("조직 구성원 표의 얼굴", () => {
  it("사진을 올린 사람은 그 사진 주소를, 그림을 고른 사람은 그 그림 키를 그린다", async () => {
    const { container } = renderPane();
    await waitFor(() => expect(screen.getByText("사진있음")).toBeInTheDocument());
    const photo = container.querySelector('img[src="/api/profile/avatar/u-photo?v=77"]');
    expect(photo).not.toBeNull();
    const picked = container.querySelector('[data-avatar-pending="thumbs:4"], [data-avatar-key="thumbs:4"]');
    expect(picked).not.toBeNull();
    // 아무것도 없는 사람은 id 씨앗의 기본 그림이다 — 서버 주소의 사진을 지어내지 않는다.
    expect(container.querySelectorAll('img[src^="/api/profile/avatar/"]').length).toBe(1);
  });
});
