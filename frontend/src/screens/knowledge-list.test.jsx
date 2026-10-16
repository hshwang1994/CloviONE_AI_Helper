/* qa-contract-change: UI 3차 조합 계약 C-1 — 사람이 고른 프로젝트도 조건이라 칩을 갖고(조건 수 = 칩 수), 목록 위 단독 「전체 N건」 줄을 걷었다. 결과 수 단언을 조건 줄로 옮기고 칩 목록 · 지우기가 프로젝트까지 푸는지 · 정렬 자리를 더한다. */
/* qa-contract-replaced-by: frontend/src/screens/teamdocs-view.test.jsx
 * qa-contract-replaced-by: frontend/src/screens/doc-create-form.test.jsx
 *
 * qa-contract-change: 화면이 카드 목록에서 탐색기와 표로 재설계돼(지시 22.4) 조작기 이름과 자리가 전부 바뀌었다. 지키는 성질은 그대로 옮기고 요약·정렬·작성자 축을 더했다.
 *
 * qa-contract-change: 요약 판독 줄 넷(role=group 「문서 요약」)과 필터 줄의 「보기」 고르개가 세그먼티드 하나(role=tablist 「문서 보기」, 칸마다 건수)로 합쳐져(핸드오프 계획 D · O-1), 요약 수 · 누르면 좁히는 계약을 탭으로 옮기고 필터 줄 순서 · 조건 줄 · 표 행 · 실패 상자 단언을 더한다.
 *
 * 옛 문서 목록(`TeamDocs.jsx`)의 목록·생성 계약을 이 파일이 이어받는다 (S14 · C2).
 * 살아 있는 것: 조건이 **서버 질의에 실려 나가는가**(화면에서만 거르면 다음 쪽에서
 * 조건이 사라진다) · 조건을 바꾸면 첫 쪽으로 돌아오는가 · 목록 줄이 종류와 태그를
 * 그리는가 · 새 문서 폼이 적은 값과 지금 보고 있는 공간을 그대로 실어 보내는가.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
/* 로그인 사용자의 역할은 시험마다 다르다 — 태그를 고치고 지우는 것은 운영자만이다.
   `vi.hoisted` 로 만든 상자를 대역이 읽는다(`vi.mock` 은 끌어올려지므로 평범한 변수를
   참조하면 초기화 전에 읽는다). */
const authState = vi.hoisted(() => ({ role: "user" }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { id: "u-1", display_name: "나", role: authState.role } }),
}));

import { Knowledge } from "./Knowledge.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const SPACE = "space-1";
const PAGE = 100;

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
      // 첫 문서에만 종류·태그·프로젝트를 준다 — 목록 줄이 실제로 그리는지만 보면 된다.
      // 나머지는 project: undefined 라 "프로젝트 미지정"으로 보여야 한다(§11.2).
      ...(offset + i === 0
        ? {
          doc_type: "회의록", tags: [{ id: "tag-1", name: "인프라" }],
          project: { id: "proj-1", code: "AAAAAA", name: "알파 프로젝트" },
        }
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
  if (text === "/api/knowledge/spaces") {
    return { items: [{ id: SPACE, name: "우리 공간", owner_kind: "organization" }] };
  }
  if (text === "/api/knowledge/tags") {
    return {
      items: [
        { id: "tag-1", name: "회의록", slug: "meeting-notes", document_count: 3 },
        { id: "tag-2", name: "인프라", slug: "infra", document_count: 0 },
      ],
    };
  }
  if (text === "/api/knowledge/categories") {
    return {
      items: [
        { id: "cat-1", name: "회의 기록", slug: "회의 기록", sort_order: 1024, document_count: 2 },
        { id: "cat-2", name: "기술 문서", slug: "기술 문서", sort_order: 2048, document_count: 0 },
      ],
    };
  }
  if (text === "/api/knowledge/summary") {
    return { total: 110, recent: 4, favorites: 3, drafts: 2 };
  }
  if (text === "/api/knowledge/templates") {
    return { items: [{ id: "blank", name: "빈 문서", help: "빈 상태로 시작합니다.", empty: true }] };
  }
  if (text.startsWith("/api/knowledge/recent")) return { items: [] };
  if (text.startsWith("/api/projects")) {
    // ProjectPicker(새 문서 폼)의 후보 — 공간이 아직 없는 프로젝트가 섞여 있다.
    return {
      items: [
        { id: "proj-1", name: "알파 프로젝트", code: "AAAAAA" },
        { id: "proj-2", name: "베타 프로젝트", code: "BBBBBB" },
      ],
      total: 2,
    };
  }
  return null;
}

