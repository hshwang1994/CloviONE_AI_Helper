import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* DataScreen 계약 테스트.
 *
 * 이 컴포넌트 하나가 관리자 화면 16개를 그린다. 그런데 지금까지 테스트가 한 줄도 없었다 —
 * 재설계로 마크업을 갈아엎기 전에 '무엇이 지켜져야 하는지'를 먼저 못 박는다.
 *
 * 여기서 보는 네 가지는 전부 과거에 실제로 틀렸거나, 틀리면 조용히 잘못 동작하는 것들이다:
 *   1) 필터가 서버로 갈 때의 형태 — 특히 datetime-local은 시간대가 없어서 KST(+09:00)를 붙여야 한다.
 *      안 붙이면 백엔드가 UTC로 읽어 9시간 어긋난 범위를 조회한다(화면엔 아무 오류도 안 뜬다).
 *   2) 페이지 이동 중 목록이 통째로 사라지지 않는다(placeholderData) — 예전엔 클릭마다 스켈레톤으로 깜빡였다.
 *   3) 액션 하나를 눌렀을 때 그 버튼만 '처리 중…'이 된다 — 예전엔 단일 boolean이라 화면의 모든
 *      버튼이 같이 처리 중으로 보였다.
 *   4) 401은 재시도해도 401이다 — 일반 오류 토스트로 뭉개면 사용자가 이유도 모른 채 막힌다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { resetSessionRedirect } from "../lib/sessionRedirect.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderScreen(config) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={config} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const BASE_CONFIG = {
  key: "audit",
  area: "운영",
  title: "감사 로그",
  endpoint: "/api/admin/audit",
  columns: [{ key: "action", label: "동작" }, { key: "actor", label: "수행자" }],
};

beforeEach(() => {
  apiMock.mockReset();
  // DataScreen은 딥링크(#/audit?action=...) 지원을 위해 마운트 시 window.location.hash를
  // **MemoryRouter를 거치지 않고 직접** 읽는다(DataScreen.jsx:50). 어느 시험이든 실제
  // hash를 남기면 다음 시험이 그 값을 "초기 필터"로 그대로 물려받는다 - 실제로 재현된
  // 순서 의존 실패였다(SEM-02 새 시험 추가 중 발견). 시험마다 깨끗하게 시작한다.
  window.location.hash = "";
});

describe("필터가 서버로 가는 형태", () => {
  it("datetime-local 필터에 KST(+09:00)를 붙여 보낸다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      filters: [{ key: "from", label: "시작", type: "datetime-local" }],
    });
    await waitFor(() => expect(apiMock).toHaveBeenCalled());

    const input = screen.getByLabelText("시작");
    await user.type(input, "2026-08-03T09:30");

    await waitFor(() => {
      const urls = apiMock.mock.calls.map((c) => c[0]);
      expect(urls.some((u) => u.includes(encodeURIComponent("2026-08-03T09:30:00+09:00")))).toBe(true);
    });
  });

  it("빈 필터 값은 쿼리에 넣지 않는다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    renderScreen({
      ...BASE_CONFIG,
      filters: [{ key: "actor", label: "수행자", type: "text" }],
    });
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    // 목록 호출만 본다 — 이 화면은 저장된 뷰 목록(/api/me/views)도 함께 받아오므로
    // '첫 번째 호출 = 목록'이라고 가정하면 무관한 변경에 깨진다.
    const listCalls = apiMock.mock.calls
      .map((c) => c[0])
      .filter((p) => p.startsWith("/api/admin/audit"));
    expect(listCalls).toEqual(["/api/admin/audit"]);
  });

  /* qa-contract-change: S16 이 R-91 의 열 수축 규칙을 배선했다 — 사용자가 그 축을 **직접**
   * 건 결과 값이 전부 같아진 열은 표가 숨기고 그 사실을 한 번 적는다. 그래서 「login 이라는
   * 글자가 셀에 있다」는 확인은 대상을 잃었다. 약화가 아니라 대상 이동이고, 단언을 하나 더
   * 더한다: 남은 행이 그대로 있다는 것과, 사라진 열을 화면이 말한다는 것 둘 다 본다. */
  it("clientFilter 필터는 서버로 보내지 않고 화면에서 거른다", async () => {
    apiMock.mockResolvedValue({
      items: [{ id: "1", action: "login", actor: "a" }, { id: "2", action: "logout", actor: "b" }],
      total: 2,
    });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      filters: [{ key: "action", label: "동작", type: "select", clientFilter: true, options: [{ value: "login", label: "로그인" }] }],
    });
    await screen.findByText("login");
    const callsBefore = apiMock.mock.calls.length;

    await user.click(screen.getByLabelText("동작"));
    await user.click(await screen.findByRole("option", { name: "로그인" }));

    // 서버 재조회 없이 화면에서만 걸러진다.
    await waitFor(() => expect(screen.queryByText("logout")).toBeNull());
    // 남은 행은 그대로 있다 — 행의 정체는 «동작» 이 아니라 행위자로 확인한다(아래 주석 참고).
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(apiMock.mock.calls.length).toBe(callsBefore);
    // S16 이 더한 것: 사용자가 그 축을 직접 걸어 값이 전부 같아진 열은 사라지고, 사라졌다는
    // 사실과 그 값을 표가 한 번 말한다(R-91). 조건을 풀면 열이 돌아온다.
    expect(screen.getByText(/동작은 이 목록에서 전부 'login'/)).toBeInTheDocument();
  });
});

