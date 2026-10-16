import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 개발자 월간 리포트 — 사람이 아무도 안 잡힌 달과, 실제 데이터가 있는 달.
 *
 * 담당자 0명은 드문 예외가 아니다: 새 달의 1일(마감일이 그 달인 티켓이 아직 없음), Notion
 * '작업' DB를 막 붙인 직후, 활성 사용자가 아직 없는 신규 설치에서 매번 나온다. 예전 화면은
 * 그때 머리글만 있고 몸통이 빈 표 두 개를 그렸다 — '아직 로딩 중인가', '고장인가'를 구분할 수
 * 없었다. 지금은 무엇이 없고 무엇을 하면 되는지 말한다.
 *
 * qa-contract-change: S16 이 「담당자별 완료 업무량」 막대를 지웠다. 바로 아래 표의 «완료 업무량» 열이 같은 사람들의 같은 숫자를 이미 말하고 있어서 한 화면이 같은 것을 두 번 말하던 자리다.
 * 게다가 막대는 값이 0 인
 * 사람을 빼고 그려 **표와 명단이 달랐다**(없는 차이를 만들던 자리다). 그래서 이 파일의
 * 두 시험은 검사할 그림을 잃었다. 지우지 않고 방향을 바꿔 다시 적는다 — 그림이 사라진
 * 뒤에도 **그 정보가 화면에 남아 있는지**를 본다. 지우기가 정보 손실이 아니었음을 이
 * 시험이 계속 증명한다.
 *
 * 함께 확인: 담당자별 업무량은 그림이 아니라 표가 말한다.
 *
 * qa-contract-change: 「팀 상태 구성」 도넛 판을 걷었다(D-501) — 도넛의 네 조각은 바로 위 팀 합계 카드가 이미 말하는 수였고, 1920 에서는 표 아래
 * 480px 판으로 서서 오른쪽 1,100px 가 비었다. 그래서 「'3건'이 카드와 도넛 범례 양쪽에 나온다(>1)」는 단언은 대상이 사라졌고, 같은 수가 **한 곳**
 * (합계 카드)에 있다는 단언으로 뒤집는다. 도넛이 하던 두 일(각주 · 막대의 색 범례)이 카드의 정의 목록과 구획 제목 줄로 옮겼는지, 합계에 안
 * 드는 취소가 사라지지 않았는지, 읽기 전용 보고서의 「새로고침」이 채움이 아닌지를 재는 시험을 더한다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 *
 * qa-contract-change: 요약 카드 아래에 구획 바로 가기 줄이 서서 「담당자별 상세 티켓」이 링크와 구획 제목 두 곳에 나온다. 구획이 있다는 단언은 글자가
 * 아니라 제목(heading) 역할로 찾는다. 0만 든 사람을 표에서 빼고 한 문장으로 말하는지, 바로 가기가 구획으로 가는지를 새로 잰다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { DevReport } from "./DevReport.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const EMPTY_TEAM = {
  total: 0, done: 0, in_progress: 0, verify: 0, plan: 0, cancel: 0,
  overdue: 0, est_done_total: 0, est_all_total: 0,
};

function renderReport() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DevReport />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("개발자 월간 리포트 — 담당자 0명", () => {
  it("빈 표 대신 무엇이 없는지 말한다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: EMPTY_TEAM, developers: [], unassigned: { total: 0 },
    });
    renderReport();

    expect(await screen.findByText("이 달에 집계할 담당자가 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("이 달에 담당한 티켓이 있는 사람이 없습니다.")).toBeInTheDocument();
    // 표 머리글만 남은 빈 표를 그리지 않는다(예전 회귀).
    expect(screen.queryByText("완료율")).toBeNull();
  });

  it("업무량을 말하던 그림이 사라진 자리에 빈 상자를 남기지 않는다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: EMPTY_TEAM, developers: [], unassigned: { total: 0 },
    });
    renderReport();

    expect(await screen.findByText("이 달에 집계할 담당자가 없습니다.")).toBeInTheDocument();
    // 옛 막대의 빈 상태 문구가 유령으로 남아 있으면 안 된다.
    expect(screen.queryByText("이 달에 완료한 업무량이 없습니다")).toBeNull();
  });
});

