import { describe, it, expect } from "vitest";
import { baseZoomFor, cameraTarget, createCamera, focusMarbleIndex, fullZoomFor, leaderIndex, stageBounds, VIEW_UNITS } from "./camera.js";
import { STAGES } from "../engine/stages/index.js";
import { createRace } from "../engine/race.js";
import { packSnapshot, FLAG_FINISHED } from "../engine/core.js";

/* 카메라 (D-578) — 그리기 전용. 모드(따라가기 · 전체 · 자유)의 목표, 시간 기반 평활(60Hz 와 120Hz 가 같은 곳에 닿는다), 그리고
 * 카메라가 무엇을 하든 엔진 결과는 그대로다. */

const WHEEL = STAGES.wheel;
const W = 1200;
const H = 800;

function snap(positions, flags, ranking, extra = {}) {
  return { positions: Float32Array.from(positions), flags: Uint8Array.from(flags), ranking: Int16Array.from(ranking), finishedCount: 0, finished: false, ...extra };
}

describe("목표", () => {
  it("판 좌표 범위는 상자를 회전한 꼭짓점으로 잰다(세로로 긴 벽의 높이를 폭으로 세지 않는다)", () => {
    const yoru = stageBounds(STAGES.yoru);
    expect(yoru.minX).toBeGreaterThan(-5);
    expect(yoru.maxX).toBeLessThan(30);
  });

  it("기본 배율은 판 폭과 뷰 높이 26 단위 중 작은 쪽", () => {
    const b = stageBounds(WHEEL);
    expect(baseZoomFor(WHEEL, W, H)).toBeCloseTo(Math.min(W / (b.maxX - b.minX + 1.5), H / VIEW_UNITS), 6);
  });

  it("전체 보기는 판 전체가 들어가는 배율, 자유 보기는 고른 자리를 1.4 배로", () => {
    const full = cameraTarget({ stage: WHEEL, snapshot: null, width: W, height: H, mode: "full" });
    expect(full.zoom).toBeCloseTo(fullZoomFor(WHEEL, W, H), 6);
    const free = cameraTarget({ stage: WHEEL, snapshot: null, width: W, height: H, mode: "free", freeTarget: { x: 12, y: 60 } });
    // 미니맵 폭(insetLeft)을 주면 그 오른쪽 자리로 장면을 맞추고, 중심을 왼쪽으로 옮겨 장면 가운데가 그 자리의 가운데에 선다.
    const inset = 120;
    const plain = cameraTarget({ stage: WHEEL, snapshot: null, width: W - inset, height: H, mode: "free", freeTarget: { x: 12, y: 60 } });
    const shifted = cameraTarget({ stage: WHEEL, snapshot: null, width: W, height: H, mode: "free", freeTarget: { x: 12, y: 60 }, insetLeft: inset });
    expect(shifted.zoom).toBeCloseTo(plain.zoom, 6);
    expect(shifted.x).toBeCloseTo(plain.x - inset / (2 * plain.zoom), 6);
    const screenX = (plain.x - shifted.x) * shifted.zoom + W / 2;
    expect(screenX).toBeCloseTo(inset + (W - inset) / 2, 6);
    expect(free.zoom).toBeCloseTo(baseZoomFor(WHEEL, W, H) * 1.4, 6);
    expect(free.y).toBeCloseTo(60, 6);
  });

  it("따라가기 — 아무도 안 넘었으면 선두, 넘기 시작하면 당첨 경계 구슬", () => {
    // 구슬 셋: 0 은 앞(y 50), 1 은 중간(y 30), 2 는 뒤(y 10). 순위는 0, 1, 2.
    const s0 = snap([12, 50, 0, 12, 30, 0, 12, 10, 0], [0, 0, 0], [0, 1, 2]);
    expect(leaderIndex(s0)).toBe(0);
    const t0 = cameraTarget({ stage: WHEEL, snapshot: s0, width: W, height: H, focusIndex: focusMarbleIndex(s0, 2, false), leader: 0 });
    expect(t0.y).toBeGreaterThan(40); // 선두 쪽
    // 0 이 결승을 넘었고 당첨 2명 — 경계는 남은 구슬 중 첫째(1).
    const s1 = snap([12, 112, 0, 12, 30, 0, 12, 10, 0], [FLAG_FINISHED, 0, 0], [0, 1, 2], { finishedCount: 1 });
    expect(focusMarbleIndex(s1, 2, false)).toBe(1);
    const t1 = cameraTarget({ stage: WHEEL, snapshot: s1, width: W, height: H, focusIndex: 1, leader: leaderIndex(s1) });
    expect(Math.abs(t1.y - 30)).toBeLessThan(H / t1.zoom / 2);
  });

  it("당첨이 정해져 빨리 감는 동안은 경주가 끝난 장면에 선다(D-580)", () => {
    const s = snap([12, 112, 0, 12, 60, 0, 12, 20, 0], [FLAG_FINISHED, 0, 0], [0, 1, 2], { finishedCount: 1 });
    const following = cameraTarget({ stage: WHEEL, snapshot: { ...s, timeScale: 1 }, width: W, height: H, focusIndex: 1, leader: 1 });
    const fast = cameraTarget({ stage: WHEEL, snapshot: { ...s, timeScale: 20 }, width: W, height: H, focusIndex: 1, leader: 1 });
    const done = cameraTarget({ stage: WHEEL, snapshot: { ...s, finished: true }, width: W, height: H, focusIndex: 1, leader: 1 });
    expect(fast).toEqual(done);
    expect(following.y).toBeLessThan(done.y - 5);
  });

  it("결승 근처에서 확대한다(뷰 높이 6 단위가 바닥)", () => {
    const far = cameraTarget({ stage: WHEEL, snapshot: snap([12, 40, 0, 12, 20, 0], [0, 0], [0, 1]), width: W, height: H, focusIndex: 0, leader: 0 });
    const near = cameraTarget({ stage: WHEEL, snapshot: snap([12, WHEEL.zoomY, 0, 12, 20, 0], [0, 0], [0, 1]), width: W, height: H, focusIndex: 0, leader: 0 });
    expect(near.zoom).toBeGreaterThan(far.zoom * 2);
    expect(H / near.zoom).toBeGreaterThanOrEqual(6 - 1e-9);
  });
});

