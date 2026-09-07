import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* qa-contract-change: S15 가 「연결이 없어 못 센다」 상태 자체를 없앴다(D-285) — 사람마다 담당자로 가리킬 값이 언제나 있으므로 그 갈래를 검사하던 시험 셋이 검사할 대상을 잃었다.
 * 셋을 지우는 대신 남은 「모른다」(티켓 읽기 실패) 하나로 옮겨 다시 적었고, 없어진 갈래는
 * 「옛 안내가 되살아나지 않는다」로 방향을 뒤집어 지킨다.
 *
 * 내 업무량 · 완료 통계 화면 — 서버가 준 숫자를 **그대로** 말하는가.
 *
 * 화면에서 다시 집계하지 않는 것이 이 화면의 설계다(홈과 숫자가 어긋나면 둘 다 못 믿는다).
 * 그래서 여기서 확인하는 것은 계산이 아니라 '전달'과 '빈/장애 상태의 구분'이다:
 *   1) 티켓이 0건인 것과 티켓을 못 읽은 것은 **다른 화면**이다.
 *   2) 없어진 안내(«Notion 연결»)가 되살아나지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1" } }),
}));

import { MyStats } from "./MyStats.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function stats(over = {}) {
  return {
    ok: true,
    source: { configured: true, ok: true, mapped: true },
    today: "2026-08-03",
    totals: {
      all: 6, active: 4, done: 1, cancelled: 1, overdue: 1, due_today: 1,
      due_soon: 0, blocked: 1, no_due: 1, completion_rate: 0.2,
    },
    workload: {
      est_wd_active: 6.5, est_wd_overdue: 2, act_wd_done: 2, est_wd_done: 1.5,
      by_status: [{ name: "진행", count: 3, est_wd: 3 }, { name: "완료", count: 1, est_wd: 1.5 }],
      by_priority: [{ name: "높음", count: 2, est_wd: 2 }],
      by_week: [
        { start: "2026-08-03", end_exclusive: "2026-08-10", label: "이번 주", count: 1, est_wd: 1 },
        { start: "2026-08-10", end_exclusive: "2026-08-17", label: "다음 주", count: 1, est_wd: 3 },
        { start: "2026-08-17", end_exclusive: "2026-08-24", label: "2주 뒤", count: 0, est_wd: 0 },
        { start: "2026-08-24", end_exclusive: "2026-08-31", label: "3주 뒤", count: 0, est_wd: 0 },
      ],
      by_week_extra: {
        overdue: { count: 1, est_wd: 2 },
        later: { count: 0, est_wd: 0 },
        no_due: { count: 1, est_wd: 0.5 },
      },
    },
    months: [
      { month: "2026-06", assigned: 0, done: 0, cancelled: 0, open: 0, overdue: 0, est_wd: 0, act_wd: 0, completion_rate: null },
      { month: "2026-07", assigned: 3, done: 1, cancelled: 1, open: 1, overdue: 1, est_wd: 4.5, act_wd: 2, completion_rate: 0.5 },
      { month: "2026-08", assigned: 3, done: 0, cancelled: 0, open: 3, overdue: 0, est_wd: 4, act_wd: 0, completion_rate: 0 },
    ],
    sync: { status: "ok", last_run_at: null, last_success_at: "2026-08-03T00:57:00", ticket_count: 8, truncated: false, error: null },
    ...over,
  };
}

