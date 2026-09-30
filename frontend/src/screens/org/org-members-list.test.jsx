import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 · 부서 구성원 목록 (계획 3.6 · D-510).
 *
 * 못박는 것:
 *   ① 조건이 서버로 간다 — 부서(하위 포함 토글), 조직(소속 종류), 상태(기본은 지금 일하는 사람), 검색.
 *   ② 하위 부서를 포함하면 부서 열이 선다 — 여러 부서가 한 목록에 섞이므로.
 *   ③ 같은 이름이 둘이면 이름 아래 이메일이 선다.
 *   ④ 행은 그 사람의 사용자 상세로 가는 진짜 링크다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { OrgMembersList } from "./OrgMembersList.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const PEOPLE = [
  { id: "u-1", display_name: "김하나", email: "hana1@goodmit.co.kr", title: "과장", role: "user", active: true, department: "영업팀" },
  { id: "u-2", display_name: "김하나", email: "hana2@goodmit.co.kr", title: null, role: "admin", active: true, department: "국내영업" },
  { id: "u-3", display_name: "박둘", email: "dul@goodmit.co.kr", title: "사원", role: "user", active: false, department: "영업팀" },
];

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: PEOPLE, total: PEOPLE.length, page: 1, page_size: 50 });
});

function renderList(props) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <MemoryRouter>
          <OrgMembersList {...props} />
        </MemoryRouter>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const lastQuery = () => new URLSearchParams(String(apiMock.mock.calls[apiMock.mock.calls.length - 1][0]).split("?")[1]);

describe("구성원 목록", () => {
  it("부서 목록은 그 부서와 지금 일하는 사람으로 시작하고, 하위 부서 포함을 켜면 서버가 가지를 편다", async () => {
    const user = userEvent.setup();
    renderList({ scope: { kind: "dept", deptId: "dep-sales" } });
    await screen.findAllByText("김하나");
    expect(lastQuery().get("department_id")).toBe("dep-sales");
    expect(lastQuery().get("state")).toBe("active");
    expect(lastQuery().get("include_descendants")).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /^부서/ })).toBeNull();

    await user.click(screen.getByRole("button", { name: "하위 부서 포함" }));
    await waitFor(() => expect(lastQuery().get("include_descendants")).toBe("true"));
    // 여러 부서가 한 목록에 섞이므로 부서 열이 선다.
    expect(await screen.findByRole("columnheader", { name: /^부서/ })).toBeInTheDocument();
  });

  it("조직 목록은 그 조직으로 좁히고, 소속 종류를 고르면 그 조건이 실린다", async () => {
    const onMembership = vi.fn();
    const { rerender } = renderList({ scope: { kind: "org", orgId: "org-1" }, membership: "", onMembership });
    await screen.findAllByText("김하나");
    expect(lastQuery().get("org_id")).toBe("org-1");
    expect(lastQuery().get("membership_kind")).toBeNull();

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <MemoryRouter>
            <OrgMembersList scope={{ kind: "org", orgId: "org-1" }} membership="unassigned" onMembership={onMembership} />
          </MemoryRouter>
        </ThemeModeProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(lastQuery().get("membership_kind")).toBe("unassigned"));
    expect(screen.getByText("여러 사람의 소속을 한 번에 지정하려면 조직 정합성 화면의 사람 탭을 쓰세요.")).toBeInTheDocument();
  });

  it("같은 이름이 둘이면 이름 아래 이메일이 서고, 이름은 사용자 상세로 가는 링크다", async () => {
    renderList({ scope: { kind: "dept", deptId: "dep-sales" } });
    const names = await screen.findAllByText("김하나");
    expect(names).toHaveLength(2);
    const table = names[0].closest("table");
    // 이메일 열과 별개로, 동명이인의 이름 칸에 이메일이 한 번 더 선다.
    expect(within(table).getAllByText("hana1@goodmit.co.kr").length).toBeGreaterThanOrEqual(2);
    expect(within(table).getAllByText("dul@goodmit.co.kr")).toHaveLength(1);
    const link = names[0].closest("a");
    expect(link && link.getAttribute("href")).toBe("#/users/u-1");
  });

  it("상태는 서버 값이 아니라 낱말로, 역할은 관리 콘솔의 이름으로 선다", async () => {
    renderList({ scope: { kind: "dept", deptId: "dep-sales" } });
    await screen.findAllByText("김하나");
    expect(screen.getByText("비활성")).toBeInTheDocument();
    expect(screen.queryByText("admin")).toBeNull();
  });
});
