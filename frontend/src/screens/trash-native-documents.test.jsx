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
  space: "공통 문서",
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
  it("🔴 문서가 티켓과 한 목록에 서고 어느 공간이었는지 말한다", async () => {
    renderScreen();
    expect(await screen.findByText("서버 인프라 리소스 현황")).toBeTruthy();
    expect(screen.getByText("로그인 오류")).toBeTruthy();
    expect(screen.getByText("공통 문서")).toBeTruthy();
    expect(screen.getByText("02. 운영 문서")).toBeTruthy();
    expect(screen.getByText("이성진")).toBeTruthy();
  });

  it("종류 조건은 서버 질의에 실려 나간다", async () => {
    renderScreen();
    await screen.findByText("서버 인프라 리소스 현황");

    await userEvent.click(screen.getByLabelText("종류"));
    await userEvent.click(await screen.findByRole("option", { name: "문서" }));

    await waitFor(() => expect(calls.some((p) => p.includes("kind=document"))).toBe(true));
    await waitFor(() => expect(screen.queryByText("로그인 오류")).toBeNull());
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
    expect(screen.getByText(/문서는 자동으로 지워지지 않으며/)).toBeTruthy();
  });
});