describe("개발자 월간 리포트 — 데이터가 있는 달", () => {
  const DEV = {
    user_id: "u-seo", email: "seo@goodmit.co.kr", state: "active", ambiguous_name: false,
    name: "서윤경", done: 3, prog: 1, verify: 0, plan: 2, cancel: 0, assigned: 6,
    overdue: 1, completion_rate: 50, est_done: 4.5, est_all: 9, act_done: 5,
    difficulty_avg: 3.2, has_tickets: true,
    tickets: [{ tid: 1201, title: "로그인 화면 정리", status: "완료", due: "2026-08-10", priority: "높음", difficulty: 3, est_wd: 1.5, act_wd: 2, url: null, overdue: false }],
  };

  it("🔴 그림을 지운 뒤에도 담당자별 완료 업무량은 표가 말한다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: { ...EMPTY_TEAM, total: 6, done: 3, in_progress: 1, plan: 2, overdue: 1, est_done_total: 4.5 },
      developers: [DEV], unassigned: { total: 0 },
    });
    renderReport();

    // 「완료 업무량」 열의 그 사람 값. 막대가 말하던 4.5 가 표에 그대로 있다.
    const head = await screen.findByText("완료 업무량");
    const at = [...head.closest("table").querySelectorAll("thead th")].indexOf(head.closest("th"));
    const row = head.closest("table").querySelector("tbody tr");
    expect(row.querySelectorAll("td")[at]).toHaveTextContent("4.5");
    // 팀 완료 3건은 합계 카드 **한 곳**이 말한다 — 같은 수를 다시 그리던 도넛 범례는 없다(D-501).
    const card = screen.getByLabelText("팀 합계");
    expect(screen.getAllByText("3건")).toHaveLength(1);
    expect(card.contains(screen.getByText("3건"))).toBe(true);
    expect(screen.getByRole("heading", { name: "담당자별 상세 티켓" })).toBeInTheDocument();
  });

  it("담당자별 상세 티켓의 우선순위는 다른 표와 같은 이름이다 — 원시 값(high)을 그대로 쓰지 않는다(r23)", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: { ...EMPTY_TEAM, total: 6, done: 3, in_progress: 1, plan: 2, overdue: 1, est_done_total: 4.5 },
      developers: [{ ...DEV, tickets: [{ ...DEV.tickets[0], priority: "high" }] }], unassigned: { total: 0 },
    });
    renderReport();
    const title = await screen.findByText("로그인 화면 정리");
    const row = title.closest("tr");
    expect(row).toHaveTextContent("높음");
    expect(row.textContent).not.toMatch(/high/);
  });

  it("도넛 판이 없고, 그 각주는 합계 카드의 정의 목록으로 · 막대의 색 범례는 구획 제목 줄로 옮겼다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: { ...EMPTY_TEAM, total: 7, done: 3, in_progress: 1, plan: 2, cancel: 1, overdue: 1, est_done_total: 4.5 },
      developers: [DEV], unassigned: { total: 0 },
    });
    renderReport();

    const card = await screen.findByLabelText("팀 합계");
    expect(screen.queryByText("팀 상태 구성")).toBeNull();
    expect(document.querySelector("[data-chart-frame='donut']")).toBeNull();
    // 세는 단위 각주 — 도넛 판 아래 문장이었다.
    const notes = card.querySelector("[data-summary-notes]");
    expect(within(notes).getByText(/팀 합계는 티켓 단위로 셉니다/)).toBeInTheDocument();
    // 합계에 안 드는 취소는 도넛만 그렸다 — 사라지지 않고 정의 목록이 수로 말한다.
    expect(within(notes).getByText("1건은 합계에서 뺐습니다.")).toBeInTheDocument();
    // 막대의 색 범례 — 일곱 칸이 이름으로 선다(보류와 기타가 빠지면 막대의 합이 담당과 다르다, 계획 3.7).
    const legend = screen.getByRole("list", { name: "상태 구성 막대의 색" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["완료", "진행", "검증", "계획", "보류", "취소", "기타"]);
  });

  it("반례: 취소가 0건이면 그 각주는 서지 않는다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: { ...EMPTY_TEAM, total: 6, done: 3, in_progress: 1, plan: 2, overdue: 1, est_done_total: 4.5 },
      developers: [DEV], unassigned: { total: 0 },
    });
    renderReport();
    await screen.findByLabelText("팀 합계");
    expect(screen.queryByText(/건은 합계에서 뺐습니다/)).toBeNull();
  });

  it("읽기 전용 보고서라 「새로고침」은 채움이 아니다 — 이 화면에는 채움 단추가 없다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: EMPTY_TEAM, developers: [], unassigned: { total: 0 },
    });
    renderReport();
    const refresh = await screen.findByRole("button", { name: "새로고침" });
    expect(refresh).not.toHaveClass("MuiButton-contained");
    expect(document.querySelector(".MuiButton-contained")).toBeNull();
  });

  /* 담당자별 상세 티켓이 **공용 표**로 흡수됐다. 이 화면만 자기 `<Table>` 을 그리던
     마지막 자리였고, 그것을 붙잡고 있던 것이 담당자 구분 행 하나였다. 흡수가 실제로
     일어났는지는 「그 줄이 여전히 있는가」와 「그 줄이 표의 묶음 머리행인가」 둘 다
     봐야 안다 — 줄만 있고 표가 갈라져 있으면 고친 것이 없다. */
  it("담당자 구분 줄이 표의 묶음 머리행으로 남는다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: { ...EMPTY_TEAM, total: 6, done: 3, in_progress: 1, plan: 2, overdue: 1, est_done_total: 4.5 },
      developers: [DEV], unassigned: { total: 0 },
    });
    const { container } = renderReport();

    await screen.findByRole("heading", { name: "담당자별 상세 티켓" });
    const groups = container.querySelectorAll("[data-group-row]");
    expect(groups).toHaveLength(1);
    // 묶는 키는 이름이 아니라 사람 id 다(같은 이름의 두 사람이 한 묶음이 되지 않게, 계획 3.7).
    expect(groups[0].getAttribute("data-group-row")).toBe("u-seo");
    expect(groups[0].textContent).toContain("서윤경");
    expect(groups[0].textContent).toContain("완료 3건, 진행과 검증 1건, 완료 예상 WD 4.5인일");
    // 스크린 리더가 아래 행들이 이 이름에 속한다고 읽는다.
    expect(groups[0].querySelector("th").getAttribute("scope")).toBe("colgroup");
    // 그 줄이 붙어 있는 표는 상세 티켓 표다(제목 열이 그 표에만 있다).
    const table = groups[0].closest("table");
    expect(within(table).getByText("로그인 화면 정리")).toBeInTheDocument();
  });

  it("같은 이름의 두 사람은 두 줄이고 이메일로 구별한다", async () => {
    const twin = (id, email) => ({
      ...DEV, user_id: id, email, ambiguous_name: true, name: "김철수",
      tickets: [{ ...DEV.tickets[0], uid: "t-" + id, title: "일 " + id }],
    });
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: { ...EMPTY_TEAM, total: 2, done: 2, est_done_total: 3 },
      developers: [twin("u1", "kim1@goodmit.co.kr"), twin("u2", "kim2@goodmit.co.kr")],
      unassigned: { total: 0 },
    });
    renderReport();
    expect((await screen.findAllByText("김철수 (kim1@goodmit.co.kr)")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("김철수 (kim2@goodmit.co.kr)").length).toBeGreaterThan(0);
  });

  it("이 달에 끝낸 일은 끝낸 날짜로 따로 보이고, 끝낸 날짜를 모르는 완료 티켓 수를 말한다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: { ...EMPTY_TEAM, total: 6, done: 3, in_progress: 1, plan: 2, overdue: 1, est_done_total: 4.5 },
      developers: [{ ...DEV, completed: { done: 4, late_done: 1, est_done: 5, act_done: 6 }, no_due: { open: 2 } }],
      unassigned: { total: 0 },
      completed: { team: { done: 4, late_done: 1, est_done: 5, act_done: 6 }, unknown_date: 3 },
      no_due: { team: { open: 2 } },
      definitions: { completed_done: "끝낸 날짜가 이 달인 완료 티켓입니다." },
    });
    renderReport();
    expect(await screen.findByText("이 달에 끝낸 일 (2026-08)")).toBeInTheDocument();
    expect(screen.getByText(/끝낸 날짜를 모르는 완료 티켓 3건/)).toBeInTheDocument();
    expect(screen.getByText(/마감일이 없는 열린 티켓 2건/)).toBeInTheDocument();
  });
});

