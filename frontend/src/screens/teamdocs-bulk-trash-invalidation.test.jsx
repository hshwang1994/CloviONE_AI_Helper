/* 문서 목록에서 선택 삭제하면, 그 문서들의 **상세 캐시**(["team-doc", id])도 무효화돼야 한다.
 *
 * 예전에는 ["team-docs"](목록)·["trash"] 만 무효화했다. 그 문서의 상세를 먼저 열어 본 적이
 * 있으면(react-query 캐시에 ["team-doc", id]가 남아 있으면) 목록에서 방금 지운 그 문서를
 * 다시 열었을 때(같은 탭에서 뒤로가기, 검색·최근 문서 위젯의 딥링크 등) staleTime(30초) 동안
 * 캐시가 무효화되지 않아 "이미 지운 문서인데 아직 멀쩡하게 뜬다"는 화면이 됐다.
 *
 * 티켓 쪽은 이 자리를 `ticket-views.js::invalidateTicketViews`의 `["ticket"]` 접두어로 이미
 * 잡아 놨다(Trash.jsx가 티켓을 복원/영구삭제할 때도 그 표를 통째로 부른다) — 문서 목록의
 * 선택 삭제만 자기 상세 캐시를 부르지 않고 있었다.
 *
 * 같은 조사(L축 재감사, 2026-08-12)에서 발견한 두 번째 구멍도 여기서 같이 잡는다: home의
 * 「최근 문서」 위젯(Home.jsx `["home","today"]`)도 지운 문서가 사라져야 하는 화면인데
 * `document-views.js`가 생기기 전에는 아무도 `["home"]`을 무효화하지 않았다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api.js", () => ({ api: vi.fn() }));
import { api } from "../lib/api.js";
import { TeamDocs } from "./TeamDocs.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const DOCS = [
  { id: "d1", title: "인프라 운영 계획", document_type: "작업 계획서", work_field: "인프라",
    tech_tags: ["Ansible"], projects: [], author_names: ["박세찬"], last_edited: "2026-08-01T00:00:00Z",
    is_favorite: false },
];

function renderScreen(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><TeamDocs /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  api.mockReset();
  api.mockImplementation((path, opts) => {
    if (path.startsWith("/api/team-docs/filters")) {
      return Promise.resolve({ doc_types: [], work_fields: [], tech_tags: [], projects: [] });
    }
    if (path === "/api/team-docs/trash-bulk") {
      return Promise.resolve({ trashed: [{ id: "d1", title: "인프라 운영 계획" }], failed: [] });
    }
    return Promise.resolve({
      items: DOCS, page: 1, page_size: 20, total: 1,
      sync: { last_success_at: "2026-08-03T00:00:00Z" }, can_sync: true,
    });
  });
});

describe("문서 목록 선택 삭제 → 상세 캐시 무효화", () => {
  it("삭제한 문서의 team-doc 상세 캐시를 무효화한다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 상세를 먼저 열어 본 적이 있는 상태를 흉내낸다 — 캐시가 없으면 '무효화됐다'가
    // 아무 뜻도 없어서, 무엇을 해도 통과하는 테스트가 된다.
    qc.setQueryData(["team-doc", "d1"], { document: { id: "d1", title: "인프라 운영 계획" } });
    expect(qc.getQueryState(["team-doc", "d1"]).isInvalidated).toBe(false);

    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");

    fireEvent.click(screen.getByRole("checkbox", { name: "인프라 운영 계획 선택" }));
    fireEvent.click(await screen.findByRole("button", { name: /선택 삭제/ }));

    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "1건 삭제" }));

    await waitFor(() => {
      expect(qc.getQueryState(["team-doc", "d1"]).isInvalidated, "문서 상세 캐시").toBe(true);
    });
  });

  it("삭제한 문서가 home의 「최근 문서」 위젯 캐시까지 무효화한다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 홈 탭이 이미 값을 들고 있는 상태를 흉내낸다 — 캐시가 없으면 '무효화됐다'가 아무
    // 뜻도 없다.
    qc.setQueryData(["home", "today"], { recent: { documents: [{ id: "d1", title: "인프라 운영 계획" }], board: [] } });
    expect(qc.getQueryState(["home", "today"]).isInvalidated).toBe(false);

    renderScreen(qc);
    await screen.findByText("인프라 운영 계획");

    fireEvent.click(screen.getByRole("checkbox", { name: "인프라 운영 계획 선택" }));
    fireEvent.click(await screen.findByRole("button", { name: /선택 삭제/ }));

    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "1건 삭제" }));

    await waitFor(() => {
      expect(qc.getQueryState(["home", "today"]).isInvalidated, "home 「최근 문서」 위젯").toBe(true);
    });
  });
});
