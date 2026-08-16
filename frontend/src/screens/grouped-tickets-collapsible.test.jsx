/* GroupedTickets의 `collapsible` prop (VIS-64).
 *
 * 스프린트 회의처럼 담당자가 많으면 이 표 하나가 11,000px를 넘어 페이지네이션 없이 한
 * 화면에 다 들어갔다(감사 근거). `collapsible`을 켜면 그룹이 접힌 채 시작해 회의에서
 * 한 사람씩 펼쳐 가는 흐름을 준다 — 기본값(false, 미지정)은 기존 세 소비처(내 티켓·
 * 미할당·팀 티켓)의 동작을 그대로 지켜야 한다.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { GroupedTickets, ticketColumns } from "./MyTickets.jsx";
import { groupByAssignee } from "./TeamTickets.jsx";

const ROWS = [
  { id: "t-1", tid: 4101, title: "로그인 실패 조사", assignee_names: ["서윤경"] },
  { id: "t-2", tid: 4102, title: "배포 스크립트 정리", assignee_names: ["서윤경"] },
  { id: "t-3", tid: 4103, title: "백업 점검", assignee_names: ["김철수"] },
];

function renderGrouped(extraProps) {
  return render(
    <GroupedTickets rows={ROWS} columns={ticketColumns({})} groupBy={groupByAssignee} {...extraProps} />,
  );
}

describe("GroupedTickets — collapsible 기본값(false)", () => {
  it("collapsible을 안 주면 모든 행이 바로 보인다(기존 세 소비처와 같은 동작)", () => {
    renderGrouped();
    expect(screen.getByText("로그인 실패 조사")).toBeInTheDocument();
    expect(screen.getByText("배포 스크립트 정리")).toBeInTheDocument();
    expect(screen.getByText("백업 점검")).toBeInTheDocument();
    // 펼치기/접기 버튼 자체가 없다 — 그룹 이름이 평문으로만 있다.
    expect(screen.queryByRole("button", { name: /서윤경/ })).toBeNull();
  });
});

describe("GroupedTickets — collapsible=true (VIS-64)", () => {
  it("그룹이 접힌 채 시작해 행이 안 보이지만, 그룹 이름과 건수는 보인다", () => {
    renderGrouped({ collapsible: true });
    expect(screen.getByText("서윤경")).toBeInTheDocument();
    expect(screen.getByText("2건")).toBeInTheDocument();
    expect(screen.getByText("김철수")).toBeInTheDocument();
    expect(screen.getByText("1건")).toBeInTheDocument();
    expect(screen.queryByText("로그인 실패 조사")).toBeNull();
    expect(screen.queryByText("백업 점검")).toBeNull();
  });

  it("한 그룹만 펼쳐도 다른 그룹은 그대로 접혀 있다", async () => {
    const user = userEvent.setup();
    renderGrouped({ collapsible: true });
    const toggle = screen.getByRole("button", { name: /서윤경/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("로그인 실패 조사")).toBeInTheDocument();
    expect(screen.getByText("배포 스크립트 정리")).toBeInTheDocument();
    // 김철수 그룹은 손대지 않았으니 계속 접혀 있다.
    expect(screen.queryByText("백업 점검")).toBeNull();

    // 다시 누르면 접힌다.
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("로그인 실패 조사")).toBeNull();
  });

  it("좁은 화면(카드 목록)에서도 같은 규칙이다", async () => {
    window.matchMedia = (query) => ({
      matches: true, media: query, // TABLE_CARD_QUERY를 항상 참으로 — 카드 분기를 강제한다
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, onchange: null,
      dispatchEvent: () => false,
    });
    try {
      const user = userEvent.setup();
      renderGrouped({ collapsible: true });
      expect(screen.queryByText("로그인 실패 조사")).toBeNull();
      await user.click(screen.getByRole("button", { name: /서윤경/ }));
      expect(screen.getByText("로그인 실패 조사")).toBeInTheDocument();
    } finally {
      delete window.matchMedia;
    }
  });
});

// VIS-163 — 담당자 열만 nowrap이 빠져 있어 1200×900처럼 좁은 폭에서 "임승환, 김동현" 같은
// 값이 글자 하나씩 세로로 무너졌다(overflowWrap:anywhere). 다른 모든 열(티켓 번호·상태·
// 우선순위·난이도·예상 WD·마감·작업)은 이미 nowrap:true라 같은 문제를 안 겪는다 — 담당자
// 열도 같은 규칙을 따라야 한다.
describe("담당자 열 — vertical_text_collapse 방지 (VIS-163)", () => {
  it("showAssignee면 담당자 열도 다른 열처럼 nowrap이다", () => {
    const cols = ticketColumns({ showAssignee: true });
    const assigneeCol = cols.find((c) => c.key === "assignee_names");
    expect(assigneeCol).toBeDefined();
    expect(assigneeCol.nowrap).toBe(true);
  });

  it("compact든 아니든 상관없이 담당자 열은 nowrap이다", () => {
    for (const compact of [true, false]) {
      const cols = ticketColumns({ showAssignee: true, compact });
      const assigneeCol = cols.find((c) => c.key === "assignee_names");
      expect(assigneeCol.nowrap).toBe(true);
    }
  });
});
