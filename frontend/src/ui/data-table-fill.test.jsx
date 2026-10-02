import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { DataTable } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* `DataTable fill` (F5 · D-531) — 작업 공간 판 몸을 채우는 표.
 *
 * 표 상자가 남은 높이를 받아 두 축으로 직접 굴리고, 열 이름은 그 상자 위에 붙고, 무한 받기 감시점은 상자 **안**에 서며(밖에 서면
 * 늘 「보여」 판을 열자마자 끝까지 받는다), 발(건수 · 「더 보기」)은 상자 아래에 고정이다. 채움이 아닌 표는 예전 그대로다(반례). */

const COLS = [{ key: "name", label: "이름", type: "name" }, { key: "email", label: "이메일", type: "identifier" }];
const ROWS = Array.from({ length: 50 }, (_, i) => ({ id: `u${i}`, name: `구성원 ${i}`, email: `m${i}@goodmit.co.kr` }));
const LIST = { total: 150, loaded: 50, hasNext: true, isFetchingNext: false, onMore: () => {}, unit: "명" };

function ui(node) {
  return render(<ThemeModeProvider>{node}</ThemeModeProvider>);
}

describe("채움 표", () => {
  it("표 상자가 남은 높이를 받아 두 축으로 굴리고, 굴림이 판 밖으로 번지지 않는다", () => {
    const { container } = ui(<DataTable fill stickyHeader columns={COLS} rows={ROWS} rowKey={(r) => r.id} list={LIST} />);
    const box = container.querySelector('[data-table-box="fill"]');
    expect(box).not.toBeNull();
    const st = getComputedStyle(box);
    expect(st.overflow).toBe("auto");
    expect(st.minHeight).toBe("0");
    expect(st.overscrollBehavior).toBe("contain");
    // 바깥 틀은 판 몸을 채우는 세로 묶음이다.
    const frame = container.querySelector("[data-table-fill]");
    expect(getComputedStyle(frame).display).toBe("flex");
    expect(getComputedStyle(frame).flexDirection).toBe("column");
  });

  it("감시점은 상자 안 표 끝에, 발은 상자 아래에 선다 — 발은 sticky 가 아니다", () => {
    const { container } = ui(<DataTable fill stickyHeader columns={COLS} rows={ROWS} rowKey={(r) => r.id} list={LIST} />);
    const box = container.querySelector('[data-table-box="fill"]');
    const sentinel = container.querySelector("[data-list-sentinel]");
    expect(sentinel).not.toBeNull();
    expect(box.contains(sentinel)).toBe(true);
    const footer = container.querySelector("[data-list-footer]");
    expect(footer).not.toBeNull();
    expect(box.contains(footer)).toBe(false);
    expect(getComputedStyle(footer).position).not.toBe("sticky");
  });

  it("숨긴 열 안내는 표 위가 아니라 판 아래 발에 선다 — 고정 도구 줄이 길어지지 않는다", () => {
    const original = Element.prototype.getBoundingClientRect;
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 300 });
    Element.prototype.getBoundingClientRect = function rect() {
      return { width: 300, height: 100, top: 0, left: 0, right: 300, bottom: 100, x: 0, y: 0, toJSON() {} };
    };
    globalThis.ResizeObserver = class {
      constructor(cb) { this.cb = cb; }
      observe() { this.cb([]); }
      unobserve() {}
      disconnect() {}
    };
    try {
      const cols = [...COLS, { key: "title", label: "직책", type: "enum", tier: "secondary" }];
      const rows = ROWS.map((r) => ({ ...r, title: "선임" }));
      const { container } = ui(<DataTable fill stickyHeader columns={cols} rows={rows} rowKey={(r) => r.id} list={LIST} onRow={() => {}} />);
      const footer = container.querySelector("[data-list-footer]");
      const note = [...container.querySelectorAll("*")].find((el) => el.children.length === 0 && /직책 열을 숨겼습니다/.test(el.textContent || ""));
      expect(note).toBeTruthy();
      expect(footer.contains(note)).toBe(true);
    } finally {
      Element.prototype.getBoundingClientRect = original;
      delete HTMLElement.prototype.clientWidth;
    }
  });

  it("열 이름은 상자 위에 붙는다 — 상자가 스크롤 창이라고 안쪽에 알린다", () => {
    const { container } = ui(<DataTable fill stickyHeader columns={COLS} rows={ROWS} rowKey={(r) => r.id} list={LIST} />);
    const box = container.querySelector('[data-table-box="fill"]');
    expect(box.style.getPropertyValue("--c-sticky-top") || getComputedStyle(box).getPropertyValue("--c-sticky-top")).toBe("0px");
  });
});

describe("반례 — 채움이 아닌 목록 판 표", () => {
  it("감시점은 표 상자 밖 흐름에 서고 발은 판 바닥에 sticky 다", () => {
    const { container } = ui(<DataTable placement="surface" stickyHeader columns={COLS} rows={ROWS} rowKey={(r) => r.id} list={LIST} />);
    expect(container.querySelector('[data-table-box="fill"]')).toBeNull();
    const box = container.querySelector(".MuiTableContainer-root");
    const sentinel = container.querySelector("[data-list-sentinel]");
    expect(box.contains(sentinel)).toBe(false);
  });
});
