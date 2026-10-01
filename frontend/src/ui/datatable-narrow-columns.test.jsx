import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { DataTable } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 칸이 좁을 때 표가 **무엇을 빼고 무엇을 말하는가**.
 *
 * 두 가지를 함께 잰다. 둘 다 부품 하나만 따로 재면 안 보이는 것이다 —
 * 실제 결함이 그 배선에 있었기 때문이다.
 *
 *   ① 안내 문구가 이 표에서 사실인가. 「행을 열면 숨긴 값도 볼 수 있습니다」는 행을
 *      열 수 있는 표에서만 사실인데, `DataTable` 이 그 조건(`onRow`)을 안 넘기고 있었다.
 *   ② 🔴 **지금 정렬 중인 열은 안 숨긴다.** 머리행은 남은 열로만 그려지므로, 정렬 축이
 *      빠지면 화살표와 정렬 단추와 `aria-sort` 가 통째로 사라진다 — 목록은 그 축으로
 *      서 있는데 화면에 그렇게 말하는 자리가 없고, 방향을 되돌릴 수도 없다.
 *
 * jsdom 은 배치를 안 하므로 폭을 직접 먹인다: `ResizeObserver` 와 `getBoundingClientRect`
 * 를 세워 「칸은 좁고 표는 넓다」를 만든다.
 */

const COLS = [
  { key: "title", label: "제목", type: "title", sortable: true },
  { key: "space", label: "프로젝트", type: "name", minWidth: "10rem", hideNarrow: true },
  { key: "who", label: "삭제한 사람", type: "name", minWidth: "11rem", hideNarrow: true },
  { key: "when", label: "삭제일", type: "datetime", sortable: true, hideNarrow: true },
];
const ROWS = [{ id: "r1", title: "줄 하나", space: "운영", who: "나", when: "2026-08-01T00:00:00" }];

/** 이 표가 받은 칸을 `px` 로 못 박는다 — `useFittedColumns` 가 그 값으로 판단한다. */
function pinBoxWidth(px) {
  const original = Element.prototype.getBoundingClientRect;
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: px });
  Element.prototype.getBoundingClientRect = function rect() {
    return { width: px, height: 100, top: 0, left: 0, right: px, bottom: 100, x: 0, y: 0, toJSON() {} };
  };
  globalThis.ResizeObserver = class {
    constructor(cb) { this.cb = cb; }
    observe() { this.cb([]); }
    unobserve() {}
    disconnect() {}
  };
  return () => {
    Element.prototype.getBoundingClientRect = original;
    delete HTMLElement.prototype.clientWidth;
  };
}

let restore = null;
beforeEach(() => { restore = pinBoxWidth(420); });
afterEach(() => { if (restore) restore(); restore = null; });

function draw(props) {
  return render(
    <ThemeModeProvider>
      <DataTable columns={COLS} rows={ROWS} rowKey={(r) => r.id} ellipsis {...props} />
    </ThemeModeProvider>,
  );
}

describe("좁은 칸에서 열을 뺄 때", () => {
  it("🔴 행을 열 수 없는 표는 「행을 열면」이라고 말하지 않는다", () => {
    draw({});
    // 판단 기준은 창이 아니라 그 표가 받은 폭이라 「표 폭」이라고 말한다(D-529).
    expect(screen.getByText(/표 폭이 좁아/)).toBeInTheDocument();
    expect(screen.queryByText(/행을 열면/)).toBeNull();
    expect(screen.getByText(/창을 넓히면 다시 보입니다/)).toBeInTheDocument();
  });

  it("반례 — 행을 열 수 있는 표에서는 그렇게 말한다", () => {
    draw({ onRow: () => {} });
    expect(screen.getByText(/행을 열면 숨긴 값도 볼 수 있습니다/)).toBeInTheDocument();
  });

  it("🔴 지금 정렬 중인 열은 좁아도 안 숨긴다 — 화살표까지 같이 사라진다", () => {
    draw({ sort: { key: "when", dir: "desc" }, onSort: () => {} });
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers.some((t) => t.includes("삭제일"))).toBe(true);
    const when = screen.getAllByRole("columnheader").find((h) => h.textContent.includes("삭제일"));
    expect(when).toHaveAttribute("aria-sort", "descending");
  });

  it("반례 — 정렬 축이 아니면 그 열은 예전처럼 빠진다(전부 남기면 표가 넘친다)", () => {
    draw({ sort: { key: "title", dir: "asc" }, onSort: () => {} });
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers.some((t) => t.includes("삭제일"))).toBe(false);
    expect(screen.getByText(/삭제일/)).toBeInTheDocument(); // 숨긴 열 안내에는 이름이 남는다
  });
});