describe("페이지네이션", () => {
  const paged = { ...BASE_CONFIG, paginated: true, pageSize: 2 };

  it("다음/이전으로 page 파라미터가 바뀌고, 이동 중에도 목록이 비지 않는다", async () => {
    apiMock.mockImplementation((url) => {
      const page = /page=(\d+)/.exec(url);
      const n = page ? Number(page[1]) : 1;
      return Promise.resolve({
        items: [{ id: `p${n}`, action: `동작-${n}`, actor: "a" }],
        total: 4, page_size: 2,
      });
    });
    const user = userEvent.setup();
    renderScreen(paged);
    await screen.findByText("동작-1");

    // VIS-117: totalPages(4/2=2) > 1이라 목록 위·아래에 페이저가 하나씩(총 2벌) 뜬다 —
    // 둘 다 같은 page 상태를 공유하므로 아무 쪽이나 눌러도 동작은 같다.
    await user.click(screen.getAllByRole("button", { name: "다음" })[0]);
    // 새 페이지가 오기 전에도 이전 결과가 남아 있어야 한다(placeholderData).
    // getAllByText로 센다 — 전환 순간에는 옛 행과 새 행이 잠깐 함께 있을 수 있고,
    // getByText는 그때 '여러 개 찾음'으로 던져서 테스트가 간헐적으로 실패했다.
    expect(screen.getAllByText(/동작-/).length).toBeGreaterThan(0);
    await screen.findByText("동작-2");
    expect(apiMock.mock.calls.some((c) => String(c[0]).includes("page=2"))).toBe(true);

    await user.click(screen.getAllByRole("button", { name: "이전" })[0]);
    await screen.findByText("동작-1");
  });

  it("페이지가 2쪽 이상이면 목록 위에도 같은 이동 버튼을 하나 더 둔다(VIS-117)", async () => {
    apiMock.mockResolvedValue({
      items: [{ id: "p1", action: "동작-1", actor: "a" }], total: 4, page_size: 2,
    });
    renderScreen(paged);
    await screen.findByText("동작-1");
    // 아래 페이저 하나뿐이던 화면에 위쪽 페이저(nav aria-label이 다르다)가 새로 생겼는지 직접 본다 —
    // 버튼 개수만 세면 우연히 둘 다 사라져도(둘 다 0) 통과할 수 있어 landmark로 확실히 짚는다.
    expect(screen.getByRole("navigation", { name: "페이지 이동(목록 위)" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "다음" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "이전" })).toHaveLength(2);
  });

  it("1쪽뿐이면 위쪽 페이저를 얹지 않는다(안 쓰는 컨트롤을 보여주지 않는다)", async () => {
    apiMock.mockResolvedValue({
      items: [{ id: "p1", action: "동작-1", actor: "a" }], total: 1, page_size: 2,
    });
    renderScreen(paged);
    await screen.findByText("동작-1");
    expect(screen.queryByRole("navigation", { name: "페이지 이동(목록 위)" })).toBeNull();
    expect(screen.getAllByRole("button", { name: "다음" })).toHaveLength(1);
  });

  it("마지막 페이지가 사라지면 페이지 번호만 유효한 값으로 되돌린다", async () => {
    let total = 4;
    apiMock.mockImplementation((url) => {
      const m = /page=(\d+)/.exec(url);
      const n = m ? Number(m[1]) : 1;
      const items = n * 2 <= total ? [{ id: `p${n}`, action: `동작-${n}`, actor: "a" }] : [];
      return Promise.resolve({ items, total, page_size: 2 });
    });
    const user = userEvent.setup();
    renderScreen(paged);
    await screen.findByText("동작-1");
    await user.click(screen.getAllByRole("button", { name: "다음" })[0]);
    await screen.findByText("동작-2");

    total = 2; // 마지막 페이지의 항목이 사라진 상황 — totalPages도 1로 줄어 위 페이저는 사라진다.
    await waitFor(() => {
      for (const btn of screen.getAllByRole("button", { name: "다음" })) expect(btn).toBeDisabled();
    });
  });
});

