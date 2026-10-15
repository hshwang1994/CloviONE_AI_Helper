import { describe, it, expect } from "vitest";
import { MINIMAP, minimapHit, minimapLayout } from "./minimap.js";
import { stageBounds } from "./camera.js";
import { STAGES } from "../engine/stages/index.js";

/* 미니맵 (D-578) — 왼쪽 위 세로 띠의 자리 · 배율과, 띠 위 한 점을 판 좌표로 바꾸는 일(자유 보기). */

describe("자리와 배율", () => {
  it("폭 96px 안, 판 높이(위아래 여백 10) 안", () => {
    for (const key of Object.keys(STAGES)) {
      const l = minimapLayout(STAGES[key], 1200, 700);
      expect(l.x).toBe(MINIMAP.inset);
      expect(l.y).toBe(MINIMAP.inset);
      expect(l.w).toBeLessThanOrEqual(MINIMAP.width + 1e-9);
      expect(l.h).toBeLessThanOrEqual(700 - MINIMAP.inset * 2 + 1e-9);
    }
  });

  it("좁은 판에서는 판 폭의 14% 로 줄고, 아주 작은 판에는 없다", () => {
    expect(minimapLayout(STAGES.wheel, 360, 300).w).toBeLessThanOrEqual(Math.max(MINIMAP.minWidth, 360 * 0.14) + 1e-9);
    expect(minimapLayout(STAGES.wheel, 200, 140)).toBeNull();
  });
});

describe("판 좌표로", () => {
  it("띠의 가운데는 판 가로 가운데 · 위끝은 판 위, 띠 밖은 없음(여유만큼은 받는다)", () => {
    const stage = STAGES.wheel;
    const l = minimapLayout(stage, 1200, 700);
    const b = stageBounds(stage);
    const mid = minimapHit(l, l.x + l.w / 2, l.y);
    expect(mid.x).toBeCloseTo((b.minX + b.maxX) / 2, 6);
    expect(mid.y).toBeCloseTo(b.top, 6);
    expect(minimapHit(l, l.x + l.w + 30, l.y + 10)).toBeNull();
    const dragged = minimapHit(l, l.x + l.w + 30, l.y + 10, 400);
    expect(dragged.x).toBeCloseTo(b.minX + l.w / l.scale, 6);
  });
});
