import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { SourcesPanel } from "./SourcesPanel.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* 참고 자료 칸(AI 채팅 개선 회차) — **고른 답**이 쓴 자료다. 예전 레일은 마지막으로 인용한 답의 출처 전부라 본문 목록과 같은
 * 문서 열 개를 되풀이했다. 여기서 못박는 것: 인용한 자료만 서고(답 글이 쓰지 않은 것 · 본문 결과 목록에 이미 선 것 · 앱 밖
 * 경로는 빠진다), 앞 답의 자료면 그렇다고 말하며, 답 안 링크에 올린 자료가 강조되고, 닫기 단추가 있다. */

const MESSAGE = {
  id: "a1", role: "assistant", created_at: "2026-10-15T01:00:05",
  structured: { sources: [
    { type: "document", id: "d1", title: "연차 규정", route: "/knowledge/d1", where: "인사 규정", cited: true },
    { type: "document", id: "d2", title: "목록에 이미 선 문서", route: "/knowledge/d2", cited: true, shown: true },
    { type: "document", id: "d3", title: "찾아만 본 문서", route: "/knowledge/d3", cited: false },
    { type: "ticket", id: "t1", title: "연차 정산 오류", route: "/tickets/t1", key: "HR-12", status: "진행", cited: true },
    { type: "document", id: "d4", title: "바깥 주소", route: "https://evil.example/d4", cited: true },
  ] },
};

function renderPanel(props = {}) {
  const all = { message: MESSAGE, isLatest: true, activeRoute: null, onClose: vi.fn(), headingId: "sources-h", ...props };
  render(<ThemeModeProvider><SourcesPanel {...all} /></ThemeModeProvider>);
  return all;
}

const items = () => within(document.querySelector("[data-sources-panel] ul")).getAllByRole("listitem");

describe("참고 자료 칸", () => {
  it("인용한 자료만 선다 — 찾아만 본 것 · 본문 목록에 이미 선 것 · 앱 밖 경로는 빠진다", () => {
    renderPanel();
    expect(screen.getByRole("complementary", { name: "참고 자료" })).toBeInTheDocument();
    expect(items().map((li) => li.querySelector("a").getAttribute("href"))).toEqual(["#/knowledge/d1", "#/tickets/t1"]);
    expect(screen.getByText("2개")).toBeInTheDocument();
    expect(items()[1].textContent).toContain("HR-12");
  });

  it("앞 답의 자료면 그렇다고 말한다", () => {
    renderPanel({ isLatest: false });
    expect(screen.getByText("앞 답의 자료입니다. 다른 답의 참고 자료 단추를 누르면 그 답의 자료로 바뀝니다.")).toBeInTheDocument();
  });

  it("답 안 링크가 가리키는 자료(문단 자리는 달라도)가 강조되고 보이는 자리로 굴러온다", () => {
    const scroll = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scroll;
    try {
      renderPanel({ activeRoute: "/knowledge/d1?block=b3" });
      expect(items()[0]).toHaveAttribute("data-active");
      expect(items()[1]).not.toHaveAttribute("data-active");
      expect(scroll).toHaveBeenCalled();
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("닫기 단추가 칸을 닫는다", async () => {
    const user = userEvent.setup();
    const props = renderPanel();
    await user.click(screen.getByRole("button", { name: "참고 자료 닫기" }));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });
});