describe("액션 진행 표시는 누른 버튼에만", () => {
  it("헤더 작업 하나를 눌러도 다른 버튼이 '처리 중…'이 되지 않는다", async () => {
    let resolveAction;
    apiMock.mockImplementation((url, opts) => {
      if (opts && opts.method === "POST") return new Promise((r) => { resolveAction = r; });
      return Promise.resolve({ items: [{ id: "1", action: "login", actor: "a" }], total: 1 });
    });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      headerActions: [
        { label: "내보내기", path: () => "/api/admin/audit/export" },
        { label: "정리", path: () => "/api/admin/audit/purge" },
      ],
    });
    await screen.findByText("login");

    await user.click(screen.getByRole("button", { name: "내보내기" }));

    /* 진행 표시는 **누른 버튼에만** 붙는다. 예전에는 라벨을 "처리 중…"으로 바꿔치기해서
       확인했는데, 그 관행 자체가 kit 이 금지한 것이다(누른 것이 무엇이었는지 화면에서
       사라진다 — Button 의 `loading` prop 주석). 지금은 라벨이 그대로 있고 그 위에 진행
       표시가 얹힌다. 나머지는 비활성화되되 진행 표시는 없다. */
    const pressed = await screen.findByRole("button", { name: "내보내기" });
    // 상태는 `aria-busy` 로 알린다 — 회전 표시 자체는 `aria-hidden` 이라 낭독 대상이 아니다.
    await waitFor(() => expect(pressed).toHaveAttribute("aria-busy", "true"));
    const other = screen.getByRole("button", { name: "정리" });
    expect(other).toBeDisabled();
    expect(other).not.toHaveAttribute("aria-busy", "true");
    const busy = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-busy") === "true");
    expect(busy).toHaveLength(1);

    resolveAction({ ok: true });
  });
});

/* 세션 만료(401)는 **공통 계층**이 처리한다 (지시 19).
 *
 * 예전에는 이 화면이 스스로 `window.location.href = "/login"` 을 했다 — 되돌아올 곳도,
 * 만료였다는 사실도 싣지 않았고, 같은 순간 다른 화면이 또 이동을 예약하면 서로 덮어썼다.
 * 지금은 `lib/sessionRedirect.js` 한 곳이 그 주소를 만든다. 그래서 여기서 재는 것은
 * "어디로 갔는가"가 아니라 **"그 공통 계층을 탔는가, 되돌아올 곳을 실었는가"** 다. */
describe("세션 만료(401)", () => {
  let originalLocation;
  let replaced;
  beforeEach(() => {
    replaced = [];
    originalLocation = window.location;
    delete window.location;
    window.location = {
      ...originalLocation, href: "", hash: "", pathname: "/", search: "",
      replace: (u) => replaced.push(u),
    };
    resetSessionRedirect();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    window.location = originalLocation;
    resetSessionRedirect();
  });

  it("액션이 401이면 안내 후 로그인 화면으로 보낸다 — 일반 오류로 뭉개지 않는다", async () => {
    apiMock.mockImplementation((url, opts) => {
      if (opts && opts.method === "POST") {
        const e = new Error("세션이 만료되었습니다");
        e.status = 401;
        return Promise.reject(e);
      }
      return Promise.resolve({ items: [{ id: "1", action: "login", actor: "a" }], total: 1 });
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderScreen({
      ...BASE_CONFIG,
      headerActions: [{ label: "정리", path: () => "/api/admin/audit/purge" }],
    });
    await screen.findByText("login");

    await user.click(screen.getByRole("button", { name: "정리" }));
    expect(await screen.findByText(/로그인이 필요합니다/)).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(1500);
    expect(replaced).toHaveLength(1);
    const url = new URL(replaced[0], "https://example.test");
    expect(url.pathname).toBe("/login");
    // 재로그인 뒤 보던 화면으로 돌아온다 — 예전에는 맨 `/login` 이라 서버가 `/` 로 떨어뜨렸다.
    expect(url.searchParams.get("next")).toBeTruthy();
    expect(url.searchParams.get("expired")).toBe("1");
  });
});

describe("빈 상태는 '데이터 없음'과 '검색 결과 없음'을 구분한다", () => {
  it("필터가 걸려 있으면 지우기 CTA가 있는 검색 결과 없음", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      searchable: true,
      emptyTitle: "감사 로그가 없습니다",
    });
    // 필터 없을 때는 온보딩 성격의 빈 상태
    expect(await screen.findByRole("heading", { name: "감사 로그가 없습니다" })).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox"), "없는값");
    expect(await screen.findByRole("heading", { name: "검색 결과가 없습니다" })).toBeInTheDocument();
    // 빈 상태 안의 CTA. 툴바에도 '필터 지우기'가 함께 떠 있으므로 이름을 정확히 지정한다.
    expect(screen.getByRole("button", { name: "검색, 필터 지우기" })).toBeInTheDocument();
  });
});