describe("시간 기반 평활", () => {
  it("60Hz 와 120Hz 가 1초 뒤 같은 곳에 닿는다", () => {
    const a = createCamera();
    const b = createCamera();
    const start = { x: 0, y: 0, zoom: 10 };
    const target = { x: 10, y: 100, zoom: 40 };
    a.jump(start);
    b.jump(start);
    for (let i = 0; i < 60; i += 1) a.follow(target, 1000 / 60);
    for (let i = 0; i < 120; i += 1) b.follow(target, 1000 / 120);
    expect(a.state().y).toBeCloseTo(b.state().y, 6);
    expect(a.state().zoom).toBeCloseTo(b.state().zoom, 6);
    expect(a.state().y).toBeGreaterThan(95);
  });

  it("탭에서 돌아온 긴 간격도 50ms 로 자른다 — 순간 이동하지 않는다", () => {
    const c = createCamera();
    c.jump({ x: 0, y: 0, zoom: 10 });
    c.follow({ x: 0, y: 100, zoom: 10 }, 5000);
    expect(c.state().y).toBeLessThan(25);
  });
});

describe("모드는 엔진에 닿지 않는다", () => {
  it("카메라를 어떻게 돌려도 경주 결과가 같다", () => {
    const parts = Array.from({ length: 8 }, (_, i) => ({ key: `k${i}`, name: `p${i}` }));
    const plain = createRace({ stage: WHEEL, participants: parts, seed: "cam", winners: 1 });
    const watched = createRace({ stage: WHEEL, participants: parts, seed: "cam", winners: 1 });
    const index = new Map(parts.map((p, i) => [p.key, i]));
    const cam = createCamera();
    const modes = ["follow", "full", "free"];
    let L = 0;
    let frame = 0;
    while (!plain.finished || !watched.finished) {
      L += 250;
      plain.stepTo(L, "c");
      watched.stepTo(L, "c");
      const s = packSnapshot(watched.snapshot(), index);
      const mode = modes[frame % 3];
      cam.follow(cameraTarget({ stage: WHEEL, snapshot: s, width: W, height: H, focusIndex: focusMarbleIndex(s, 1, false), leader: leaderIndex(s), mode, freeTarget: { x: 12, y: 50 } }), 16);
      frame += 1;
      if (L > 2_000_000) break;
    }
    expect(watched.result).toEqual(plain.result);
  }, 60_000);
});
