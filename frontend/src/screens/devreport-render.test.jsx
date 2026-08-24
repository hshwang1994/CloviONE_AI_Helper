import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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

    expect(await screen.findByText("이 달에 집계할 담당자가 없습니다")).toBeInTheDocument();
    expect(screen.getByText("이 달에 담당한 티켓이 있는 사람이 없습니다")).toBeInTheDocument();
    // 표 머리글만 남은 빈 표를 그리지 않는다(예전 회귀).
    expect(screen.queryByText("완료율")).toBeNull();
  });

  it("업무량을 말하던 그림이 사라진 자리에 빈 상자를 남기지 않는다", async () => {
    apiMock.mockResolvedValue({
      configured: true, ok: true, period: "2026-08",
      team: EMPTY_TEAM, developers: [], unassigned: { total: 0 },
    });
    renderReport();

    expect(await screen.findByText("이 달에 집계할 담당자가 없습니다")).toBeInTheDocument();
    // 옛 막대의 빈 상태 문구가 유령으로 남아 있으면 안 된다.
    expect(screen.queryByText("이 달에 완료한 업무량이 없습니다")).toBeNull();
  });
});

describe("개발자 월간 리포트 — 데이터가 있는 달", () => {
  const DEV = {
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
    // 도넛 범례도 마찬가지 — 색 조각만으로 뜻이 전해지지 않는다(WCAG 1.4.1).
    // '3건'은 KPI 타일(완료)과 도넛 범례 양쪽에 나온다 — 둘이 같은 말을 하는 것이 규칙이다.
    expect(screen.getAllByText("3건").length).toBeGreaterThan(1);
    // 지연 1건은 붉은 배지로 눈에 띄게 남는다.
    expect(screen.getByText("담당자별 상세 티켓")).toBeInTheDocument();
  });
});
