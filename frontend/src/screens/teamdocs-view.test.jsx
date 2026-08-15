/* 문서 목록의 **보기 전환**과 카드 격자 (R7).
 *
 * 기준 목업의 문서 화면은 3열 카드 격자인데 우리는 표 하나뿐이었다. 카드로 바꾸면서
 * **표를 없애지 않은 것**이 이 검사의 핵심이다 — 실제 문서가 104건이라 여러 건을 골라
 * 지우거나 한 번에 훑는 일이 실재한다. 보기를 바꿨다고 할 수 있던 일이 사라지면
 * 그건 개선이 아니라 기능 축소다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api.js", () => ({ api: vi.fn() }));
import { api } from "../lib/api.js";
import { TeamDocs } from "./TeamDocs.jsx";

const DOCS = [
  { id: "d1", title: "인프라 운영 계획", document_type: "작업 계획서", work_field: "인프라",
    tech_tags: ["Ansible"], projects: [], author_names: ["박세찬"], last_edited: "2026-08-01T00:00:00Z",
    is_favorite: false },
  { id: "d2", title: "권한 체계 설계", document_type: "설계서", work_field: "개발",
    tech_tags: ["RBAC"], projects: [], author_names: ["김하나"], last_edited: "2026-08-02T00:00:00Z",
    is_favorite: false },
];

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><TeamDocs /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  api.mockReset();
  api.mockImplementation((path) => {
    if (path.startsWith("/api/team-docs/filters")) {
      return Promise.resolve({ doc_types: [], work_fields: [], tech_tags: [], projects: [] });
    }
    return Promise.resolve({
      items: DOCS, page: 1, page_size: 20, total: 2,
      sync: { last_success_at: "2026-08-03T00:00:00Z" }, can_sync: true,
    });
  });
});

describe("제목 계층 — 필터·목록 구획 (SEM-02, PA-F-031)", () => {
  it("h1 하나뿐이던 화면에 필터·목록 h2가 있다", async () => {
    renderScreen();
    await screen.findByText("인프라 운영 계획");

    expect(screen.getByRole("heading", { level: 1, name: "문서" })).toBeInTheDocument();
    const h2s = screen.getAllByRole("heading", { level: 2 }).map((el) => el.textContent);
    expect(h2s).toEqual(["필터", "목록"]);
  });
});

describe("문서 목록 보기", () => {
  it("기본은 카드 격자다 — 기준 목업이 카드이고 문서는 훑어보며 고르는 화면이다", async () => {
    renderScreen();
    await screen.findByText("인프라 운영 계획");
    // 표가 아니라는 것을 본다: 열 머리글이 없어야 한다.
    expect(screen.queryByRole("columnheader", { name: "문서 종류" })).toBeNull();
    // 분류가 제목보다 먼저 보인다(카드의 요점).
    expect(screen.getByText("작업 계획서")).toBeTruthy();
  });

  it("표로 바꾸면 표가 나온다 — 카드로 바꾸면서 표를 없애지 않았다", async () => {
    renderScreen();
    await screen.findByText("인프라 운영 계획");
    fireEvent.click(screen.getByRole("button", { name: "표" }));
    await waitFor(() => expect(screen.getByRole("columnheader", { name: "문서 종류" })).toBeTruthy());
  });

  it("고른 보기를 기억한다 — 화면을 옮길 때마다 다시 바꾸게 하면 선택지가 아니라 잔소리다", async () => {
    const first = renderScreen();
    await screen.findByText("인프라 운영 계획");
    fireEvent.click(screen.getByRole("button", { name: "표" }));
    await waitFor(() => expect(window.localStorage.getItem("team-docs-view")).toBe("table"));
    first.unmount();

    renderScreen();
    await screen.findByText("인프라 운영 계획");
    expect(screen.getByRole("columnheader", { name: "문서 종류" })).toBeTruthy();
  });

  it("카드에서도 여러 건을 고를 수 있다 — 104건짜리 화면에서 선택이 사라지면 안 된다", async () => {
    renderScreen();
    await screen.findByText("인프라 운영 계획");
    const box = screen.getByRole("checkbox", { name: "인프라 운영 계획 선택" });
    fireEvent.click(box);
    await waitFor(() => expect(screen.getByRole("button", { name: /선택 삭제/ })).toBeTruthy());
  });
});

describe("열람 제한 배지(SEC-10)", () => {
  it("제한된 문서는 카드·표 양쪽에서 자물쇠로 표시된다", async () => {
    api.mockImplementation((path) => {
      if (path.startsWith("/api/team-docs/filters")) {
        return Promise.resolve({ doc_types: [], work_fields: [], tech_tags: [], projects: [] });
      }
      return Promise.resolve({
        items: [{ ...DOCS[0], restricted: true }, DOCS[1]],
        page: 1, page_size: 20, total: 2,
        sync: { last_success_at: "2026-08-03T00:00:00Z" }, can_sync: true,
      });
    });
    renderScreen();
    await screen.findByText("인프라 운영 계획");
    expect(screen.getAllByLabelText("열람 제한")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "표" }));
    await waitFor(() => expect(screen.getByRole("columnheader", { name: "문서 종류" })).toBeTruthy());
    expect(screen.getAllByLabelText("열람 제한")).toHaveLength(1);
  });
});
