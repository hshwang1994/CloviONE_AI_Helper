import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useNavigationType, useSearchParams } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 같은 메뉴를 다시 누르면 **새로 들어온 것**이다 — 두 번 누른 끝 상태가 한 번 누른 끝 상태와 같다.
 *
 * 운영에서 드러난 결함(2026-09-21): 작업 보드에 들어가면 화면이 팀 · 회차를 스스로 골라 주소에
 * 적는다. 그 상태에서 같은 메뉴를 다시 누르면 주소는 질의 없는 `/work-board` 로 바뀌는데 본문
 * 경계의 키가 경로뿐이라 화면이 다시 마운트되지 않았고, 「진입 때 한 번」 도는 회차 자동 선택이
 * 무장이 풀린 채 남아 회차 없는 판이 섰다. 한 번 누른 화면과 두 번 누른 화면이 달랐다.
 *
 * 여기서 못박는 것:
 *   · 같은 경로의 사이드바 항목을 누르면 진입 번호가 올라 화면이 새로 마운트되고, 주소는 replace 다.
 *   · 다른 경로의 항목은 지금처럼 push 다(뒤로 가기가 그대로다).
 *   · 수정키 · 가운데 단추 클릭은 브라우저에 맡긴다(새 탭 열기).
 *   · 「진입 때 한 번」 상태를 가진 화면은 두 번 눌러도 한 번 누른 것과 끝 상태가 같다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { CommandPalette } from "./CommandPalette.jsx";
import { USER_NAV } from "./navConfig.js";
import { NavEntryProvider, isReentry, useNavEntry } from "./navEntry.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function setMatchMedia() {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: /min-width/.test(query),
    media: query,
    onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

let mounts = 0;

/* 작업 보드의 「진입 때 한 번」 자동 선택을 그대로 흉내 낸 화면 — 팀이 없으면 팀을, 회차가 없고
   아직 한 번도 안 골랐으면 회차를 고른다. 두 번째부터는 사용자가 비운 회차를 다시 덮지 않는다.

   🔴 무장 여부는 **마운트할 때의 주소**가 정한다 — 실제 화면과 같다(`WorkBoard.jsx::autoSelectedFor` 가
   `useRef(state.sprint ? teamId : null)`, `Sprint.jsx::autoFor` 도 같은 모양). 주소에 회차가 이미 있으면 그 팀은
   「골랐다」로 치고 다시 고르지 않는다. 그래서 새 인스턴스가 **옛 주소를 보고 먼저 한 번 그려지면** 자동 선택이
   막힌다 — 재진입 번호만 급한 갱신으로 올리고 주소는 라우터의 전환(transition)으로 늦게 오면 정확히 그렇게 된다
   (2026-09-21 고친 빌드 실측: 작업 보드 · 스프린트 회의가 두 번 누르면 `?team=A` 에서 멈췄다). */
function OneShotScreen() {
  const [params, setParams] = useSearchParams();
  const autoSelectedFor = React.useRef(params.get("sprint") ? params.get("team") : null);
  React.useEffect(() => { mounts += 1; }, []);
  React.useEffect(() => {
    if (!params.get("team")) { setParams({ team: "t1" }, { replace: true }); return; }
    if (!params.get("sprint") && autoSelectedFor.current !== params.get("team")) {
      autoSelectedFor.current = params.get("team");
      setParams({ team: params.get("team"), sprint: "s-open" }, { replace: true });
    }
  }, [params, setParams]);
  return null;
}

function Probe() {
  const loc = useLocation();
  const type = useNavigationType();
  return <div data-testid="probe">{`${loc.pathname}${loc.search}|${type}`}</div>;
}

/* App.jsx 의 본문 경계와 같은 키 — `경로:진입 번호`. */
function Body() {
  const loc = useLocation();
  const entry = useNavEntry();
  return (
    <>
      <Probe />
      <div key={`${loc.pathname}:${entry}`}>
        {loc.pathname === "/work-board" ? <OneShotScreen /> : null}
      </div>
    </>
  );
}

function renderShell(initialPath) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <NavEntryProvider>
        <QueryClientProvider client={qc}>
          <ThemeModeProvider>
            <ToastProvider>
              <ConfirmProvider>
                <AppShell nav={USER_NAV} ariaLabel="사용자 메뉴" isUser showMenu>
                  <Body />
                </AppShell>
              </ConfirmProvider>
            </ToastProvider>
          </ThemeModeProvider>
        </QueryClientProvider>
      </NavEntryProvider>
    </MemoryRouter>,
  );
}

const probe = () => screen.getByTestId("probe").textContent;

beforeEach(() => {
  mounts = 0;
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0, rooms: [] });
  window.localStorage.clear();
  setMatchMedia();
});

afterEach(() => { delete window.matchMedia; vi.restoreAllMocks(); });