beforeEach(() => {
  calls.length = 0;
  authState.role = "user";
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

function renderList(entry = "/knowledge?project=none") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[entry]}>
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

describe("문서 목록의 묶음 이어 받기", () => {
  it("전체 건수와 받은 건수를 말하고, 더 받으면 **이어 붙는다**", async () => {
    renderList();
    await seeRows();

    /* 「이 조건에 몇 건인가」는 필터 면 안 조건 줄이, 「그중 몇 건을 받았는가」는 목록 끝 줄이 말한다. 목록 위 단독
       「전체 N건」 줄은 없다(조합 계약 C-1). 이 화면은 「프로젝트 미지정」을 고른 채 열리므로 조건이 하나다. */
    await waitFor(() => expect(document.querySelector("[data-condition-count]")).not.toBeNull());
    expect(document.querySelector("[data-condition-count]").textContent).toBe("검색 결과 110건");
    expect(screen.queryByText("전체 110건")).toBeNull();
    expect(documentCalls()[0]).toContain(`limit=${PAGE}`);
    expect(documentCalls()[0]).toContain("offset=0");
    expect(await screen.findByText(`전체 110건 중 ${PAGE}건 표시`)).toBeTruthy();

    /* 단추 경로가 정본이다 — 키보드·스크린리더 사용자가 실제로 쓰는 길이고, 그 길이 없으면
       이 목록은 그들에게 첫 묶음이 전부다. */
    await userEvent.click(screen.getByRole("button", { name: "문서 더 보기" }));
    await waitFor(() => expect(documentCalls().length).toBeGreaterThan(1));
    expect(lastDocumentCall()).toContain(`offset=${PAGE}`);

    /* 🔴 「이어 붙였는가」는 **받은 행 수**로 잰다. 화면에서 100번째 행을 찾으면 안 된다 —
       가상화가 목적대로 돌면 그 행은 DOM 에 없다(그것이 가상화가 하는 일이다).
       `data-virtual-total` 이 그 자리를 위해 있는 속성이다(§18.2). */
    await waitFor(() => {
      const table = document.querySelector("table[data-virtual-total]");
      expect(table.getAttribute("data-virtual-total")).toBe("110");
    });
    expect(await screen.findByText("전체 110건 중 110건 표시")).toBeTruthy();
    /* 다 받았으면 더 받을 단추가 없다. */
    expect(screen.queryByRole("button", { name: "문서 더 보기" })).toBeNull();
    /* 앞 묶음이 그대로 남아 있다 = 갈아 끼운 게 아니라 이어 붙였다. */
    expect(screen.getAllByText("문서 0").length).toBeGreaterThan(0);
  });

  it("끝까지 굴려도 같은 일이 일어난다 — 단추와 자동 로딩이 같은 것을 부른다", async () => {
    renderList();
    await seeRows();
    await act(async () => { globalThis.__intersect(); });
    await waitFor(() => expect(documentCalls().length).toBeGreaterThan(1));
    expect(lastDocumentCall()).toContain(`offset=${PAGE}`);
  });

  it("즐겨찾기 조건은 서버 질의에 실려 나간다", async () => {
    renderList();
    await seeRows();

    const views = await screen.findByRole("tablist", { name: "문서 보기" });
    await userEvent.click(within(views).getByRole("tab", { name: /^즐겨찾기/ }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("favorites=true"))).toBe(true));
  });

  it("조건을 바꾸면 받아 둔 묶음을 **버린다** — 옛 조건의 문서가 새 목록 위에 남지 않는다", async () => {
    renderList();
    await seeRows();
    await userEvent.click(screen.getByRole("button", { name: "문서 더 보기" }));
    await waitFor(() => expect(documentCalls().length).toBeGreaterThan(1));
    await waitFor(() => {
      expect(document.querySelector("table[data-virtual-total]").getAttribute("data-virtual-total")).toBe("110");
    });

    const views = await screen.findByRole("tablist", { name: "문서 보기" });
    await userEvent.click(within(views).getByRole("tab", { name: /^즐겨찾기/ }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("favorites=true"))).toBe(true));
    expect(lastDocumentCall()).toContain("offset=0");
    /* 두 번째 묶음이 사라졌다. 남으면 hasNext 가 옛 데이터에서 나오고, 센티넬이 그 자리에서
       다음을 불러 옛 조건 아래에 새 조건이 붙는다(`keepPreviousData` 를 안 쓰는 이유). */
    await waitFor(() => {
      expect(document.querySelector("table[data-virtual-total]").getAttribute("data-virtual-total")).toBe("100");
    });
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

  it("별을 같은 틱에 두 번 눌러도 즐겨찾기 요청은 한 번이다 (P4)", async () => {
    /* 별은 누르는 동안 꺼지지 않는 맨 단추라, 두 번 누르면 둘 다 아직 안 바뀐 옛 상태로 같은 요청을 만든다. */
    const base = apiMock.getMockImplementation();
    apiMock.mockImplementation((path, opts) => {
      if (String(path).includes("/favorite?")) return new Promise(() => {});
      return base(path, opts);
    });
    renderList();
    await seeRows();
    const star = screen.getByRole("button", { name: "문서 0 즐겨찾기 해제" });
    act(() => {
      fireEvent.click(star);
      fireEvent.click(star);
    });
    const favorites = () => apiMock.mock.calls.filter(([p]) => String(p).includes("/favorite?"));
    await waitFor(() => expect(favorites()).toHaveLength(1));
    await act(async () => {});
    expect(favorites()).toHaveLength(1);
    expect(String(favorites()[0][0])).toContain("/favorite?on=false");
  });

  it("문서 줄에 종류와 태그가 보인다 — 필터만 있고 줄에는 없으면 손실처럼 보인다", async () => {
    renderList();
    await seeRows();
    expect((await screen.findAllByText("인프라")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("회의록").length).toBeGreaterThan(0);
  });

  it("🔴 프로젝트 열이 공간이 아니라 프로젝트를 낸다 — 없으면 「프로젝트 미지정」이다(§11.2·§11.3)", async () => {
    renderList();
    await seeRows();
    // doc-0 만 project 를 받았다(픽스처) — 그 줄은 프로젝트 이름, 나머지는 미지정.
    expect((await screen.findAllByText("알파 프로젝트")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("프로젝트 미지정").length).toBeGreaterThan(0);
    // "공간"이라는 낱말 자체가 목록 화면에 안 남는다("공간 추가" 관리자 버튼은 예외).
    expect(screen.queryByText("우리 공간")).toBeNull();
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

    const clear = await screen.findByRole("button", { name: "필터 초기화" }, { timeout: 3000 });
    await userEvent.click(clear);
    await waitFor(() => expect(screen.getByRole("searchbox", { name: "문서 검색" }).value).toBe(""));
  });

  it("태그 조건도 서버 질의에 실려 나간다 — 옛 화면의 문서 종류, 업무 분야, 태그를 대신한다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByLabelText("태그"));
    await userEvent.click(await screen.findByRole("option", { name: /^회의록/ }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes(`tags=${encodeURIComponent("회의록")}`))).toBe(true));
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

describe("보기 전환 — 세그먼티드 하나가 요약 넷과 「보기」 고르개를 합친다", () => {
  it("서버가 센 수를 탭마다 그대로 말한다 — 「최근 열람」은 건수가 없다", async () => {
    renderList();
    await seeRows();
    const views = await screen.findByRole("tablist", { name: "문서 보기" });
    await waitFor(() => expect(within(views).getByRole("tab", { name: "전체 문서 110" })).toBeTruthy());
    const tabs = within(views).getAllByRole("tab").map((t) => t.textContent.replace(/\s+/g, " ").trim());
    expect(tabs).toEqual(["전체 문서 110", "최근 24시간 4", "즐겨찾기 3", "내 초안 2", "최근 열람"]);
    // 지금 보기는 「전체 문서」다.
    expect(within(views).getByRole("tab", { name: "전체 문서 110" })).toHaveAttribute("aria-selected", "true");
    // 같은 축을 두 자리에서 그리지 않는다 — 필터 줄의 「보기」 고르개와 요약 줄은 없다.
    expect(screen.queryByRole("group", { name: "문서 요약" })).toBeNull();
    expect(screen.queryByLabelText("보기")).toBeNull();
  });

  it("🔴 누르면 목록이 그 조건으로 좁아진다 — 장식용 숫자를 두지 않는다", async () => {
    renderList();
    await seeRows();
    const views = await screen.findByRole("tablist", { name: "문서 보기" });

    await userEvent.click(within(views).getByRole("tab", { name: /^내 초안/ }));
    await waitFor(() => {
      const last = lastDocumentCall();
      expect(last).toContain("mine=true");
      expect(last).toContain("drafts=true");
    });
    expect(within(views).getByRole("tab", { name: /^내 초안/ })).toHaveAttribute("aria-selected", "true");
    // 보기도 조건이다 — 조건 줄이 서고 칩으로 풀 수 있다(예전 「보기」 고르개와 같은 계약). 사람이 고른 프로젝트(미지정)도
    // 조건이라 칩이 둘이고 조건 수는 칩 수다(조합 계약 C-1).
    const line = document.querySelector("[data-condition-line]");
    expect(line).toBeTruthy();
    expect(line.textContent).toContain("검색 결과");
    const chipNames = [...line.querySelectorAll("[data-condition-chip]")].map((c) => c.textContent);
    expect(chipNames).toEqual(["보기: 내 초안", "프로젝트: 프로젝트 미지정"]);
    await userEvent.click(within(line).getByRole("button", { name: "필터 초기화" }));
    await waitFor(() => expect(lastDocumentCall()).not.toContain("drafts=true"));
    // 지우기는 칩이 선 축을 전부 지운다 — 프로젝트 조건도 풀린다.
    await waitFor(() => expect(lastDocumentCall()).not.toContain("project_id=none"));
  });

  it("「최근 열람」은 탭으로 고르고 쪽을 나누지 않는다", async () => {
    renderList();
    await seeRows();
    const views = await screen.findByRole("tablist", { name: "문서 보기" });
    await userEvent.click(within(views).getByRole("tab", { name: "최근 열람" }));
    await waitFor(() => expect(calls.some((p) => p.startsWith("/api/knowledge/recent"))).toBe(true));
    expect(screen.queryByRole("button", { name: "문서 더 보기" })).toBeNull();
  });
});

describe("필터 바 — 한 줄 순서와 조건 줄 (핸드오프 README §3 · ACCEPTANCE D1 · D3)", () => {
  it("검색 → 프로젝트 · 분류 · 태그 · 작성자 → 오른쪽 끝 정렬 순서로 한 줄에 선다", async () => {
    renderList();
    await seeRows();
    const row = document.querySelector("[data-filter-surface] [data-search-slot]");
    expect(row).toBeTruthy();
    const search = screen.getByRole("searchbox", { name: "문서 검색" });
    const order = [
      search,
      screen.getByLabelText("프로젝트"),
      screen.getByLabelText("분류"),
      screen.getByLabelText("태그"),
      screen.getByLabelText("작성자"),
      screen.getByLabelText("정렬"),
    ];
    for (const el of order) expect(row.contains(el), "필터 칸이 한 줄 밖에 섰다").toBe(true);
    for (let i = 1; i < order.length; i += 1) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING, `${i} 번째 순서`).toBeTruthy();
    }
    // 걸린 조건은 고른 프로젝트 하나다 — 조건 줄이 필터 면 안 마지막 줄에 서고, 목록 위 단독 결과 줄은 없다(조합 계약 C-1).
    const surface = document.querySelector("[data-filter-surface]");
    const line = surface.querySelector("[data-condition-line]");
    expect(line).not.toBeNull();
    expect(surface.lastElementChild).toBe(line);
    expect(line.querySelector("[data-condition-count]").textContent).toBe("검색 결과 110건");
    expect([...line.querySelectorAll("[data-condition-chip]")].map((c) => c.textContent)).toEqual(["프로젝트: 프로젝트 미지정"]);
    expect(screen.queryByText("전체 110건")).toBeNull();
    // 정렬은 오른쪽 끝 묶음이라 칸 흐름의 마지막이다.
    expect(row.lastElementChild.contains(screen.getByLabelText("정렬"))).toBe(true);
  });
});

describe("문서 표 — 두 줄 행 · 태그 넷 + N · 분류 점 + 낱말 (ACCEPTANCE J2)", () => {
  it("행은 바닥 76 의 두 줄 행이고, 분류는 점 + 낱말이며, 작업은 작은 단추다", async () => {
    renderList();
    await seeRows();
    const first = screen.getAllByText("문서 0")[0].closest("tr");
    expect(first).toBeTruthy();
    const dot = first.querySelector("[data-dot-label]");
    expect(dot, "분류가 점 + 낱말이 아니다").toBeTruthy();
    expect(dot).toHaveTextContent("회의록");
    const more = within(first).getByRole("button", { name: "문서 0 작업" });
    expect(more.className).toMatch(/MuiIconButton-sizeSmall/);
    const cell = first.querySelector("td");
    expect(getComputedStyle(cell).height).toBe("4.75rem");
    // 제목은 표 공통 제목 칸(`TitleCell`)이다 — 링크색 600 한 줄 · 전체 제목은 title. 행 열기는 표가 들어서 제목은 색만 받는다(`link`).
    const title = first.querySelector("[data-title-cell]");
    expect(title, "제목이 표 공통 제목 칸이 아니다").not.toBeNull();
    expect(title.getAttribute("data-title-cell")).toBe("link");
    expect(title).toHaveTextContent("문서 0");
    expect(title).toHaveAttribute("title", "문서 0");
    expect(getComputedStyle(title).whiteSpace).toBe("nowrap");
    // 요약 · 태그는 제목 칸 아래 그대로다 — 제목 칸이 한 줄이 됐다고 둘을 걷지 않는다.
    expect(title.parentElement.contains(first.querySelector(".k-tag"))).toBe(true);
  });

  it("태그가 넷을 넘으면 넷만 서고 남은 수를 「+N」 하나가 말한다", async () => {
    apiMock.mockImplementation((path) => {
      calls.push(String(path));
      const base = baseRoutes(path);
      if (base) return Promise.resolve(base);
      const page = docsPage(0, 3, 3);
      page.items[0].tags = ["A", "B", "C", "D", "E", "F"].map((n, i) => ({ id: `t-${i}`, name: n }));
      return Promise.resolve(page);
    });
    renderList();
    await seeRows();
    const first = screen.getAllByText("문서 0")[0].closest("tr");
    const tags = [...first.querySelectorAll(".k-tag")].map((t) => t.textContent);
    expect(tags).toEqual(["A", "B", "C", "D", "+2"]);
    expect(first.querySelector(".k-tag:last-child")).toHaveAttribute("title", "E, F");
  });
});

describe("실패는 그 자리의 메시지 박스다 (핸드오프 RULES §1 · 계획 표 6)", () => {
  it("별을 눌러 실패하면 목록 위 상자가 말하고, 다시 눌러 성공하면 걷힌다", async () => {
    let fail = true;
    apiMock.mockImplementation((path, opts) => {
      calls.push(String(path));
      if (String(path).includes("/favorite")) {
        if (fail) return Promise.reject(new Error("즐겨찾기를 바꾸지 못했습니다."));
        return Promise.resolve({ ok: true });
      }
      const base = baseRoutes(path);
      if (base) return Promise.resolve(base);
      const url = new URL(String(path), "https://x");
      const offset = Number(url.searchParams.get("offset") || 0);
      return Promise.resolve(docsPage(offset, Math.min(PAGE, 110 - offset), 110));
    });
    renderList();
    await seeRows();
    await userEvent.click(screen.getByRole("button", { name: "문서 0 즐겨찾기 해제" }));
    const box = await screen.findByText("즐겨찾기를 바꾸지 못했습니다.");
    // 상자는 목록 판보다 앞에 선다 — 토스트처럼 사라지지 않고, 페이지 머리로 가지 않는다.
    const table = document.querySelector("table");
    expect(box.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "문서 0 즐겨찾기 해제" }));
    await waitFor(() => expect(screen.queryByText("즐겨찾기를 바꾸지 못했습니다.")).toBeNull());
  });

  it("분류 관리에서 추가가 실패하면 그 창 안 상자가 말하고, 창을 닫았다 열면 걷힌다", async () => {
    authState.role = "system_admin";
    apiMock.mockImplementation((path, opts) => {
      calls.push(String(path));
      if (String(path) === "/api/knowledge/categories" && opts && opts.method === "POST") {
        return Promise.reject(new Error("같은 이름의 분류가 이미 있습니다."));
      }
      const base = baseRoutes(path);
      if (base) return Promise.resolve(base);
      const url = new URL(String(path), "https://x");
      const offset = Number(url.searchParams.get("offset") || 0);
      return Promise.resolve(docsPage(offset, Math.min(PAGE, 110 - offset), 110));
    });
    renderList();
    await seeRows();
    await userEvent.click(screen.getByRole("button", { name: "분류 관리" }));
    let dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("새 분류"), "회의 기록");
    await userEvent.click(within(dialog).getByRole("button", { name: "추가" }));
    expect(await within(dialog).findByText("같은 이름의 분류가 이미 있습니다.")).toBeTruthy();

    // 발의 「닫기」로 닫는다(머리의 닫기 아이콘과 같은 이름이라 마지막 것을 누른다).
    const closes = within(dialog).getAllByRole("button", { name: "닫기" });
    await userEvent.click(closes[closes.length - 1]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "분류 관리" }));
    dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText("같은 이름의 분류가 이미 있습니다.")).toBeNull();
  });
});