function renderStats() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/my-stats"]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <MyStats />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("내 업무량 · 완료 통계", () => {
  it("서버가 준 숫자를 카드에 그대로 낸다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    expect(await screen.findByText("남은 일")).toBeInTheDocument();
    expect(screen.getByText("완료율(취소 제외)")).toBeInTheDocument();
    // 20% = 서버가 준 0.2. 화면이 다시 계산하지 않는다.
    expect(screen.getByText("20%")).toBeInTheDocument();
  });

  it("SEM-02: 단독 라우트라 PageHeader가 h1이고, 5개 구역 제목이 그 바로 아래 h2다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    await screen.findByText("남은 일");

    expect(screen.getByRole("heading", { level: 1, name: "내 업무량, 완료 통계" })).toBeInTheDocument();
    const level2Names = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    for (const title of ["달별 배정과 완료", "앞으로의 부하(주별)", "상태 구성", "남은 일의 우선순위", "공수(WD)"]) {
      expect(level2Names).toContain(title);
    }
    expect(level2Names).toHaveLength(5);
  });

  it("배정이 0건인 달의 완료율은 '-' 다 — 0% 가 아니다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    await screen.findByText("달별 배정과 완료");
    const row = screen.getByText("2026-06").closest("tr");
    expect(row).not.toBeNull();
    expect(row.textContent).toContain("-");
    // 같은 표에서 0% 인 달(2026-08)은 실제로 0% 로 나온다 — 둘이 구분된다.
    expect(screen.getByText("2026-08").closest("tr").textContent).toContain("0%");
  });

  it("티켓이 0건이면 '없다'고 말하고 갈 곳을 준다", async () => {
    apiMock.mockResolvedValue(stats({
      totals: { all: 0, active: 0, done: 0, cancelled: 0, overdue: 0, due_today: 0, due_soon: 0, blocked: 0, no_due: 0, completion_rate: null },
    }));
    renderStats();
    expect(await screen.findByText("아직 집계할 티켓이 없습니다")).toBeInTheDocument();
    expect(screen.getByText("내 티켓으로")).toBeInTheDocument();
  });

  /* 「연결이 없다」 갈래가 여기 셋 있었다 (S15). 그 상태는 없어졌다 — 사람마다 담당자로
   * 가리킬 값이 언제나 있다(D-285). 옛 응답 모양이 실려 와도 화면은 **없어진 절차를
   * 안내하지 않는다.** 남은 「모른다」는 티켓 읽기 실패 하나뿐이고, 그때 카드는 0 이 아니라
   * '-' 를 그린다(과거엔 totals.all===0 이 undefined 에서 거짓이라 아래 차트 분기로 빠져
   * load.by_week.map() 에서 죽었다). */
  it("옛 연결 안내가 되살아나지 않는다", async () => {
    apiMock.mockResolvedValue(stats({ source: { configured: true, ok: true, mapped: false } }));
    renderStats();
    await screen.findByText("남은 일");
    expect(screen.queryByText(/Notion/)).toBeNull();
  });

  it("티켓을 못 읽어 totals/workload/months가 아예 안 실려도 카드는 '-'를 그리고 안 죽는다", async () => {
    apiMock.mockResolvedValue({
      ok: true,
      source: { configured: true, ok: false, error: "티켓을 읽지 못했습니다." },
      today: "2026-08-03",
      sync: null,
    });
    renderStats();
    expect(await screen.findByText("티켓을 읽지 못했습니다.")).toBeInTheDocument();
    expect(screen.getByText("아직 집계할 티켓이 없습니다")).toBeInTheDocument();
    /* 판독 칸이 상태 칩으로 바뀌었다 — 재는 것은 그대로다: **0 이 아니라 「모른다」**를
       그리는가. 티켓을 못 읽으면 0건이 아니라 값 자체를 모르는 것이고, 그것을 0으로
       그리면 없는 사실을 만든다. */
    const remaining = screen.getAllByText("남은 일")[0].closest(".k-status-chip");
    expect(remaining).not.toBeNull();
    expect(remaining.textContent).toContain("-");
    // 「0건」으로 접히지 않는다 — 접기는 진짜 0 에게만 쓴다.
    expect(screen.queryByText(/0건$/)).toBeNull();
  });

  it("소스가 미설정이면 그 사실을 말한다", async () => {
    apiMock.mockResolvedValue(stats({
      source: { configured: false, ok: false, mapped: true, message: "Notion 연동이 설정되지 않았습니다." },
    }));
    renderStats();
    expect(await screen.findByText("Notion 연동이 설정되지 않았습니다.")).toBeInTheDocument();
  });

  it("조회 자체가 실패하면 다시 시도할 길을 준다", async () => {
    apiMock.mockRejectedValue(Object.assign(new Error("서버 오류"), { status: 500 }));
    renderStats();
    expect(await screen.findByText("불러오지 못했습니다")).toBeInTheDocument();
  });

  it("기간을 바꾸면 그 값으로 다시 조회한다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    await screen.findByText("남은 일");
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/me/stats?months=6&weeks=4"));

    /* 이 시험은 오래 기본값만 봤다 — 「바꾸면」이라고 적혀 있는데 아무것도 안 눌렀다.
       기간이 세그먼티드가 되면서 세 값이 다 화면에 서므로, 실제로 눌러서 잰다. */
    const period = screen.getByRole("tablist", { name: "기간" });
    expect(within(period).getAllByRole("tab")).toHaveLength(3);
    expect(within(period).getByRole("tab", { name: "최근 6개월" })).toHaveAttribute("aria-selected", "true");

    await userEvent.click(within(period).getByRole("tab", { name: "최근 12개월" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/me/stats?months=12&weeks=4"));
    expect(within(period).getByRole("tab", { name: "최근 12개월" })).toHaveAttribute("aria-selected", "true");
    // 카드 머리의 이름도 그 기간을 따라온다 — 숫자만 바뀌고 이름이 6개월로 남으면 거짓이다.
    expect(await screen.findByText("최근 12개월 내 티켓")).toBeInTheDocument();
  });

  /* 요약 카드가 **부분과 신호를 가른다.**
   *
   * 완료·남은 일·취소는 전체를 남김없이 나눈 부분이라 비율이 참이다. 지연·오늘 마감·
   * 막힌 일은 남은 일의 부분집합이면서 서로 겹치므로(한 티켓이 지연이면서 막힌 일일 수
   * 있다) 같은 바에 넣으면 합이 전체를 넘는다. */
  it("전체를 나누는 셋만 비율을 갖고, 겹치는 신호는 위험 요약으로 선다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    const card = await screen.findByRole("group", { name: "내 업무량" });

    // 부분 셋은 스택 바와 비율을 갖는다.
    expect(within(card).getByText("완료")).toBeInTheDocument();
    expect(card.querySelector("[data-ratio-bar]")).toBeInTheDocument();
    // 신호 셋은 같은 카드 안에 있되 비율을 안 갖는다(합이 전체를 넘기 때문이다).
    for (const name of ["지연", "오늘 마감", "막힌 일"]) {
      expect(within(card).queryAllByText(name).length, name).toBeGreaterThan(0);
    }
  });

  /* 선이 아니라 막대다 — 선은 점과 점 사이를 이어 「그 사이에도 값이 있었다」고 말한다. */
  it("배정이 없던 달은 0% 가 아니라 그 사실을 말한다", async () => {
    apiMock.mockResolvedValue(stats({
      months: [
        { month: "2026-06", assigned: 0, done: 0, cancelled: 0, open: 0, overdue: 0, est_wd: 0, act_wd: 0, completion_rate: null },
        { month: "2026-07", assigned: 4, done: 2, cancelled: 0, open: 2, overdue: 0, est_wd: 3, act_wd: 2, completion_rate: 0.5 },
      ],
    }));
    renderStats();
    await screen.findByText("달별 배정과 완료");
    /* 그림이 말하는 것은 **건수**다 — 완료율은 아래 표에 열이 하나 있고 요약 카드의 링이
       또 말한다. 셋째로 말하면 정보가 안 늘어난다(D-478). */
    const card = screen.getByText("달별 배정과 완료").closest('[data-surface="plate"]');
    expect(within(card).getByText("2건")).toBeInTheDocument();
    // 완료율은 여전히 그 카드의 표에 있다.
    expect(within(card).getByText("50%")).toBeInTheDocument();
    /* 배정이 없던 달은 «-» 다. 0 으로 적으면 막대 길이와 글자가 함께 「하나도 못 끝냈다」로
       읽히는데 사실은 「할 것이 없었다」다 — 막대로는 그 둘을 못 가르니 글자가 가른다.
       그림과 표가 같은 낱말을 쓴다: 화면 어디에도 「0%」가 없다. */
    expect(screen.queryByText("0%")).toBeNull();
    expect(screen.getAllByText("-").length).toBeGreaterThanOrEqual(2);
  });

  /* 앞으로의 부하 — **요약 한 줄이 먼저, 주별 목록은 접기 안**.
   *
   * 예전에는 여덟 줄이 그대로 서 있었고 전부 0건이어도 여덟 줄이었다. 이 카드가 답하는
   * 질문은 「어느 주에 몰려 있나」인데, 몰린 곳이 없으면 그 답은 한 줄이면 된다. */
  it("주별 목록은 접혀 있고 요약 한 줄이 먼저 답한다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    expect(await screen.findByText(/마감인 티켓이 .*건입니다/)).toBeInTheDocument();
    // 접혀 있으니 주 이름이 아직 없다.
    expect(screen.queryByText("이번 주")).toBeNull();
    expect(screen.getByRole("button", { name: "주별로 펴기" })).toBeInTheDocument();
  });

  it("펴면 주별 줄이 서고, 주가 아닌 둘은 구분선 아래로 내려간다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    await screen.findByText(/마감인 티켓이 .*건입니다/);
    await userEvent.click(screen.getByRole("button", { name: "주별로 펴기" }));

    expect(screen.getByText("이번 주")).toBeInTheDocument();
    /* 🔴 「지난 마감」은 이미 지난 일이고 「마감 없음」은 축 위에 자리가 없다 — 주와 나란히
       두면 시간축 위의 값처럼 읽힌다. 둘이 실선 아래의 다른 묶음에 있는지를 잰다. */
    const past = screen.getByText("지난 마감").closest("div").parentElement;
    expect(past).toContainElement(screen.getByText("마감 없음"));
    expect(past).not.toContainElement(screen.getByText("이번 주"));
    // 다시 누르면 접힌다.
    await userEvent.click(screen.getByRole("button", { name: "주별로 접기" }));
    expect(screen.queryByText("이번 주")).toBeNull();
  });

  /* 라벨은 **한 줄 고정 트랙**이다. 예전에는 주의 시작 날짜가 라벨 아래 자기 줄을 만들어
     넷 중 둘만 키가 커졌고, 그래서 막대들의 세로 리듬이 깨졌다. */
  it("주의 시작 날짜는 줄을 만들지 않고 툴팁으로 남는다", async () => {
    apiMock.mockResolvedValue(stats());
    renderStats();
    await screen.findByText(/마감인 티켓이 .*건입니다/);
    await userEvent.click(screen.getByRole("button", { name: "주별로 펴기" }));

    const label = screen.getByText("이번 주");
    expect(label).toHaveAttribute("title");
    expect(label.getAttribute("title")).toMatch(/시작$/);
    expect(getComputedStyle(label).whiteSpace).toBe("nowrap");
  });

  it("옛 sync 블록이 error 로 되돌아와도 미러 안내를 안 그린다", async () => {
    /* 예전에는 이 시험이 반대를 단언했다: 실패하면 "마지막 정상 데이터를 보고 있습니다"
       를 보여 준다. 서버가 sync 블록을 더 이상 안 싣는다 — 티켓 표가 이 서버의 정본이라
       낡을 것이 없다. 원인 문자열이 새지 않는다는 성질은 그대로 지킨다. */
    apiMock.mockResolvedValue(stats({
      sync: { status: "error", last_run_at: null, last_success_at: "2026-08-03T00:57:00", ticket_count: 8, truncated: false, error: "boom" },
    }));
    renderStats();
    await screen.findByText("남은 일");
    expect(screen.queryByText(/error/)).not.toBeInTheDocument();
    expect(screen.queryByText(/마지막 정상 데이터를 보고 있습니다/)).toBeNull();
    expect(screen.queryByText(/최근 동기화에 실패했습니다/)).toBeNull();
  });

  it("미러 상태 줄 자체가 이 화면에 없다 (지시 1)", async () => {
    apiMock.mockResolvedValue(stats({
      sync: { status: "ok", last_run_at: null, last_success_at: "2026-08-03T00:57:00", ticket_count: 8, truncated: false },
    }));
    renderStats();
    await screen.findByText("남은 일");
    expect(screen.queryByText(/미러 상태/)).toBeNull();
    expect(screen.queryByText(/마지막 동기화/)).toBeNull();
    expect(screen.queryByText(/아직 한 번도 동기화되지 않았습니다/)).toBeNull();
  });
});
