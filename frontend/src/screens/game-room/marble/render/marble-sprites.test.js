import { describe, it, expect, vi, afterEach } from "vitest";
import { createSpriteCache, spriteBucket, INITIAL_MAX_TOTAL } from "./marbleSprites.js";

/* 구슬 그림 (D-578) — 크기 칸, 같은 조건이면 다시 그리지 않음, 얼굴이 오면 다시 그림, 61명부터 머리글자 대신 번호. */

const palette = { mode: "light", marble: { s: 76, l: 56 }, highlight: "rgba(255,255,255,.7)", marbleEdge: "rgba(0,0,0,.3)", spriteFace: "#F5F6FB", fontFamily: "sans-serif" };
const realGetContext = HTMLCanvasElement.prototype.getContext;
afterEach(() => { HTMLCanvasElement.prototype.getContext = realGetContext; });

function recordingContext(log) {
  const g = { addColorStop() {} };
  return {
    clearRect() {}, save() {}, restore() {}, beginPath() {}, arc() {}, closePath() {}, clip() {}, fillRect() {}, stroke() {},
    drawImage: (...a) => log.push(["drawImage", ...a]),
    createRadialGradient: () => g,
    fillText: (t) => log.push(["text", t]),
    set fillStyle(v) {}, set strokeStyle(v) {}, set lineWidth(v) {}, set font(v) {}, set textAlign(v) {}, set textBaseline(v) {},
    set shadowColor(v) {}, set shadowBlur(v) {},
  };
}

describe("크기 칸", () => {
  it("2r · 배율 · dpr 를 8 단위로 올리고 16 ~ 256 에 가둔다", () => {
    expect(spriteBucket(0.25, 40, 1)).toBe(24);
    expect(spriteBucket(0.25, 40, 2)).toBe(40);
    expect(spriteBucket(0.25, 2, 1)).toBe(16);
    expect(spriteBucket(0.25, 900, 2)).toBe(256);
  });
});

describe("저장소", () => {
  it("같은 조건이면 같은 그림, 얼굴 상태 · 칸이 바뀌면 다시 그린다", () => {
    const log = [];
    HTMLCanvasElement.prototype.getContext = () => recordingContext(log);
    let entry = { img: null, status: "loading" };
    const cache = createSpriteCache({ total: 6, imageOf: () => entry });
    const p = { key: "u:1", name: "김하나", user_id: "u1", hue: 30 };
    const a = cache.get(0, p, 24, palette);
    expect(cache.get(0, p, 24, palette)).toBe(a);
    expect(log.filter((x) => x[0] === "text")).toEqual([["text", "김"]]);
    entry = { img: { width: 64, height: 64 }, status: "ready" };
    cache.get(0, p, 24, palette);
    expect(log.some((x) => x[0] === "drawImage")).toBe(true);
    const bigger = cache.get(0, p, 40, palette);
    expect(bigger).not.toBe(a);
    expect(bigger.width).toBe(40);
  });

  it("자유 이름은 머리글자, 61명부터는 번호 — 사람이 아니면 얼굴을 찾지 않는다", () => {
    const log = [];
    HTMLCanvasElement.prototype.getContext = () => recordingContext(log);
    const imageOf = vi.fn();
    createSpriteCache({ total: INITIAL_MAX_TOTAL, imageOf }).get(4, { key: "n:a", name: "이두리", hue: 0 }, 24, palette);
    createSpriteCache({ total: INITIAL_MAX_TOTAL + 1, imageOf }).get(4, { key: "n:a", name: "이두리", hue: 0 }, 24, palette);
    expect(log.filter((x) => x[0] === "text").map((x) => x[1])).toEqual(["이", "5"]);
    expect(imageOf).not.toHaveBeenCalled();
  });
});
