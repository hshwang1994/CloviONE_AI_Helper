import React from "react";
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
const authMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => authMock() }));

import { AppShell } from "./AppShell.jsx";
import { NAV, USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { CONTROL, FONT_WEIGHT, ICON, NAV_ANATOMY, createClovirTheme } from "../ui/theme.js";

/* Navigation 계약 — 사이드바가 실제로 그리는 것을 본다 (W3 · R-48 · R-79 · 지시 79).
 *
 * ## 왜 이 파일이 필요한가
 *
 * W1·W2 독립 검수가 사이드바에서 같은 종류의 결함 셋을 잡았고, 셋 다 **시험은 초록인 채로**
 * 배포본에 살아 있었다.
 *
 *   · `F-W1R-05` 활성 신호가 넷으로 겹친다(2px 레일 + `fontWeight 700 vs 600` + 색 +
 *     `icon opacity 1 vs .82`). 한글에서 semibold→bold 전환은 글자 폭을 실제로 바꿔 항목을
 *     움직인다 — 신호가 아니라 흔들림이다.
 *   · `F-W1R-18` 라벨 시작선이 그룹 60px / 자식 64px 로 어긋난다(픽셀 실측). 4px 차이는
 *     사이드바가 격자를 두 벌 쓰는 것처럼 보이게 한다. 레일은 2px 이고 가장자리에서 20px
 *     안쪽에 떠 있었다.
 *   · `F-W2R-02` 3840 에서 아이콘과 라벨이 맞붙는다. `minWidth: 30`(px)인 칸에 rem 글리프를
 *     넣으면 4K 레버가 루트를 20px 로 올릴 때 글리프만 칸을 넘친다. 같은 줄의
 *     `size={18} strokeWidth={1.8}` 은 MUI `SvgIcon` 에 **없는 prop** 이라 조용히 무시됐고,
 *     그 결과 자식 아이콘(24px 기본값)이 부모 그룹 아이콘(20px)보다 크게 그려졌다.
 *
 * 공통점은 하나다: **선언은 있는데 아무도 그 선언을 세지 않았다.** 그래서 이 파일은
 * 값 하나하나가 아니라 **관계**를 센다 — 라벨 시작선이 그룹과 자식에서 같은가, 활성 신호가
 * 정확히 둘인가, 글리프 칸과 글리프가 같은 단위인가. 값이 바뀌어도 관계가 유지되면 통과하고,
 * 관계가 깨지면 값이 그대로여도 실패한다.
 *
 * 색 대비는 여기서 재지 않는다 — `ui/theme-contract.test.js` 가 팔레트 차원에서,
 * `scripts/ui_qa/nav_e2e.py` 가 실제 브라우저에서 잰다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_SHELL_SRC = readFileSync(path.join(HERE, "AppShell.jsx"), "utf-8");
const PALETTE_SRC = readFileSync(path.join(HERE, "CommandPalette.jsx"), "utf-8");

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

/** emotion 이 이 요소의 클래스로 낸 규칙 전부 — `::before` 같은 의사요소 블록까지.
 *
 *  jsdom 은 레이아웃도 논리 속성 계산도 하지 않는다(`inset-inline-start` 는 빈 문자열).
 *  물리 속성으로 바꿔 재면 저장소가 논리 속성으로 통일해 둔 방향을 시험 편의로 깨는 것이라,
 *  계산값 대신 **선언**을 읽는다 — `topbar-contract.test.jsx`·`brand-logo.test.jsx` 와 같은 기법. */
function cssRules(el) {
  const css = [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n");
  const out = [];
  for (const cls of [...el.classList].filter((c) => c.startsWith("css-"))) {
    const marker = new RegExp(`\\.${cls}(?![\\w-])`, "g");
    let m;
    while ((m = marker.exec(css)) !== null) {
      let i = css.indexOf("{", m.index);
      if (i < 0) break;
      const start = i;
      let depth = 0;
      for (; i < css.length; i += 1) {
        if (css[i] === "{") depth += 1;
        else if (css[i] === "}") { depth -= 1; if (depth === 0) { i += 1; break; } }
      }
      // 이 클래스로 시작하는 규칙만 — 다른 선택자 안에 우연히 든 문자열은 건너뛴다.
      const selector = css.slice(css.lastIndexOf("}", m.index) + 1, start).trim();
      if (selector.startsWith(`.${cls}`)) {
        out.push({ cls, selector, body: css.slice(start + 1, i - 1) });
      }
      marker.lastIndex = i;
    }
  }
  return out;
}

function rulesOf(el) {
  return cssRules(el).map((r) => `${r.selector}{${r.body}}`).join("");
}

/** 선택자가 **정확히** `.css-xxx<suffix>` 인 규칙의 선언만.
 *
 *  `rulesOf()` 로 뭉친 문자열에서 값을 찾으면 **이웃 규칙이 대신 답한다.** 실제로 그랬다:
 *  선택 행 배경 단언이 `.css-x.Mui-selected` 와 `.css-x.Mui-selected:hover` 를 이어 붙인
 *  문자열에서 토큰을 찾고 있어서, `&.Mui-selected` 를 `transparent` 로 되돌려도 `:hover`
 *  한 줄이 남아 20/20 초록이었다(독립 검수자가 변이로 실증). 상태를 재는 단언은 **그 상태의
 *  규칙 하나**만 봐야 한다. */
function ruleBody(el, suffix) {
  // 한 요소가 emotion 클래스를 여러 개 갖는다(MUI 기본 + sx). 같은 접미사를 가진 규칙이
  // 여러 개면 **문서 순서상 마지막**이 캐스케이드에서 이긴다 — `declPx` 와 같은 이유다.
  const hits = cssRules(el).filter((r) => r.selector === `.${r.cls}${suffix}`);
  return hits.length ? hits[hits.length - 1].body : "";
}

/** 그 상태 규칙에서 실제로 이기는 선언 하나. 없으면 빈 문자열. */
function declOf(el, suffix, prop) {
  const all = [...ruleBody(el, suffix).matchAll(new RegExp(`${prop}:\\s*([^;]+)`, "g"))];
  return all.length ? all[all.length - 1][1].trim() : "";
}

/** 선언 하나의 값. `rem`/`px` 어느 쪽이든 기본 단계(root 16px)의 px 로 환산한다.
 *
 *  **마지막** 선언을 읽는다. emotion 은 MUI 기본 스타일과 `sx` 오버라이드를 같은 클래스의
 *  같은 블록에 이어 붙인다(`padding-left:16px` 뒤에 `padding-left:0.75rem`). 첫 선언을
 *  읽으면 우리가 덮어쓴 값이 아니라 MUI 기본값을 재게 된다 — 캐스케이드에서 실제로 이기는
 *  것은 뒤에 온 쪽이다. 이 시험을 처음 돌렸을 때 정확히 그 함정을 밟았다. */
function declPx(block, prop) {
  const all = [...block.matchAll(new RegExp(`${prop}:\\s*([\\d.]+)(rem|px)`, "g"))];
  if (!all.length) return null;
  const m = all[all.length - 1];
  return m[2] === "rem" ? Number(m[1]) * 16 : Number(m[1]);
}

function renderShell({ nav, isUser, initialPath, role }) {
  authMock.mockReturnValue({ data: { role, id: role === "user" ? "u1" : "a1" } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={nav} ariaLabel="메뉴" isUser={isUser} showMenu>
                <div>본문</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const userShell = () => renderShell({ nav: USER_NAV, isUser: true, initialPath: "/me", role: "user" });
const adminShell = () =>
  renderShell({ nav: NAV, isUser: false, initialPath: "/dashboard", role: "system_admin" });

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
  window.localStorage.clear();
  setMatchMedia();
});
afterEach(() => { delete window.matchMedia; vi.restoreAllMocks(); });

describe("라벨 시작선 — 그룹과 자식이 같은 42px 열에서 시작한다", () => {
  it("계약의 산수가 한 곳에서 나온다 (12 + 20 + 10 = 42)", () => {
    expect(NAV_ANATOMY.padInline + NAV_ANATOMY.glyph + NAV_ANATOMY.gap).toBe(NAV_ANATOMY.labelStart);
    expect(NAV_ANATOMY.glyph).toBe(ICON.nav);
  });

  it("그룹 헤더: 안쪽 여백 12 + 글리프 칸 30 → 라벨이 42 에서 시작한다", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const header = within(nav).getByRole("button", { name: /내 업무/ });
    const row = rulesOf(header);
    expect(declPx(row, "padding-left"), "행 안쪽 여백이 계약값과 다르다")
      .toBe(NAV_ANATOMY.padInline);

    const slot = header.querySelector(".MuiListItemIcon-root");
    expect(slot, "그룹이 랜드마크 글리프 칸을 잃었다").toBeTruthy();
    expect(declPx(rulesOf(slot), "min-width"), "글리프 칸이 글리프+간격과 다르다")
      .toBe(NAV_ANATOMY.glyph + NAV_ANATOMY.gap);
  });

  it("자식 항목: 글리프가 없고, 그 자리를 padding 이 채워 라벨이 같은 42 에서 시작한다", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const item = within(nav).getByRole("link", { name: /^내 티켓$/ });
    expect(declPx(rulesOf(item), "padding-left"), "자식 라벨 시작선이 그룹과 어긋났다")
      .toBe(NAV_ANATOMY.labelStart);
    expect(item.querySelector(".MuiListItemIcon-root"),
      "자식이 글리프를 되찾았다 — 그룹이 글리프를 가지면 자식은 갖지 않는다").toBeNull();
  });

  it("자식 목록에 들여쓰기가 없다 — 깊이는 접힘 상태 하나로만 말한다", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const item = within(nav).getByRole("link", { name: /^내 티켓$/ });
    const innerList = item.closest("ul");
    const pad = declPx(rulesOf(innerList), "padding-left");
    expect(pad === null || pad === 0, "자식 목록이 다시 들여쓰기를 얻었다").toBe(true);
  });

  it("두 콘솔이 같은 해부구조를 쓴다 — 차이는 깊이 표현뿐이다", async () => {
    const view = adminShell();
    const nav = await screen.findByRole("navigation");
    const header = within(nav).getByRole("button", { name: /운영/ });
    expect(declPx(rulesOf(header), "padding-left")).toBe(NAV_ANATOMY.padInline);
    const item = within(nav).getByRole("link", { name: /^대시보드$/ });
    expect(declPx(rulesOf(item), "padding-left")).toBe(NAV_ANATOMY.labelStart);
    view.unmount();
  });
});

