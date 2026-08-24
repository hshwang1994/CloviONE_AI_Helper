import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 문서 목록이 **몇 건 중 어디쯤인지** 말한다 (S14 · C2).
 *
 * 서버는 처음부터 `limit`·`offset`·`total` 을 줬는데 화면이 그중 하나도 안 썼다. 운영에서
 * 문서가 110건인데 50건에서 끊겨서, 나머지 60건은 **있다는 사실 자체가** 사용자에게 안
 * 보였다. 목록이 끊긴 자리에 아무 표시도 없으면 사람은 그것이 전부라고 믿는다.
 *
 * 이건 디자인이 아니라 **데이터가 안 보이는 결함**이다. 그래서 여기서 못박는 것은 모양이
 * 아니라 동작이다: 다음 쪽을 누르면 그 다음 50건을 실제로 **요청**하는가.
 *
 * 즐겨찾기도 같은 자리에서 본다 — 옛 문서 화면에만 있던 필터를 옮겨 왔고, 조건을 켜면
 * 서버 질의에 실려 나가야 한다(화면에서만 거르면 다음 쪽에서 조건이 사라진다).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { Knowledge } from "./Knowledge.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const SPACE = "space-1";

function docsPage(offset, count, total) {
  return {
    items: Array.from({ length: count }, (_, i) => ({
      id: `doc-${offset + i}`,
      title: `문서 ${offset + i}`,
      source_type: "USER",
      is_favorite: offset + i === 0,
      // 첫 문서에만 종류·태그를 준다 — 목록 줄이 실제로 그리는지만 보면 된다.
      ...(offset + i === 0
        ? { doc_type: "회의록", tags: [{ id: "tag-1", name: "인프라" }] }
        : {}),
    })),
    total,
    limit: 50,
    offset,
  };
}

const calls = [];

beforeEach(() => {
  calls.length = 0;
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    calls.push(String(path));
    if (String(path).startsWith("/api/knowledge/spaces/")) {
      return Promise.resolve({ folders: [] });
    }
    if (String(path) === "/api/knowledge/spaces") {
      return Promise.resolve({ items: [{ id: SPACE, name: "우리 공간" }] });
    }
    if (String(path) === "/api/knowledge/tags") {
      return Promise.resolve({ items: [{ id: "tag-1", name: "회의록", slug: "meeting-notes" }] });
    }
    const url = new URL(String(path), "https://x");
    const offset = Number(url.searchParams.get("offset") || 0);
    const count = offset === 0 ? 50 : 60;
    return Promise.resolve(docsPage(offset, Math.min(count, 110 - offset), 110));
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

function documentCalls() {
  return calls.filter((p) => p.startsWith("/api/knowledge/documents"));
}

describe("문서 목록의 쪽 넘기기", () => {
  it("전체 건수를 말하고, 다음 쪽을 누르면 그 다음 문서를 실제로 요청한다", async () => {
    renderList();
    await screen.findByText("문서 0");

    // 「1 / 3, 총 110건」 — 51번째 문서가 있다는 사실이 여기서 처음 보인다.
    expect(await screen.findByText(/총 110건/)).toBeTruthy();
    expect(documentCalls()[0]).toContain("limit=50");
    expect(documentCalls()[0]).toContain("offset=0");

    await userEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(documentCalls().length).toBeGreaterThan(1));
    expect(documentCalls()[documentCalls().length - 1]).toContain("offset=50");
    expect(await screen.findByText("문서 50")).toBeTruthy();
  });

  it("즐겨찾기 조건은 서버 질의에 실려 나간다", async () => {
    renderList();
    await screen.findByText("문서 0");

    await userEvent.click(screen.getByRole("button", { name: "즐겨찾기만" }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("favorites=true"))).toBe(true));
  });

  it("조건을 바꾸면 첫 쪽으로 돌아온다 — 세 번째 쪽에서 걸러 놓고 빈 화면을 보면 안 된다", async () => {
    renderList();
    await screen.findByText("문서 0");
    await userEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(documentCalls().length).toBeGreaterThan(1));

    await userEvent.click(screen.getByRole("button", { name: "즐겨찾기만" }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("favorites=true"))).toBe(true));
    const last = documentCalls()[documentCalls().length - 1];
    expect(last).toContain("offset=0");
  });

  it("담아 둔 문서에는 별이 보인다", async () => {
    renderList();
    await screen.findByText("문서 0");
    expect(screen.getAllByLabelText("즐겨찾기").length).toBe(1);
  });

  it("문서 줄에 종류와 태그가 보인다 — 필터만 있고 줄에는 없으면 손실처럼 보인다", async () => {
    renderList();
    await screen.findByText("문서 0");
    expect(await screen.findByText("회의록")).toBeTruthy();
    expect(await screen.findByText("인프라")).toBeTruthy();
  });

  /* 🔴 **화면이 말하는 조건과 실제 질의 조건이 같아야 한다** (S15 · C7).
   *
   * 이 검색 상자는 맨 `TextField` 에 `defaultValue={q}` 였다 — 값을 **처음 한 번만** 읽는
   * 입력이라, 주소가 바깥에서 바뀌어도 상자는 따라오지 않았다. 그래서 「검색, 필터 지우기」를
   * 누르면 목록은 조건 없이 다시 받아 오는데 상자에는 방금 지운 검색어가 그대로 남았다.
   * 뒤로가기도 같다. 사용자는 걸려 있지도 않은 조건을 화면에서 읽는다. */
  it("검색어를 지우면 상자도 함께 빈다 — 화면이 없는 조건을 말하지 않는다", async () => {
    renderList();
    await screen.findByText("문서 0");

    const box = screen.getByRole("searchbox", { name: "문서 찾기" });
    await userEvent.type(box, "회의");
    await waitFor(() => expect(documentCalls().some((p) => p.includes("q=%ED%9A%8C%EC%9D%98"))).toBe(true),
                  { timeout: 2000 });
    expect(box.value).toBe("회의");

    // 0건이 되는 응답으로 갈아 끼워 「검색, 필터 지우기」 버튼을 띄운다.
    apiMock.mockImplementation((path) => {
      calls.push(String(path));
      if (String(path).startsWith("/api/knowledge/spaces/")) return Promise.resolve({ folders: [] });
      if (String(path) === "/api/knowledge/spaces") return Promise.resolve({ items: [{ id: SPACE, name: "우리 공간" }] });
      if (String(path) === "/api/knowledge/tags") return Promise.resolve({ items: [] });
      return Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 });
    });
    await userEvent.clear(box);
    await userEvent.type(box, "없는말");
    const clear = await screen.findByRole("button", { name: "검색, 필터 지우기" }, { timeout: 3000 });
    await userEvent.click(clear);

    await waitFor(() => expect(screen.getByRole("searchbox", { name: "문서 찾기" }).value).toBe(""));
  });

  it("분류(태그) 조건도 서버 질의에 실려 나간다 — 옛 화면의 문서 종류·업무 분야·기술 태그를 대신한다", async () => {
    renderList();
    await screen.findByText("문서 0");

    await userEvent.click(screen.getByLabelText("분류"));
    await userEvent.click(await screen.findByRole("option", { name: "회의록" }));
    await waitFor(() =>
      expect(documentCalls().some((p) => p.includes("tag=meeting-notes"))).toBe(true));
    // 필터를 바꾸면 첫 쪽으로 — 다른 필터와 같은 규칙이다.
    expect(documentCalls()[documentCalls().length - 1]).toContain("offset=0");
  });
});
