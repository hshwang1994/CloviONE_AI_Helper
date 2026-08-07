import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

import { readBaselineCss, topLevelRules, lastDeclaration } from "../ui/baselineTokens.js";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import TopBrand from "./TopBrand.jsx";
import TopSearch from "./TopSearch.jsx";
import { MascotButton, MascotSidebarCard, MascotTopButton } from "../ui/Mascot.jsx";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

/* 상단바·마스코트 자리의 겉모습이 기준선과 같은가.
 *
 * ## 왜 이 파일에 색·크기 리터럴이 하나도 없는가
 *
 * theme-baseline.test.js 와 같은 이유다. 기준선 값을 손으로 옮겨 적으면 옮긴 값과 화면 코드가
 * **같이** 틀렸을 때 통과한다. 그 사고가 이 저장소에서 이미 여러 번 났다. 그래서 기대값은
 * 전부 design/baseline/preview-standalone.html 을 파싱해서 만든다.
 *
 * ## 사용자 지적 세 가지가 여기 있다
 *
 *   "왼쪽 상단에 아이콘 ClovirAssist 흰바탕이 너무 크다"
 *        → 기준선의 .brand-lockup > img 는 background:transparent 다. 흰 판이 없다.
 *   "상단 검색은 왜 저렇게 나옴?"
 *        → 기준선의 .top-search 는 높이 40, 반지름 12, 왼쪽 여백 42(아이콘 자리)인 **버튼**이다.
 *   "왼쪽 하단이랑 오른쪽 상단 하단 클로비 아이콘 및 디자인 이거 바꾸자고 했는데 왜 적용 안 돼있음"
 *        → .top-clovi-btn / .ai-fab / .sidebar-clovi 세 자리 전부 기준선에 치수가 있다.
 */

const rules = topLevelRules(readBaselineCss());
const decl = (sel, prop) => {
  const value = lastDeclaration(rules, sel, prop);
  if (value === undefined) throw new Error(`기준선에 ${sel} { ${prop} } 이 없다`);
  return value;
};
const px = (sel, prop) => Number.parseFloat(decl(sel, prop));

/* 화면 코드는 여백을 rem 으로 쓴다(styles/root.css 의 루트 폰트사이즈 레버 하나로 4K 에서
 * 글자와 여백이 같이 커지게 한 장치다). 기준선은 px 다. 루트 16px 기준으로 맞춰 본다. */
const toPx = (value) => {
  const text = String(value).trim();
  const n = Number.parseFloat(text);
  return /rem$/.test(text) ? n * 16 : n;
};

/* 색 비교용 정규화. 기준선은 `rgba(8,14,42,.22)`, 브라우저는 `rgba(8, 14, 42, 0.22)` 로 쓴다. */
function rgbaKey(text) {
  const value = String(text).trim().toLowerCase();
  const fn = /^rgba?\(([^)]+)\)$/.exec(value);
  if (fn) {
    const parts = fn[1].split(/[,/\s]+/).filter(Boolean).map(Number);
    const alpha = parts.length > 3 ? parts[3] : 1;
    return `${parts[0]},${parts[1]},${parts[2]},${Number(alpha.toFixed(3))}`;
  }
  const hex = /^#([0-9a-f]{6})$/.exec(value);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},1`;
  }
  return value;
}

