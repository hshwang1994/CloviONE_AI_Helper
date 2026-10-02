import React from "react";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { DataTable } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 그려진 표가 열 배분(D-529)을 실제로 쓰는가. 배분 함수만 맞고 `<col>` 에 옛 rem 바닥이 그대로 서면 화면은 하나도 안 바뀐다 —
 * 표가 받은 칸(px)을 못 박고 그려진 `<col>` · 표 폭 · 숨긴 열 알림 · 붙박이 첫 열을 잰다. jsdom 은 배치를 안 하므로 칸 폭을
 * 직접 먹인다(`datatable-narrow-columns.test.jsx` 와 같은 방식).
 *
 * qa-contract-change: 남는 폭의 첫 몫이 내용 몫이 됐다(P17V, `plan-columns.test.js` 와 같은 까닭). 1366 칸에서 이메일 열이 값 폭
 * (232px)을 받고 이름 · 부서 열이 그 차이를 내준다 — 그려진 `<col>` 폭도 그 값으로 옮겼다. */

const ROLE_LABELS = ["일반 사용자", "운영자", "감사자", "관리자", "시스템 관리자"];
const COLS = [
  { key: "name", label: "이름", type: "name" },
  { key: "title", label: "직책", type: "enum", tier: "secondary" },
  { key: "email", label: "이메일", type: "identifier" },
  { key: "dept", label: "부서", type: "path" },
  { key: "status", label: "상태", type: "status" },
  { key: "role", label: "역할", type: "enum", values: ROLE_LABELS },
];
const ROWS = [
  { id: "u1", name: "UI QA", title: "팀장", email: "ui-qa@goodmit.co.kr", dept: "플랫폼개발팀", status: "활성", role: "시스템 관리자" },
  { id: "u2", name: "김지훈", title: "선임", email: "kim.jihoon@goodmit.co.kr", dept: "플랫폼개발팀", status: "활성", role: "운영자" },
];

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
afterEach(() => { if (restore) restore(); restore = null; });

function draw(props = {}) {
  return render(
    <ThemeModeProvider>
      <DataTable placement="surface" columns={COLS} rows={ROWS} rowKey={(r) => r.id} onRow={() => {}} {...props} />
    </ThemeModeProvider>,
  );
}

const colWidths = (container) => [...container.querySelectorAll("colgroup col")].map((c) => c.style.width);

describe("그려진 표가 열 배분을 쓴다", () => {
  beforeEach(() => { restore = pinBoxWidth(724); });

  it("조직 @1366 의 칸(724px)에서 보조 열 직책만 숨기고 남은 열이 px 폭을 받는다", () => {
    const { container } = draw();
    expect(screen.queryByRole("columnheader", { name: /직책/ })).toBeNull();
    expect(colWidths(container)).toEqual(["127px", "232px", "149px", "96px", "120px"]);
    const table = container.querySelector("table");
    expect(table.style.width || getComputedStyle(table).width).toBe("100%");
    // 숨긴 사실은 표 발이 말한다 — 판단은 창이 아니라 표가 받은 폭이라 「표 폭」이다.
    expect(screen.getByText(/표 폭이 좁아 직책 열을 숨겼습니다\./)).toBeInTheDocument();
    expect(screen.getByText(/행을 열면 숨긴 값도 볼 수 있습니다/)).toBeInTheDocument();
    // 굴리지 않는 표에는 붙박이 열이 없다.
    expect(container.querySelector("[data-sticky-col]")).toBeNull();
  });
});

describe("필수 열만으로도 칸이 모자라면", () => {
  beforeEach(() => { restore = pinBoxWidth(500); });

  it("더 숨기지 않고 표가 바닥 합 폭으로 서서 가로로 굴러가며, 첫 열은 붙박이다", () => {
    const { container } = draw();
    // 필수 넷(이름 · 이메일 · 상태 · 역할)과 부서는 그대로 보인다.
    for (const name of ["이름", "이메일", "부서", "상태", "역할"]) {
      expect(screen.getByRole("columnheader", { name: new RegExp(name) })).toBeInTheDocument();
    }
    expect(colWidths(container)).toEqual(["144px", "176px", "160px", "96px", "120px"]);
    const table = container.querySelector("table");
    expect(getComputedStyle(table).width).toBe("696px");
    const stuck = [...container.querySelectorAll("tbody td[data-sticky-col]")];
    expect(stuck.map((td) => td.textContent)).toEqual(["UI QA", "김지훈"]);
    expect(getComputedStyle(stuck[0]).position).toBe("sticky");
    expect(getComputedStyle(stuck[0]).left).toBe("0px");
    const head = screen.getByRole("columnheader", { name: /이름/ });
    expect(getComputedStyle(head).position).toBe("sticky");
  });
});