describe("활성 신호는 정확히 둘 — 위치(레일)와 색(면·잉크)", () => {
  it("활성 행에 3px 레일이 하우징 가장자리(inline-start 0)에 붙는다", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const active = within(nav).getByRole("link", { name: /^홈$/ });
    expect(active).toHaveAttribute("aria-current", "page");
    const block = rulesOf(active);
    expect(/&?::before/.test(block) || block.includes("::before"), "레일 의사요소가 없다").toBe(true);
    expect(declPx(block, "width"), "레일 두께가 계약값(3)과 다르다").toBe(NAV_ANATOMY.rail);
    expect(block, "레일이 목록 안쪽으로 들어가 떠 있다").toMatch(/inset-inline-start:\s*0/);
  });

  it("활성 행이 면을 칠한다 — 선택 상태가 색으로도 말한다", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const active = within(nav).getByRole("link", { name: /^홈$/ });
    const light = createClovirTheme("light").palette;
    const wanted = light.sidebar.selected.replace(/\s/g, "");
    /* `.Mui-selected` **그 규칙 하나**에서 실제로 이기는 선언을 본다. 이웃 `:hover` 규칙까지
       뭉쳐서 문자열로 찾으면 선택 상태를 transparent 로 되돌려도 hover 한 줄이 남아 통과한다
       (독립 검수가 변이로 실증했다). MUI 기본 `.Mui-selected` 도 같은 접미사를 갖지만
       sx 가 뒤에 와서 이긴다 — `ruleBody` 가 문서 순서상 마지막을 돌려준다. */
    const selected = declOf(active, ".Mui-selected", "background-color").replace(/\s/g, "");
    expect(selected, "선택 행이 투명하게 남았다 — 위치 신호 하나에 전부 걸려 있다").toBe(wanted);
    // hover 가 선택 면을 덮어 지금 있는 자리가 흐려지지 않는다.
    expect(declOf(active, ".Mui-selected:hover", "background-color").replace(/\s/g, ""),
      "선택된 행에 hover 하면 면이 옅어진다").toBe(wanted);
  });

  it("굵기는 선택으로 바뀌지 않는다 — nav 라벨은 제품 전체에서 medium 고정", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const weightOf = (name) => {
      const el = within(nav).getByRole("link", { name });
      return getComputedStyle(el.querySelector(".MuiListItemText-primary")).fontWeight;
    };
    expect(weightOf(/^홈$/)).toBe(String(FONT_WEIGHT.medium));
    expect(weightOf(/^내 티켓$/)).toBe(String(FONT_WEIGHT.medium));
    expect(weightOf(/^홈$/), "활성 행만 굵어지면 한글에서 글자 폭이 바뀌어 항목이 움직인다")
      .toBe(weightOf(/^내 티켓$/));
  });

  it("아이콘 투명도로 상태를 말하지 않는다 — 흐린 글리프를 더 흐리게 하면 탁해질 뿐이다", () => {
    expect(APP_SHELL_SRC, "`opacity: active ? …` 가 사이드바로 되돌아왔다")
      .not.toMatch(/opacity:\s*active\s*\?/);
  });

  it("포커스 링은 행 **안쪽**으로 그린다 — 가장자리 행에서 링이 하우징 밖으로 새지 않게", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const item = within(nav).getByRole("link", { name: /^내 티켓$/ });
    expect(rulesOf(item)).toMatch(/outline-offset:\s*-2px/);
  });

  it("그룹 헤더는 위치 신호를 갖지 않는다 — 펼침과 선택이 헷갈리던 자리다 (지시 48)", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const header = within(nav).getByRole("button", { name: /내 업무/ });
    expect(rulesOf(header), "그룹 헤더가 활성 레일을 얻었다").not.toMatch(/::before/);
  });
});

