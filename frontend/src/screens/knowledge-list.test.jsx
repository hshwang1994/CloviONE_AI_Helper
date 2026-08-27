/* qa-contract-replaced-by: frontend/src/screens/teamdocs-view.test.jsx
 * qa-contract-replaced-by: frontend/src/screens/doc-create-form.test.jsx
 *
 * qa-contract-change: 화면이 카드 목록에서 탐색기와 표로 재설계돼(지시 22.4) 조작기 이름과 자리가 전부 바뀌었다. 지키는 성질은 그대로 옮기고 요약·정렬·작성자 축을 더했다.
 *
 * 옛 문서 목록(`TeamDocs.jsx`)의 목록·생성 계약을 이 파일이 이어받는다 (S14 · C2).
 * 살아 있는 것: 조건이 **서버 질의에 실려 나가는가**(화면에서만 거르면 다음 쪽에서
 * 조건이 사라진다) · 조건을 바꾸면 첫 쪽으로 돌아오는가 · 목록 줄이 종류와 태그를
 * 그리는가 · 새 문서 폼이 적은 값과 지금 보고 있는 공간을 그대로 실어 보내는가.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 문서 작업공간 — **찾는 데 필요한 것이 화면에 있는가** (지시 22.4).
 *
 * ## 쪽 넘기기
 *
 * 서버는 처음부터 `limit`·`offset`·`total` 을 줬는데 예전 화면이 그중 하나도 안 썼다.
 * 운영에서 문서가 110건인데 50건에서 끊겨서, 나머지 60건은 **있다는 사실 자체가**
 * 사용자에게 안 보였다. 여기서 못박는 것은 모양이 아니라 동작이다: 다음 쪽을 누르면 그
 * 다음 문서를 실제로 **요청**하는가.
 *
 * ## 조건은 전부 서버로 간다
 *
 * 태그 · 작성자 · 정렬 · 즐겨찾기 · 내 초안. 화면에서만 거르면 다음 쪽에서 조건이 사라진다.
 *
 * ## 요약 넷은 **누르면 좁혀진다**
 *
 * 장식 숫자를 안 둔다는 결정을 시험이 지킨다 — 「즐겨찾기 36」을 눌렀는데 목록이 그대로면
 * 그 수는 그림이다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { id: "u-1", display_name: "나", role: "user" } }),
}));

import { Knowledge } from "./Knowledge.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const SPACE = "space-1";
const PAGE = 25;

function docsPage(offset, count, total) {
  return {
    items: Array.from({ length: count }, (_, i) => ({
      id: `doc-${offset + i}`,
      title: `문서 ${offset + i}`,
      source_type: "USER",
      is_favorite: offset + i === 0,
      updated_at: "2026-08-20T01:00:00",
      space_name: "우리 공간",
      folder_path: "",
      excerpt: "",
      author: { user_id: "u-1", display_name: "나" },
      counts: { attachments: 0, comments: 0, relations: 0 },
      // 첫 문서에만 종류·태그를 준다 — 목록 줄이 실제로 그리는지만 보면 된다.
      ...(offset + i === 0
        ? { doc_type: "회의록", tags: [{ id: "tag-1", name: "인프라" }] }
        : {}),
    })),
    authors: [{ value: "u-1", label: "나" }],
    total,
    limit: PAGE,
    offset,
  };
}

const calls = [];

function baseRoutes(path) {
  const text = String(path);
  if (text.startsWith("/api/knowledge/spaces/")) return { folders: [] };
  if (text === "/api/knowledge/spaces") return { items: [{ id: SPACE, name: "우리 공간" }] };
  if (text === "/api/knowledge/tags") {
    return { items: [{ id: "tag-1", name: "회의록", slug: "meeting-notes" }] };
  }
  if (text === "/api/knowledge/summary") {
    return { total: 110, recent: 4, favorites: 3, drafts: 2 };
  }
  if (text === "/api/knowledge/templates") {
    return { items: [{ id: "blank", name: "빈 문서", help: "빈 상태로 시작합니다.", empty: true }] };
  }
  if (text.startsWith("/api/knowledge/recent")) return { items: [] };
  return null;
}

beforeEach(() => {
  calls.length = 0;
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    calls.push(String(path));
    const base = baseRoutes(path);
    if (base) return Promise.resolve(base);
    const url = new URL(String(path), "https://x");
    const offset = Number(url.searchParams.get("offset") || 0);
    return Promise.resolve(docsPage(offset, Math.min(PAGE, 110 - offset), 110));
  });
});

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[`/knowledge?space=${SPACE}`]}>
          <Knowledge />
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/* 목록이 그려졌는가. **여러 개를 받는다** — 곁열(즐겨찾기)에도 같은 제목이 서고, 그것이
   의도다: 자주 보는 문서는 목록 어디쯤 있든 곁열에서 바로 열린다. */