function mount(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

// ════════════════════════════════════════════════════════════════════════════
// 1. 좌상단 로고 — 흰 판이 없다
// ════════════════════════════════════════════════════════════════════════════
describe("좌상단 브랜드 로고", () => {
  it("로고를 감싼 어느 상자에도 불투명한 흰 바탕이 없다", () => {
    // 기준선: .brand-lockup > img { background: transparent }
    expect(rgbaKey(decl(".brand-lockup > img", "background"))).toBe(rgbaKey("transparent"));

    const { container } = mount(<TopBrand onClick={() => {}} />);
    const painted = [...container.querySelectorAll("*")].filter((el) => {
      const bg = getComputedStyle(el).backgroundColor;
      const key = rgbaKey(bg);
      // 완전 불투명한 흰색만 잡는다 — 반투명 유리판(rgba(255,255,255,.x))은 기준선의
      // .top-clovi-btn 처럼 쓰이는 자리가 따로 있다.
      return key === "255,255,255,1";
    });

    expect(painted.map((el) => el.tagName), "로고 뒤에 흰 판이 깔려 있다").toEqual([]);
  });

  it("어두운 상단바 위에서도 워드마크가 배경에 묻히지 않는다", () => {
    // 흰 판을 걷어 내는 대신, 기준선이 그 자리에 쓰는 반전 자산의 글자색을 쓴다
    // (app/static/brand/logo/clovirassist-logo-horizontal-dark.svg).
    const { container } = mount(<TopBrand onClick={() => {}} />);
    const fills = [...container.querySelectorAll("text")].map((el) => el.getAttribute("fill"));

    expect(fills.length, "워드마크 글자를 못 찾았다").toBeGreaterThan(0);
    // 브랜드 인디고(#536CD6)는 딥 인디고 상단바 위에서 읽히지 않는다 — 반전 자산이
    // 그 자리에 #B7C4FA 를 쓰는 이유다.
    expect(fills.map(rgbaKey)).not.toContain(rgbaKey("#536CD6"));
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 2. 상단 검색
// ════════════════════════════════════════════════════════════════════════════
describe("상단 검색", () => {
  it("높이·반지름·바탕·테두리가 기준선의 .top-search 와 같다", () => {
    mount(<TopSearch onOpen={() => {}} />);
    const style = getComputedStyle(screen.getByRole("button"));

    expect(toPx(style.height)).toBe(px(".top-search", "height"));
    expect(toPx(style.borderRadius)).toBe(px(".top-search", "border-radius"));
    expect(rgbaKey(style.backgroundColor)).toBe(rgbaKey(decl(".top-search", "background")));
    // 기준선: border: 1px solid rgba(255,255,255,.24)
    const [width, , color] = decl(".top-search", "border").split(/\s+/);
    expect(toPx(style.borderTopWidth)).toBe(Number.parseFloat(width));
    expect(rgbaKey(style.borderTopColor)).toBe(rgbaKey(color));
  });

  it("돋보기 아이콘이 들어갈 왼쪽 자리를 기준선만큼 비운다", () => {
    // 기준선: .top-search { padding: 0 10px 0 42px } — 왼쪽 42px 이 아이콘 자리다.
    mount(<TopSearch onOpen={() => {}} />);
    const style = getComputedStyle(screen.getByRole("button"));
    const [, right, , left] = decl(".top-search", "padding").split(/\s+/);

    expect(toPx(style.paddingLeft)).toBe(Number.parseFloat(left));
    expect(toPx(style.paddingRight)).toBe(Number.parseFloat(right));
  });

  it("안내 문구 크기가 기준선의 .top-search-placeholder 와 같다", () => {
    mount(<TopSearch onOpen={() => {}} />);
    const label = screen.getByTestId("top-search-placeholder");

    expect(toPx(getComputedStyle(label).fontSize))
      .toBe(px(".top-search-placeholder", "font-size"));
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 3. 클로비가 앉는 세 자리
// ════════════════════════════════════════════════════════════════════════════
describe("상단바 우측 클로비(.top-clovi-btn)", () => {
  it("반지름·바탕·테두리색이 기준선과 같다", () => {
    mount(<MascotTopButton onClick={() => {}} />);
    const style = getComputedStyle(screen.getByRole("button"));

    expect(toPx(style.borderRadius)).toBe(px(".top-clovi-btn", "border-radius"));
    expect(rgbaKey(style.backgroundColor)).toBe(rgbaKey(decl(".top-clovi-btn", "background")));
    const [, , color] = decl(".top-clovi-btn", "border").split(/\s+/);
    expect(rgbaKey(style.borderTopColor)).toBe(rgbaKey(color));
  });

  it("마스코트 크기가 기준선의 .top-clovi-btn .mascot-mini 와 같다", () => {
    mount(<MascotTopButton onClick={() => {}} />);
    const mini = screen.getByTestId("mascot-mini");

    expect(toPx(getComputedStyle(mini).width))
      .toBe(px(".top-clovi-btn .mascot-mini", "width"));
  });
});

describe("우하단 플로팅 버튼(.ai-fab)", () => {
  it("크기·반지름·안쪽 여백이 기준선과 같다", () => {
    mount(<MascotButton onClick={() => {}} />);
    const style = getComputedStyle(screen.getByRole("button"));

    expect(toPx(style.width)).toBe(px(".ai-fab", "width"));
    expect(toPx(style.borderRadius)).toBe(px(".ai-fab", "border-radius"));
    expect(toPx(style.padding)).toBe(px(".ai-fab", "padding"));
  });

  it("마스코트 크기가 기준선의 .ai-fab .mascot-mini 와 같다", () => {
    mount(<MascotButton onClick={() => {}} />);
    const mini = screen.getByTestId("mascot-mini");

    expect(toPx(getComputedStyle(mini).width))
      .toBe(px(".ai-fab .mascot-mini", "width"));
  });
});

describe("사이드바 하단 클로비(.sidebar-clovi)", () => {
  it("반지름과 안쪽 여백이 기준선과 같다", () => {
    mount(<MascotSidebarCard onClick={() => {}} />);
    const style = getComputedStyle(screen.getByRole("button"));
    const [vertical, horizontal] = decl(".sidebar-clovi", "padding").split(/\s+/);

    expect(toPx(style.borderRadius)).toBe(px(".sidebar-clovi", "border-radius"));
    expect(toPx(style.paddingTop)).toBe(Number.parseFloat(vertical));
    expect(toPx(style.paddingLeft)).toBe(Number.parseFloat(horizontal));
  });

  it("마스코트 크기가 기준선의 .sidebar-clovi .mascot-mini 와 같다", () => {
    mount(<MascotSidebarCard onClick={() => {}} />);
    const mini = screen.getByTestId("mascot-mini");

    expect(toPx(getComputedStyle(mini).width))
      .toBe(px(".sidebar-clovi .mascot-mini", "width"));
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 4. 셸이 실제로 그것을 쓰는가
// ════════════════════════════════════════════════════════════════════════════
/* 위 검사들은 조각을 하나씩 그려서 본다. 조각이 맞아도 **셸이 그 조각을 안 쓰면** 사용자
 * 화면은 그대로다 — 이 저장소가 여러 번 겪은 실패가 정확히 그것이다("파일은 고쳤는데
 * 배포된 화면은 그대로"). 그래서 마지막 한 검사는 진짜 셸을 띄운다. */
import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/me"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={USER_NAV} ariaLabel="사용자 메뉴" isUser showMenu>
                <div>본문</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("셸의 상단바", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
    window.matchMedia = (query) => ({
      matches: /min-width/.test(query),
      media: query,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, onchange: null,
      dispatchEvent: () => false,
    });
  });

  it("상단바 어디에도 불투명한 흰 판이 깔려 있지 않다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar, "상단바를 못 찾았다").toBeTruthy();
    const white = [...bar.querySelectorAll("*")].filter(
      (el) => rgbaKey(getComputedStyle(el).backgroundColor) === "255,255,255,1",
    );

    expect(white.length, "상단바에 흰 판이 남아 있다").toBe(0);
  });

  it("상단바가 기준선 치수의 검색 버튼을 그린다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    const search = screen.getByLabelText("통합 검색과 명령 열기");
    expect(toPx(getComputedStyle(search).height)).toBe(px(".top-search", "height"));
  });
});
