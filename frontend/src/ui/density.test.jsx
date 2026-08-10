import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import { baseline, lastDeclaration } from "./baselineTokens.js";
import { createClovirTheme } from "./theme.js";
import { Card, StatCard } from "./kit.jsx";
import {
  BASELINE_CONTENT_FILLS, BASELINE_CONTENT_PADDING_PX, BASELINE_PX, BASELINE_TRACKS,
  CARD_PADDING, SECTION_GAP, STAT_CARD_PADDING, STAT_VALUE_FONT_SIZE,
} from "./density.js";
import { DashSection } from "./adminKit.jsx";
import { DETAIL_GRID } from "../screens/Ticket.jsx";
import { DOC_DETAIL_GRID } from "../screens/TeamDoc.jsx";
import { NEW_TICKET_GRID } from "../screens/MyTickets.jsx";
import { STAT_GRID as HOME_STAT_GRID } from "../screens/Home.jsx";
import { PEOPLE_GRID } from "../screens/Sprint.jsx";

/* 레이아웃·밀도 기준선 대조.
 *
 * ## 왜 이 검사가 필요한가
 *
 * 설계 기준선(`design/baseline/preview-standalone.html`)이 저장소 안에 있는데도 화면 작업이
 * 그 파일을 열지 않고 진행됐고, 배포 화면을 본 사용자가 "설계한 대로 된 게 하나도 없다"고
 * 했다. 토큰(색)만 맞추고 **치수**는 아무도 안 봤기 때문이다.
 *
 * 그래서 이 검사는 값을 손으로 적지 않는다. **기준선 HTML 을 실제로 열어** 선택자로 찾아간
 * 선언을 읽고, 그것과 우리 상수를 비교한다. 기준선이 바뀌면 검사가 먼저 빨개진다.
 *
 * ## 무엇을 잡으려고 만들었나 (사용자가 배포 화면에서 지적한 것)
 *
 *   1) "새 티켓 / 티켓 상세 / 문서 상세가 왼쪽으로 쏠려있다. 페이지 전체에 정보가 담기는 게
 *      아니라" — 격자 트랙의 상한이 전부 고정값(`minmax(0,78ch) minmax(18rem,26rem)`)이면
 *      격자는 컨테이너가 아무리 넓어도 그 합만큼만 차지하고 오른쪽을 빈 채 남긴다.
 *      `mx:"auto"` 로는 안 고쳐진다(가운데로 옮길 뿐 채우지 않는다). 트랙에 `fr` 이 하나도
 *      없으면 실패시킨다.
 *   2) "카드가 담은 정보에 비해 너무 크다" — 카드 안쪽 여백이 기준선(20px / 17·18px)보다
 *      컸다(24px). 실제로 그려진 CSS 에서 읽어 비교한다.
 *   3) "그리드 높이가 너무 크다" — 카드 수를 나누어떨어지지 않는 열 수(6장을 4열·5열)는
 *      마지막 줄에 빈 칸을 남기고 줄을 하나 더 만든다.
 *
 * ## jsdom 한계
 *
 * jsdom 은 레이아웃을 계산하지 않는다(모든 폭이 0이다). 그래서 "실제로 몇 px 로 그려졌나"는
 * 물어볼 수 없다. 대신 emotion 이 내보낸 CSS 규칙 자체를 읽는다 — `new-ticket-layout.test.jsx`
 * 가 쓰는 것과 같은 수법이고, 판정 규칙이 어디에 있는지를 보는 것이라 오히려 안정적이다.
 */

/* 기준선 파서는 `baselineTokens.js` 를 그대로 쓴다 — 색 대조(theme-baseline.test.js)와
 * **같은 파서**여야 한다. 파서가 둘이면 한쪽만 @media 를 건너뛰거나 한쪽만 뒤 규칙을
 * 우선하는 식으로 갈라지고, 그때부터 두 검사는 서로 다른 기준선을 보게 된다. */