/* 0만 든 사람 — 서버는 활성 사용자 전원을 싣는다(이 달 티켓이 없으면 0). 예전에는 그 사람들이 두 표에서 모든 칸이 0인 줄과
 * 빈 회색 막대로 섰다. 이제 두 표에는 일이 있는 사람만 서고, 뺀 사람은 표 아래 한 문장이 이름으로 말한다. 팀 합계는 그대로다. */
describe("개발자 월간 리포트 — 0만 든 사람은 표 대신 한 문장", () => {
  const WORKER = {
    user_id: "u-seo", email: "seo@goodmit.co.kr", state: "active", ambiguous_name: false,
    name: "서윤경", done: 3, prog: 1, verify: 0, plan: 2, hold: 0, cancel: 0, other: 0, assigned: 6,
    overdue: 1, completion_rate: 50, est_done: 4.5, est_all: 9, act_done: 5, difficulty_avg: 3.2, has_tickets: true,
    no_due: { open: 0 }, tickets: [],
  };
  const idle = (id, name, extra = {}) => ({
    user_id: id, email: id + "@goodmit.co.kr", state: "active", ambiguous_name: false, name,
    done: 0, prog: 0, verify: 0, plan: 0, hold: 0, cancel: 0, other: 0, assigned: 0, overdue: 0, completion_rate: null,
    est_done: 0, est_all: 0, act_done: 0, act_per_done: null, estimate_accuracy_pct: null, difficulty_avg: null,
    has_tickets: false, tickets: [], no_due: { open: 0 }, ...extra,
  });
  const TEAM = { ...EMPTY_TEAM, total: 6, done: 3, in_progress: 1, plan: 2, overdue: 1, est_done_total: 4.5 };
  const tableUnder = (heading) => screen.getByRole("heading", { name: heading }).closest("section").querySelector("table");

  it("일이 있는 사람만 두 표에 서고, 0만 든 사람은 표 아래 한 문장이 이름으로 말한다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08", team: TEAM,
      developers: [WORKER, idle("u-kim", "김지훈"), idle("u-park", "박민준")], unassigned: { total: 0 },
    });
    renderReport();
    await screen.findByRole("heading", { name: "개발자별 상세 (2026-08)" });
    for (const heading of ["개발자별 상세 (2026-08)", "업무량 분석 (완료 업무량 기준)"]) {
      const table = tableUnder(heading);
      expect(within(table).getByText("서윤경")).toBeInTheDocument();
      expect(within(table).queryByText("김지훈")).toBeNull();
      expect(within(table).queryByText("박민준")).toBeNull();
    }
    expect(screen.getByText("김지훈, 박민준 2명은 이 달에 집계된 티켓이 없어 이 표와 업무량 분석 표에서 뺐습니다.")).toBeInTheDocument();
    // 팀 합계는 서버 값 그대로다 — 줄을 뺀 것이 합을 바꾸지 않는다.
    expect(within(screen.getByLabelText("팀 합계")).getByText("3건")).toBeInTheDocument();
  });

  it("마감 없는 열린 티켓만 있는 사람은 0만 든 사람이 아니다 — 표에 서고 문장에 들지 않는다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08", team: TEAM,
      developers: [WORKER, idle("u-lee", "이서연", { no_due: { open: 2 } }), idle("u-kim", "김지훈")], unassigned: { total: 0 },
    });
    renderReport();
    await screen.findByRole("heading", { name: "개발자별 상세 (2026-08)" });
    expect(within(tableUnder("개발자별 상세 (2026-08)")).getByText("이서연")).toBeInTheDocument();
    // 한 사람이면 조사가 이름의 받침을 따른다(「김지훈은」).
    expect(screen.getByText("김지훈은 이 달에 집계된 티켓이 없어 이 표와 업무량 분석 표에서 뺐습니다.")).toBeInTheDocument();
  });

  it("모두 0이면 0만 든 표 대신 빈 상태와 한 문장이 선다 — 표 머리도 0 줄도 없다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08", team: EMPTY_TEAM,
      developers: [idle("u-kim", "김지훈"), idle("u-park", "박민준")], unassigned: { total: 2 },
    });
    renderReport();
    expect(await screen.findByText("이 달 마감 티켓을 맡은 담당자가 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("이 달에 집계할 업무량이 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("김지훈, 박민준 2명은 이 달에 집계된 티켓이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText("완료율")).toBeNull();
    expect(screen.queryByRole("list", { name: "상태 구성 막대의 색" })).toBeNull();
  });

  it("반례: 모두 일이 있으면 그 문장은 서지 않는다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08", team: TEAM, developers: [WORKER], unassigned: { total: 0 },
    });
    renderReport();
    await screen.findByRole("heading", { name: "개발자별 상세 (2026-08)" });
    expect(document.querySelector("[data-idle-people]")).toBeNull();
  });
});