describe("요약 줄 — 카드 수와 무관하게 빈 칸이 안 생긴다 (VIS-119/137/151)", () => {
  /* 예전 고정 `repeat(4,...)`는 카드 수가 4의 배수가 아니면 마지막 줄에 빈 칸을 남겼다
     (jobs 6장 → 4+2, notifications 1장 → 3칸 빔). 그 다음 해법이 auto-fit 격자였고,
     지금은 격자 자체가 없다 — 요약은 판 하나를 여럿이 나눠 쓰는 판독 줄
     (kit.jsx::MetricStrip)이다. 칸이 아니라 flex 이므로 남는 폭을 항목들이 나눠 갖고,
     "마지막 줄 빈 칸"이라는 결함이 구조적으로 생길 수 없다.

     검사 대상도 트랙 문자열이 아니라 그 구조다: 요약 항목이 **판 하나 안에** 모여 있고,
     그 줄이 접힐 수 있는가(flex-wrap). */
  const LABELS = ["대기", "실행 중", "실행 가능(ready)", "실패", "완료", "취소됨"];

  it("summary.cards가 6장이어도(4의 배수가 아님) 판 하나를 나눠 쓴다", async () => {
    apiMock.mockImplementation((url) => {
      if (String(url).includes("/summary")) {
        return Promise.resolve({ queued: 1, running: 2, ready: 1, failed: 0, succeeded: 10, cancelled: 0 });
      }
      return Promise.resolve({ items: [], total: 0 });
    });
    renderScreen({
      ...BASE_CONFIG,
      summary: {
        endpoint: "/api/admin/jobs/summary",
        cards: (s) => [
          { value: s.queued, label: "대기" }, { value: s.running, label: "실행 중" },
          { value: s.ready, label: "실행 가능(ready)" }, { value: s.failed, label: "실패" },
          { value: s.succeeded, label: "완료" }, { value: s.cancelled, label: "취소됨" },
        ],
      },
    });
    await screen.findByText("실행 가능(ready)");

    const strips = document.querySelectorAll(".k-metrics");
    expect(strips, "요약 줄이 하나여야 한다").toHaveLength(1);
    for (const label of LABELS) {
      expect(within(strips[0]).getByText(label), label).toBeInTheDocument();
    }
    // 줄은 접힌다 — 좁아지면 다음 줄로 내려간다. W4 에서 판을 벗기면서 `.k-metrics` 자체가
    // flex 컨테이너가 됐다(예전에는 그 안의 첫 자식이었다).
    expect(getComputedStyle(strips[0]).flexWrap).toBe("wrap");
    // W4 — **판독 한 줄에 plate 금지**(PLAN «Surface 위계» 하드 금지). 요약 줄은 판을
    // 갖지 않는다: 자기 배경도, 테두리도 없다. 예전에는 `<Card>` 였고 그래서 canvas ->
    // plate -> inset 세 톤이 한 줄에 겹쳤다(F-W1R-16).
    expect(strips[0].className, "판(MuiCard/MuiPaper)이 남아 있으면 안 된다")
      .not.toMatch(/MuiCard|MuiPaper/);
    const stripStyle = getComputedStyle(strips[0]);
    expect(stripStyle.backgroundColor === "" || stripStyle.backgroundColor === "rgba(0, 0, 0, 0)").toBe(true);
    expect(Number.parseFloat(stripStyle.borderTopWidth || "0")).toBe(0);
    // 칸 사이 실선은 **실제로 그려지는 형태**여야 한다 — `borderInlineStart: 1` 은 MUI 가
    // 펴 주지 않아 style 없는 무효 선언이 된다(F-W2R-01, 배포본에서 구분선 픽셀 0개였다).
    const cells = strips[0].querySelectorAll(".k-readout");
    expect(cells.length).toBe(LABELS.length);
    const second = getComputedStyle(cells[1]);
    expect(second.borderInlineStartStyle).toBe("solid");
    expect(second.borderInlineStartWidth).toBe("1px");
  });

  it("unreadCountKey가 항목 1개뿐이어도 같은 판독 줄을 쓴다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0, unread_count: 3 });
    renderScreen({ ...BASE_CONFIG, unreadCountKey: "unread_count" });
    const label = await screen.findByText("안 읽음");

    const plate = label.closest(".k-metrics");
    expect(plate, "판독 줄 안에 있어야 한다").not.toBeNull();
    expect(within(plate).getByText("3")).toBeInTheDocument();
  });
});