const { rules: RULES } = baseline();

/* 같은 선택자가 여러 번 나오면 **뒤에 온 것이 이긴다**(CSS 그대로).
 * 기준선은 파일 뒤쪽에 "2026-07-31 full rebuild" 절이 있어서 `.kpi-card`·`.content` 같은
 * 선택자가 두 번 나온다 — 앞쪽만 읽으면 이미 폐기된 값을 기준으로 삼게 된다. */
function baselineDecl(selector, prop) {
  const found = lastDeclaration(RULES, selector, prop);
  if (found === undefined) throw new Error(`기준선에 '${selector} { ${prop} }' 가 없다`);
  return found;
}

function baselinePx(selector, prop) {
  const raw = baselineDecl(selector, prop);
  const nums = raw.match(/-?[\d.]+px/g);
  if (!nums) throw new Error(`기준선 '${selector} { ${prop}: ${raw} }' 에 px 값이 없다`);
  return nums.map((n) => parseFloat(n));
}

/* 기준선 :root 의 커스텀 프로퍼티. */
function baselineVar(name) {
  return baselineDecl(":root", `--${name}`);
}

// ── 1. 상수가 기준선 파일과 같은가 ────────────────────────────────────────────

describe("density.js 의 값은 기준선 파일에서 온다", () => {
  it("카드·지표 카드·타일의 여백이 기준선과 같다", () => {
    expect(baselinePx(".card.pad", "padding")).toEqual([BASELINE_PX.cardPadding]);
    expect(baselinePx(".detail-block", "padding")).toEqual([BASELINE_PX.detailBlockPadding]);
    expect(baselinePx(".kpi-card", "padding")).toEqual([BASELINE_PX.kpiPaddingY, BASELINE_PX.kpiPaddingX]);
    expect(baselinePx(".health-card", "padding")).toEqual([BASELINE_PX.healthCardPadding]);
  });

  it("글자·간격·셸 치수가 기준선과 같다", () => {
    expect(baselinePx(".kpi-value", "font-size")).toEqual([BASELINE_PX.kpiValueFontSize]);
    expect(baselinePx(".kpi-label", "font-size")).toEqual([BASELINE_PX.kpiLabelFontSize]);
    expect(baselinePx(".grid", "gap")).toEqual([BASELINE_PX.gridGap]);
    expect(baselinePx(".admin-health", "gap")).toEqual([BASELINE_PX.healthGridGap]);
    expect(baselinePx(".section", "margin-top")).toEqual([BASELINE_PX.sectionGap]);
    expect(baselinePx(".card-head", "margin-bottom")).toEqual([BASELINE_PX.cardHeadGap]);
    expect(baselineVar("topbar-h")).toBe(`${BASELINE_PX.topbarHeight}px`);
    expect(baselineVar("sidebar-w")).toBe(`${BASELINE_PX.sidebarWidth}px`);
  });

  /* 기준선의 본문 열은 폭을 남기지 않는다. 앞쪽 `.content { width: min(1720px, 100%) }` 만
     읽으면 "1720 에서 멈춘다"고 잘못 결론 내린다 — 파일 뒤쪽 최종 절이 100% 로 덮어쓴다.
     마지막 선언을 읽는지 확인하는 검사이기도 하다. */
  it("기준선 본문 열은 폭을 남기지 않는다(뒤쪽 선언이 이긴다)", () => {
    expect(BASELINE_CONTENT_FILLS).toBe(true);
    expect(baselineDecl(".content", "width")).toBe("100%");
    expect(baselineDecl(".content", "max-width")).toBe("100%");
    expect(baselinePx(".content", "padding")).toEqual([
      BASELINE_CONTENT_PADDING_PX.top,
      BASELINE_CONTENT_PADDING_PX.xMin,
      BASELINE_CONTENT_PADDING_PX.xMax,
      BASELINE_CONTENT_PADDING_PX.bottom,
    ]);
  });

  it("격자 트랙이 기준선과 같다(공백·앞자리 0만 다듬는다)", () => {
    const norm = (s) => s.replace(/\s+/g, "").replace(/(^|[(,])\.(\d)/g, "$10.$2");
    expect(norm(baselineDecl(".ticket-layout", "grid-template-columns"))).toBe(norm(BASELINE_TRACKS.detail));
    expect(norm(baselineDecl(".grid.two", "grid-template-columns"))).toBe(norm(BASELINE_TRACKS.two));
    expect(norm(baselineDecl(".grid.kpi", "grid-template-columns"))).toBe(norm(BASELINE_TRACKS.kpi));
    expect(norm(baselineDecl(".grid.three", "grid-template-columns"))).toBe(norm(BASELINE_TRACKS.three));
    expect(norm(baselineDecl(".admin-health", "grid-template-columns"))).toBe(norm(BASELINE_TRACKS.health));
  });
});

// ── 2. 왼쪽 쏠림: 격자가 컨테이너를 채우는가 ─────────────────────────────────

/* 트랙 목록에 `fr` 이 하나도 없으면 그 격자는 컨테이너를 채우지 못한다. */
function fills(track) {
  return /\dfr\b/.test(track);
}

/* sx 의 `gridTemplateColumns` 는 문자열이거나 브레이크포인트 객체다. 둘 다 받아
 * (브레이크포인트, 트랙) 목록으로 편다. */
function trackEntries(sx) {
  const v = sx.gridTemplateColumns;
  return typeof v === "string" ? [["(기본)", v]] : Object.entries(v);
}

describe("상세·폼 화면의 격자는 본문 폭을 채운다(왼쪽 쏠림 방지)", () => {
  const grids = [
    ["티켓 상세", DETAIL_GRID],
    ["문서 상세", DOC_DETAIL_GRID],
    ["새 티켓", NEW_TICKET_GRID],
  ];

  it.each(grids)("%s 의 모든 트랙 조합에 fr 이 있다", (name, sx) => {
    const stuck = trackEntries(sx).filter(([, track]) => !fills(track));
    expect(stuck.map(([bp, track]) => `${bp}: ${track}`), `${name}: 상한이 전부 고정값인 트랙은 오른쪽을 비운다`).toEqual([]);
  });

  it("티켓 상세와 문서 상세는 기준선 .ticket-layout 트랙을 쓴다", () => {
    const detail = BASELINE_TRACKS.detail;
    expect(Object.values(DETAIL_GRID.gridTemplateColumns)).toContain(detail);
    expect(Object.values(DOC_DETAIL_GRID.gridTemplateColumns)).toContain(detail);
  });

  it("새 티켓은 기준선 .grid.two 트랙을 쓴다", () => {
    expect(Object.values(NEW_TICKET_GRID.gridTemplateColumns)).toContain(BASELINE_TRACKS.two);
  });
});

// ── 3. 카드 밀도: 그려진 CSS 의 여백이 기준선과 같은가 ────────────────────────

/* emotion 이 <style> 에 넣은 규칙 중 이 요소의 클래스에 걸린 **조건 없는** 선언을 읽는다.
 * (`new-ticket-layout.test.jsx` 의 rulesFor 를 이 파일에 필요한 만큼만 줄인 것) */
function baseDecl(el, prop) {
  const classes = [...el.classList].filter((c) => c.startsWith("css-"));
  const css = [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n");
  let found = null;
  let i = 0;
  while (i < css.length) {
    const brace = css.indexOf("{", i);
    if (brace === -1) break;
    const head = css.slice(i, brace).trim();
    let depth = 1;
    let j = brace + 1;
    while (j < css.length && depth > 0) {
      if (css[j] === "{") depth += 1;
      else if (css[j] === "}") depth -= 1;
      j += 1;
    }
    // @media 등 조건부 규칙은 보지 않는다 — 기본 밀도를 재는 검사다.
    if (!head.startsWith("@") && head.split(",").some((s) => classes.includes(s.trim().replace(/^\./, "")))) {
      /* 같은 규칙 안에 같은 속성이 여러 번 나올 수 있다 — emotion 은 MUI 기본 스타일과 sx 를
         **한 클래스로 합치기** 때문에 `font-size` 가 두 번 찍힌다(먼저 body1, 나중에 sx).
         첫 번째를 읽으면 sx 로 덮어쓴 값을 못 보고 엉뚱한 값이 나온다. 마지막이 이긴다. */
      const body = css.slice(brace + 1, j - 1);
      const re = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, "g");
      let m;
      while ((m = re.exec(body)) !== null) found = m[1].trim();
    }
    i = j;
  }
  return found;
}

function withTheme(node) {
  return render(<ThemeProvider theme={createClovirTheme()}>{node}</ThemeProvider>);
}

describe("카드 밀도는 기준선 치수를 쓴다", () => {
  it("Card 의 안쪽 여백이 기준선 .card.pad(20px) 와 같다", () => {
    withTheme(<Card>내용</Card>);
    const card = document.querySelector(".MuiCard-root");
    expect(baseDecl(card, "padding")).toBe(CARD_PADDING);
  });

  it("DashSection 의 섹션 간격이 기준선 .section(24px) 과 같다", () => {
    withTheme(<DashSection title="오늘"><div>본문</div></DashSection>);
    const section = document.querySelector("section");
    expect(baseDecl(section, "margin-bottom")).toBe(SECTION_GAP);
  });

  it("StatCard 의 안쪽 여백과 값 글자 크기가 기준선 .kpi-card / .kpi-value 와 같다", () => {
    withTheme(<StatCard value={3} label="오늘 마감" />);
    const tile = document.querySelector(".k-stat");
    expect(baseDecl(tile, "padding")).toBe(STAT_CARD_PADDING);
    const value = screen.getByText("3");
    expect(baseDecl(value, "font-size")).toBe(STAT_VALUE_FONT_SIZE);
  });
});

// ── 4. 격자 높이: 마지막 줄에 빈 칸을 남기지 않는가 ──────────────────────────

function columnCount(track) {
  const repeat = /^repeat\(\s*(\d+)\s*,/.exec(track.trim());
  if (repeat) return Number(repeat[1]);
  return track.replace(/\([^)]*\)/g, "x").split(/\s+/).filter(Boolean).length;
}

describe("개수가 고정된 카드 줄은 마지막 줄에 빈 칸을 남기지 않는다", () => {
  /* 홈의 지표 줄은 항상 정확히 6장이다(오늘 마감·지연·진행 중·7일 내 마감·안 읽은 알림·
     안 읽은 채팅 또는 막힘). 4열이면 4+2, 5열이면 5+1 이라 오른쪽이 빈 채 줄만 하나 늘어난다. */
  it("홈 지표 줄(6장)의 모든 열 수가 6을 나누어떨어뜨린다", () => {
    const bad = trackEntries(HOME_STAT_GRID)
      .map(([bp, track]) => [bp, columnCount(track)])
      .filter(([, cols]) => 6 % cols !== 0)
      .map(([bp, cols]) => `${bp}: ${cols}열 → 마지막 줄에 ${cols - (6 % cols)}칸이 빈다`);
    expect(bad).toEqual([]);
  });

  /* 담당자 현황은 이름 + 숫자 셋짜리 작은 타일이다. 기준선에서 그만한 정보가 놓이는 자리는
     `.admin-health`(5열)이지 `.card.pad` 급 3열 카드가 아니다. */
  it("담당자 현황은 기준선 .admin-health 만큼 촘촘하게 편다", () => {
    const widest = Math.max(...trackEntries(PEOPLE_GRID).map(([, track]) => columnCount(track)));
    expect(widest).toBe(columnCount(BASELINE_TRACKS.health));
  });
});