describe("아이콘 — 한 계열, rem, 자식이 부모보다 크지 않다", () => {
  it("MUI 아이콘에 없는 prop 을 넘기지 않는다 (`size=` / `strokeWidth=`)", () => {
    /* `SvgIcon` 에는 `size` 가 없고(`fontSize` 다) fill 기반이라 `strokeWidth` 도 무효다.
       무시되는 선언이라 화면에는 "기본값 24px" 이 나왔고, 그것이 그룹 20px 보다 컸다. */
    for (const [name, src] of [["AppShell.jsx", APP_SHELL_SRC], ["CommandPalette.jsx", PALETTE_SRC]]) {
      expect(src, `${name} 에 MUI 아이콘용 죽은 prop 이 있다`).not.toMatch(/\bsize=\{\d/);
      expect(src, `${name} 에 MUI 아이콘용 죽은 prop 이 있다`).not.toMatch(/\bstrokeWidth=/);
    }
  });

  it("사이드바의 모든 글리프가 rem 으로 선언되고 nav 슬롯을 넘지 않는다", async () => {
    adminShell();
    const nav = await screen.findByRole("navigation");
    const glyphs = [...nav.querySelectorAll("svg")];
    expect(glyphs.length, "사이드바에 글리프가 하나도 없다").toBeGreaterThan(5);
    for (const g of glyphs) {
      const size = declPx(rulesOf(g), "font-size");
      expect(size, "글리프가 크기 선언 없이 MUI 기본값(24)으로 떨어졌다").not.toBeNull();
      expect(size, "글리프가 nav 슬롯보다 크다").toBeLessThanOrEqual(ICON.nav);
      expect(rulesOf(g), "글리프가 px 로 굳어 4K 레버를 안 탄다").toMatch(/font-size:\s*[\d.]+rem/);
    }
  });

  it("펼침 화살표는 랜드마크 글리프보다 한 단 작다 — 정체와 상태가 같은 무게로 다투지 않게", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const header = within(nav).getByRole("button", { name: /내 업무/ });
    const svgs = [...header.querySelectorAll("svg")];
    expect(svgs).toHaveLength(2);
    expect(declPx(rulesOf(svgs[0]), "font-size")).toBe(ICON.nav);
    expect(declPx(rulesOf(svgs[1]), "font-size")).toBe(ICON.inline);
    expect(ICON.inline).toBeLessThan(ICON.nav);
  });

  it("Command Palette 의 메뉴 줄은 목적지마다가 아니라 **그룹**의 글리프를 쓴다", () => {
    expect(PALETTE_SRC, "팔레트가 다시 항목별 아이콘 키를 읽는다").not.toMatch(/navIcon\(it\.icon\)/);
    /* 랜드마크 글리프가 먼저다. 최근 방문 목록은 여러 그룹에서 모이므로 시계로 **덮으면**
       네 줄이 전부 같은 그림이 된다 — 이 파일이 예전부터 적어 둔 경고이고, W3 이 한 번
       그 상태를 만들었다가 독립 재검증이 잡았다. 시계는 소속을 모를 때의 마지막 수단이다. */
    expect(PALETTE_SRC, "최근 방문 줄이 다시 전부 같은 시계 글리프가 됐다")
      .toMatch(/Icon:\s*it\.groupIcon\s*\|\|\s*g\.icon\s*\|\|\s*\(g\.recent/);
    expect(PALETTE_SRC, "최근 방문 항목이 자기 그룹의 글리프를 잃었다")
      .toMatch(/byPath\.set\(it\.to,\s*\{\s*\.\.\.it,\s*groupIcon:\s*g\.icon\s*\}\)/);
  });
});

describe("행 높이와 접힘 기본값", () => {
  it("행 높이가 CONTROL.navItem 에서 온다 (리터럴 금지)", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    const item = within(nav).getByRole("link", { name: /^내 티켓$/ });
    expect(declPx(rulesOf(item), "min-height")).toBe(CONTROL.navItem);
  });

  it("사용자 콘솔은 펼침이 기본이다 — 4그룹 20항목은 다 펼쳐도 한 화면에 들어간다", async () => {
    userShell();
    const nav = await screen.findByRole("navigation");
    for (const name of ["내 업무", "팀 업무", "팀 공간", "내 정보"]) {
      expect(within(nav).getByRole("button", { name: new RegExp(name) }),
        `${name} 가 접힌 채로 시작한다`).toHaveAttribute("aria-expanded", "true");
    }
  });

  it("관리자 콘솔은 접힘이 기본이다 — 6그룹 31항목을 다 펼치면 레일이 스크롤된다", async () => {
    adminShell();
    const nav = await screen.findByRole("navigation");
    // 활성 그룹(운영, /dashboard 가 속함)은 강제로 펼쳐진다 — 그 외는 접힘.
    expect(within(nav).getByRole("button", { name: /운영/ })).toHaveAttribute("aria-expanded", "true");
    for (const name of ["설정", "사용자와 권한", "AI", "감사"]) {
      expect(within(nav).getByRole("button", { name: new RegExp(`^${name}`) }),
        `${name} 가 펼쳐진 채로 시작한다`).toHaveAttribute("aria-expanded", "false");
    }
  });

  it("마운트 뒤 신원이 바뀌면 **그 계정의** 접힘 기록을 다시 읽는다 (대리 보기·재로그인)", async () => {
    /* 접힘 키는 계정별이다(`clovirone_nav_collapsed:<userId>`) — 공용 PC 에서 남의 배치가
       넘어오지 않게 나눈 것이다. 그런데 `useState` 초기화 함수는 한 번만 도니까, 이 컴포넌트가
       마운트된 채로 신원이 바뀌면(대리 보기 시작·종료, 재로그인 handoff) 앞 계정의 상태가
       남고 다음 `toggle` 이 **새 계정 키에 앞 계정 상태를 쓴다** — 키를 나눈 이유가 그
       자리에서 무너진다.
       평상시 새로고침은 이 경로가 아니다(셸이 `auth.isLoading` 동안 스켈레톤을 그려
       `SidebarNav` 는 userId 가 있는 채로 마운트된다). 여기서는 신원이 **뒤늦게** 들어오는
       순서를 실제 훅으로 재현한다. */
    window.localStorage.setItem("clovirone_nav_collapsed:u1", JSON.stringify({ "팀 공간": true }));
    authMock.mockImplementation(function useLateAuth() {
      const [data, setData] = React.useState(undefined);
      React.useEffect(() => { setData({ role: "user", id: "u1" }); }, []);
      return { data };
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/me"]}>
        <QueryClientProvider client={qc}>
          <ThemeModeProvider>
            <ToastProvider>
              <ConfirmProvider>
                <AppShell nav={USER_NAV} ariaLabel="메뉴" isUser showMenu><div>본문</div></AppShell>
              </ConfirmProvider>
            </ToastProvider>
          </ThemeModeProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    const nav = await screen.findByRole("navigation");
    const header = within(nav).getByRole("button", { name: /팀 공간/ });
    await waitFor(() =>
      expect(header, "신원이 바뀌었는데 그 계정의 접힘 기록을 안 읽는다")
        .toHaveAttribute("aria-expanded", "false"));
    // 활성 그룹은 여전히 강제로 펼쳐진다 — 이 수정이 그 계약을 덮지 않는다.
    expect(within(nav).getByRole("button", { name: /내 업무/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("펼침 기본은 **재서** 정한다 — 뷰포트 상수를 박지 않는다", () => {
    /* 1366x768 에서 사용자 rail 을 전부 펼치면 «내 정보» 랜드마크가 통째로 창 밖으로 나갔다
       (독립 검수가 배포본 픽셀로 실측: 22행 중 17행). jsdom 은 레이아웃을 하지 않아 여기서
       그 높이를 잴 수 없다 — 실제 판정은 `scripts/ui_qa/nav_e2e.py` 가 네 뷰포트에서
       "스크롤 없이 안 보이는 랜드마크 0건" 으로 확인한다. 이 시험이 지키는 것은 그 판정이
       **측정 기반으로 남아 있는가** 다: 뷰포트 리터럴로 되돌아가거나 측정이 사라지면
       실브라우저 프로브가 다시 눈이 멀기 전에 여기서 걸린다. */
    expect(APP_SHELL_SRC, "펼침 적합성 측정이 사라졌다").toMatch(/setFitsExpanded\(needed <= el\.clientHeight\)/);
    expect(APP_SHELL_SRC, "판정이 그리기 전에 끝나야 깜빡임이 없다 (useEffect 로 내려가면 펼쳤다 접힌다)")
      .toMatch(/useLayoutEffect\(\(\) => \{[\s\S]{0,1200}?setFitsExpanded/);
    expect(APP_SHELL_SRC, "기본값이 측정 결과와 곱해지지 않는다")
      .toMatch(/const openByDefault = groupsOpenByDefault && fitsExpanded;/);
    expect(APP_SHELL_SRC, "사이드바에 뷰포트 높이 리터럴이 되돌아왔다")
      .not.toMatch(/min-height:\s*\d{3,}px/);
    /* 자동 접힘 판정이 **저장되면 안 된다.** 활성 그룹 강제 펼침 effect 의 조건을
       `isCollapsed()`(기록 없음 + 자동 접힘 포함)로 걸면 화면 형편이 사용자 선택으로
       localStorage 에 남고, 그 기록은 자동 판정을 영원히 이긴다 — 1366 에서 네 그룹을 한 번씩
       방문하는 것만으로 결함이 되돌아온다(독립 재검증이 배포본에서 실증했다). */
    expect(APP_SHELL_SRC, "자동 접힘 판정이 사용자 선택으로 저장되는 경로가 되돌아왔다")
      .toMatch(/if \(!activeGroup \|\| collapsed\[activeGroup\.group\] !== true\) return;/);
    expect(APP_SHELL_SRC, "강제 펼침 effect 가 자동 판정(isCollapsed)으로 조건을 건다")
      .not.toMatch(/if \(!activeGroup \|\| !isCollapsed\(/);
  });

  it("사용자가 접은 기록은 활성 진입으로 '펼침' 기록이 되고, **기록 없는** 그룹은 아무것도 저장하지 않는다", async () => {
    /* 앞의 절반은 W2 부터의 계약이다(딥링크로 접힌 그룹에 도착하면 그 그룹은 계속 펼쳐진
       것으로 기록된다 — `sidebar-group-sticky-open.test.jsx`). 뒤의 절반이 이 Wave 가
       더한 것이다: 기록이 **없는** 그룹은 활성이어도 저장하지 않는다. 그래야 화면 형편으로
       접힌 상태가 사용자 선택으로 굳지 않는다. */
    window.localStorage.setItem("clovirone_nav_collapsed:u1", JSON.stringify({ "팀 공간": true }));
    renderShell({ nav: USER_NAV, isUser: true, initialPath: "/chat-rooms", role: "user" });
    const nav = await screen.findByRole("navigation");
    await waitFor(() =>
      expect(within(nav).getByRole("button", { name: /팀 공간/ }))
        .toHaveAttribute("aria-expanded", "true"));
    const stored = JSON.parse(window.localStorage.getItem("clovirone_nav_collapsed:u1"));
    expect(stored["팀 공간"], "명시적으로 접었던 그룹이 활성 진입으로 펼침 기록이 된다").toBe(false);
    for (const name of ["내 업무", "팀 업무", "내 정보"]) {
      expect(name in stored, `${name} 는 사용자가 손댄 적이 없는데 기록이 생겼다`).toBe(false);
    }
  });

  it("메뉴 필터는 **콘솔**로 정해진다 — 역할로 정하면 관리자가 사용자 트리에 들어갔을 때 어긋난다", () => {
    expect(APP_SHELL_SRC).toMatch(/showFilter=\{!homeUser\}/);
    expect(APP_SHELL_SRC).toMatch(/groupsOpenByDefault=\{Boolean\(homeUser\)\}/);
  });
});
