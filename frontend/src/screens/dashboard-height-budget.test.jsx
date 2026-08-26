import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 대시보드 판의 **높이 예산** — 자라는 것은 판이 아니라 판 안의 한 칸이다.
 *
 * ## 이 시험이 막는 실패
 *
 * 실측(2026-08-26 · 1920)에서 홈의 판들이 자료 수를 그대로 따라 자랐다:
 * 「오늘 마감」이 2건 272px · 30건 440px · **0건 451px**, AI 도우미가 444px 에서
 * **1,318px**(문장 요약 1,200자). 한 화면 안에서 같은 판이 세 배가 되면 그 아래에 오는
 * 것들의 자리가 매번 달라진다.
 *
 * 고친 구조는 한 줄이다: **머리와 꼬리는 굴리지 않고, 자라는 칸만 굴린다.**
 * 그래서 이 시험은 높이(px)가 아니라 **무엇이 스크롤 칸 안에 있고 무엇이 밖에 있는가**를
 * 고정한다 — jsdom 에는 레이아웃이 없어서 px 은 잴 수 없고, px 을 적어 두면 값을 고칠
 * 때마다 시험이 함께 틀린다. 실제 높이는 실브라우저 실측이 본다.
 *
 * 「밖에 있어야 하는 것」이 이 계약의 전부다:
 *   오늘 마감   제목 · 「내 티켓 전체」 · 「N건만 표시했습니다」
 *   AI 도우미   탭 · 결론 한 문장(핵심 요약) · 아래 버튼 줄
 *   이번 주     제목 · 스프린트 진척(도넛과 그 문장)
 *   최근 문서   제목 · 「문서 전체」
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u-1" } }) }));

import { Home } from "./Home.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { AI_DETAIL_MAX, PLATE_BUDGET, plateBudget } from "../ui/density.js";

const TODAY = "2026-08-26";

function ticket(n) {
  return {
    id: "p" + n, tid: n, title: `티켓 ${n} — 화면에서 읽히는 제목`, status: "진행",
    due: TODAY, est_wd: 1, priority: "Normal", difficulty: "중", project: "",
    assignee_names: [], assignee_user_ids: [], project_names: [],
  };
}

/* 서버 상한(12줄)까지 실은 «다량» 응답. `count` 는 진짜 총계라 화면이 잘랐다고 말한다. */
const MANY = Array.from({ length: 12 }, (_, i) => ticket(i + 1));

const TODAY_MANY = {
  ok: true,
  today: TODAY,
  tickets: {
    configured: true, ok: true, mapped: true,
    due_today: { count: 30, items: MANY },
    overdue: { count: 18, items: MANY },
    in_progress: { count: 62, items: MANY },
    due_soon: { count: 14, items: MANY },
    blocked: { count: 4, items: MANY.slice(0, 4) },
    done_total: 20,
  },
  sprint: {
    window: { start: "2026-08-24", end_exclusive: "2026-08-31" },
    assigned: 50, done: 6, remaining: 44, cancelled: 0, overdue: 4,
    completion_rate: 12, est_wd_total: 75, est_wd_done: 9,
  },
  inbox: { notifications_unread: 6, chat_unread: 12 },
  recent: {
    documents: Array.from({ length: 12 }, (_, i) => ({
      id: "d" + i, title: `문서 ${i + 1} — 회의록`, document_type: "회의록",
      owner: "동료", last_edited: "2026-08-26T01:00:00Z",
    })),
    board: [],
  },
  sync: { status: "ok", last_run_at: null, last_success_at: null, ticket_count: 150, truncated: false, error: null },
};

/* 「이번 주」 곁열의 세부. 프로젝트 축과 최근 완료 추이가 여기서 온다. */
const WORK = {
  projects: { troubled: { count: 3, items: [] }, unscored: 2, low_confidence: 1, truncated: false },
  milestones: { overdue: { count: 5, items: [] } },
  completion_trend: [
    { week_of: "2026-08-03", assigned: 9, done: 9 },
    { week_of: "2026-08-10", assigned: 9, done: 9 },
    { week_of: "2026-08-17", assigned: 23, done: 9 },
    { week_of: "2026-08-24", assigned: 50, done: 6 },
  ],
};

/* 러너가 낼 수 있는 **가장 긴** 문장 요약. 상한은 서버가 자른다
   (`app/assistant/narrate.py::MAX_TEXT_CHARS` = 1200). */
