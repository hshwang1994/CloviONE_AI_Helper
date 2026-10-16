/* 공용 휴지통이 **Native 문서를 든다** (지시 22.7).
 *
 * ## 무엇이 없었나
 *
 * 문서 삭제는 `documents.archived` 를 세우는 일인데, 이 화면은 옛 미러 표(`trash_items`)만
 * 읽었다. 그래서 `/knowledge` 에서 지운 문서는 **어디에도 안 나타났다** — 화면에 「휴지통」
 * 버튼이 있는데 거기 그 문서가 없으니, 지운 사람은 자기가 되돌릴 수 있는지조차 알 수 없었다.
 *
 * ## 여기서 보는 것
 *
 *   1. 문서 줄이 티켓과 **한 목록에** 선다. 공간과 폴더가 보인다(옛 항목은 그 개념이 없어
 *      빈 칸이고, 없는 값을 「-」로 지어내지 않는다).
 *   2. 「종류」로 좁히면 **서버 질의에 실려 나간다.** 화면에서만 거르면 상한 너머의 그
 *      종류가 안 보이면서 화면은 「이게 전부」라고 말한다.
 *   3. 문서 화면의 「휴지통」이 그 조건을 걸고 연다 — 주소로 들어와도 같은 화면이 선다.
 *   4. 복원과 영구 삭제가 그 줄의 id 로 나간다. 되돌릴 수 없는 쪽은 확인을 거친다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api.js", () => ({ api: vi.fn() }));
import { api } from "../lib/api.js";
import { Trash } from "./Trash.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const DOC_UUID = "11111111-2222-3333-4444-555555555555";

const DOC_ROW = {
  id: `doc:${DOC_UUID}`,
  item_type: "document",
  type_label: "문서",
  source: "knowledge",
  title: "서버 인프라 리소스 현황",
  notion_page_id: null,
  // 서버는 프로젝트 소유 공간이면 그 프로젝트 이름을, 아니면 「프로젝트 미지정」을
  // 보낸다. 「공통 문서」 같은 공간 이름은 프로젝트 열에 서지 않는다.
  space: "프로젝트 미지정",
  folder: "02. 운영 문서",
  deleted_by: "이성진",
  deleted_at: "2026-08-26T02:00:00",
  purge_after: "2026-09-02T02:00:00",
  can_manage: true,
};

const TICKET_ROW = {
  id: "trash-1",
  item_type: "ticket",
  type_label: "티켓",
  source: "legacy",
  title: "로그인 오류",
  notion_page_id: "np-1",
  space: "",
  folder: "",
  deleted_by: "박세찬",
  deleted_at: "2026-08-25T02:00:00",
  purge_after: "2026-09-01T02:00:00",
  can_manage: true,
};

const calls = [];

function stub(rows, policy) {
  api.mockImplementation((path, options) => {
    calls.push(String(path));
    if (String(path).startsWith("/api/trash?")) {
      const url = new URL(String(path), "https://x");
      const kind = url.searchParams.get("kind");
      const items = kind ? rows.filter((r) => r.item_type === kind) : rows;
      return Promise.resolve({
        items, total: items.length, retention_days: 7,
        document_autopurge: true, document_retention_days: 7,
        // 개수는 **조건과 무관**하다 — 서버가 좁히기 전에 센다(app/trash/router.py).
        counts: {
          ticket: rows.filter((r) => r.item_type === "ticket").length,
          document: rows.filter((r) => r.item_type === "document").length,
          all: rows.length,
          urgent: 0,
        },
        ...(policy || {}),
      });
    }
    if (options && options.method === "POST") return Promise.resolve({ ok: true });
    return Promise.resolve({});
  });
}

function renderScreen(entry = "/team-docs/trash") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[entry]}><Trash /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
  return qc;
}

beforeEach(() => {
  calls.length = 0;
  api.mockReset();
  stub([DOC_ROW, TICKET_ROW]);
});

describe("휴지통의 Native 문서", () => {
  it("🔴 문서가 티켓과 한 목록에 서고 어느 프로젝트였는지 말한다", async () => {
    renderScreen();
    expect(await screen.findByText("서버 인프라 리소스 현황")).toBeTruthy();
    expect(screen.getByText("로그인 오류")).toBeTruthy();
    expect(screen.getByText("프로젝트 미지정")).toBeTruthy();
    // 🔴 폴더 줄은 안 본다. 폴더 축이 화면에서 걷히면서(문서 개편 1·5번) 복원한 뒤 그
    // 폴더를 볼 자리가 없어졌고, 열도 함께 걷었다. 응답의 `folder` 는 그대로 온다 —
    // 없어진 것은 그리는 자리뿐이므로 여기서 그 자리를 찾으면 안 된다.
    expect(screen.queryByText("02. 운영 문서")).toBeNull();
    expect(screen.getByText("이성진")).toBeTruthy();
  });

  /* 🔴 되돌릴 수 없는 결정 앞에서 무엇을 지우는지 볼 수 있어야 한다.
   *
   * 옛 Notion 링크를 걷으면서 **대체를 안 놓았고**, 그래서 이 표에서 지우려는 것이
   * 무엇인지 제목 말고는 볼 방법이 없었다. 영구 삭제는 되돌릴 수 없다. 서버는 이미
   * 열어 준다(`get_scoped_document_or_404` 는 `archived` 를 안 막는다) — 막고 있던 것은
   * 화면뿐이었다. */
  it("🔴 제목이 그 문서로 가는 링크다 — 지우기 전에 본문을 볼 수 있다", async () => {
    renderScreen();
    const link = await screen.findByRole("link", { name: "서버 인프라 리소스 현황" });
    expect(link.getAttribute("href")).toBe(`#/knowledge/${DOC_UUID}`);
    // 같은 탭에서 나갔다 오면 고른 줄과 일괄 선택이 사라진다.
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it("🔴 옛 미러 문서와 티켓은 링크가 아니다 — 없는 화면으로 보내지 않는다", async () => {
    /* 접두(`doc:`)만 보고 이으면 옛 미러 문서까지 링크가 된다. 그것들은 우리 쪽에 열
       문서가 없어서(`source: "legacy"`) 누르면 빈 화면이 나온다. 반례가 없으면
       「접두만 본다」로 고쳐도 위 시험이 초록이다. */
    const MIRROR = {
      ...DOC_ROW,
      id: "doc:99999999-8888-7777-6666-555555555555",
      source: "legacy",
      title: "옛 미러 문서",
    };
    stub([DOC_ROW, TICKET_ROW, MIRROR]);
    renderScreen();

    await screen.findByText("옛 미러 문서");
    expect(screen.queryByRole("link", { name: "옛 미러 문서" })).toBeNull();
    expect(screen.queryByRole("link", { name: "로그인 오류" })).toBeNull();
    // 우리 문서는 그대로 링크다 — 셋을 함께 재야 「전부 평문」으로 고쳐도 안 걸린다.
    expect(screen.getByRole("link", { name: "서버 인프라 리소스 현황" })).toBeTruthy();
  });

  /* 🔴 조작기가 **탭**이다. 예전에는 같은 축(`?kind=`)을 둘이 나눠 쥐고 있었다 — 큰 숫자
     판독 줄이 필터 구실을 겸하고 그 위에 「종류」 드롭다운이 또 있었다. 사용자가 「탭도
     이상하고」라고 부른 것이 그 줄이다. 재는 것(서버 질의에 조건이 실린다)은 그대로다. */
  it("종류 조건은 서버 질의에 실려 나간다", async () => {
    renderScreen();
    await screen.findByText("서버 인프라 리소스 현황");

    await userEvent.click(screen.getByRole("tab", { name: /문서/ }));

    await waitFor(() => expect(calls.some((p) => p.includes("kind=document"))).toBe(true));
    await waitFor(() => expect(screen.queryByText("로그인 오류")).toBeNull());
  });

  it("탭이 진짜 탭이다 — 고른 것이 aria-selected 로 낭독된다", async () => {
    renderScreen("/team-docs/trash?kind=document");
    await screen.findByText("서버 인프라 리소스 현황");
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent.replace(/\s*\d+$/, ""))).toEqual(["전체", "티켓", "문서"]);
    expect(screen.getByRole("tab", { name: /문서/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /전체/ })).toHaveAttribute("aria-selected", "false");
  });

  it("탭 라벨의 숫자는 **서버가 준 조건-무관 개수**다 — 문서 탭에서 「티켓 0」이 아니다", async () => {
    /* 예전에는 화면이 받아 온(이미 걸러진) 목록에서 셌다. 문서 화면의 「휴지통」 단추가
       `?kind=document` 로 열기 때문에 첫 화면부터 「티켓 0」이 떴다 — 티켓이 들어 있어도. */
    renderScreen("/team-docs/trash?kind=document");
    await screen.findByText("서버 인프라 리소스 현황");
    expect(screen.getByRole("tab", { name: "티켓 1" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "문서 1" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "전체 2" })).toBeTruthy();
  });

  it("문서 화면에서 넘어오면 그 조건이 걸린 채로 열린다", async () => {
    renderScreen("/team-docs/trash?kind=document");
    await screen.findByText("서버 인프라 리소스 현황");
    expect(calls.some((p) => p.includes("kind=document"))).toBe(true);
  });

  it("복원은 그 줄의 id 로 나간다 — 문서 id 를 그대로 쓰지 않는다", async () => {
    renderScreen();
    const row = (await screen.findByText("서버 인프라 리소스 현황")).closest("tr");
    await userEvent.click(within(row).getByRole("button", { name: "복원" }));

    await waitFor(() => {
      const post = api.mock.calls.find(([p, o]) => o && o.method === "POST" && String(p).includes("/restore"));
      expect(post, "복원 요청이 안 나갔다").toBeTruthy();
      expect(post[0]).toBe(`/api/trash/doc:${DOC_UUID}/restore`);
    });
  });

  it("영구 삭제는 확인을 거친다 — 문서는 되돌릴 수 없다", async () => {
    renderScreen();
    const row = (await screen.findByText("서버 인프라 리소스 현황")).closest("tr");
    await userEvent.click(within(row).getByRole("button", { name: "영구 삭제" }));

    // 확인 창이 뜨고, 누르기 전에는 아무 요청도 안 나간다.
    const dialog = await screen.findByRole("dialog");
    expect(api.mock.calls.some(([p, o]) => o && o.method === "POST" && String(p).includes("/purge"))).toBe(false);

    await userEvent.click(within(dialog).getByRole("button", { name: "영구 삭제" }));
    await waitFor(() => {
      const post = api.mock.calls.find(([p, o]) => o && o.method === "POST" && String(p).includes("/purge"));
      expect(post, "영구 삭제 요청이 안 나갔다").toBeTruthy();
      expect(post[0]).toBe(`/api/trash/doc:${DOC_UUID}/purge`);
    });
  });
});

/* 자동 영구 삭제는 **끌 수 있다** (D-352). 화면이 그 사실을 말해야 한다.
 *
 * 꺼져 있을 때 「삭제 예정」 칸을 비워 두면 사람은 「곧 사라지는데 날짜만 안 보인다」로
 * 읽는다 — 정확히 반대 뜻이다.
 */
describe("자동 영구 삭제 정책", () => {
  it("켜져 있으면 언제 지워지는지 날짜로 말한다", async () => {
    renderScreen();
    await screen.findByText("서버 인프라 리소스 현황");
    expect(screen.getByText(/문서는 7일 동안 보관합니다/)).toBeTruthy();
  });

  it("🔴 꺼져 있으면 「자동 삭제 안 함」이라고 말한다", async () => {
    stub(
      [{ ...DOC_ROW, purge_after: null }],
      { document_autopurge: false },
    );
    renderScreen();
    await screen.findByText("서버 인프라 리소스 현황");
    expect(screen.getByText("자동 삭제 안 함")).toBeTruthy();
    expect(screen.getByText(/문서는 자동으로 삭제되지 않으며/)).toBeTruthy();
  });
});
