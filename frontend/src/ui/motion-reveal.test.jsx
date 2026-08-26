import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";

/* 짧은 연출이 지키는 것 셋.
 *
 *   1. **처음 보는 그림만 자란다.** 탭을 떠났다 돌아오면 부품이 다시 마운트되는데, 그때마다
 *      막대가 0 에서 자라면 그것은 연출이 아니라 방해다(사용자 지시: 탭을 볼 때마다 반복
 *      재생되지 않게).
 *   2. **값이 바뀌면 다시 자란다.** 같은 이름으로 다른 수를 그리는데 그림이 안 움직이면
 *      바뀐 줄을 모른다.
 *   3. **동작 최소화를 켠 사람에게는 아예 시작하지 않는다.** CSS 전역 규칙이 길이를 0 으로
 *      만들지만, 시작 상태가 0 폭이면 「0 이었다가 갑자기 최종값」이 되어 깜빡임으로 보인다.
 *      그래서 처음부터 최종 상태로 그린다.
 */

import { resetRevealMemory, useRevealOnce } from "./motion.js";

function Probe({ revealKey }) {
  const shown = useRevealOnce(revealKey);
  return <div data-testid="probe">{shown ? "final" : "start"}</div>;
}

const state = () => screen.getByTestId("probe").textContent;

/* jsdom 에는 rAF 가 있지만 자동으로 돌지 않는 판이 있다 — 프레임을 시험이 직접 넘긴다. */
let frames;

beforeEach(() => {
  resetRevealMemory();
  frames = [];
  vi.stubGlobal("requestAnimationFrame", (cb) => { frames.push(cb); return frames.length; });
  vi.stubGlobal("cancelAnimationFrame", () => {});
  vi.stubGlobal("matchMedia", (q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function nextFrame() {
  const queued = frames.splice(0, frames.length);
  act(() => { queued.forEach((cb) => cb(0)); });
}

describe("useRevealOnce", () => {
  it("처음 보는 지문은 시작 상태에서 한 프레임 뒤 최종 상태가 된다", () => {
    render(<Probe revealKey="trend:1,2,3" />);
    expect(state()).toBe("start");
    nextFrame();
    expect(state()).toBe("final");
  });

  it("🔴 같은 지문으로 다시 마운트되면 **안 움직인다** — 탭을 볼 때마다 재생되지 않는다", () => {
    const first = render(<Probe revealKey="trend:1,2,3" />);
    nextFrame();
    first.unmount();

    render(<Probe revealKey="trend:1,2,3" />);
    expect(state()).toBe("final");
    expect(frames).toHaveLength(0);
  });

  it("값이 바뀌면 다시 자란다 — 지문에 값이 들어가는 이유다", () => {
    const first = render(<Probe revealKey="trend:1,2,3" />);
    nextFrame();
    first.unmount();

    render(<Probe revealKey="trend:1,2,4" />);
    expect(state()).toBe("start");
    nextFrame();
    expect(state()).toBe("final");
  });

  it("지문을 안 주면 연출 자체가 없다", () => {
    render(<Probe revealKey={null} />);
    expect(state()).toBe("final");
    expect(frames).toHaveLength(0);
  });

  it("동작 최소화를 켜면 처음부터 최종 상태다", () => {
    vi.stubGlobal("matchMedia", (q) => ({
      matches: q.includes("prefers-reduced-motion"), media: q,
      addEventListener() {}, removeEventListener() {},
    }));
    render(<Probe revealKey="trend:9,9,9" />);
    expect(state()).toBe("final");
    expect(frames).toHaveLength(0);
  });
});