const LONG_NARRATIVE = "지연된 티켓을 먼저 닫고 오늘 마감인 일을 그 다음에 봅니다. ".repeat(40).slice(0, 1200);

function routeApi(over = {}) {
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/home/today")) return Promise.resolve(over.today || TODAY_MANY);
    if (path.startsWith("/api/home/work-dashboard")) return Promise.resolve(WORK);
    if (path.startsWith("/api/assistant/")) {
      return Promise.resolve({
        kind: "briefing", today: TODAY,
        tickets: (over.today || TODAY_MANY).tickets,
        sprint: (over.today || TODAY_MANY).sprint,
        narrative: over.narrative || null,
      });
    }
    return Promise.resolve({});
  });
}

function renderHome() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Home />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/** 이름으로 판 하나를 집는다. 제목(h2)이 그 판의 이름이다. */
function plate(startsWith) {
  const heads = screen.getAllByRole("heading", { level: 2 });
  const head = heads.find((h) => h.textContent.trim().startsWith(startsWith));
  expect(head, `판을 못 찾았다: ${startsWith}`).toBeTruthy();
  return head.closest('[data-surface="plate"]');
}

/** 그 판 안의 스크롤 칸들. */
const areasIn = (el) => Array.from(el.querySelectorAll(".k-scrollarea"));

/** 이 요소가 어떤 스크롤 칸 안에 있는가. */
const insideArea = (el) => !!(el && el.closest(".k-scrollarea"));

beforeEach(() => {
  apiMock.mockReset();
});

describe("높이 예산 — 값", () => {
  it("모든 판이 천장을 갖는다. 바닥은 있으면 천장보다 낮다", () => {
    const rem = (v) => {
      expect(v, `rem 이 아니다: ${v}`).toMatch(/^\d+(\.\d+)?rem$/);
      return parseFloat(v);
    };
    for (const [name, budget] of Object.entries(PLATE_BUDGET)) {
      expect(budget.max, `${name}: 천장이 없다`).toBeTruthy();
      const max = rem(budget.max);
      if (budget.min) expect(rem(budget.min), `${name}: 바닥이 천장보다 높다`).toBeLessThan(max);
    }
    expect(rem(AI_DETAIL_MAX)).toBeGreaterThan(0);
  });

  it("예산은 **넓은 화면에만** 건다 — 좁은 화면에서 판마다 상한을 주면 스크롤 축이 늘어난다", () => {
    const sx = plateBudget("today");
    expect(sx.minHeight).toEqual({ lg: PLATE_BUDGET.today.min });
    expect(sx.maxHeight).toEqual({ lg: PLATE_BUDGET.today.max });
    // 판 자신이 세로 flex 라야 안쪽 칸이 «남는 높이» 를 받는다.
    expect(sx.display).toBe("flex");
    expect(sx.flexDirection).toBe("column");
  });

  it("바닥이 없는 판은 바닥을 안 만든다 — 세 줄짜리 목록 아래를 비우지 않는다", () => {
    expect(plateBudget("docs").minHeight).toBeUndefined();
    expect(plateBudget("week").minHeight).toBeUndefined();
  });

  it("예산에 없는 이름을 부르면 조용히 넘어가지 않는다", () => {
    expect(() => plateBudget("없는판")).toThrow(/없는판/);
  });
});

