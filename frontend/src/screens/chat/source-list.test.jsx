/* 「참고한 자료」 — 서버가 만든 앱 안 경로만 링크가 되고, 바깥 주소 · 그림은 그리지 않는다 (D-535 · D-538).
 *
 * qa-contract-replaced-by: frontend/src/screens/chat-card-chrome.test.jsx
 * qa-contract-replaced-by: frontend/src/screens/chat-ticket-card-deeplink.test.jsx
 * qa-contract-replaced-by: frontend/src/screens/chat/message-thread-inline-cards.test.jsx
 *
 * 옛 결과 카드(TicketCard · CardStack)는 서버가 더는 싣지 않는 구조를 그리던 닿지 않는 코드였다. 그 시험들이 지키던 성질 —
 * 앱 안 상세로 가는 링크, 바깥 주소를 앵커로 만들지 않음, 말풍선 안 구조화 결과 — 은 출처 목록이 그대로 진다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { SourceList, safeSourceRoute, SOURCE_ROUTE_PREFIXES } from "./SourceList.jsx";
import { RAIL_SOURCE_LIMIT, ResultsRail } from "./ResultsRail.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

function renderList(sources, props) {
  return render(
    <ThemeModeProvider>
      <SourceList sources={sources} {...props} />
    </ThemeModeProvider>,
  );
}

const TICKET = { type: "ticket", id: "t-1", title: "결재 화면 개선", route: "/tickets/t-1", key: "ABCDEF-12", status: "진행" };
const DOC = { type: "document", id: "d-1", title: "연차 규정", route: "/knowledge/d-1?block=b1", where: "사내 규정" };

describe("참고한 자료", () => {
  it("앱 안 경로는 같은 창의 해시 링크이고 종류와 메타가 함께 보인다", () => {
    renderList([TICKET, DOC]);
    const ticket = screen.getByRole("link", { name: "결재 화면 개선" });
    expect(ticket).toHaveAttribute("href", "#/tickets/t-1");
    expect(screen.getByRole("link", { name: "연차 규정" })).toHaveAttribute("href", "#/knowledge/d-1?block=b1");
    expect(screen.getByText("ABCDEF-12")).toBeInTheDocument();
    expect(screen.getByText("사내 규정")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "참고한 자료" })).toBeInTheDocument();
  });

  it("바깥 주소 · 허용 밖 경로 · 모르는 종류는 그리지 않는다 — 앵커도 그림도 없다", () => {
    const { container } = renderList([
      { type: "document", id: "x1", title: "바깥", route: "https://evil.example/x" },
      { type: "document", id: "x2", title: "두 빗금", route: "//evil.example/x" },
      { type: "document", id: "x3", title: "관리 화면", route: "/admin/users" },
      { type: "person", id: "x4", title: "사람", route: "/tickets/x4" },
      DOC,
    ]);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(container.querySelectorAll('a[href^="http"], a[href^="//"]')).toHaveLength(0);
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });

  it("여덟 개가 넘으면 나머지는 「더 보기」 뒤에 있다", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 11 }, (_, i) => ({ ...DOC, id: "d" + i, title: "문서 " + i, route: "/knowledge/d" + i }));
    renderList(many);
    expect(screen.getAllByRole("link")).toHaveLength(8);
    await user.click(screen.getByRole("button", { name: "3개 더 보기" }));
    expect(screen.getAllByRole("link")).toHaveLength(11);
  });

  it("출처가 없으면 아무것도 그리지 않는다", () => {
    const { container } = renderList([]);
    expect(container.textContent).toBe("");
  });

  it("허용 경로 판정", () => {
    expect(SOURCE_ROUTE_PREFIXES).toEqual(["/knowledge/", "/tickets/", "/projects/", "/my-approvals", "/board/", "/sprint"]);
    expect(safeSourceRoute("/my-approvals?id=a1")).toBe("/my-approvals?id=a1");
    expect(safeSourceRoute("/sprint?team=dep-1&sprint=s-1")).toBe("/sprint?team=dep-1&sprint=s-1");
    expect(safeSourceRoute("/sprints-x")).toBeNull();
    expect(safeSourceRoute("javascript:alert(1)")).toBeNull();
    expect(safeSourceRoute(null)).toBeNull();
  });

  it("회의록 출처는 「회의록」 종류로 스프린트 회의 화면을 가리킨다(A8)", () => {
    renderList([{ type: "sprint", id: "s-1", title: "10월 2주 회차", route: "/sprint?team=dep-1&sprint=s-1" }]);
    expect(screen.getByRole("link", { name: "10월 2주 회차" })).toHaveAttribute("href", "#/sprint?team=dep-1&sprint=s-1");
    expect(screen.getByText("회의록")).toBeInTheDocument();
  });
});

describe("참고한 자료 레일 (A8)", () => {
  it("레일은 서버가 싣는 서른 개까지 접지 않고 세우고, 그 뒤만 「더 보기」 뒤에 둔다", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 35 }, (_, i) => ({ ...DOC, id: "d" + i, title: "문서 " + i, route: "/knowledge/d" + i }));
    const railMsg = { id: "a1", role: "assistant", created_at: "2026-01-01T00:00:03", structured: { kind: "assistant", sources: many } };
    render(<ThemeModeProvider><ResultsRail railOpen railMsg={railMsg} railIsLast /></ThemeModeProvider>);
    expect(RAIL_SOURCE_LIMIT).toBe(30);
    expect(screen.getAllByRole("link")).toHaveLength(30);
    await user.click(screen.getByRole("button", { name: "5개 더 보기" }));
    expect(screen.getAllByRole("link")).toHaveLength(35);
  });
});
