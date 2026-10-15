import { describe, it, expect } from "vitest";
import { BURST_COUNT, createEffects, MAX_PARTICLES } from "./effects.js";
import { FLAG_FINISHED } from "../engine/core.js";

/* 경주 효과 (D-578) — 처음 본 장면(늦은 입장)에는 효과가 없고, 새로 결승을 넘은 구슬마다 조각 36개, 선두가 바뀌면 맥박, 조각은
 * 600개까지. */

const palette = { marble: { s: 70, l: 60 }, winnerRing: "#5A4FCF", fontFamily: "sans-serif", labelHalo: "#fff", finish: "#2E9E6B" };
const parts = Array.from({ length: 30 }, (_, i) => ({ hue: i * 12, name: `p${i}` }));

function snap(step, finishedSet, n = 30) {
  const flags = new Uint8Array(n);
  for (const i of finishedSet) flags[i] = FLAG_FINISHED;
  return { step, flags, positions: new Float32Array(n * 3) };
}

function countingContext(counter) {
  return {
    save() {}, restore() {}, translate() {}, rotate() {}, beginPath() {}, arc() {}, stroke() {},
    fillRect() { counter.n += 1; },
    set globalAlpha(v) {}, set fillStyle(v) {}, set strokeStyle(v) {}, set lineWidth(v) {},
  };
}

describe("효과", () => {
  it("처음 본 장면은 기억만 한다 — 늦게 들어온 사람에게 지난 완주를 터뜨리지 않는다", () => {
    const fx = createEffects();
    fx.observe(snap(100, [0, 1, 2]), parts, palette, 0, 3);
    expect(fx.alive(0)).toBe(false);
  });

  it("새로 결승을 넘은 구슬마다 조각 36개", () => {
    const fx = createEffects();
    fx.observe(snap(100, []), parts, palette, 0, 0);
    fx.observe(snap(101, [5]), parts, palette, 10, 0);
    expect(fx.alive(10)).toBe(true);
    const counter = { n: 0 };
    fx.drawWorld(countingContext(counter), { now: 20, zoom: 30, marbles: [], palette });
    expect(counter.n).toBe(BURST_COUNT);
    fx.drawWorld(countingContext(counter), { now: 5000, zoom: 30, marbles: [], palette });
    expect(fx.alive(5000)).toBe(false);
  });

  it("선두가 바뀌면 맥박 고리(0.6초)", () => {
    const fx = createEffects();
    fx.observe(snap(1, []), parts, palette, 0, 2);
    fx.observe(snap(2, []), parts, palette, 5, 7);
    expect(fx.alive(100)).toBe(true);
    expect(fx.alive(700)).toBe(false);
  });

  it("조각은 600개까지", () => {
    const fx = createEffects();
    fx.observe(snap(1, []), parts, palette, 0, 0);
    fx.observe(snap(2, parts.map((_, i) => i)), parts, palette, 1, 0);
    const counter = { n: 0 };
    fx.drawWorld(countingContext(counter), { now: 2, zoom: 30, marbles: [], palette });
    expect(counter.n).toBe(MAX_PARTICLES);
  });
});
