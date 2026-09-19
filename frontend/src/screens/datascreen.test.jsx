import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, render, screen, within, waitFor } from "@testing-library/react";
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
 *
 * qa-contract-change: 요약이 판독 줄(MetricStrip) 대신 뜻에 맞는 그릇(summary.kind — KPI 타일 줄 · 상태 요약 카드 · 속성 줄)으로 선다(계획 B-6, 표 7).
 * 요약 줄 구조 단언을 KPI 타일 줄 한 묶음과 칸 수로, 안 읽음 한 칸을 큰 숫자 카드로 옮기고, 옛 판독 줄이 남지 않았다는 단언을 더한다.
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
import { ConfirmProvider, SessionExpiredOutlet, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderScreen(config) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              {/* 셸의 본문 자리와 같다 — 세션이 끊기면 이 자리가 오류 상태(401 갈래)로 바뀐다. */}
              <SessionExpiredOutlet>
                <DataScreen config={config} />
              </SessionExpiredOutlet>
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

    /* 단추 경로가 정본이다 — 키보드·스크린리더 사용자가 실제로 쓰는 길이고, 그 길이 없으면
       이 목록은 그들에게 첫 묶음이 전부다. */
    await user.click(screen.getByRole("button", { name: "더 보기" }));
    await screen.findByText("동작-2");
    expect(apiMock.mock.calls.some((c) => String(c[0]).includes("page=2"))).toBe(true);
    /* 🔴 **이어 붙였다** — 갈아 끼운 게 아니다. 앞 묶음의 행이 그대로 남아 있어야 한다. */
    expect(screen.getByText("동작-1")).toBeTruthy();
    expect(screen.getByText("4건 중 2건을 받았습니다.")).toBeTruthy();
  });

  it("끝까지 굴려도 같은 일이 일어난다 — 단추와 자동 로딩이 같은 것을 부른다", async () => {
    apiMock.mockImplementation((url) => {
      const m = /page=(\d+)/.exec(url);
      const n = m ? Number(m[1]) : 1;
      return Promise.resolve({
        items: [{ id: `p${n}`, action: `동작-${n}`, actor: "a" }], total: 4, page_size: 2,
      });
    });
    renderScreen(paged);
    await screen.findByText("동작-1");
    await act(async () => { globalThis.__intersect(); });
    await screen.findByText("동작-2");
    expect(apiMock.mock.calls.some((c) => String(c[0]).includes("page=2"))).toBe(true);
  });

  it("다 받았으면 「더 보기」가 사라진다 — 안 쓰는 컨트롤을 남기지 않는다", async () => {
    apiMock.mockResolvedValue({
      items: [{ id: "p1", action: "동작-1", actor: "a" }], total: 1, page_size: 2,
    });
    renderScreen(paged);
    await screen.findByText("동작-1");
    expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull();
  });

  it("VIS-117 이 고치려던 결함 자체가 없어졌다 — 위쪽 이동 조작기를 두지 않는다", async () => {
    /* 예전 결함: 100행짜리 화면에서 다음 쪽으로 넘기려고 매번 6,186px 를 굴러 내려가야 했다.
       그래서 목록 위에 같은 페이저를 하나 더 뒀었다. 이제는 굴러 내려가는 그 행동이 곧
       다음 묶음을 부른다 — 위쪽 조작기는 아무 문제도 안 푼다. */
    apiMock.mockResolvedValue({
      items: [{ id: "p1", action: "동작-1", actor: "a" }], total: 4, page_size: 2,
    });
    renderScreen(paged);
    await screen.findByText("동작-1");
    expect(screen.queryByRole("navigation", { name: "페이지 이동(목록 위)" })).toBeNull();
    expect(screen.getAllByRole("button", { name: "더 보기" })).toHaveLength(1);
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

  /* 조합 계약 C-4 — 정말 빈 화면에서도 화면의 채움은 머리 동작 하나다. 빈 상태의 만드는 단추는 같은 일을 하는 30 보조다
     (핸드오프 RULES §1 「제목 + 만드는 버튼 30px」). 예전에는 머리와 빈 상태에 같은 이름의 채움이 둘 섰다(대리 보기 실측). */
  const isContained = (el) => [...el.classList].some((c) => /^MuiButton-contained[A-Z]/.test(c));

  it("정말 빈 화면: 머리의 '추가'만 채움이고 빈 상태의 '추가'는 30 보조다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    const { container } = renderScreen({
      ...BASE_CONFIG,
      key: "prompts",
      emptyTitle: "프롬프트가 없습니다",
      create: { roles: ["system_admin"], fields: [{ name: "name", label: "이름", type: "text", required: true }] },
    });
    expect(await screen.findByRole("heading", { name: "프롬프트가 없습니다" })).toBeInTheDocument();
    const adds = screen.getAllByRole("button", { name: "추가" });
    expect(adds).toHaveLength(2);
    const filled = Array.from(container.querySelectorAll("button")).filter(isContained);
    expect(filled.map((b) => b.textContent)).toEqual(["추가"]);
    const emptyAdd = adds.find((b) => !isContained(b));
    expect(emptyAdd).not.toBeUndefined();
    expect([...emptyAdd.classList].some((c) => /^MuiButton-sizeSmall/.test(c))).toBe(true);
  });

  it("정말 빈 화면: 머리의 주 동작(primary 머리 액션)도 빈 상태에서는 30 보조로 한 번 더 선다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    const { container } = renderScreen({
      ...BASE_CONFIG,
      key: "impersonation",
      emptyTitle: "대리 보기 기록이 없습니다",
      headerActions: [{ label: "대리 보기 시작", variant: "primary", primary: true, path: () => "/x" }],
    });
    expect(await screen.findByRole("heading", { name: "대리 보기 기록이 없습니다" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "대리 보기 시작" })).toHaveLength(2);
    const filled = Array.from(container.querySelectorAll("button")).filter(isContained);
    expect(filled.map((b) => b.textContent)).toEqual(["대리 보기 시작"]);
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

    /* 뜻을 말하지 않은 요약(`summary.kind` 없음)은 서로 다른 측정값의 **KPI 타일 줄**이다(계획 표 7).
       타일 줄은 칸 수만큼만 트랙을 만든다(`fixedTileTrack`) — 여섯 장이 한 묶음 안에 여섯 칸으로 선다. */
    const strips = screen.getAllByRole("group", { name: "요약" });
    expect(strips, "요약 묶음이 하나여야 한다").toHaveLength(1);
    for (const label of LABELS) {
      expect(within(strips[0]).getByText(label), label).toBeInTheDocument();
    }
    expect(strips[0].children.length, "칸 수가 카드 수와 같아야 한다").toBe(LABELS.length);
    // 서버 숫자를 그대로 쓴다 — 칸마다 **자기** 값이 선다. 칸은 묶음의 직계 자식이고, 이름과 값이 같은 칸에 있다.
    const tileOf = (label) => [...strips[0].children].find((el) => within(el).queryByText(label));
    for (const [label, value] of [["대기", "1"], ["실행 중", "2"], ["실행 가능(ready)", "1"], ["실패", "0"], ["완료", "10"], ["취소됨", "0"]]) {
      const tile = tileOf(label);
      expect(tile, label + " 칸이 없다").toBeTruthy();
      expect(within(tile).getByText(value), label + " 칸의 값").toBeInTheDocument();
    }
    expect(getComputedStyle(strips[0]).display).toBe("grid");
    // 옛 판독 줄이 되살아나지 않는다 — 합이 전체가 아닌 값들을 한 줄 판독으로 늘어놓던 그릇이다.
    expect(document.querySelectorAll(".k-metrics, .k-readout")).toHaveLength(0);
  });

  it("unreadCountKey 한 값은 큰 숫자 하나로 선다(값 하나 갈래)", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0, unread_count: 3 });
    renderScreen({ ...BASE_CONFIG, unreadCountKey: "unread_count" });
    const label = await screen.findByText("안 읽음");

    const plate = label.closest("[data-summary-single]");
    expect(plate, "값 하나 카드 안에 있어야 한다").not.toBeNull();
    expect(within(plate).getByText("3")).toBeInTheDocument();
    expect(plate.querySelector('[data-ratio-bar]'), "값 하나에는 비율 바가 없다").toBeNull();
    // 안 읽음이 남아 있으면 주의다 — 판독 줄의 톤 색 대신 이름 앞 점이 말한다(숫자는 잉크색).
    expect(label.querySelector("[data-status-dot]"), "안 읽음이 남았는데 주의 점이 없다").not.toBeNull();
  });

  it("안 읽음이 0 이면 주의 점을 그리지 않는다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0, unread_count: 0 });
    renderScreen({ ...BASE_CONFIG, unreadCountKey: "unread_count" });
    const label = await screen.findByText("안 읽음");
    expect(label.closest("[data-summary-single]")).not.toBeNull();
    expect(label.querySelector("[data-status-dot]")).toBeNull();
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

describe("REAUDIT §15.1 — 행이 많으면 가상화가 자동으로 켜진다", () => {
  it("🔴 60건을 넘으면 DataTable이 가상화된다 — 총 건수는 그대로고 그려진 행은 그보다 적다", async () => {
    const items = Array.from({ length: 100 }, (_, i) => ({ id: `a${i}`, action: `동작-${i}`, actor: "관리자" }));
    apiMock.mockResolvedValue({ items, total: 100 });
    const { container } = renderScreen(BASE_CONFIG);
    await screen.findByText("동작-0");

    const list = container.querySelector('[data-virtual-total]');
    expect(list, "가상화 스크롤 창을 찾지 못했다").not.toBeNull();
    expect(list).toHaveAttribute("data-virtual-total", "100");
    // 100건 전부가 <tr>로 그려지지는 않는다 — 가상화의 요점이다.
    expect(container.querySelectorAll("tbody tr").length).toBeLessThan(100);
  });

  it("60건 이하면 그대로 전부 그린다 — 가상화 창이 없다(회귀 0)", async () => {
    const items = Array.from({ length: 10 }, (_, i) => ({ id: `a${i}`, action: `동작-${i}`, actor: "관리자" }));
    apiMock.mockResolvedValue({ items, total: 10 });
    const { container } = renderScreen(BASE_CONFIG);
    await screen.findByText("동작-0");
    expect(container.querySelector('[data-virtual-total]')).toBeNull();
    expect(container.querySelectorAll("tbody tr").length).toBe(10);
  });
});

/* 빈 상태는 제목 + 한 문장 + 동작이다(D-456). 준비물·절차·기대 결과는 제목 옆 `?` 도움말이
   든다 — 예전에는 빈 상태 안에만 있어서 목록이 차면 읽을 수 없었고, 사용자 화면의 빈 상태와
   모양이 달랐다(대리 보기 화면의 여섯 줄 절차). */
describe("절차 안내는 빈 상태가 아니라 제목 옆 도움말에 있다 (D-456)", () => {
  const GUIDED = {
    ...BASE_CONFIG,
    help: "감사 로그를 봅니다.",
    create: { fields: [{ name: "action", label: "동작" }] },
    emptyTitle: "감사 로그가 없습니다",
    emptySituation: "아직 기록이 없습니다.",
    emptyPrerequisite: "기록할 동작이 있어야 합니다.",
    emptySteps: ["첫째 단계를 합니다.", "둘째 단계를 합니다."],
    emptyExpected: "기록이 목록에 나타납니다.",
  };

  it("빈 상태에는 제목·상황·동작만 남고 절차는 도움말 패널에 있다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    renderScreen(GUIDED);
    const title = await screen.findByRole("heading", { name: "감사 로그가 없습니다" });
    const empty = title.closest(".k-empty");
    expect(within(empty).getByText("아직 기록이 없습니다.")).toBeInTheDocument();
    expect(within(empty).queryByText("필요한 것")).toBeNull();
    expect(within(empty).queryByText("첫째 단계를 합니다.")).toBeNull();
    const toggle = screen.getByRole("button", { name: "도움말 보기" });
    expect(toggle.closest(".k-page-head")).not.toBeNull();
    const panel = document.getElementById(toggle.getAttribute("aria-controls"));
    expect(within(panel).getByText("감사 로그를 봅니다.")).toBeInTheDocument();
    expect(within(panel).getByText("필요한 것")).toBeInTheDocument();
    expect(within(panel).getByText("첫째 단계를 합니다.")).toBeInTheDocument();
    expect(within(panel).getByText("기대 결과")).toBeInTheDocument();
  });

  it("그 동작을 볼 수 없는 역할에게는 절차도 안 보인다 — 반례", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    renderScreen({ ...GUIDED, help: undefined, create: { roles: ["nobody"], fields: [] } });
    await screen.findByRole("heading", { name: "감사 로그가 없습니다" });
    expect(screen.queryByRole("button", { name: "도움말 보기" })).toBeNull();
    expect(screen.queryByText("첫째 단계를 합니다.")).toBeNull();
  });
});