async function seeRows() {
  return screen.findAllByText("문서 0");
}

function documentCalls() {
  return calls.filter((p) => p.startsWith("/api/knowledge/documents"));
}

function lastDocumentCall() {
  const rows = documentCalls();
  return rows[rows.length - 1];
}

describe("문서 목록의 쪽 넘기기", () => {
  it("전체 건수를 말하고, 다음 쪽을 누르면 그 다음 문서를 실제로 요청한다", async () => {
    renderList();
    await seeRows();

    expect(await screen.findByText(/총 110건/)).toBeTruthy();
    expect(documentCalls()[0]).toContain(`limit=${PAGE}`);
    expect(documentCalls()[0]).toContain("offset=0");

    await userEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(documentCalls().length).toBeGreaterThan(1));
    expect(lastDocumentCall()).toContain(`offset=${PAGE}`);
    expect((await screen.findAllByText(`문서 ${PAGE}`)).length).toBeGreaterThan(0);
  });

  it("즐겨찾기 조건은 서버 질의에 실려 나간다", async () => {
    renderList();
    await seeRows();

    const strip = await screen.findByRole("group", { name: "문서 요약" });
    await userEvent.click(within(strip).getByText("즐겨찾기"));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("favorites=true"))).toBe(true));
  });

  it("조건을 바꾸면 첫 쪽으로 돌아온다 — 세 번째 쪽에서 걸러 놓고 빈 화면을 보면 안 된다", async () => {
    renderList();
    await seeRows();
    await userEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(documentCalls().length).toBeGreaterThan(1));

    const strip = await screen.findByRole("group", { name: "문서 요약" });
    await userEvent.click(within(strip).getByText("즐겨찾기"));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("favorites=true"))).toBe(true));
    expect(lastDocumentCall()).toContain("offset=0");
  });

  it("담아 둔 문서에는 별이 보이고, 그 별로 담고 뺄 수 있다", async () => {
    renderList();
    await seeRows();
    /* 별은 **조작기**다. 예전에는 그림뿐이라 목록에서 즐겨찾기를 걸려면 문서를 열어야
       했다 — 자주 보는 문서를 고르는 일은 목록에서 하는 일이다. */
    const star = screen.getByRole("button", { name: "문서 0 즐겨찾기 해제" });
    expect(star.getAttribute("aria-pressed")).toBe("true");
    await userEvent.click(star);
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p]) => String(p).includes("/favorite?on=false"));
      expect(post, "별을 눌렀는데 요청이 안 나갔다").toBeTruthy();
    });
  });

  it("문서 줄에 종류와 태그가 보인다 — 필터만 있고 줄에는 없으면 손실처럼 보인다", async () => {
    renderList();
    await seeRows();
    expect((await screen.findAllByText("인프라")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("회의록").length).toBeGreaterThan(0);
  });

  /* 🔴 **화면이 말하는 조건과 실제 질의 조건이 같아야 한다** (S15 · C7).
   *
   * 이 검색 상자는 한때 맨 `TextField` 에 `defaultValue={q}` 였다 — 값을 **처음 한 번만**
   * 읽는 입력이라 주소가 바깥에서 바뀌어도 상자는 따라오지 않았다. 그래서 「필터 지우기」를
   * 누르면 목록은 조건 없이 다시 받아 오는데 상자에는 방금 지운 검색어가 그대로 남았다. */
  it("검색어를 지우면 상자도 함께 빈다 — 화면이 없는 조건을 말하지 않는다", async () => {
    renderList();
    await seeRows();

    const box = screen.getByRole("searchbox", { name: "문서 검색" });
    await userEvent.type(box, "회의");
    await waitFor(
      () => expect(documentCalls().some((p) => p.includes("q=%ED%9A%8C%EC%9D%98"))).toBe(true),
      { timeout: 2000 },
    );
    expect(box.value).toBe("회의");

    const clear = await screen.findByRole("button", { name: "필터 지우기" }, { timeout: 3000 });
    await userEvent.click(clear);
    await waitFor(() => expect(screen.getByRole("searchbox", { name: "문서 검색" }).value).toBe(""));
  });

  it("태그 조건도 서버 질의에 실려 나간다 — 옛 화면의 문서 종류, 업무 분야, 기술 태그를 대신한다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByLabelText("태그"));
    await userEvent.click(await screen.findByRole("option", { name: "회의록" }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("tag=meeting-notes"))).toBe(true));
    expect(lastDocumentCall()).toContain("offset=0");
  });

  it("작성자와 정렬도 조건이다 — 후보는 목록 응답이 들고 온다", async () => {
    renderList();
    await seeRows();

    /* 🔴 후보를 사용자 표에서 통째로 뽑으면 문서를 한 건도 안 쓴 사람이 목록에 서고,
       남의 부서 문서만 쓴 사람의 이름이 이 화면에 나온다. 후보 목록도 데이터다. */
    await userEvent.click(screen.getByLabelText("작성자"));
    await userEvent.click(await screen.findByRole("option", { name: "나" }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("created_by=u-1"))).toBe(true));

    await userEvent.click(screen.getByLabelText("정렬"));
    await userEvent.click(await screen.findByRole("option", { name: "제목순" }));
    await waitFor(() => expect(documentCalls().some((p) => p.includes("sort=title"))).toBe(true));
  });
});

