import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

/* 표가 **가로로 넘칠 때** 고정 열 이름이 데이터를 덮지 않는가.
 *
 * 표가 자기 칸보다 넓으면 `TableContainer` 는 넘침을 바깥에 못 넘긴다(넘기면 표가 판 밖으로
 * 삐져나와 사이드바 위에 겹쳐 그려진다). 그 순간 이 상자가 스크롤 창이 되는데, 아무도 상자
 * 위에 `--c-sticky-top: 0px` 를 안 박으면 열 이름이 `stickyTopSx()` 의 대체값인 상단바
 * 높이(52px)를 받는다 — 그 52px 는 「윈도가 굴러갈 때 fixed AppBar 를 피하라」는 뜻이라
 * 이 상자 안에서는 피할 대상이 없다. 결과는 열 이름 줄이 상자 위쪽에서 52px 내려온 자리에
 * 붙박이고 **그 아래 첫 행을 통째로 덮는** 것이다.
 *
 * 실측(2026-09-06 · 1600x900 `#/schedules`): th rect 451-496, 첫 행 rect 444-479, 행
 * 가로폭의 93%에서 `elementFromPoint` 가 THEAD 를 돌려줬다(첫 행은 클릭도 안 먹었다).
 * 1280x800 에서는 `#/approvals` 가 90% 로 같아졌다. 가로로 안 넘치는 표는 같은 창에서 0% 다.
 *
 * 「`position` 이 sticky 인가」만 재는 검사는 그때도 통과한다(theme.js 가 예고한 그 구멍).
 * 그래서 여기서 재는 것은 **누가 스크롤 창인지를 상자가 안쪽에 알리는가** 다 — jsdom 은
 * 레이아웃을 안 하므로 겹침 자체는 못 재지만, 겹침을 만드는 두 값(상자가 선언한 변수 ·
 * 머리 칸이 그 변수를 읽는 계산식)은 그대로 잰다. */

import { DataTable } from "./kit.jsx";
import { APPBAR_HEIGHT, STICKY_TOP_VAR, createClovirTheme } from "./theme.js";

const COLUMNS = [
  { key: "title", label: "제목", type: "title" },
  { key: "state", label: "상태", type: "status" },
];
const ROWS = [{ title: "가", state: "완료" }, { title: "나", state: "계획" }];

const fallbackTop = `calc(var(${STICKY_TOP_VAR}, ${APPBAR_HEIGHT.xs}px) + 0px)`;

const rect = (width) => ({
  width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0, toJSON: () => ({}),
});

/** 표 너비와 칸 너비를 실제로 재는 자리를 대신 답하게 한다 — jsdom 은 둘 다 0 이라
 *  가로 넘침이 영영 안 일어난다(그 갈래가 이 결함의 갈래다). */
function renderWithWidths({ tableWidth, boxWidth, ...props }) {
  vi.spyOn(HTMLTableElement.prototype, "getBoundingClientRect").mockReturnValue(rect(tableWidth));
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(boxWidth);
  render(
    <ThemeProvider theme={createClovirTheme()}>
      <DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.title} {...props} />
    </ThemeProvider>,
  );
  return document.querySelector(".MuiTableContainer-root");
}

const stickyVar = (el) => window.getComputedStyle(el).getPropertyValue(STICKY_TOP_VAR).trim();

describe("가로로 넘치는 표의 고정 열 이름", () => {
  afterEach(() => { vi.restoreAllMocks(); });

  it("표 컨테이너가 스크롤 창이 되면 자기 위에 상단바가 없다고 안쪽에 선언한다", () => {
    const box = renderWithWidths({ tableWidth: 900, boxWidth: 500, stickyHeader: true });
    // 이 갈래에서는 넘김을 못 고른다 — 상자가 가로 스크롤을 맡는다.
    expect(window.getComputedStyle(box).overflowX).not.toBe("visible");
    expect(stickyVar(box)).toBe("0px");
    // 머리 칸의 top 은 그 변수를 읽는 계산식이다 — 상자가 0 을 박았으므로 상자 위쪽에 붙고
    // 52px 내려앉지 않는다(내려앉으면 그 아래 첫 행이 덮인다).
    const th = screen.getByText("제목").closest("th");
    expect(window.getComputedStyle(th).top).toBe(fallbackTop);
  });

  it("표가 칸에 들어가면 아무도 그 변수를 안 박는다 — 대체값(상단바 높이)이 그대로 선다", () => {
    const box = renderWithWidths({ tableWidth: 500, boxWidth: 800, stickyHeader: true });
    // 반례: 윈도가 스크롤 창이라 열 이름은 fixed AppBar 를 피해야 한다. 여기까지 0 을 박으면
    // 열 이름이 상단바 뒤로 숨는다 — 고치려던 것과 정반대의 결함이 된다.
    expect(window.getComputedStyle(box).overflowX).toBe("visible");
    expect(stickyVar(box)).toBe("");
    const th = screen.getByText("제목").closest("th");
    expect(window.getComputedStyle(th).top).toBe(fallbackTop);
  });

  it("자기 높이 안에서 굴러가는 표(virtualize box)도 같은 선언을 한다", () => {
    const box = renderWithWidths({
      tableWidth: 500, boxWidth: 800, stickyHeader: true, virtualize: { height: 400 },
    });
    expect(window.getComputedStyle(box).overflowY).toBe("auto");
    expect(stickyVar(box)).toBe("0px");
  });
});
