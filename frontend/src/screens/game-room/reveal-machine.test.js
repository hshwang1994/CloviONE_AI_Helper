import { describe, it, expect, vi, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { ANNOUNCE_MS, REVEAL_INITIAL, reduceReveal, transitionFor, useRevealMachine } from "./revealMachine.js";

/* 결과 발표의 상태 기계 (D-576).
 *
 * 못박는 것: 열쇠의 변화가 어느 전이인가(RESET · INSTANT · ANNOUNCE), 발표가 끝나면 같은 열쇠일 때만 공개(REVEAL), 닫기 · 다시 열기는
 * 단계를 바꾸지 않는다(재발표 · 축포 없음), 축포는 열쇠당 한 번이고 승자가 없거나 늦게 들어온 결과에는 없다. */

afterEach(() => { vi.useRealTimers(); });

describe("전이 (순수 함수)", () => {
  it("결과가 없어지면 RESET — 단계를 비우고 닫는다", () => {
    const s = reduceReveal({ key: "r:4", phase: "revealed", open: true }, { type: "RESET" });
    expect(s).toEqual(REVEAL_INITIAL);
    expect(transitionFor("r:4", null, false)).toEqual({ type: "RESET" });
    expect(transitionFor(null, null, false)).toBeNull();
  });

  it("처음 연 방의 지난 결과는 INSTANT — 공개 상태로 바로 연다", () => {
    expect(transitionFor(null, "r:4", true)).toEqual({ type: "INSTANT", key: "r:4" });
    expect(reduceReveal(REVEAL_INITIAL, { type: "INSTANT", key: "r:4" })).toEqual({ key: "r:4", phase: "revealed", open: true });
  });

  it("새로 나온 결과는 ANNOUNCE — 발표 단계로 연다", () => {
    expect(transitionFor(null, "r:5", false)).toEqual({ type: "ANNOUNCE", key: "r:5" });
    expect(reduceReveal(REVEAL_INITIAL, { type: "ANNOUNCE", key: "r:5" })).toEqual({ key: "r:5", phase: "announcing", open: true });
  });

  it("같은 열쇠면 아무 전이도 없다(폴링 · 리렌더)", () => {
    expect(transitionFor("r:5", "r:5", false)).toBeNull();
  });

  it("REVEAL 은 같은 열쇠의 발표 중일 때만 공개한다", () => {
    const announcing = { key: "r:5", phase: "announcing", open: true };
    expect(reduceReveal(announcing, { type: "REVEAL", key: "r:5" }).phase).toBe("revealed");
    expect(reduceReveal(announcing, { type: "REVEAL", key: "r:4" })).toBe(announcing);
  });

  it("CLOSE 는 단계를 그대로 두고 닫는다", () => {
    const s = reduceReveal({ key: "r:5", phase: "revealed", open: true }, { type: "CLOSE" });
    expect(s).toEqual({ key: "r:5", phase: "revealed", open: false });
  });

  it("OPEN 은 단계를 그대로 두고 다시 연다 — 재발표가 아니다", () => {
    const s = reduceReveal({ key: "r:5", phase: "revealed", open: false }, { type: "OPEN" });
    expect(s).toEqual({ key: "r:5", phase: "revealed", open: true });
  });

  it("결과가 없으면 OPEN 해도 열리지 않는다", () => {
    expect(reduceReveal(REVEAL_INITIAL, { type: "OPEN" })).toBe(REVEAL_INITIAL);
  });
});

describe("훅 — 축포는 열쇠당 한 번", () => {
  it("새 결과: 발표 → ANNOUNCE_MS 뒤 공개 + 축포 한 번, 닫고 다시 열어도 다시 쏘지 않는다", () => {
    vi.useFakeTimers();
    const fire = vi.fn();
    const { result, rerender } = renderHook((p) => useRevealMachine(p), { initialProps: { key: null, instant: false, hasWinners: true, fire } });
    rerender({ key: "r:9", instant: false, hasWinners: true, fire });
    expect(result.current.phase).toBe("announcing");
    expect(result.current.open).toBe(true);
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS); });
    expect(result.current.phase).toBe("revealed");
    expect(fire).toHaveBeenCalledTimes(1);
    expect(fire).toHaveBeenCalledWith("r:9");
    act(() => { result.current.closeDialog(); });
    expect(result.current.open).toBe(false);
    act(() => { result.current.openDialog(); });
    expect(result.current.open).toBe(true);
    expect(result.current.phase).toBe("revealed");
    rerender({ key: "r:9", instant: false, hasWinners: true, fire });
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS * 3); });
    expect(fire).toHaveBeenCalledTimes(1);
  });

  it("늦게 들어온 사람(instant)은 발표 · 축포 없이 공개 상태로 연다", () => {
    vi.useFakeTimers();
    const fire = vi.fn();
    const { result } = renderHook(() => useRevealMachine({ key: "r:3", instant: true, hasWinners: true, fire }));
    expect(result.current.phase).toBe("revealed");
    expect(result.current.open).toBe(true);
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS * 2); });
    expect(fire).not.toHaveBeenCalled();
  });

  it("승자가 없는 결과는 발표하지만 축포가 없다", () => {
    vi.useFakeTimers();
    const fire = vi.fn();
    const { result, rerender } = renderHook((p) => useRevealMachine(p), { initialProps: { key: null, instant: false, hasWinners: false, fire } });
    rerender({ key: "r:2", instant: false, hasWinners: false, fire });
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS); });
    expect(result.current.phase).toBe("revealed");
    expect(fire).not.toHaveBeenCalled();
  });

  it("초기화하면 닫히고, 새 열쇠는 다시 발표 · 축포한다", () => {
    vi.useFakeTimers();
    const fire = vi.fn();
    const { result, rerender } = renderHook((p) => useRevealMachine(p), { initialProps: { key: null, instant: false, hasWinners: true, fire } });
    rerender({ key: "r:1", instant: false, hasWinners: true, fire });
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS); });
    rerender({ key: null, instant: false, hasWinners: false, fire });
    expect(result.current.open).toBe(false);
    expect(result.current.phase).toBe("none");
    rerender({ key: "r:7", instant: false, hasWinners: true, fire });
    expect(result.current.phase).toBe("announcing");
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS); });
    expect(fire).toHaveBeenCalledTimes(2);
    expect(fire).toHaveBeenLastCalledWith("r:7");
  });

  it("발표 도중 결과가 바뀌면 옛 열쇠는 공개 · 축포하지 않는다", () => {
    vi.useFakeTimers();
    const fire = vi.fn();
    const { result, rerender } = renderHook((p) => useRevealMachine(p), { initialProps: { key: null, instant: false, hasWinners: true, fire } });
    rerender({ key: "r:1", instant: false, hasWinners: true, fire });
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS / 2); });
    rerender({ key: "r:2", instant: false, hasWinners: true, fire });
    act(() => { vi.advanceTimersByTime(ANNOUNCE_MS); });
    expect(fire).toHaveBeenCalledTimes(1);
    expect(fire).toHaveBeenCalledWith("r:2");
    expect(result.current.key).toBe("r:2");
  });
});
