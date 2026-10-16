import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-replaced-by: frontend/src/screens/org/org-members-list.test.jsx
 * qa-contract-change: 구성원 목록이 작업 공간의 구성원 판이 됐다(O1 · D-533) — 부서의 기본이 하위 포함이 되어 「하위 부서 포함」 토글 단언을 「직속만」 토글로 뒤집었고, 동명이인 이름 칸 둘째 줄의 이메일을 걷어 「이메일이 두 번 선다」 단언을 「한 번만 선다」로 바꿨다.
 *
 * 구성원 판 (O1 · D-533) — 옛 `OrgMembersList`(계획 3.6 · D-510)의 자리를 잇는다.
 *
 * 못박는 것:
 *   ① 조건이 서버로 간다 — 부서는 **하위 포함이 기본**(「직속만」 토글로 끈다), 조직은 소속 종류, 상태는 기본 활성, 검색.
 *      트리 줄의 수(가지 전체)와 목록의 수가 같아진다 — 예전에는 상위 부서가 트리에 12명인데 목록이 직속 0명이었다.
 *   ② 부서 열은 조직 보기와 하위가 있는 부서의 하위 포함 보기에만 선다(말단 부서 직속은 모두 같은 부서다).
 *   ③ 동명이인은 이메일 열이 가른다 — 이름 칸 둘째 줄의 이메일은 걷었다(두 번 보였다).
 *   ④ 칩은 기본과 다른 조건만 만들고, 「필터 초기화」는 기본으로 되돌린다.
 *   ⑤ 행은 그 사람의 사용자 상세로 가는 진짜 링크다. 수는 「구성원 N명」(서버 total)이 말한다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { OrgMembersPane } from "./OrgMembersPane.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const PEOPLE = [
  { id: "u-1", display_name: "김하나", email: "hana1@example.com", title: "과장", role: "user", active: true, department: "영업팀" },
  { id: "u-2", display_name: "김하나", email: "hana2@example.com", title: null, role: "system_admin", active: true, department: "국내영업" },
  { id: "u-3", display_name: "박둘", email: "dul@example.com", title: "사원", role: "user", active: false, department: "영업팀" },
];

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: PEOPLE, total: PEOPLE.length, page: 1, page_size: 50 });
});

function renderPane(props) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <MemoryRouter>
          <OrgMembersPane label="영업팀" {...props} />
        </MemoryRouter>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const lastQuery = () => new URLSearchParams(String(apiMock.mock.calls[apiMock.mock.calls.length - 1][0]).split("?")[1]);
const header = (name) => screen.queryByRole("columnheader", { name: new RegExp("^" + name) });

describe("부서 구성원", () => {
  it("하위 포함이 기본이다 — 하위가 있으면 부서 열이 서고, 「직속만」을 켜면 그 부서만 받고 부서 열이 빠진다", async () => {
    const user = userEvent.setup();
    renderPane({ scope: { kind: "dept", deptId: "dep-sales", hasChildren: true } });
    await screen.findAllByText("김하나");
    expect(lastQuery().get("department_id")).toBe("dep-sales");
    expect(lastQuery().get("include_descendants")).toBe("true");
    expect(lastQuery().get("state")).toBe("active");
    expect(header("부서")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-condition-chip]")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "직속만" }));
    await waitFor(() => expect(lastQuery().get("include_descendants")).toBeNull());
    await waitFor(() => expect(header("부서")).toBeNull());
    // 기본과 다른 조건이라 칩이 선다. 기본 조건(상태 활성 · 하위 포함)은 칩을 만들지 않는다.
    expect([...document.querySelectorAll("[data-condition-chip]")].map((c) => c.textContent)).toEqual(["직속만"]);
  });

  it("말단 부서는 하위 포함이어도 부서 열을 그리지 않는다", async () => {
    renderPane({ scope: { kind: "dept", deptId: "dep-kr", hasChildren: false } });
    await screen.findAllByText("김하나");
    expect(lastQuery().get("include_descendants")).toBe("true");
    expect(header("부서")).toBeNull();
  });

  it("수는 「구성원 N명」 하나다 — 서버의 total 이다", async () => {
    apiMock.mockResolvedValue({ items: PEOPLE, total: 1234, page: 1, page_size: 50 });
    renderPane({ scope: { kind: "dept", deptId: "dep-sales", hasChildren: true } });
    expect(await screen.findByRole("heading", { level: 3, name: "구성원 1,234명" })).toBeInTheDocument();
  });
});

