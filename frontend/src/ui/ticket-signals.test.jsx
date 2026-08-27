import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

/* Status 와 Signal 은 **다른 축**이다 (D-349).
 *
 * 여기서 지키는 것은 셋이다:
 *   1) `지연` 은 저장값이 아니라 계산값이고, **끝난 일은 지연이 아니다**.
 *   2) 화면이 상태 이름을 하드코딩하지 않는다 — 「끝났는가」는 서버가 준다.
 *   3) 밀도가 둘이어도 어휘는 하나다: 좁은 표의 아이콘도 접근 이름은 온전한 낱말이다.
 */

import {
  SIGNALS, isOverdue, terminalKeys, ticketSignals, todayIso,
} from "../lib/ticketSignals.js";
import { TicketSignals } from "./TicketSignals.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

const TODAY = "2026-08-27";
const TERMINAL = new Set(["완료", "취소"]);

function draw(ui) {
  return render(<ThemeModeProvider>{ui}</ThemeModeProvider>);
}

describe("지연은 계산한다 — 저장하지 않는다", () => {
  it("마감이 지났고 안 끝났으면 지연이다", () => {
    expect(isOverdue({ due: "2026-08-26", status: "진행" }, { today: TODAY, terminal: TERMINAL })).toBe(true);
  });

  it("🔴 끝난 일은 마감이 지났어도 지연이 아니다", () => {
    // 지난주에 끝낸 일이 오늘 빨갛게 뜨면 그 색은 아무 행동도 요구하지 않는다.
    expect(isOverdue({ due: "2026-08-26", status: "완료" }, { today: TODAY, terminal: TERMINAL })).toBe(false);
    expect(isOverdue({ due: "2026-08-26", status: "취소" }, { today: TODAY, terminal: TERMINAL })).toBe(false);
  });

  it("오늘 마감은 아직 지연이 아니다", () => {
    expect(isOverdue({ due: TODAY, status: "진행" }, { today: TODAY, terminal: TERMINAL })).toBe(false);
  });

  it("마감이 없으면 지연이 아니다", () => {
    expect(isOverdue({ due: null, status: "진행" }, { today: TODAY, terminal: TERMINAL })).toBe(false);
  });

  it("🔴 「끝났는가」는 **서버 어휘**에서 온다 — 화면이 상태 이름을 안 적는다", () => {
    const body = {
      statuses: [
        { key: "진행", terminal: false },
        { key: "완료", terminal: true },
        { key: "보류", terminal: false },
        { key: "취소", terminal: true },
      ],
    };
    expect([...terminalKeys(body)].sort()).toEqual(["완료", "취소"]);
    // 어휘가 아직 안 왔으면 빈 집합이다. 상태 이름을 여기 적어 두는 것보다 낫다 —
    // 적어 두면 어휘가 바뀐 날 이 파일만 옛 이름으로 남고 그 어긋남은 오류를 안 낸다.
    expect(terminalKeys(undefined).size).toBe(0);
  });
});

describe("한 티켓이 신호를 여러 개 갖는다", () => {
  it("진행 중이면서 막혀 있고 지연일 수 있다", () => {
    const got = ticketSignals(
      { status: "진행", due: "2026-08-01", blocked: true, issue: true },
      { today: TODAY, terminal: TERMINAL },
    );
    expect(got.map((s) => s.key)).toEqual(["blocked", "overdue", "issue"]);
  });

  it("아무것도 안 켜지면 빈 목록이다", () => {
    expect(ticketSignals({ status: "진행", due: null }, { today: TODAY, terminal: TERMINAL })).toEqual([]);
  });

  it("🔴 상태값에는 빨강이 없다 — 빨강은 신호가 쓴다", () => {
    expect(SIGNALS.blocked.tone).toBe("danger");
    expect(SIGNALS.overdue.tone).toBe("danger");
    // 이슈는 알고는 있어야 하지만 오늘 당장은 아니다. 셋 다 빨강이면 셋 다 안 보인다.
    expect(SIGNALS.issue.tone).toBe("warn");
  });

  it("🔴 차단 사연이 있으면 그 신호에만 붙는다(A8) — 공유 어휘 항목은 안 건드린다", () => {
    const got = ticketSignals(
      { status: "진행", blocked: true, blocked_reason: "배포 승인 대기" },
      { today: TODAY, terminal: TERMINAL },
    );
    expect(got.find((s) => s.key === "blocked").reason).toBe("배포 승인 대기");
    // `SIGNALS.blocked` 는 모든 차단 티켓이 보는 공유 참조다 — 복제본에 사연을 얹었다고
    // 원본까지 오염되면 안 된다(다음 티켓이 이전 티켓의 사연을 보게 된다).
    expect(SIGNALS.blocked.reason).toBeUndefined();
  });

  it("사연 없는 차단은 지금과 같다 — reason 이 없다", () => {
    const got = ticketSignals({ status: "진행", blocked: true }, { today: TODAY, terminal: TERMINAL });
    expect(got.find((s) => s.key === "blocked").reason).toBeUndefined();
  });
});

describe("밀도는 둘이고 어휘는 하나다", () => {
  it("넓은 표는 낱말을 쓴다", () => {
    draw(<TicketSignals signals={[SIGNALS.blocked, SIGNALS.overdue]} />);
    expect(screen.getByText("차단됨")).toBeInTheDocument();
    expect(screen.getByText("지연")).toBeInTheDocument();
  });

  it("🔴 좁은 표는 아이콘만 쓰되 **접근 이름은 온전한 낱말**이다", () => {
    draw(<TicketSignals signals={[SIGNALS.issue]} variant="mark" />);
    expect(screen.getByRole("img", { name: "이슈 있음" })).toBeInTheDocument();
  });

  it("신호가 없으면 아무것도 안 그린다 — 대시도 안 찍는다", () => {
    const { container } = draw(<TicketSignals signals={[]} />);
    // 「신호가 없다」는 값이 빠진 것이 아니라 정상이고, 목록의 대부분이 그 상태다.
    expect(container.textContent).toBe("");
  });

  it("🔴 차단 사연은 Tooltip 으로 본다(A8) — 넓은 표에서 hover 하면 사연이 뜬다", async () => {
    const user = userEvent.setup();
    draw(<TicketSignals signals={[{ ...SIGNALS.blocked, reason: "배포 승인 대기" }]} />);
    await user.hover(screen.getByText("차단됨"));
    expect(await screen.findByText("배포 승인 대기")).toBeInTheDocument();
  });

  it("좁은 표는 title 에 사연을 이어 붙인다 — 사연 없으면 이름만이다", () => {
    draw(<TicketSignals signals={[{ ...SIGNALS.blocked, reason: "배포 승인 대기" }]} variant="mark" />);
    expect(screen.getByRole("img", { name: "차단됨: 배포 승인 대기" })).toBeInTheDocument();
  });
});

describe("오늘은 브라우저의 달력일이다", () => {
  beforeEach(() => { vi.useRealTimers(); });

  it("YYYY-MM-DD 로 읽는다 — ISO 문자열은 사전순 비교가 곧 날짜순 비교다", () => {
    expect(todayIso(new Date(2026, 7, 3))).toBe("2026-08-03");
    expect(todayIso(new Date(2026, 11, 25))).toBe("2026-12-25");
  });
});
