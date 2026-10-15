import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

/* 결과 블록(AI 채팅 개선 회차) — 도우미가 보여 주기로 한 목록을 서버가 준 칸 그대로 그린다.
 *
 * 예전에는 모델이 쓴 「- [제목](route) 작성자, 수정일」 줄을 다시 읽어 그려, 같은 작성자 · 날짜가 줄마다 되풀이됐고 열 건
 * 뒤로는 이어 볼 길이 없었다. 여기서 못박는 것:
 *   - 머리는 무엇의 목록인지와 「전체 N건 중 보인 M건」이다. 내 문서는 줄마다 작성자를 되풀이하지 않는다.
 *   - 「N건 더 보기」는 모델을 부르지 않고 다음 쪽을 덧붙인다(남은 수만큼). 실패는 그 자리의 문장이고 줄은 남는다.
 *   - 정렬을 바꾸면 처음부터 다시 받는다. 「전체 목록 열기」는 허용한 화면 경로일 때만 선다.
 *   - 줄의 링크는 앱 안 출처 경로일 때만이다. */

const apiMock = vi.fn();
vi.mock("../../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ResultBlock } from "./ResultList.jsx";
import { ThemeModeProvider } from "../../../ui/ThemeModeProvider.jsx";

function doc(i, extra = {}) {
  return { ref: `d${i}`, title: `문서 ${i}`, route: `/knowledge/d${i}`, space: "기술 문서", author: "황형섭", updated_at: "2026-09-04T01:00:00", ...extra };
}

function page(offset, count, total = 25) {
  return { block: { id: "r1", tool: "my_documents", kind: "document", total, offset, returned: count,
    items: Array.from({ length: count }, (_, k) => doc(offset + k)) } };
}

const MINE = {
  id: "r1", tool: "my_documents", kind: "document", shown: true, total: 25, offset: 0, returned: 10,
  items: Array.from({ length: 10 }, (_, i) => doc(i)),
  list_route: "/knowledge?author=u1&sort=recent", sort_options: ["recent", "created", "title"], sort: "recent",
};

function renderBlock(block, props = {}) {
  return render(<ThemeModeProvider><ResultBlock block={block} messageId="m1" {...props} /></ThemeModeProvider>);
}

const rows = () => within(document.querySelector("[data-result-block] ul")).getAllByRole("listitem");

beforeEach(() => {
  apiMock.mockReset();
});

describe("결과 목록", () => {
  it("머리는 「내 문서 · 25건 중 10건」이고, 내 문서는 줄마다 작성자를 되풀이하지 않는다", () => {
    renderBlock(MINE);
    expect(screen.getByRole("region", { name: "내 문서 25건 중 10건" })).toBeInTheDocument();
    expect(rows()).toHaveLength(10);
    expect(screen.getByRole("link", { name: "문서 0" })).toHaveAttribute("href", "#/knowledge/d0");
    expect(document.querySelector("[data-result-block]").textContent).not.toContain("황형섭");
    expect(screen.getByRole("link", { name: "전체 목록 열기" })).toHaveAttribute("href", "#/knowledge?author=u1&sort=recent");
  });

  it("문서 검색 결과는 작성자를 싣는다", () => {
    renderBlock({ ...MINE, tool: "search_documents", list_route: null, sort_options: null });
    expect(document.querySelector("[data-result-block]").textContent).toContain("황형섭");
    expect(screen.queryByRole("link", { name: "전체 목록 열기" })).toBeNull();
  });

  it("「10건 더 보기」는 다음 쪽을 덧붙이고, 남은 수만큼 다시 선다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => {
      const offset = Number(new URL(path, "https://x.test").searchParams.get("offset"));
      return Promise.resolve(page(offset, Math.min(10, 25 - offset)));
    });
    renderBlock(MINE);
    await user.click(screen.getByRole("button", { name: "10건 더 보기" }));
    await waitFor(() => expect(rows()).toHaveLength(20));
    expect(apiMock.mock.calls[0][0]).toBe("/api/messages/m1/results/r1?offset=10&sort=recent");
    expect(screen.getByRole("region", { name: "내 문서 25건 중 20건" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "5건 더 보기" }));
    await waitFor(() => expect(rows()).toHaveLength(25));
    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
    expect(screen.getByRole("region", { name: "내 문서 25건" })).toBeInTheDocument();
  });

  it("이어 묻기의 블록(11번째부터)은 몇 번째인지 말하고 남은 수를 그 끝에서 센다", () => {
    renderBlock({ ...MINE, offset: 10, items: Array.from({ length: 10 }, (_, i) => doc(i + 10)) });
    expect(screen.getByRole("region", { name: "내 문서 25건 중 11~20번째" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5건 더 보기" })).toBeInTheDocument();
  });

  it("다음 쪽을 못 받으면 그 자리에 문장이 서고 받은 줄은 그대로다", async () => {
    const user = userEvent.setup();
    apiMock.mockRejectedValue(new Error("목록을 더 받지 못했습니다. 잠시 후 다시 시도해 주세요."));
    renderBlock(MINE);
    await user.click(screen.getByRole("button", { name: "10건 더 보기" }));
    expect(await screen.findByText("목록을 더 받지 못했습니다. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
    expect(rows()).toHaveLength(10);
  });

  it("정렬을 바꾸면 처음부터 다시 받는다", async () => {
    const user = userEvent.setup();
    apiMock.mockResolvedValue({ block: { ...page(0, 10).block, sort: "title", items: Array.from({ length: 10 }, (_, i) => doc(i + 100)) } });
    renderBlock(MINE);
    await user.click(screen.getByRole("tab", { name: "제목" }));
    await waitFor(() => expect(screen.getByRole("link", { name: "문서 100" })).toBeInTheDocument());
    expect(apiMock.mock.calls[0][0]).toBe("/api/messages/m1/results/r1?offset=0&sort=title");
    expect(rows()).toHaveLength(10);
    expect(screen.queryByRole("link", { name: "문서 0" })).toBeNull();
  });

  it("허용하지 않은 목록 경로 · 출처 모양이 아닌 줄 경로는 링크가 되지 않는다", () => {
    renderBlock({ ...MINE, list_route: "https://evil.example/knowledge", items: [doc(1, { route: "javascript:alert(1)" }), doc(2, { route: "//evil.example/x" })], total: 2, returned: 2 });
    expect(screen.queryByRole("link", { name: "전체 목록 열기" })).toBeNull();
    expect(screen.queryByRole("link", { name: "문서 1" })).toBeNull();
    expect(screen.queryByRole("link", { name: "문서 2" })).toBeNull();
    expect(screen.getByText("문서 1")).toBeInTheDocument();
  });

  it("제목에 대괄호가 든 문서도 링크 하나다", () => {
    renderBlock({ ...MINE, items: [doc(1, { title: "[포스코DX] 부가서비스·NAS 빌링 화면 가이드" })], total: 1, returned: 1 });
    expect(screen.getByRole("link", { name: "[포스코DX] 부가서비스·NAS 빌링 화면 가이드" })).toHaveAttribute("href", "#/knowledge/d1");
  });

  it("티켓 줄은 키 · 상태 · 담당 · 마감을 싣는다", () => {
    renderBlock({ id: "r2", tool: "my_work", kind: "ticket", shown: true, total: 1, offset: 0, returned: 1,
      items: [{ ref: "t1", key: "ZCYMPW-542", title: "스토리지 증설 검토", status: "진행", assignees: ["황형섭"], due: "2026-10-20", route: "/tickets/t1" }] });
    const block = document.querySelector("[data-result-block]");
    expect(screen.getByRole("region", { name: "내 티켓 1건" })).toBeInTheDocument();
    expect(block.textContent).toContain("ZCYMPW-542");
    expect(block.textContent).toContain("담당 황형섭");
    expect(block.textContent).toContain("마감 2026-10-20");
    expect(screen.getByRole("link", { name: "스토리지 증설 검토" })).toHaveAttribute("href", "#/tickets/t1");
  });

  it("항목이 없으면 그 사실을 말한다", () => {
    renderBlock({ ...MINE, items: [], total: 0, returned: 0 });
    expect(screen.getByText("조건에 맞는 항목이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
  });
});