/* 구획 바로 가기 (D-596) · 머리 문구 — 다섯 구획이 이어지는 긴 보고서라 요약 아래에서 각 구획으로 간다. 인쇄에는 서지 않는다. */
describe("개발자 월간 리포트 — 구획 바로 가기와 머리 문구", () => {
  const DATA = {
    configured: true, ok: true, period: "2026-08",
    team: { ...EMPTY_TEAM, total: 1, done: 1, est_done_total: 1 }, developers: [], unassigned: { total: 0 },
  };

  it("요약 아래에 네 구획으로 가는 링크가 서고, 누르면 그 구획으로 굴러가 제목에 초점이 간다", async () => {
    apiMock.mockResolvedValue(DATA);
    const scrolled = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function scrollIntoView() { scrolled.push(this); };
    try {
      const user = userEvent.setup();
      renderReport();
      const nav = await screen.findByRole("navigation", { name: "리포트 구획 바로 가기" });
      expect(within(nav).getAllByRole("button").map((b) => b.textContent))
        .toEqual(["개발자별 상세", "업무량 분석", "이 달에 끝낸 일", "담당자별 상세 티켓"]);
      await user.click(within(nav).getByRole("button", { name: "업무량 분석" }));
      const heading = screen.getByRole("heading", { name: "업무량 분석 (완료 업무량 기준)" });
      expect(scrolled).toEqual([heading.closest("section")]);
      expect(heading.contains(document.activeElement)).toBe(true);
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("설명은 보고 있는 달로 시작하는 한 문장이고, 인쇄 단추는 명사구다", async () => {
    apiMock.mockResolvedValue(DATA);
    renderReport();
    expect(await screen.findByText("2026년 8월 마감 티켓을 담당자별로 집계한 보고서입니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "인쇄 또는 PDF 저장" })).toBeInTheDocument();
  });
});
