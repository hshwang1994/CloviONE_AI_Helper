import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { DataTable, TitleCell } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 좁은 폭 카드의 제목은 두 줄까지 쓴다 (r23 #9).
 *
 * 390 폭 홈의 지연 카드에서 제목이 한 줄 말줄임으로 「업무 15 — 화면에서 읽히…」에서 끊겼다. 표 행의 한 줄 말줄임은 열 폭을
 * 지키는 계약이지만, 카드에서는 제목이 가장 중요한 줄이고 터치 화면에는 `title` 툴팁이 없다. 그래서 카드 판이 자기 안의
 * `[data-title-cell]` 에만 두 줄 자르기를 건다. 표 행은 그대로 한 줄이다.
 *
 * jsdom 의 계산 스타일은 자손 선택자의 특이도를 풀지 않는다 — 카드 판의 클래스에 걸린 규칙 글을 읽는다.
 */

function setNarrow(narrow) {
  window.matchMedia = vi.fn().mockImplementation((q) => ({
    matches: narrow, media: q, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  }));
}
const originalMatchMedia = window.matchMedia;
afterEach(() => { window.matchMedia = originalMatchMedia; });

const ROWS = [{ id: "t-1", title: "업무 15 — 화면에서 읽히는 제목이 카드 폭보다 깁니다" }];
const COLS = [
  { key: "title", label: "제목", type: "title", render: (r) => <TitleCell title={r.title} onOpen={() => {}} /> },
  { key: "due", label: "마감", type: "date" },
];

const titleClampRules = (el) => {
  const cls = [...el.classList].filter((c) => c.startsWith("css-"));
  return [...document.styleSheets].flatMap((sh) => [...sh.cssRules].map((r) => r.cssText))
    .filter((t) => cls.some((c) => t.includes(`.${c} [data-title-cell]`)));
};

function draw() {
  return render(
    <ThemeModeProvider>
      <DataTable columns={COLS} rows={ROWS} rowKey={(r) => r.id} />
    </ThemeModeProvider>,
  );
}

describe("표 카드 뷰의 제목", () => {
  it("카드 판이 제목 칸에 두 줄 자르기를 건다(한 줄 말줄임을 푼다)", () => {
    setNarrow(true);
    draw();
    const title = screen.getByRole("button", { name: ROWS[0].title });
    const card = title.closest(".MuiPaper-root");
    const rules = titleClampRules(card);
    expect(rules.length, "카드 판에 제목 규칙이 없다").toBeGreaterThan(0);
    expect(rules.some((t) => /-webkit-line-clamp:\s*2/.test(t) && /white-space:\s*normal/.test(t))).toBe(true);
  });

  it("넓은 표의 행에는 그 규칙이 없다 — 표 행의 제목은 한 줄이다", () => {
    setNarrow(false);
    draw();
    const title = screen.getByRole("button", { name: ROWS[0].title });
    let el = title.parentElement;
    while (el && el !== document.body) {
      expect(titleClampRules(el), "표 행 조상에 카드 제목 규칙이 걸렸다").toHaveLength(0);
      el = el.parentElement;
    }
  });
});