describe("같은 메뉴를 다시 누르면 새로 들어온 것이다", () => {
  it("한 번 누른 끝 상태와 두 번 누른 끝 상태가 같다(자동 선택이 다시 선다)", async () => {
    const user = userEvent.setup();
    renderShell("/me");
    const nav = await screen.findByRole("navigation");
    const item = within(nav).getByRole("link", { name: "작업 보드" });

    await user.click(item);
    const once = probe().split("|")[0];
    expect(once).toBe("/work-board?team=t1&sprint=s-open");

    // 🔴 같은 메뉴를 다시 누른다 — 예전에는 주소가 `/work-board` 로 비고 화면이 그대로 살아
    // 회차 자동 선택이 다시 안 섰다(`?team=t1` 에서 멈췄다).
    await user.click(item);
    expect(probe().split("|")[0]).toBe(once);
    expect(mounts).toBe(2);

    // 빠른 연타(더블클릭)도 같다.
    await user.dblClick(item);
    expect(probe().split("|")[0]).toBe(once);
  });

  it("같은 경로의 재진입은 주소를 replace 하고, 다른 경로로 가는 것은 push 다", async () => {
    const user = userEvent.setup();
    renderShell("/work-board?team=t1&sprint=s-old");
    const nav = await screen.findByRole("navigation");

    await user.click(within(nav).getByRole("link", { name: "작업 보드" }));
    expect(probe().split("|")[1]).toBe("REPLACE");

    await user.click(within(nav).getByRole("link", { name: "스프린트 회의" }));
    expect(probe()).toBe("/sprint|PUSH");
  });

  it("수정키를 누른 클릭은 브라우저에 맡긴다 — 새 탭 열기를 가로채지 않는다", async () => {
    renderShell("/work-board?team=t1&sprint=s-open");
    const nav = await screen.findByRole("navigation");
    const before = mounts;
    const item = within(nav).getByRole("link", { name: "작업 보드" });
    /* 화면이 기본 동작을 막았는지는 창 단계에서 읽는다(React 의 뿌리 처리기가 끝난 뒤다). 읽은 뒤에는 jsdom 이
       링크를 따라가려다 「navigation 미구현」을 찍지 않게 여기서 막는다 — 앱의 판정과는 상관없는 뒷정리다. */
    let appPrevented = null;
    const readThenStop = (e) => { appPrevented = e.defaultPrevented; e.preventDefault(); };
    window.addEventListener("click", readThenStop);
    fireEvent.click(item, { ctrlKey: true, button: 0 });
    window.removeEventListener("click", readThenStop);
    // 기본 동작을 막지 않았고(= 브라우저가 새 탭을 연다) 새 진입도 없다.
    expect(appPrevented).toBe(false);
    expect(mounts).toBe(before);
  });
});

describe("재진입 판정 — 같은 경로이고 대상이 다른 질의를 들지 않았다", () => {
  const here = { pathname: "/work-board", search: "?team=t1&sprint=s1" };

  it("메뉴 항목(질의 없는 화면 경로)은 재진입이다", () => {
    expect(isReentry("/work-board", here)).toBe(true);
    expect(isReentry({ pathname: "/work-board" }, here)).toBe(true);
    expect(isReentry("/work-board?", here)).toBe(true);
  });

  it("지금과 같은 질의를 든 이동도 재진입이다", () => {
    expect(isReentry("/work-board?team=t1&sprint=s1", here)).toBe(true);
  });

  it("같은 경로라도 다른 질의를 든 이동은 평범한 이동이다(뒤로 가기로 앞 상태에 돌아간다)", () => {
    expect(isReentry("/search?q=b", { pathname: "/search", search: "?q=a" })).toBe(false);
    expect(isReentry("/work-board?team=t2", here)).toBe(false);
  });

  it("다른 경로는 재진입이 아니다", () => {
    expect(isReentry("/sprint", here)).toBe(false);
    expect(isReentry("/work-board/x", here)).toBe(false);
  });
});

describe("명령 팔레트도 같은 셸 규칙을 쓴다", () => {
  it("지금 화면의 메뉴를 팔레트에서 고르면 사이드바에서 누른 것과 끝 상태가 같다", async () => {
    apiMock.mockResolvedValue({ query: "작업", mode: "like", total: 0, truncated: false, groups: [] });
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/work-board?team=t1&sprint=s-open"]}>
        <NavEntryProvider>
          <QueryClientProvider client={qc}>
            <ThemeModeProvider>
              <CommandPalette open onClose={() => {}} groups={USER_NAV} />
              <Body />
            </ThemeModeProvider>
          </QueryClientProvider>
        </NavEntryProvider>
      </MemoryRouter>,
    );
    const before = mounts;
    await user.type(screen.getByRole("textbox", { name: "통합 검색" }), "작업 보드");
    await user.click(await screen.findByText("작업 보드"));
    // 🔴 예전에는 팔레트가 맨 navigate 라 주소만 `/work-board` 로 비고 화면이 그대로 살아 회차가 빠졌다.
    expect(probe()).toBe("/work-board?team=t1&sprint=s-open|REPLACE");
    expect(mounts).toBe(before + 1);
  });
});
