/* 축포가 **터질 자리에서만** 터진다.
 *
 * 이 파일이 지키는 성질은 하나다: 「목록이 0이 됐다」와 「내가 일을 끝냈다」는 다른 사실이다.
 * 검색어를 쳐서 결과가 0건이 된 사람에게 종잇조각이 쏟아지면 그것은 축하가 아니라 조롱이다.
 * 그 구별을 `useCelebrateOnCleared` 의 **조건 지문**(token)이 한다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render } from "@testing-library/react";

const confettiSpy = vi.fn();
vi.mock("canvas-confetti", () => ({ default: (...a) => confettiSpy(...a) }));

import { celebrateIfCleared, useCelebrateOnCleared } from "./celebrate.js";

function Probe({ total, token }) {
  useCelebrateOnCleared(total, token);
  return null;
}

beforeEach(() => {
  confettiSpy.mockClear();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
});

describe("비운 순간에만 터진다", () => {
  it("남은 건수가 0 이 아니면 아무 일도 없다", () => {
    expect(celebrateIfCleared(3)).toBe(false);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("셀 수 없으면(응답에 총계가 없으면) 축하하지 않는다 — 모르는 것을 축하하지 않는다", () => {
    expect(celebrateIfCleared(null)).toBe(false);
    expect(celebrateIfCleared(undefined)).toBe(false);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("0 이 되면 터진다", () => {
    expect(celebrateIfCleared(0)).toBe(true);
    expect(confettiSpy).toHaveBeenCalled();
  });
});

describe("목록이 비워진 순간 — 조건을 바꿔서 빈 것과 구별한다", () => {
  it("🔴 같은 조건에서 3 → 0 이면 터진다", () => {
    const { rerender } = render(<Probe total={3} token="status=open" />);
    expect(confettiSpy).not.toHaveBeenCalled();
    rerender(<Probe total={0} token="status=open" />);
    expect(confettiSpy).toHaveBeenCalled();
  });

  it("🔴 **조건이 바뀌어** 0 이 된 것에는 안 터진다 — 검색어를 쳐서 0건이 된 자리다", () => {
    const { rerender } = render(<Probe total={3} token="status=open" />);
    rerender(<Probe total={0} token="status=open&q=없는말" />);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("처음부터 0 이면 안 터진다 — 빈 채로 들어온 사람은 방금 끝낸 것이 아니다", () => {
    render(<Probe total={0} token="status=open" />);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("0 인 채로 다시 그려도 두 번 터지지 않는다", () => {
    const { rerender } = render(<Probe total={1} token="t" />);
    rerender(<Probe total={0} token="t" />);
    const first = confettiSpy.mock.calls.length;
    expect(first).toBeGreaterThan(0);
    rerender(<Probe total={0} token="t" />);
    expect(confettiSpy.mock.calls.length).toBe(first);
  });

  it("총계를 아직 모르는 동안(null)에는 기억을 더럽히지 않는다", () => {
    const { rerender } = render(<Probe total={2} token="t" />);
    rerender(<Probe total={null} token="t" />);
    rerender(<Probe total={0} token="t" />);
    expect(confettiSpy).toHaveBeenCalled();
  });
});
