import React from "react";
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/* 스크롤 칸은 **넘칠 때만** 초점을 받는다.
 *
 * 굴릴 수 있는 칸은 키보드로도 굴릴 수 있어야 하고(WCAG 2.1.1), 그러려면 초점을 받아야
 * 한다. 그런데 굴릴 것이 없는 칸까지 초점을 받으면 탭 순서에 아무 일도 안 하는 정거장이
 * 하나 생긴다 — 「지금은 안 넘치지만 자료가 늘면 넘치는 자리」에 이 부품을 쓸 수 있는
 * 이유가 이 판정이다.
 */

import { ScrollArea } from "./kit.jsx";

/* jsdom 은 레이아웃을 안 한다 — `scrollHeight`/`clientHeight` 가 언제나 0 이다.
 * 그래서 넘침 여부를 시험이 직접 만든다. */
function stubMetrics({ scrollHeight, clientHeight }) {
  const proto = window.Element.prototype;
  Object.defineProperty(proto, "scrollHeight", { configurable: true, get() { return scrollHeight; } });
  Object.defineProperty(proto, "clientHeight", { configurable: true, get() { return clientHeight; } });
  // jsdom 은 이 둘을 프로토타입 접근자로 갖고 있지 않다 — 원래대로 되돌리는 것은 «지우는 것»이다.
  return () => {
    delete proto.scrollHeight;
    delete proto.clientHeight;
  };
}

let restore = null;
afterEach(() => {
  if (restore) restore();
  restore = null;
  vi.unstubAllGlobals();
});

function area() {
  return document.querySelector(".k-scrollarea");
}

describe("ScrollArea", () => {
  it("넘치면 초점을 받고 이름을 갖는다", () => {
    restore = stubMetrics({ scrollHeight: 500, clientHeight: 200 });
    act(() => { render(<ScrollArea maxHeight="12rem" ariaLabel="긴 목록"><div>내용</div></ScrollArea>); });
    expect(area().getAttribute("tabindex")).toBe("0");
    expect(screen.getByRole("group", { name: "긴 목록" })).toBeInTheDocument();
    expect(area().getAttribute("data-overflows")).toBe("true");
  });

  it("🔴 안 넘치면 초점을 안 받는다 — 아무 일도 안 하는 탭 정거장을 만들지 않는다", () => {
    restore = stubMetrics({ scrollHeight: 120, clientHeight: 200 });
    act(() => { render(<ScrollArea maxHeight="12rem" ariaLabel="짧은 목록"><div>내용</div></ScrollArea>); });
    expect(area().getAttribute("tabindex")).toBeNull();
    expect(screen.queryByRole("group")).toBeNull();
    expect(area().getAttribute("data-overflows")).toBe("false");
  });

  it("ResizeObserver 가 없는 환경에서도 첫 측정은 한다", () => {
    restore = stubMetrics({ scrollHeight: 500, clientHeight: 200 });
    vi.stubGlobal("ResizeObserver", undefined);
    act(() => { render(<ScrollArea maxHeight="12rem" ariaLabel="긴 목록"><div>내용</div></ScrollArea>); });
    expect(area().getAttribute("data-overflows")).toBe("true");
  });
});