describe("요약 넷", () => {
  it("서버가 센 수를 그대로 말한다", async () => {
    renderList();
    await seeRows();
    const strip = await screen.findByRole("group", { name: "문서 요약" });
    expect(within(strip).getByText("110")).toBeTruthy();
    expect(within(strip).getByText("전체 문서")).toBeTruthy();
    expect(within(strip).getByText("내 초안")).toBeTruthy();
  });

  it("🔴 누르면 목록이 그 조건으로 좁아진다 — 장식용 숫자를 두지 않는다", async () => {
    renderList();
    await seeRows();
    const strip = await screen.findByRole("group", { name: "문서 요약" });

    await userEvent.click(within(strip).getByText("내 초안"));
    await waitFor(() => {
      const last = lastDocumentCall();
      expect(last).toContain("mine=true");
      expect(last).toContain("drafts=true");
    });
  });
});

/* 폼과 API 가 어긋나면 사용자가 적은 값이 조용히 사라진다.
 *
 * 옛 문서 화면에서 실제로 그랬다: 서버는 소유자 칸을 받는데 폼에 그 칸이 없어서, 포털에서
 * 만든 문서는 그 값을 채울 방법이 아예 없었고 상세 화면은 빈 줄을 보여 줬다.
 */
describe("새 문서 만들기", () => {
  it("적은 제목과 고른 공간, 틀이 그대로 생성 요청에 실린다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByRole("button", { name: "새 문서" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/문서 제목/), "인수인계 메모");
    await userEvent.click(within(dialog).getByRole("button", { name: "만들기" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(
        ([p, opts]) => String(p) === "/api/knowledge/documents" && opts && opts.method === "POST");
      expect(post, "생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.title).toBe("인수인계 메모");
      expect(post[1].body.space_id, "지금 보고 있는 공간이 안 실렸다").toBe(SPACE);
      expect(post[1].body.template, "고른 틀이 안 실렸다").toBe("blank");
    });
  });

  it("제목이 비면 만들 수 없다 — 이름 없는 문서는 목록에서 다시 못 찾는다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByRole("button", { name: "새 문서" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "만들기" });
    expect(submit.hasAttribute("disabled")).toBe(true);
  });
});