describe("조직 구성원", () => {
  it("그 조직으로 좁히고, 소속을 고르면 그 조건이 실린다 — 미지정을 고르면 정합성 화면 안내가 선다", async () => {
    const user = userEvent.setup();
    renderPane({ label: "클로비원", scope: { kind: "org", orgId: "org-1", unassigned: 0 } });
    await screen.findAllByText("김하나");
    expect(lastQuery().get("org_id")).toBe("org-1");
    expect(lastQuery().get("membership_kind")).toBeNull();
    // 조직 보기는 여러 부서가 섞이므로 부서 열이 선다.
    expect(header("부서")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: /소속/ }));
    await user.click(await screen.findByRole("option", { name: "미지정" }));
    await waitFor(() => expect(lastQuery().get("membership_kind")).toBe("unassigned"));
    expect(await screen.findByText("여러 사람의 소속을 한 번에 지정하려면 조직 정합성 화면의 사람 탭을 쓰세요.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "조직 정합성 열기" })).toHaveAttribute("href", "#/integrity?tab=people");
  });

  it("부서도 조직 직속도 아닌 사람이 있으면 한 줄 메시지 상자가 서고, 「목록 보기」가 목록을 그 사람들로 바꾼다", async () => {
    const user = userEvent.setup();
    renderPane({ label: "클로비원", scope: { kind: "org", orgId: "org-1", unassigned: 3 } });
    const notice = await screen.findByText("부서도 조직 직속도 아닌 사람이 3명 있습니다.");
    await user.click(within(notice.closest(".k-callout")).getByRole("button", { name: "목록 보기" }));
    await waitFor(() => expect(lastQuery().get("membership_kind")).toBe("unassigned"));
    expect(screen.queryByText("부서도 조직 직속도 아닌 사람이 3명 있습니다.")).toBeNull();
  });
});

describe("표", () => {
  it("동명이인은 이메일 열이 가른다 — 이메일은 한 행에 한 번만 보이고, 이름은 사용자 상세 링크다", async () => {
    renderPane({ scope: { kind: "dept", deptId: "dep-sales", hasChildren: true } });
    const names = await screen.findAllByText("김하나");
    expect(names).toHaveLength(2);
    const table = names[0].closest("table");
    expect(within(table).getAllByText("hana1@example.com")).toHaveLength(1);
    const link = names[0].closest("a");
    expect(link && link.getAttribute("href")).toBe("#/users/u-1");
  });

  it("상태는 서버 값이 아니라 낱말로, 역할은 관리 콘솔의 이름으로 선다", async () => {
    renderPane({ scope: { kind: "dept", deptId: "dep-sales", hasChildren: true } });
    await screen.findAllByText("김하나");
    expect(screen.getByText("비활성")).toBeInTheDocument();
    expect(screen.getByText("시스템 관리자")).toBeInTheDocument();
    expect(screen.queryByText("system_admin")).toBeNull();
  });

  it("조건 없이 0명이면 표 머리 아래 한 줄이 서고, 사용자 화면으로 가는 동작이 있다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    renderPane({ scope: { kind: "dept", deptId: "dep-empty", hasChildren: false }, emptyText: "이 부서에 배치된 사람이 없습니다." });
    expect(await screen.findByText("이 부서에 배치된 사람이 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "사용자 화면 열기" })).toHaveAttribute("href", "#/users");
    // 표 머리는 그대로 서 있다 — 판을 흰 면으로 채우는 큰 빈 상태가 아니다.
    expect(header("이름")).toBeInTheDocument();
  });

  it("조건 때문에 0명이면 「필터 초기화」가 기본 조건으로 되돌린다", async () => {
    const user = userEvent.setup();
    renderPane({ scope: { kind: "dept", deptId: "dep-sales", hasChildren: true } });
    await screen.findAllByText("김하나");
    apiMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    await user.click(screen.getByRole("combobox", { name: /상태/ }));
    await user.click(await screen.findByRole("option", { name: "보관" }));
    expect(await screen.findByText("검색 조건에 맞는 항목이 없습니다.")).toBeInTheDocument();
    const clears = screen.getAllByRole("button", { name: "필터 초기화" });
    await user.click(clears[clears.length - 1]);
    await waitFor(() => expect(lastQuery().get("state")).toBe("active"));
  });

  it("목록을 못 받으면 판 안에서 상태를 말한다 — 권한 없음은 다시 시도가 없다", async () => {
    const err = Object.assign(new Error("forbidden"), { status: 403 });
    apiMock.mockRejectedValue(err);
    renderPane({ scope: { kind: "dept", deptId: "dep-sales", hasChildren: true } });
    expect(await screen.findByText("이 목록을 볼 권한이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /다시 시도/ })).toBeNull();
  });
});
