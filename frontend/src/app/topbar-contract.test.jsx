import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { createClovirTheme } from "../ui/theme.js";
import TopSearch from "./TopSearch.jsx";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

/* 상단바 계약 — 실제 셸이 그리는 것을 본다.
 *
 * ## 이 파일이 무엇을 대체했는가 (두 번)
 *
 * 1차. `topbar-baseline.test.jsx` 는 폐기된 목업(지시 64)에서 치수를 파싱해 왔다. 그 값들은
 *      **어두운 상단바를 전제**하고 있었다 — 높이 40 검색창, 반투명 남색 바탕, 흰 글자.
 *      D-141 로 chrome 이 캔버스 계열이 되면서 더는 맞지 않아 치수 대조를 버렸다.
 *
 * 2차 (W2, 이 개정). 그 자리에 남아 있던 단언 하나가 **"상단바가 그라디언트를 쓰지 않는다
 *      (chrome 은 발광하지 않는다)"** 였다. 그것은 접근성 단언이 아니라 D-141 의 **방향**
 *      단언이고, D-179 가 그 방향을 사용자 명령으로 뒤집었다. 그대로 두면 시험이 제품에
 *      Brand 가 생기는 것을 금지한다. 그래서 **삭제가 아니라 뒤집어 재작성**한다 — 같은
 *      자리에서 더 강한 형태로:
 *
 *        · 상단바의 채움은 사이드바 Gradient 의 **첫 stop** 이다(두 층이 한 물체로 읽힌다).
 *        · AI 워시는 상단바 **전체가 아니라** 우상단 앵커에만 있다(합성 대비 때문이다).
 *        · 셸 위 컨트롤은 캔버스 면이 아니라 chrome 반전 면에 앉는다(순백 구멍 금지).
 *        · chrome 과 캔버스의 경계선은 사이드바 열 **다음**부터 그어진다(L 을 자르지 않는다).
 *        · 본문의 위쪽 오프셋은 상단바 높이와 **같은 단위**다(넓은 화면에서 어긋나지 않는다).
 *
 * 색 대비의 절대값은 여기서 재지 않는다 — `ui/theme-contract.test.js` 가 팔레트 차원에서
 * 강조색 프리셋 전체 × 두 모드로 강제하고, `scripts/ui_qa` 하네스가 실제 브라우저에서 잰다.
 * 이 파일이 지키는 것은 **셸이 그 토큰을 실제로 읽는가**다(W1 이 토큰만 만들고 소비처가
 * 0이었던 F-W1R-39 가 정확히 그 구멍이다).
 */

const APPBAR_MIN_HEIGHT_PX = 52; // AppShell.APPBAR_HEIGHT.xs
const DRAWER_WIDTH_PX = 248;     // AppShell.DRAWER_WIDTH.xs

function withProviders(node) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>{node}</ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

