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
 *
 * ## 업무 판만 «예산» 이 아니라 «계약» 이다
 *
 * 판독 줄의 다섯 칸(오늘 마감·지연·진행 중·7일 내 마감·막힌 일)은 판 다섯이 아니라 **한
 * 판의 다섯 칸**이다. 예산(범위)으로 두면 칸마다 판이 다른 높이로 서고(실측 164~512px),
 * 누를 때마다 아래의 AI 도우미가 위아래로 뛴다. 그래서 그 판은 하나의 `height` 를 갖는다.
 * 여기서는 **그 계약이 값으로 성립하는지**와 **칸을 옮겨도 판이 같은 상자인지**를 잡고,
 * 실제 픽셀은 실브라우저 실측이 본다(1366 · 1920 · 2560).
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

/* 칸마다 건수가 **다른** 상태. 사용자가 지목한 전환 그대로다:
   오늘 마감 0 → 진행 중 30 → 7일 내 마감 1 → 막힌 일 0. 계약이 없으면 이 넷이 판을
   서로 다른 높이로 세운다. */
const MIXED = {
  ...TODAY_MANY,
  tickets: {
    configured: true, ok: true, mapped: true,
    due_today: { count: 0, items: [] },
    overdue: { count: 3, items: MANY.slice(0, 3) },
    in_progress: { count: 30, items: MANY },
    due_soon: { count: 1, items: MANY.slice(0, 1) },
    blocked: { count: 0, items: [] },
    done_total: 20,
  },
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

/** 이 요소가 **브라우저에서 실제로 받는** 데스크톱 규칙(`@media (min-width:1200px)`).
 *
 * sx 객체를 읽는 것으로는 부족하다 — 「값은 고쳤는데 화면이 받는 CSS 에는 안 들어간」
 * 실패가 이 저장소에서 실제로 있었다. emotion 이 내보낸 style 태그를 그대로 읽는다.
 * 모양은 실측했다: `@media (min-width:1200px){.css-x{height:32rem;min-height:32rem;…}}` */
function lgRule(el) {
  const css = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("");
  for (const cls of String(el.className).split(/\s+/).filter(Boolean)) {
    const head = "@media (min-width:1200px){." + cls + "{";
    const at = css.indexOf(head);
    if (at < 0) continue;
    return css.slice(at + head.length, css.indexOf("}", at + head.length));
  }
  return null;
}

/** 그 규칙이 선언한 높이 셋. 계약이면 셋이 같은 값이어야 한다. */
function heightsOf(rule) {
  const out = { height: null, min: null, max: null };
  for (const decl of String(rule || "").split(";")) {
    const at = decl.indexOf(":");
    const prop = decl.slice(0, at).trim();
    const value = decl.slice(at + 1).trim();
    if (prop === "height") out.height = value;
    else if (prop === "min-height") out.min = value;
    else if (prop === "max-height") out.max = value;
  }
  return out;
}

beforeEach(() => {
  apiMock.mockReset();
});

const rem = (v) => {
  expect(v, `rem 이 아니다: ${v}`).toMatch(/^\d+(\.\d+)?rem$/);
  return parseFloat(v);
};

describe("높이 예산 — 값", () => {
  it("판마다 위쪽 한계가 있다 — 예산이면 천장, 계약이면 그 높이", () => {
    for (const [name, budget] of Object.entries(PLATE_BUDGET)) {
      expect(budget.height || budget.max, `${name}: 위쪽 한계가 없다`).toBeTruthy();
      if (budget.height) {
        // 한 판이 계약과 범위를 함께 가지면 무엇이 이기는지 읽는 사람이 알 수 없다.
        expect(budget.min, `${name}: 계약과 바닥이 함께 있다`).toBeUndefined();
        expect(budget.max, `${name}: 계약과 천장이 함께 있다`).toBeUndefined();
        rem(budget.height);
      } else if (budget.min) {
        expect(rem(budget.min), `${name}: 바닥이 천장보다 높다`).toBeLessThan(rem(budget.max));
      }
    }
    expect(rem(AI_DETAIL_MAX)).toBeGreaterThan(0);
  });

  /* 이 시험이 지키는 것이 이번 계약의 전부다: 업무 판은 **범위가 아니라 한 높이**다.
     바닥만 남기면 30건에서 판이 자라고, 천장만 남기면 0건에서 판이 쪼그라든다. */
  it("업무 판은 하나의 높이다 — 계약·바닥·천장이 같은 값이다", () => {
    const h = PLATE_BUDGET.today.height;
    expect(h, "업무 판에 계약이 없다").toBeTruthy();
    const sx = plateBudget("today");
    expect(sx.height).toEqual({ lg: h });
    expect(sx.minHeight).toEqual({ lg: h });
    expect(sx.maxHeight).toEqual({ lg: h });
  });

  it("계약도 예산도 **넓은 화면에만** 건다 — 좁은 화면에서 판마다 상한을 주면 스크롤 축이 늘어난다", () => {
    for (const name of Object.keys(PLATE_BUDGET)) {
      const sx = plateBudget(name);
      for (const key of ["height", "minHeight", "maxHeight"]) {
        if (sx[key] === undefined) continue;
        expect(Object.keys(sx[key]), `${name}.${key}: 중단점이 lg 하나가 아니다`).toEqual(["lg"]);
      }
      // 판 자신이 세로 flex 라야 안쪽 칸이 «남는 높이» 를 받는다.
      expect(sx.display).toBe("flex");
      expect(sx.flexDirection).toBe("column");
    }
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

  /* 계약의 회귀는 대개 **판을 내용에 매다는** 모양으로 들어온다(`rows.length ? A : B`).
     jsdom 은 픽셀을 못 재지만 그 실수는 잡을 수 있다 — 판이 칸마다 다른 모양이면 emotion 이
     다른 규칙을 내보내고, 판이 다시 그려지면 요소 자체가 바뀐다. 둘 다 아님을 잡는다.
     실제 픽셀(1366·1920·2560 에서 다섯 칸의 판 높이와 AI 도우미 시작 Y)은 실브라우저가 잰다. */
  it("업무 판 — 다섯 칸을 오가도 같은 상자가 같은 높이 하나를 받는다", async () => {
    routeApi({ today: MIXED });
    renderHome();
    /* MIXED 는 「오늘 마감 0 · 지연 3」이라 화면이 **지연 칸으로 연다**(Home.jsx 의
       `defaultFocus`) — 빈 판으로 열지 않는다. 이 시험이 잡는 것은 어느 칸으로 여는가가
       아니라 «칸을 옮겨도 판이 같은 상자에 같은 높이로 서는가» 다. */
    await screen.findByRole("heading", { level: 2, name: /지연 3건/ });

    const card = plate("지연");
    const contract = heightsOf(lgRule(card));
    // 계약은 «범위» 가 아니다 — 셋이 같은 값이라야 0건과 30건이 같은 자리에 선다.
    expect(contract.height, "판이 데스크톱 높이 규칙을 안 받았다").toBeTruthy();
    expect(contract.min).toBe(contract.height);
    expect(contract.max).toBe(contract.height);

    const cells = Array.from(document.querySelectorAll("button.k-readout"));
    expect(cells).toHaveLength(5);

    for (const cell of cells) {
      const label = cell.textContent;
      await userEvent.click(cell);
      // 판을 제목이 아니라 **안에 있는 것으로** 다시 잡는다 — 제목은 칸마다 바뀐다.
      const after = screen.getByRole("link", { name: "내 티켓 전체" }).closest('[data-surface="plate"]');
      expect(after, `${label}: 판이 다시 만들어졌다`).toBe(card);
      expect(heightsOf(lgRule(after)), `${label}: 판의 높이 계약이 달라졌다`).toEqual(contract);
    }

    // 0건 칸에서는 굴릴 칸을 안 만들고, 30건 칸에서는 목록만 굴린다 — 판은 그대로다.
    await userEvent.click(cells[0]);
    await screen.findByText("오늘 마감에 해당하는 티켓이 없습니다");
    expect(areasIn(card)).toHaveLength(0);
    await userEvent.click(cells[2]);
    await screen.findByRole("heading", { level: 2, name: /진행 중 30건/ });
    expect(areasIn(card)).toHaveLength(1);
    expect(insideArea(card.querySelector("table"))).toBe(true);
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
