/* 좁은 칸에서 티켓 표가 **부가 열을 접는가** (D-380).
 *
 * `ui/kit.test.jsx` 가 `DataTable` 에 대해 이미 못박은 계약과 **같은 계약**이다. 이 파일이
 * 따로 있는 이유는 이 저장소가 그 교훈을 두 번 비싸게 배웠기 때문이다 — 열 정의를 읽어
 * `<td>` 를 그리는 자리가 둘이고(`DataTable` 과 여기 `GroupedTickets`), 규칙을 한쪽에만
 * 적으면 「팀 티켓은 접히는데 내 티켓은 안 접히는」 상태가 된다. W5 의 카드 접기가 정확히
 * 그렇게 갈렸다(`control_baseline_mismatch`).
 *
 * jsdom 에는 배치가 없어 `clientWidth` 가 언제나 0 이다. 그 값을 시험이 직접 정해 준다 —
 * 「무엇을 재는가」가 이 규칙의 전부라, 그것을 흉내내는 것이 곧 규칙을 재는 것이다. */
import React from "react";
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { act, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { GroupedTickets, ticketColumns } from "./MyTickets.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROWS = [
  {
    id: "t-1", tid: 4101, title: "로그인 실패 조사", project: "인프라",
    status: "진행", priority: "높음", difficulty: "상",
    est_wd: 2, act_wd: 1, due: "2026-09-10", created_at: "2026-08-01T00:00:00Z",
  },
];

let boxWidth = 0;
let original;

function draw(px) {
  boxWidth = px;
  const cols = ticketColumns({ showAssignee: true, onEdit: () => {} });
  render(
    <ThemeModeProvider>
      <GroupedTickets rows={ROWS} columns={cols} />
    </ThemeModeProvider>,
  );
}

/** 관찰 직후의 첫 알림(`test-setup.js` 의 ResizeObserver 대역)을 act 안에서 흘린다. */
const settle = () => act(async () => {});

describe("GroupedTickets — 좁은 칸에서 접히는 열 (D-380)", () => {
  beforeEach(() => {
    original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true, get() { return boxWidth; },
    });
  });
  afterEach(() => {
    if (original) Object.defineProperty(HTMLElement.prototype, "clientWidth", original);
    else delete HTMLElement.prototype.clientWidth;
  });

  it("칸이 넉넉하면 열 전부가 선다", async () => {
    draw(2400);
    await settle();
    for (const name of ["티켓", "제목", "상태", "우선순위", "신호", "난이도", "예상 WD", "실제 WD", "마감", "생성 일자", "담당자"]) {
      expect(screen.getByRole("columnheader", { name: new RegExp(`^${name}`) }), name).toBeInTheDocument();
    }
    expect(screen.queryByText(/열을 숨겼습니다/)).toBeNull();
  });

  /* 🔴 이 목록이 없으면 이 표는 1366 화면에서 756px 을 가로로 밀어야 했다(실측). */
  it("🔴 칸이 좁으면 부가 열이 접힌다 — 뒤에 적은 열부터다", async () => {
    draw(900);
    await settle();
    expect(screen.queryByRole("columnheader", { name: /^생성 일자/ })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /^실제 WD/ })).toBeNull();
  });

  /* 접는 순서가 뜻을 갖는다 — 「무엇이 누구 것이고 언제까지인가」와 「지금 무엇이
     잘못됐나」는 마지막까지 남는다. */
  it("🔴 제목·상태·마감·담당자·신호는 아무리 좁아도 안 접힌다", async () => {
    draw(200);
    await settle();
    for (const name of ["티켓", "제목", "상태", "신호", "마감", "담당자"]) {
      expect(screen.getByRole("columnheader", { name: new RegExp(`^${name}`) }), name).toBeInTheDocument();
    }
  });

  it("접은 열이 무엇인지 표가 말한다", async () => {
    draw(900);
    await settle();
    expect(screen.getByText(/열을 숨겼습니다/)).toBeInTheDocument();
    expect(screen.getByText(/생성 일자/)).toBeInTheDocument();
  });

  it("아직 못 쟀으면 아무 것도 안 접는다 — 열이 사라졌다 돌아오지 않는다", async () => {
    draw(0);
    await settle();
    expect(screen.getByRole("columnheader", { name: /^생성 일자/ })).toBeInTheDocument();
  });
});