/** `#RRGGBB` -> `rgb(r, g, b)` — jsdom 의 computed 값과 비교하려면 형식을 맞춰야 한다. */
function toRgb(hex) {
  const n = parseInt(String(hex).replace("#", ""), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}

/** emotion 이 이 요소에 붙인 클래스의 규칙 본문 — 중첩 media 블록까지 포함해 통째로.
 *
 *  jsdom 의 `getComputedStyle` 은 논리 속성(`inset-inline-start`)을 계산하지 않는다(빈 문자열).
 *  그렇다고 물리 속성(`left`)으로 바꿔 쓰면 이 저장소가 논리 속성으로 통일해 둔 방향
 *  (`borderInlineEnd`·`insetInlineStart`)을 시험 편의 때문에 깨는 것이다. 그래서 계산된
 *  값 대신 **선언**을 읽는다 — `brand-logo.test.jsx` 가 같은 이유로 쓰는 기법이다. */
function styleBlockOf(el) {
  const css = [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n");
  let out = "";
  for (const cls of [...el.classList].filter((c) => c.startsWith("css-"))) {
    let from = 0;
    for (;;) {
      const at = css.indexOf(`.${cls}{`, from);
      if (at < 0) break;
      let i = css.indexOf("{", at);
      let depth = 0;
      const start = i;
      for (; i < css.length; i += 1) {
        if (css[i] === "{") depth += 1;
        else if (css[i] === "}") { depth -= 1; if (depth === 0) { i += 1; break; } }
      }
      out += css.slice(start, i);
      from = i;
    }
  }
  return out;
}

/** `rem`/`px` 어느 쪽으로 선언됐든 **기본 단계의 px** 로 환산한다.
 *  셸 컨트롤은 4K 레버를 타려고 rem 으로 선언돼 있고(`styles/root.css` 의 기본 단계는 16px),
 *  jsdom 은 레이아웃을 안 하므로 선언값을 그대로 돌려준다. */
function cssPx(value) {
  const raw = String(value);
  const n = Number.parseFloat(raw);
  return raw.includes("rem") ? n * 16 : n;
}

/** 색 문자열에서 숫자만 뽑는다 — `rgba(255,255,255,.08)` 와 `rgba(255, 255, 255, 0.08)` 의
 *  표기 차이를 흡수하고 값만 비교하기 위해서다. */
function nums(value) {
  return (String(value).match(/[\d.]+/g) || []).map(Number);
}

describe("상단 검색", () => {
  it("실제로 검색되지 않는 '채팅'을 광고하지 않는다", () => {
    /* app/search/models.py 의 SEARCH_KINDS 는 채팅을 **의도적으로** 뺀다(1:1 DM 이 공용
       인덱스에 들어가면 멤버십 확인 한 줄이 틀려도 남의 DM 이 샌다 —
       tests/security/test_search_no_chat.py 가 그 경계를 못박는다). 안내 문구가 그것을
       검색된다고 말하면 안 된다. */
    render(withProviders(<TopSearch onOpen={() => {}} />));
    const placeholder = screen.getByTestId("top-search-placeholder");
    expect(placeholder.textContent).not.toMatch(/채팅/);
    expect(placeholder.textContent).toMatch(/티켓/);
    expect(placeholder.textContent).toMatch(/문서/);
  });

  it("상단바 안에 들어가고 누를 만한 크기다", () => {
    render(withProviders(<TopSearch onOpen={() => {}} />));
    const button = screen.getByLabelText("통합 검색과 명령 열기");
    const h = cssPx(getComputedStyle(button).height);
    expect(h).toBeGreaterThanOrEqual(28);
    expect(h).toBeLessThan(APPBAR_MIN_HEIGHT_PX);
  });

  it("입력처럼 보이지만 실제로는 버튼이다 (결과가 뜰 자리가 상단바에 없다)", () => {
    render(withProviders(<TopSearch onOpen={() => {}} />));
    const button = screen.getByLabelText("통합 검색과 명령 열기");
    expect(button.tagName).toBe("BUTTON");
  });

  /* W2 신규. 이 컨트롤이 이 저장소에서 **두 번** 틀린 자리다 — 리터럴(어두운 상단바 전제)
     -> 캔버스 토큰(밝은 상단바 전제). 세 번째를 막는 것은 값이 아니라 계열이다. */
  it("검색 면이 chrome 반전 트랙이다 — 캔버스 판(순백)이 아니다", () => {
    render(withProviders(<TopSearch onOpen={() => {}} />));
    const p = createClovirTheme("light").palette;
    const bg = getComputedStyle(screen.getByLabelText("통합 검색과 명령 열기")).backgroundColor;
    expect(nums(bg)).toEqual(nums(p.chrome.track));
    expect(bg).not.toBe(toRgb(p.background.plate));
  });

  it("폭과 높이가 rem 이다 — 4K 루트 폰트사이즈 레버를 함께 탄다 (R-6: 해상도 전용 px 금지)", () => {
    render(withProviders(<TopSearch onOpen={() => {}} />));
    const cs = getComputedStyle(screen.getByLabelText("통합 검색과 명령 열기"));
    expect(cs.flex).toMatch(/rem/);
    expect(cs.flex).not.toMatch(/\d+px/);
    /* 셸의 **틀**은 브레이크포인트로 커지는데(상단바 52→68, 사이드바 248→320) 컨트롤만
       px 로 고정되면 4K 에서 비율이 어긋난다 — 실측 1920→3840 에서 틀 1.31× vs inset 1.00×. */
    expect(cs.height, "높이가 px 로 고정되면 4K 에서 틀만 자란다").toMatch(/rem/);
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 셸이 실제로 그것을 쓰는가
// ════════════════════════════════════════════════════════════════════════════
/* 조각이 맞아도 **셸이 그 조각을 안 쓰면** 사용자 화면은 그대로다 — 이 저장소가 여러 번
 * 겪은 실패가 정확히 그것이다("파일은 고쳤는데 배포된 화면은 그대로", 그리고 W1 의
 * "토큰은 만들었는데 소비처가 0"). */
import { AppShell } from "./AppShell.jsx";
import { NAV, USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function renderShell(path = "/me") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
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

/** 관리자 콘솔 셸 — 사이드바 '메뉴 찾기' 는 `showFilter={!isUser}` 라 여기서만 렌더된다. */
function renderAdminShell(path = "/dashboard") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={NAV} ariaLabel="관리 메뉴" showMenu>
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

  /* 옛 단언("그라디언트를 쓰지 않는다")을 뒤집어 재작성한 자리. 지키는 불변식이
     "chrome 은 무채색이다"에서 "chrome 은 하나의 물체다"로 바뀐다. */
  it("상단바 채움이 사이드바 Gradient 의 첫 stop 이다 — 두 층이 한 물체로 읽힌다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar, "상단바를 못 찾았다").toBeTruthy();
    const p = createClovirTheme("light").palette;
    expect(getComputedStyle(bar).backgroundColor).toBe(toRgb(p.chrome.shellTop));
    // 팔레트 쪽 항등식은 theme-contract 가 이미 단언한다 — 여기서는 **제품이 그 값을
    // 읽는다**는 것까지 확인한다.
    expect(p.chrome.shellImage.toUpperCase()).toContain(p.chrome.shellTop.toUpperCase());
  });

  it("AI 워시는 상단바 전체가 아니라 우상단 앵커에만 있다 (합성 대비 때문이다)", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const bar = document.querySelector(".MuiAppBar-root");
    const anchor = document.querySelector('[data-shell-region="ai"]');
    expect(anchor, "AI 앵커를 못 찾았다").toBeTruthy();
    const barImage = getComputedStyle(bar).backgroundImage;
    expect(barImage === "" || barImage === "none").toBe(true);
    expect(getComputedStyle(anchor).backgroundImage).toContain("radial-gradient");
  });

  it("AI 앵커 안에 클로비·알림·계정이 함께 산다 (PLAN «Chrome 설계»가 명명한 집합)", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const anchor = document.querySelector('[data-shell-region="ai"]');
    expect(anchor.querySelector('[aria-label="클로비 AI 도우미 열기"]')).toBeTruthy();
    expect(anchor.querySelector('[aria-label^="알림"]')).toBeTruthy();
    expect(anchor.querySelector('[aria-haspopup="menu"]')).toBeTruthy();
  });

  it("사이드바가 Gradient 를 실제로 읽는다 — 평평한 단색이 아니다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const paper = document.querySelector(".MuiDrawer-paper");
    expect(paper, "사이드바를 못 찾았다").toBeTruthy();
    const image = getComputedStyle(paper.firstElementChild).backgroundImage;
    expect(image).toContain("linear-gradient");
    expect(image).toContain("#28336F");
  });

  it("chrome/캔버스 경계선이 사이드바 열 다음부터 그어진다 — L 을 한가운데서 자르지 않는다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const seam = screen.getByTestId("shell-seam");
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar.contains(seam), "경계선이 상단바 안에 없다").toBe(true);
    const block = styleBlockOf(seam);
    expect(block, "경계선의 스타일 선언을 못 찾았다").toContain("inset-inline-start");
    expect(block).toMatch(new RegExp(`inset-inline-start:\\s*${DRAWER_WIDTH_PX}px`));
    // 전폭으로 되돌아가면(= 하우징을 자르던 예전 상태) 여기서 걸린다.
    expect(block).not.toMatch(/inset-inline-start:\s*0(px)?\s*[;}]/);
    // 상단바 자신이 전폭 테두리를 되찾으면(= 예전 상태) 이 단언이 걸린다.
    expect(Number.parseFloat(getComputedStyle(bar).borderBottomWidth) || 0).toBe(0);
  });

  it("브랜드 자리에 자기 배경(판)이 없다 — 로고가 상단바 위에 그대로 얹힌다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const brand = screen.getByLabelText("홈으로");
    /* MUI v7 은 text variant 배경을 `var(--variant-textBg)`(런타임 투명)로 낸다. jsdom 은
       그 변수를 풀지 못하므로 색 문자열 대신 **variant 자체**를 본다 — 판이 깔리는 것은
       contained/outlined 이고, 그 둘이 아니면 자기 배경이 없다는 뜻이다. */
    expect(brand.className).toMatch(/MuiButton-text/);
    expect(brand.className).not.toMatch(/MuiButton-(contained|outlined)/);
  });

  /* 상단바 락업은 두 줄이다. 부제는 ClovirAssist 바로 아래, 같은 폭으로 붙는다.
     옆에 세로 구분선으로 떼어 두지 않는다. */
  it("상단바 로고는 두 줄 락업이다 — 부제가 워드마크 아래에 있다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const bar = document.querySelector(".MuiAppBar-root");
    const lockup = bar.querySelector('[role="img"][aria-label*="Smart Workspace Assistant"]');
    expect(lockup, "로고의 접근 가능한 이름에서 태그라인이 사라졌다").toBeTruthy();
    const subtitle = [...lockup.querySelectorAll("span")].find(
      (el) => el.textContent === "SMART WORKSPACE ASSISTANT",
    );
    expect(subtitle, "락업 안에 부제가 없다").toBeTruthy();
    expect(subtitle.getAttribute("aria-hidden")).toBe("true");
    const wordmark = lockup.querySelector("svg.wordmark");
    expect(subtitle.parentElement).toBe(wordmark.parentElement);
    // 상단바 흐름에 세로 구분선 옆 부제를 따로 두지 않는다.
    const extras = [...bar.querySelectorAll("span")].filter(
      (el) => el.textContent === "SMART WORKSPACE ASSISTANT" && !lockup.contains(el),
    );
    expect(extras).toHaveLength(0);
  });

  it("상단바가 검색 버튼을 실제로 그린다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar.querySelector('[aria-label="통합 검색과 명령 열기"]')).toBeTruthy();
  });

  it("검색이 브랜드 칸과 AI 앵커 사이 가운데에 선다 — 양옆에 신축 스페이서가 있다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const search = screen.getByLabelText("통합 검색과 명령 열기");
    const row = search.parentElement;
    const kids = [...row.children];
    const i = kids.indexOf(search);
    const grows = (el) => Number.parseFloat(getComputedStyle(el).flexGrow || "0");
    expect(i, "검색 앞에 아무것도 없다").toBeGreaterThan(0);
    expect(grows(kids[i - 1]), "검색 왼쪽 스페이서가 안 늘어난다").toBe(1);
    expect(grows(kids[i + 1]), "검색 오른쪽 스페이서가 안 늘어난다").toBe(1);
  });

  // PA-RC-0020: 사이드바 카드·우하단 FAB 을 없애 "클로비 AI 도우미 열기" aria-label 을
  // 가진 요소는 이제 상단바 버튼 하나뿐이다.
  it("AI-57: /chat 에서는 상단바 클로비 버튼을 안 그린다 — 이미 전체화면 채팅이 열려 있다", async () => {
    renderShell("/chat");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    expect(screen.queryAllByLabelText("클로비 AI 도우미 열기")).toHaveLength(0);
  });

  it("/chat 이 아닌 화면에서는 상단바 클로비 버튼을 그대로 그린다 (마스코트는 제품 정체성이다)", async () => {
    renderShell("/me");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    expect(screen.getAllByLabelText("클로비 AI 도우미 열기")).toHaveLength(1);
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar.querySelector('[aria-label="클로비 AI 도우미 열기"]'), "상단바 안에 클로비 버튼이 없다").toBeTruthy();
  });

  it("상단바 높이가 테마가 정한 값이고, 그 안에 검색·벨·사용자 영역이 함께 들어간다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar.querySelector('[aria-label="통합 검색과 명령 열기"]')).toBeTruthy();
    // 벨은 알림 개수에 따라 aria-label 이 바뀌므로 접두사로 찾는다.
    expect(bar.querySelector('[aria-label^="알림"]')).toBeTruthy();
  });

  /* R-6. 상단바는 px 로 높이를 정하고 본문은 spacing(rem)으로 그만큼 내려오고 있었다.
     루트 폰트사이즈가 2200/3000 에서 커지므로 **넓은 화면에서만** 어긋난다 — 실측 2560 에서
     7.5px, 3840 에서 17px 의 죽은 띠. 두 축을 같은 단위로 묶는다. */
  it("본문의 위쪽 오프셋이 상단바 높이와 같은 단위·같은 값이다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const main = document.getElementById("main-content");
    expect(getComputedStyle(main).paddingTop).toBe(`${APPBAR_MIN_HEIGHT_PX}px`);
  });

  /* 소스 철자 검사(`shell-surface-contract.test.js`)만으로는 부족하다 — 그 검사는 한 번
     **철자를 좁게 잡아 아무것도 못 막은 전력**이 있다(독립 검수자가 되돌림 변이로 실증했다).
     그래서 같은 계약을 **렌더 후 실제 색**으로 한 번 더 확인한다. 소스가 어떤 철자를 쓰든
     화면에 나온 색은 하나다. */
  it("셸 위 컨트롤 넷이 전부 chrome 반전 트랙 위에 앉는다 (렌더 후 실제 색)", async () => {
    renderAdminShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const p = createClovirTheme("light").palette;
    const track = nums(p.chrome.track);
    const plate = toRgb(p.background.plate);
    const targets = [
      ["상단바 검색", screen.getByLabelText("통합 검색과 명령 열기")],
      ["사이드바 메뉴 찾기", document.querySelector("#app-sidebar .MuiOutlinedInput-root")],
      ["클로비 알약", document.querySelector('.MuiAppBar-root [aria-label="클로비 AI 도우미 열기"]')],
      ["계정 아바타", document.querySelector(".MuiAppBar-root .MuiAvatar-root")],
    ];
    for (const [label, el] of targets) {
      expect(el, `${label} 를 못 찾았다`).toBeTruthy();
      const bg = getComputedStyle(el).backgroundColor;
      expect(nums(bg), `${label} 가 chrome.track 이 아니다 (${bg})`).toEqual(track);
      expect(bg, `${label} 가 캔버스 판으로 되돌아갔다`).not.toBe(plate);
    }
  });

  it("본문 열이 이름을 갖는다 — 폭 캡을 소유한 층을 하네스가 잴 수 있어야 한다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const main = document.getElementById("main-content");
    const column = main.querySelector(".c-content");
    expect(column, "`.c-content` 를 못 찾았다 — narrow_main 프로브가 열을 못 잰다").toBeTruthy();
    expect(column.contains(screen.getByText("본문"))).toBe(true);
  });
});

describe("테마가 chrome 색의 정본이다", () => {
  it.each(["light", "dark"])("%s — 사이드바·상단바가 같은 chrome 재료를 쓴다", (mode) => {
    const p = createClovirTheme(mode).palette;
    // 상단바(AppBar)는 `chrome.shellTop`, 사이드바는 `chrome.shell` + `chrome.shellImage`.
    expect(p.sidebar.bg).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(p.sidebar.line).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(p.chrome.shellTop).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(p.chrome.shellImage).toContain(p.chrome.shellTop);
  });
});