/* 폼과 API 가 어긋나면 사용자가 적은 값이 조용히 사라진다.
 *
 * 옛 문서 화면에서 실제로 그랬다: 서버는 소유자 칸을 받는데 폼에 그 칸이 없어서, 포털에서
 * 만든 문서는 그 값을 채울 방법이 아예 없었고 상세 화면은 빈 줄을 보여 줬다.
 */
describe("새 문서 만들기", () => {
  /** 필수 셋을 채운다 — 제목·분류·태그. 프로젝트는 선택이라 안 건드린다. */
  async function fillRequired(dialog, title) {
    await userEvent.type(within(dialog).getByLabelText(/문서 제목/), title);
    await userEvent.click(within(dialog).getByLabelText(/^분류/));
    await userEvent.click(await screen.findByRole("option", { name: "회의 기록" }));
    await userEvent.click(within(dialog).getByLabelText(/^태그/));
    // MUI Autocomplete 의 옵션은 Portal 로 body 에 붙는다 — within(dialog) 밖이다.
    await userEvent.click(await screen.findByRole("option", { name: /^인프라/ }));
  }

  it("🔴 프로젝트를 안 골라도 만들어진다 — 공간 id 를 화면이 짓지 않는다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByRole("button", { name: "새 문서" }));
    const dialog = await screen.findByRole("dialog");
    await fillRequired(dialog, "인수인계 메모");
    await userEvent.click(within(dialog).getByRole("button", { name: "만들기" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(
        ([p, opts]) => String(p) === "/api/knowledge/documents" && opts && opts.method === "POST");
      expect(post, "생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.title).toBe("인수인계 메모");
      /* qa-contract-change: 예전에는 화면이 공간 목록을 뒤져 space_id 를 지어 보냈다.
         이제 아무 자리 값도 안 보낸다 — 서버가 조직 공통 공간을 찾거나 만든다. */
      expect(post[1].body.space_id).toBeUndefined();
      expect(post[1].body.project_id).toBeUndefined();
      expect(post[1].body.category_id).toBeTruthy();
      expect(post[1].body.tag_names.length).toBeGreaterThan(0);
      expect(post[1].body.template, "고른 틀이 안 실렸다").toBe("blank");
      // 폴더 축은 화면에서 걷혔다 — 요청에도 안 실린다.
      expect(post[1].body.folder_id).toBeUndefined();
    });
  });

  it("🔴 공간이 아직 없는 프로젝트도 고를 수 있다 — project_id 로 나가고 폴더 칸은 없다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByRole("button", { name: "새 문서" }));
    const dialog = await screen.findByRole("dialog");
    await fillRequired(dialog, "알파 회의록");
    /* qa-contract-change: 이 고르개의 라벨이 「문서 범위」에서 「프로젝트」로 돌아왔다. */
    await userEvent.click(within(dialog).getByRole("combobox", { name: /프로젝트/ }));
    await userEvent.click(await screen.findByRole("option", { name: /알파 프로젝트/ }));
    // 폴더 칸은 아예 없다 — 폴더 축이 화면에서 걷혔다.
    expect(within(dialog).queryByLabelText(/폴더/)).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "만들기" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(
        ([p, opts]) => String(p) === "/api/knowledge/documents" && opts && opts.method === "POST");
      expect(post, "생성 요청이 안 나갔다").toBeTruthy();
      // 서버가 공간을 찾거나 만든다(resolve_or_create_project_space) — 화면은 프로젝트만 안다.
      expect(post[1].body.project_id).toBe("proj-1");
      expect(post[1].body.space_id).toBeUndefined();
    });
  });

  it("🔴 분류와 태그도 필수다 — 하나만 비어도 만들 수 없다", async () => {
    /* 둘 다 나중에 찾는 길이다. 비워 두고 만든 문서는 어느 조건에도 안 걸려서, 제목을
       정확히 기억하는 사람 말고는 다시 못 찾는다(문서 개편 3번). */
    renderList();
    await seeRows();

    await userEvent.click(screen.getByRole("button", { name: "새 문서" }));
    const dialog = await screen.findByRole("dialog");
    const submit = () => within(dialog).getByRole("button", { name: "만들기" });

    await userEvent.type(within(dialog).getByLabelText(/문서 제목/), "제목만 있는 문서");
    expect(submit().hasAttribute("disabled"), "분류와 태그가 비었는데 만들 수 있다").toBe(true);

    await userEvent.click(within(dialog).getByLabelText(/^분류/));
    await userEvent.click(await screen.findByRole("option", { name: "회의 기록" }));
    expect(submit().hasAttribute("disabled"), "태그가 비었는데 만들 수 있다").toBe(true);

    await userEvent.click(within(dialog).getByLabelText(/^태그/));
    await userEvent.click(await screen.findByRole("option", { name: /^인프라/ }));
    expect(submit().hasAttribute("disabled")).toBe(false);
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

/* 어휘(카테고리·태그)를 사람이 관리한다 (지시 22-5 개정 · 0026).
 *
 * 태그는 지금까지 문서를 저장할 때 곁다리로 생겼고 카테고리는 아예 관리 입구가 없었다.
 * 여기서 보는 것은 두 어휘의 세 동작(추가·이름 고치기·지우기)이 **실제 요청으로**
 * 나가는가와, 지우기 전에 화면이 「몇 건에 붙어 있는가」를 말하는가다.
 * 입구는 「분류 관리」 하나이고, 창 안에서 카테고리 탭과 태그 탭으로 나뉜다.
 */
async function openTaxonomy(tab) {
  await userEvent.click(screen.getByRole("button", { name: "분류 관리" }));
  const dialog = await screen.findByRole("dialog");
  if (tab === "tags") {
    await userEvent.click(within(dialog).getByRole("tab", { name: "태그" }));
  }
  return dialog;
}

describe("분류 관리 — 태그 탭", () => {
  it("목록이 태그마다 몇 건에 붙어 있는지 말한다", async () => {
    renderList();
    await seeRows();

    const dialog = await openTaxonomy("tags");
    expect(within(dialog).getByText("문서 3건")).toBeTruthy();
    expect(within(dialog).getByText("문서 0건")).toBeTruthy();
  });

  it("새 태그를 추가한다 — 문서를 열지 않고도 어휘를 만들 수 있다", async () => {
    renderList();
    await seeRows();

    const dialog = await openTaxonomy("tags");
    await userEvent.type(within(dialog).getByLabelText("새 태그"), "배포 관리");
    await userEvent.click(within(dialog).getByRole("button", { name: "추가" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(
        ([p, o]) => String(p) === "/api/knowledge/tags" && o && o.method === "POST");
      expect(post, "태그 추가 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.name).toBe("배포 관리");
    });
  });

  it("이름 칸에서 Enter 를 두 번 쳐도 추가 요청은 한 번이다 (P4)", async () => {
    /* 「추가」 단추는 추가 중에 꺼지지만 이름 칸의 Enter 처리기는 꺼지지 않는다. 예전에는 Enter 두 번이 같은
       이름의 POST 두 번이었고, 둘째가 「이미 있습니다」로 실패해 창 안에 실패 상자가 섰다. 응답을 붙잡아 그 창을 연다. */
    const base = apiMock.getMockImplementation();
    apiMock.mockImplementation((path, opts) => {
      if (String(path) === "/api/knowledge/tags" && opts && opts.method === "POST") return new Promise(() => {});
      return base(path, opts);
    });
    renderList();
    await seeRows();

    const dialog = await openTaxonomy("tags");
    await userEvent.type(within(dialog).getByLabelText("새 태그"), "배포 관리");
    await userEvent.keyboard("{Enter}{Enter}");

    const posts = () => apiMock.mock.calls.filter(
      ([p, o]) => String(p) === "/api/knowledge/tags" && o && o.method === "POST");
    await waitFor(() => expect(posts()).toHaveLength(1));
    await act(async () => {});
    expect(posts()).toHaveLength(1);
    expect(posts()[0][1].body.name).toBe("배포 관리");
  });

  it("🔴 지우기 전에 몇 건에서 떨어지는지 묻는다 — 0건과 3건은 다른 일이다", async () => {
    authState.role = "admin";
    renderList();
    await seeRows();

    const dialog = await openTaxonomy("tags");
    // 첫 줄이 「회의록」(문서 3건)이다. 태그 목록은 서버가 준 순서 그대로 선다.
    await userEvent.click(within(dialog).getAllByRole("button", { name: "삭제" })[0]);

    expect(await screen.findByText(/문서 3건에서 이 태그가 떨어집니다/)).toBeTruthy();
    // 확인하기 전에는 아무 요청도 안 나간다.
    expect(apiMock.mock.calls.some(([, o]) => o && o.method === "DELETE")).toBe(false);
  });

  it("운영자는 이름을 고칠 수 있고, 그 요청이 서버로 나간다", async () => {
    authState.role = "admin";
    renderList();
    await seeRows();

    const dialog = await openTaxonomy("tags");
    await userEvent.click(within(dialog).getAllByRole("button", { name: "수정" })[0]);
    const box = within(dialog).getByDisplayValue("회의록");
    await userEvent.clear(box);
    await userEvent.type(box, "회의 자료");
    await userEvent.click(within(dialog).getByRole("button", { name: "저장" }));

    await waitFor(() => {
      const patch = apiMock.mock.calls.find(([, o]) => o && o.method === "PATCH");
      expect(patch, "이름 고치기 요청이 안 나갔다").toBeTruthy();
      expect(String(patch[0])).toBe("/api/knowledge/tags/tag-1");
      expect(patch[1].body.name).toBe("회의 자료");
    });
  });

  it("이름 고치기와 지우기는 운영자만 본다 — 서버가 같은 기준으로 막는다", async () => {
    renderList();
    await seeRows();
    const dialog = await openTaxonomy("tags");
    /* 이 시험의 로그인 사용자는 일반 사용자다(맨 위 `useAuth` 대역). 추가는 되고
       고치기·지우기는 안 보인다. */
    expect(within(dialog).getByRole("button", { name: "추가" })).toBeTruthy();
    expect(within(dialog).queryByRole("button", { name: "수정" })).toBeNull();
    expect(within(dialog).getByText(/운영자만 할 수 있습니다/)).toBeTruthy();
  });

  it("새 문서 창에서 이미 있는 태그를 검색해 고른다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByRole("button", { name: "새 문서" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/문서 제목/), "새 회의록");
    /* qa-contract-change: 분류도 필수가 됐으므로 함께 채운다 — 안 채우면 「만들기」가
       비활성이라 클릭 자체가 안 된다(그 상태를 재는 시험은 따로 있다). */
    await userEvent.click(within(dialog).getByLabelText(/^분류/));
    await userEvent.click(await screen.findByRole("option", { name: "회의 기록" }));
    await userEvent.click(within(dialog).getByLabelText(/^태그/));
    // MUI Autocomplete 의 옵션 목록은 Portal 로 document.body 에 붙는다 — dialog DOM
    // 서브트리 밖이라 within(dialog) 로는 못 찾는다.
    await userEvent.click(await screen.findByRole("option", { name: /^인프라/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "만들기" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(
        ([p, o]) => String(p) === "/api/knowledge/documents" && o && o.method === "POST");
      expect(post[1].body.tag_names).toEqual(["인프라"]);
    });
  });
});

describe("분류 관리 — 분류 탭 (0026)", () => {
  it("분류 탭이 기본으로 열리고, 사용 건수를 말한다", async () => {
    renderList();
    await seeRows();

    const dialog = await openTaxonomy();
    expect(within(dialog).getByText("문서 2건")).toBeTruthy();
    expect(within(dialog).getByText("기술 문서")).toBeTruthy();
  });

  it("새 분류를 추가한다 — 회사에 맞는 갈래를 화면에서 만든다", async () => {
    renderList();
    await seeRows();

    const dialog = await openTaxonomy();
    await userEvent.type(within(dialog).getByLabelText("새 분류"), "고객 지원");
    await userEvent.click(within(dialog).getByRole("button", { name: "추가" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(
        ([p, o]) => String(p) === "/api/knowledge/categories" && o && o.method === "POST");
      expect(post, "카테고리 추가 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.name).toBe("고객 지원");
    });
  });

  it("🔴 지우기 전에 몇 건이 미분류가 되는지 묻는다", async () => {
    authState.role = "admin";
    renderList();
    await seeRows();

    const dialog = await openTaxonomy();
    await userEvent.click(within(dialog).getAllByRole("button", { name: "삭제" })[0]);

    expect(await screen.findByText(/문서 2건이 미분류로 돌아갑니다/)).toBeTruthy();
    expect(apiMock.mock.calls.some(([, o]) => o && o.method === "DELETE")).toBe(false);
  });

  it("운영자는 분류 이름을 고칠 수 있고, 그 요청이 서버로 나간다", async () => {
    authState.role = "admin";
    renderList();
    await seeRows();

    const dialog = await openTaxonomy();
    await userEvent.click(within(dialog).getAllByRole("button", { name: "수정" })[0]);
    const box = within(dialog).getByDisplayValue("회의 기록");
    await userEvent.clear(box);
    await userEvent.type(box, "회의");
    await userEvent.click(within(dialog).getByRole("button", { name: "저장" }));

    await waitFor(() => {
      const patch = apiMock.mock.calls.find(([, o]) => o && o.method === "PATCH");
      expect(patch, "이름 고치기 요청이 안 나갔다").toBeTruthy();
      expect(String(patch[0])).toBe("/api/knowledge/categories/cat-1");
      expect(patch[1].body.name).toBe("회의");
    });
  });
});

describe("카테고리 필터 (0026)", () => {
  it("🔴 분류 조건이 서버 질의에 실려 나간다 — 화면에서 거르지 않는다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByLabelText("분류"));
    await userEvent.click(await screen.findByRole("option", { name: "회의 기록" }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("category_id=cat-1"))).toBe(true));
    expect(lastDocumentCall()).toContain("offset=0");
  });

  it("걸린 조건은 칩으로 서고, 칩을 지우면 조건이 풀린다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByLabelText("분류"));
    await userEvent.click(await screen.findByRole("option", { name: "회의 기록" }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("category_id=cat-1"))).toBe(true));

    // 칩 라벨은 「분류: 이름」이다. 지우면 조건 없는 질의가 다시 나간다.
    const chip = await screen.findByText("분류: 회의 기록");
    const del = chip.closest(".MuiChip-root").querySelector(".MuiChip-deleteIcon");
    await userEvent.click(del);
    await waitFor(() => expect(lastDocumentCall().includes("category_id=")).toBe(false));
  });
});

describe("새 문서의 분류", () => {
  it("고른 분류가 생성 요청에 실린다", async () => {
    renderList();
    await seeRows();

    await userEvent.click(screen.getByRole("button", { name: "새 문서" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/문서 제목/), "분류 있는 문서");
    await userEvent.click(within(dialog).getByLabelText(/^분류/));
    await userEvent.click(await screen.findByRole("option", { name: "기술 문서" }));
    /* qa-contract-change: 태그도 필수가 됐다. */
    await userEvent.click(within(dialog).getByLabelText(/^태그/));
    await userEvent.click(await screen.findByRole("option", { name: /^인프라/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "만들기" }));

    await waitFor(() => {
      const post = apiMock.mock.calls.find(
        ([p, o]) => String(p) === "/api/knowledge/documents" && o && o.method === "POST");
      expect(post, "생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.category_id).toBe("cat-2");
    });
  });
});

describe("프로젝트 축과 옛 주소", () => {
  it("목록 요청이 프로젝트 축으로 나간다 — space_id 는 더 이상 안 쓴다", async () => {
    renderList();
    await seeRows();
    expect(documentCalls()[0]).toContain("project_id=none");
    expect(documentCalls()[0]).not.toContain("space_id=");
  });

  it("옛 ?space= 링크는 프로젝트 축으로 열린다 — 북마크가 조용히 죽지 않는다", async () => {
    renderList(`/knowledge?space=${SPACE}`);
    await seeRows();
    // 변환이 자리 잡으면 마지막 목록 요청이 새 축이다(조직 공간 → 공통 문서).
    await waitFor(() => {
      expect(lastDocumentCall()).toContain("project_id=none");
    });
    expect(lastDocumentCall()).not.toContain("space_id=");
  });

  /* qa-contract-change: 이 두 시험은 **좌측 내비**를 재고 있었다. 그 내비가 걷혔으므로
     (문서 개편 5번) 같은 사실을 프로젝트 축의 유일한 입구 — 조건 줄의 고르개 — 에서
     잰다. 재는 사실 자체는 그대로다: 후보는 공간 목록이 아니라 프로젝트 전체이고,
     고르면 그 `project_id` 로 목록을 조회한다. */
  it("🔴 프로젝트 고르개가 전체 프로젝트를 보여준다 — 공간 없는 프로젝트도 (공간 목록이 아니라)", async () => {
    // spaces 는 조직 공간(공통) 하나뿐이지만 projects 에는 알파·베타 둘이 있다.
    // 예전에는 이 축이 공간 목록을 읽어 공간 없는 둘이 통째로 안 보였다.
    renderList();
    await seeRows();
    await userEvent.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    expect(await screen.findByRole("option", { name: "알파 프로젝트" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "베타 프로젝트" })).toBeTruthy();
    // 「프로젝트 미지정」은 조건 없이 늘 선다 — 공간 목록에 무엇이 있든.
    expect(screen.getByRole("option", { name: "프로젝트 미지정" })).toBeTruthy();
  });

  it("공간 없는 프로젝트를 고르면 그 project_id 로 목록을 조회한다", async () => {
    renderList();
    await seeRows();
    await userEvent.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await userEvent.click(await screen.findByRole("option", { name: "알파 프로젝트" }));
    await waitFor(() => {
      expect(lastDocumentCall()).toContain("project_id=proj-1");
    });
  });
});