describe("높이 예산 — 무엇이 굴러가고 무엇이 안 굴러가는가", () => {
  it("「오늘 마감」 — 표만 굴리고 제목·「내 티켓 전체」·「잘랐다」는 밖에 남는다", async () => {
    routeApi();
    renderHome();
    await screen.findByRole("heading", { level: 2, name: /오늘 마감 30건/ });

    const card = plate("오늘 마감");
    const areas = areasIn(card);
    expect(areas).toHaveLength(1);

    // 표는 안에 있다.
    expect(insideArea(card.querySelector("table"))).toBe(true);
    // 제목과 전체 보기 링크, 그리고 잘랐다는 안내는 밖에 있다.
    expect(insideArea(screen.getByRole("heading", { level: 2, name: /오늘 마감 30건/ }))).toBe(false);
    const all = screen.getByRole("link", { name: "내 티켓 전체" });
    expect(insideArea(all)).toBe(false);
    const note = screen.getByText(/12건만 표시했습니다/);
    expect(insideArea(note)).toBe(false);
  });

  it("「오늘 마감」 0건 — 굴릴 칸을 안 만들고 판을 채우는 빈 상태가 선다", async () => {
    const empty = {
      ...TODAY_MANY,
      tickets: {
        configured: true, ok: true, mapped: true,
        due_today: { count: 0, items: [] }, overdue: { count: 0, items: [] },
        in_progress: { count: 0, items: [] }, due_soon: { count: 0, items: [] },
        blocked: { count: 0, items: [] }, done_total: 0,
      },
    };
    routeApi({ today: empty });
    renderHome();
    await screen.findByText("담당한 티켓이 없습니다");

    const card = plate("오늘 마감");
    expect(areasIn(card)).toHaveLength(0);
    // 판 하나가 통째로 빈 자리라 «가운데» 구성이다 — 판의 높이를 채운다.
    expect(card.querySelector(".k-empty").dataset.emptyLayout).toBe("card");
  });

  it("AI 도우미 — 결론 문장과 버튼 줄은 밖에, 목록·그림·문장 요약은 안에", async () => {
    routeApi({ narrative: { enabled: true, text: LONG_NARRATIVE, error: null } });
    renderHome();
    await screen.findByRole("heading", { level: 2, name: "AI 도우미" });
    await screen.findByText(/오늘 가장 급합니다|지금 맡고 있는 티켓이 없습니다|막힌 티켓/);

    const card = plate("AI 도우미");
    const areas = areasIn(card);
    expect(areas).toHaveLength(1);

    // 결론 한 문장(핵심 요약)은 굴리지 않는다.
    const lede = screen.getByText(/오늘 가장 급합니다|지금 맡고 있는 티켓이 없습니다|막힌 티켓/);
    expect(insideArea(lede)).toBe(false);
    // 탭도 밖이다.
    expect(insideArea(screen.getByRole("tab", { name: "오늘 요약" }))).toBe(false);
    // 아래 버튼 줄도 밖이다.
    expect(insideArea(screen.getByRole("button", { name: /문장 요약 만들기/ }))).toBe(false);
    // 길어지는 것은 전부 안이다.
    expect(insideArea(screen.getByText("지금 볼 것"))).toBe(true);
    expect(insideArea(screen.getByText(LONG_NARRATIVE))).toBe(true);
  });

  it("AI 도우미 — 탭을 옮겨도 같은 계약이다(칸은 언제나 하나)", async () => {
    routeApi();
    renderHome();
    await screen.findByRole("heading", { level: 2, name: "AI 도우미" });
    await userEvent.click(screen.getByRole("tab", { name: "이번 주 요약" }));
    await waitFor(() => expect(areasIn(plate("AI 도우미"))).toHaveLength(1));
  });

  it("「이번 주」 — 도넛과 그 문장은 밖에, 프로젝트와 최근 완료 추이는 안에", async () => {
    routeApi();
    renderHome();
    await screen.findByText("최근 완료 추이");

    const card = plate("이번 주");
    expect(areasIn(card)).toHaveLength(1);
    expect(insideArea(screen.getByText(/내 티켓 50건 중 6건 완료/))).toBe(false);
    expect(insideArea(screen.getByText("프로젝트"))).toBe(true);
    expect(insideArea(screen.getByText("최근 완료 추이"))).toBe(true);
  });

  it("「최근 문서」 — 목록만 굴리고 「문서 전체」는 밖에 남는다", async () => {
    routeApi();
    renderHome();
    await screen.findByRole("heading", { level: 2, name: "최근 문서" });

    const card = plate("최근 문서");
    expect(areasIn(card)).toHaveLength(1);
    expect(insideArea(screen.getByRole("link", { name: "문서 전체" }))).toBe(false);
    expect(insideArea(screen.getByRole("link", { name: /문서 1 — 회의록/ }))).toBe(true);
  });

  it("한 판에 스크롤 축이 둘이 되지 않는다", async () => {
    routeApi({ narrative: { enabled: true, text: LONG_NARRATIVE, error: null } });
    renderHome();
    await screen.findByRole("heading", { level: 2, name: "AI 도우미" });
    for (const name of ["오늘 마감", "AI 도우미", "이번 주", "최근 문서"]) {
      const card = plate(name);
      expect(areasIn(card).length, `${name}: 스크롤 칸이 여럿이다`).toBeLessThanOrEqual(1);
      // 칸 안에 또 칸이 있으면 굴리는 사람이 무엇을 굴리는지 모른다.
      for (const area of areasIn(card)) {
        expect(area.querySelectorAll(".k-scrollarea")).toHaveLength(0);
      }
    }
  });
});
