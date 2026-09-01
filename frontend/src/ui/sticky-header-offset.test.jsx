import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

/* 고정 열 이름은 **상단바 아래**에 선다.
 *
 * 이 앱의 스크롤 창은 윈도다 — `AppShell` 은 본문(`main#main-content`)에 `overflow` 를 안
 * 준다. 그래서 MUI `stickyHeader` 가 붙이는 `top: 0` 은 «뷰포트 맨 위» 이고, 거기에는
 * `position: fixed` 인 AppBar 가 이미 앉아 있다. 그 상태에서는 열 이름을 보려고 켠 sticky 가
 * 정확히 열 이름을 가린다 — 그리고 «`position` 이 sticky 인가» 만 재는 검사는 그때도 통과한다
 * (D-347 이 같은 부류를 한 번 적었다).
 *
 * 그래서 여기서 재는 것은 **값**이다: 표의 머리행 오프셋과 셸의 상단바 높이가 같은 토큰에서
 * 나오는가. 둘이 갈라지는 순간(누가 한쪽만 고치는 순간) 이 시험이 빨개진다. */

import { DataTable, ScrollArea } from "./kit.jsx";
import { APPBAR_HEIGHT, BREAKPOINTS, STICKY_TOP_VAR, createClovirTheme, stickyTopSx } from "./theme.js";

const COLUMNS = [
  { key: "title", label: "제목", type: "title" },
  { key: "state", label: "상태", type: "status" },
];
const ROWS = [{ title: "가", state: "완료" }, { title: "나", state: "계획" }];

function renderTable(props) {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.title} {...props} />
    </ThemeProvider>,
  );
}

/* 오프셋의 대체값(윈도가 스크롤 창일 때)은 상단바 높이다. 실제 값은 CSS 변수라 계산식을
   대조한다 — 변수를 누가 박았는지에 따라 답이 달라지는 것이 이 설계의 핵심이다. */
const fallbackTop = (h, extra = 0) => `calc(var(${STICKY_TOP_VAR}, ${h}px) + ${extra}px)`;

describe("고정 열 이름의 top 오프셋", () => {
  it("stickyTopSx 는 셸의 상단바 높이에서 파생된다 — 리터럴을 따로 들지 않는다", () => {
    const sx = stickyTopSx();
    expect(sx.top).toBe(fallbackTop(APPBAR_HEIGHT.xs));
    expect(sx[`@media (min-width:${BREAKPOINTS.xxl}px)`].top).toBe(fallbackTop(APPBAR_HEIGHT.xxl));
    expect(sx[`@media (min-width:${BREAKPOINTS.uhd}px)`].top).toBe(fallbackTop(APPBAR_HEIGHT.uhd));
  });

  it("추가 오프셋을 주면 세 단 전부에 더해진다 — 한 단만 더하면 넓은 화면에서만 어긋난다", () => {
    const sx = stickyTopSx(8);
    expect(sx.top).toBe(fallbackTop(APPBAR_HEIGHT.xs, 8));
    expect(sx[`@media (min-width:${BREAKPOINTS.xxl}px)`].top).toBe(fallbackTop(APPBAR_HEIGHT.xxl, 8));
    expect(sx[`@media (min-width:${BREAKPOINTS.uhd}px)`].top).toBe(fallbackTop(APPBAR_HEIGHT.uhd, 8));
  });

  it("stickyHeader 를 켠 표의 머리 칸이 그 값을 실제로 받는다", () => {
    renderTable({ stickyHeader: true });
    const th = screen.getByText("제목").closest("th");
    expect(th).toBeTruthy();
    expect(window.getComputedStyle(th).top).toBe(fallbackTop(APPBAR_HEIGHT.xs));
  });

  it("stickyHeader 를 안 켠 표는 오프셋을 안 받는다 — 안 쓰는 화면은 한 픽셀도 안 바뀐다", () => {
    renderTable({});
    const th = screen.getByText("제목").closest("th");
    expect(window.getComputedStyle(th).top).not.toBe(fallbackTop(APPBAR_HEIGHT.xs));
  });
});