describe("제목 계층 — 필터·목록 구획 (SEM-02, PA-F-031)", () => {
  // 빈 목록으로 재면 EmptyState 자신의 제목도 h2(role=heading aria-level=2, kit.jsx)라 셋이
  // 섞인다 - 그건 별개의 기존 규약이라, 행이 있는 상태로 필터/목록 h2 둘만 본다.
  it("h1 하나뿐이던 화면에 필터·목록 h2가 있다(28개 registry 화면이 공유하는 셸이라 여기 한 곳)", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "1", action: "login", actor: "a" }], total: 1 });
    renderScreen(BASE_CONFIG);
    await screen.findByText("login");

    expect(screen.getByRole("heading", { level: 1, name: "감사 로그" })).toBeInTheDocument();
    const h2s = screen.getAllByRole("heading", { level: 2 }).map((el) => el.textContent);
    expect(h2s).toEqual(["필터", "목록"]);
  });

  it("config.compact(하위 패널)에서는 h2 대신 h3으로 한 단계 낮춘다 - PageHeader 자체가 h2다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "1", action: "login", actor: "a" }], total: 1 });
    renderScreen({ ...BASE_CONFIG, compact: true });
    await screen.findByText("login");

    expect(screen.getByRole("heading", { level: 2, name: "감사 로그" })).toBeInTheDocument();
    const h3s = screen.getAllByRole("heading", { level: 3 }).map((el) => el.textContent);
    expect(h3s).toEqual(["필터", "목록"]);
    expect(screen.queryAllByRole("heading", { level: 2 })).toHaveLength(1);
  });
});

// PA-RC-0005 — kit.test.jsx는 FormField가 maxLength prop을 받으면 렌더하는지만 본다. 여기서는
// 그 prop이 실제 등록 화면(config.key)에서 fieldLimits.json까지 끊기지 않고 이어지는지 본다 —
// DataScreen이 FormDrawer에 screenKey를 안 넘기거나 kit.jsx가 그 이름을 놓치면 이 화면
// 하나만으로는 안 잡히고 실제 관리자 화면에서만 드러난다.
describe("등록 화면 maxLength가 fieldLimits.json까지 실제로 이어진다 (PA-RC-0005)", () => {
  it("create 폼을 열면 백엔드 스키마 상한이 그대로 maxLength로 걸린다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      key: "prompts",
      create: { roles: ["system_admin"], fields: [{ name: "name", label: "이름", type: "text", required: true }] },
    });
    await waitFor(() => expect(apiMock).toHaveBeenCalled());

    // 빈 화면이면 헤더/빈 상태 두 군데에 '추가'가 함께 뜰 수 있다(페이지네이션의 '다음'/'이전'과
    // 같은 이유) — 아무 쪽이나 같은 동작이라 첫 번째로 충분하다.
    await user.click((await screen.findAllByRole("button", { name: "추가" }))[0]);
    // app/prompts/router.py PromptCreateRequest.name = Field(min_length=1, max_length=120).
    expect(await screen.findByLabelText(/이름/)).toHaveAttribute("maxlength", "120");
  });

  it("fieldLimits.json에 없는 화면 키는 maxLength를 걸지 않는다(있지도 않은 상한을 지어내지 않는다)", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      key: "무매핑-화면",
      create: { roles: ["system_admin"], fields: [{ name: "name", label: "이름", type: "text", required: true }] },
    });
    await waitFor(() => expect(apiMock).toHaveBeenCalled());

    await user.click((await screen.findAllByRole("button", { name: "추가" }))[0]);
    expect(await screen.findByLabelText(/이름/)).not.toHaveAttribute("maxlength");
  });
});
