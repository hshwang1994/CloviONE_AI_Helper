/* 새 티켓의 **공유 범위** 안내 (0060 §13).
 *
 * 작성자의 소속과 프로젝트의 소속은 다를 수 있다. A-1 사람이 상위 A 프로젝트에 티켓을
 * 만들면 A-2 사람도 그 티켓을 본다 — 만든 뒤에 알게 되면 늦다.
 *
 * ⚠️ 경로는 **서버가 준다**(`/api/tickets/projects` 의 `dept_path`). 예전에는 화면이
 * 조직 트리에서 만들기로 돼 있었는데, 그 트리 API 는 관리자 전용이라 일반 사용자에게는
 * 언제나 비어 있었다 — 부서 프로젝트를 골라도 "조직 전체 공통" 이라고 **반대로** 안내했다.
 * 그 회귀를 여기서 못박는다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TicketShareScope } from "./MyTickets.jsx";

const ME = {
  department_path: [{ id: "d0", name: "본부" }, { id: "d1", name: "개발팀" }],
  organization: { id: "o1", name: "굿모닝아이텍" },
};

describe("공유 범위 안내", () => {
  it("부서 프로젝트는 **그 부서 경로**를 말한다", () => {
    render(<TicketShareScope me={ME} project={{
      id: "p1", name: "프런트팀 UI 정비",
      dept_path: [{ id: "d0", name: "본부" }, { id: "d1", name: "개발팀" }, { id: "d2", name: "프런트팀" }],
    }} />);
    expect(screen.getByText(/본부 › 개발팀 › 프런트팀/)).toBeTruthy();
    expect(screen.queryByText(/전체 공통/)).toBeNull();
  });

  it("부서 없는 프로젝트는 조직 공통이라고 말한다", () => {
    render(<TicketShareScope me={ME} project={{ id: "p2", name: "전사 보안 점검", dept_path: [] }} />);
    expect(screen.getByText(/굿모닝아이텍 전체 공통/)).toBeTruthy();
  });

  it("요청자의 소속을 함께 보여 준다 — 두 소속이 다를 수 있다", () => {
    render(<TicketShareScope me={ME} project={{
      id: "p1", name: "영업팀 제안", dept_path: [{ id: "d9", name: "영업팀" }],
    }} />);
    expect(screen.getByText(/요청자 본부 › 개발팀/)).toBeTruthy();
    expect(screen.getByText(/영업팀/)).toBeTruthy();
  });

  it("프로젝트를 안 고르면 아무것도 안 그린다", () => {
    const { container } = render(<TicketShareScope me={ME} project={null} />);
    expect(container.textContent).toBe("");
  });
});