/* 🔴 **상단바 높이가 정답인 것은 스크롤 창이 윈도일 때뿐이다.**
 *
 * 표가 자기 스크롤 칸 안에 있으면(`ScrollArea` — 홈의 업무 판이 그렇다) 그 칸 위쪽에는
 * AppBar 가 없다. 그런데도 52px 를 주면 열 이름이 칸 위쪽에서 52px 내려온 자리에 붙박이고,
 * 그 위로 데이터 행이 굴러 올라가 **열 이름과 겹쳐 그려진다** — 실측(2026-09-01 · 홈
 * 「지연 14건」)에서 머리글 「티켓 · 제목 · 상태」 위로 첫 행이 그대로 비쳤다.
 *
 * 「position 이 sticky 인가」만 재는 검사는 그때도 통과한다(D-347 과 같은 부류). 그래서
 * 여기서 재는 것은 **스크롤 칸이 안쪽에 무엇을 알리는가** 다. */
describe("스크롤 칸 안의 고정 열 이름", () => {
  it("ScrollArea 는 자기 위에 상단바가 없다고 안쪽에 선언한다", () => {
    render(
      <ThemeProvider theme={createClovirTheme()}>
        <ScrollArea ariaLabel="목록">
          <DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.title} stickyHeader />
        </ScrollArea>
      </ThemeProvider>,
    );
    const box = document.querySelector(".k-scrollarea");
    expect(box).toBeTruthy();
    expect(window.getComputedStyle(box).getPropertyValue(STICKY_TOP_VAR).trim()).toBe("0px");
    // 머리 칸의 top 은 그 변수를 읽는 계산식이다 — 칸이 0 을 박았으므로 칸 위쪽에 붙는다.
    const th = screen.getByText("제목").closest("th");
    expect(window.getComputedStyle(th).top).toBe(fallbackTop(APPBAR_HEIGHT.xs));
  });

  it("스크롤 칸 밖에서는 아무도 그 변수를 박지 않는다 — 대체값(상단바 높이)이 그대로 선다", () => {
    renderTable({ stickyHeader: true });
    const th = screen.getByText("제목").closest("th");
    expect(window.getComputedStyle(th).getPropertyValue(STICKY_TOP_VAR).trim()).toBe("");
  });
});

/* 넘침을 바깥으로 넘기는 것은 **표가 칸 안에 들어갈 때만**이다.
 *
 * CSS 는 `overflow-x: auto; overflow-y: visible` 을 허용하지 않는다 — 한쪽이 `visible` 이
 * 아니면 나머지도 `auto` 로 계산된다. 그래서 「가로는 이 상자가 굴리고 세로는 바깥에 넘긴다」
 * 가 한 요소에서 성립하지 않고, 둘 중 하나를 골라야 한다. 넓은 표에까지 넘김을 고르면
 * 표가 판 밖으로 삐져나와 **옆 사이드바 위에 겹쳐 그려진다** — 실브라우저(문서 목록,
 * 1600px)에서 130px 삐져나온 것을 쟀다. 유닛 시험이 「sticky 인가」만 보면 이 부류는 안 보인다. */
describe("표가 칸보다 넓으면 가로 스크롤을 이 상자가 맡는다", () => {
  const rect = (width) => ({ width, height: 0, top: 0, left: 0, right: width,
                             bottom: 0, x: 0, y: 0, toJSON: () => ({}) });

  function renderWithWidths({ tableWidth, boxWidth }) {
    vi.spyOn(HTMLTableElement.prototype, "getBoundingClientRect")
      .mockReturnValue(rect(tableWidth));
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(boxWidth);
    renderTable({ stickyHeader: true });
    return document.querySelector(".MuiTableContainer-root");
  }

  afterEach(() => { vi.restoreAllMocks(); });

  it("표가 들어가면 넘침을 바깥에 넘긴다 — 고정 열 이름이 바깥 창을 따라온다", () => {
    const box = renderWithWidths({ tableWidth: 500, boxWidth: 800 });
    expect(window.getComputedStyle(box).overflowX).toBe("visible");
  });

  it("표가 칸보다 넓으면 안 넘긴다 — 안 그러면 판 밖에 겹쳐 그려진다", () => {
    const box = renderWithWidths({ tableWidth: 900, boxWidth: 500 });
    expect(window.getComputedStyle(box).overflowX).not.toBe("visible");
  });
});