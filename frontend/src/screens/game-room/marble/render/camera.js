import { FLAG_FINISHED } from "../engine/core.js";

/* 카메라 — 그리기 전용이다. 물리 · 지문에 닿지 않는다 (D-564).
 *
 * 판 폭을 캔버스에 맞추고(배율 = 픽셀/단위), 세로는 「당첨 경계에 선 구슬」을 따라간다 — 아직 정해질 당첨 자리가 n개 남았으면
 * 결승선을 안 넘은 구슬 중 n번째, 꼴찌 당첨이면 맨 뒤 구슬이다(원본 roulette.ts 의 규칙). 결승 근처(`zoomY`)에서는 확대한다.
 * 움직임은 보간(lerp)으로 부드럽게 — 프레임이 끊겨도 튀지 않는다. */

const boundsCache = new WeakMap();

/** 판의 좌표 범위(엔티티에서 한 번 계산해 둔다). 위쪽 여유는 출발 격자(최대 y ≈ -4)보다 조금 위다. */
export function stageBounds(stage) {
  let b = boundsCache.get(stage);
  if (b) return b;
  let minX = Infinity;
  let maxX = -Infinity;
  for (const e of stage.entities || []) {
    const s = e.shape;
    if (s.type === "polyline") {
      for (const [x] of s.points) { minX = Math.min(minX, e.position.x + x); maxX = Math.max(maxX, e.position.x + x); }
    } else {
      const r = s.type === "circle" ? s.radius : Math.max(s.width || 0, s.height || 0);
      minX = Math.min(minX, e.position.x - r);
      maxX = Math.max(maxX, e.position.x + r);
    }
  }
  if (!Number.isFinite(minX)) { minX = 0; maxX = 27; }
  b = { minX, maxX, top: -9, bottom: (stage.goalY || 111) + 5 };
  boundsCache.set(stage, b);
  return b;
}

/** 당첨 경계에 선 구슬의 참가자 번호. 없으면 -1. */
export function focusMarbleIndex(snapshot, winnersCount, pickLast) {
  if (!snapshot || !snapshot.ranking) return -1;
  const live = [];
  for (let i = 0; i < snapshot.ranking.length; i += 1) {
    const idx = snapshot.ranking[i];
    if (!(snapshot.flags[idx] & FLAG_FINISHED)) live.push(idx);
  }
  if (!live.length) return snapshot.ranking.length ? snapshot.ranking[snapshot.ranking.length - 1] : -1;
  if (pickLast) return live[live.length - 1];
  const remaining = Math.max(0, (winnersCount || 1) - (snapshot.finishedCount || 0));
  return remaining > 0 ? live[Math.min(live.length, remaining) - 1] : live[0];
}

export function cameraTarget({ stage, snapshot, width, height, focusIndex, waiting }) {
  const b = stageBounds(stage);
  const trackW = b.maxX - b.minX;
  const baseZoom = Math.max(6, width / (trackW + 1.5));
  let fx = (b.minX + b.maxX) / 2;
  let fy = 1.5;
  if (!waiting && snapshot && focusIndex >= 0) {
    fx = snapshot.positions[focusIndex * 3];
    fy = snapshot.positions[focusIndex * 3 + 1];
  }
  const finished = !waiting && !!(snapshot && snapshot.finished);
  const near = finished || (!waiting && fy >= (stage.zoomY || Infinity));
  const zoom = near ? baseZoom * 1.8 : waiting ? baseZoom * 1.5 : baseZoom;
  const viewW = width / zoom;
  const viewH = height / zoom;
  if (finished) {
    // 마지막 장면 — 결승선이 화면 위쪽 1/4 에 서고 그 아래에 들어온 구슬들이 보인다(결과 판이 아래를 덮어도 남는다).
    fx = (b.minX + b.maxX) / 2;
    fy = (stage.goalY || 111) + viewH * 0.25;
  }
  const x = near ? Math.min(Math.max(fx, b.minX + viewW / 2), b.maxX - viewW / 2) : (b.minX + b.maxX) / 2;
  const minY = b.top + viewH / 2;
  const maxY = b.bottom - viewH / 2;
  const y = maxY <= minY ? (b.top + b.bottom) / 2 : Math.min(Math.max(fy, minY), maxY);
  return { x, y, zoom };
}

export function createCamera() {
  const cam = { x: 13, y: 1.5, zoom: 24, ready: false };
  return {
    state() { return { x: cam.x, y: cam.y, zoom: cam.zoom }; },
    jump(target) {
      cam.x = target.x; cam.y = target.y; cam.zoom = target.zoom; cam.ready = true;
    },
    follow(target, lerp = 0.14) {
      if (!cam.ready) { this.jump(target); return; }
      cam.x += (target.x - cam.x) * lerp;
      cam.y += (target.y - cam.y) * lerp;
      cam.zoom += (target.zoom - cam.zoom) * lerp;
    },
    reset() { cam.ready = false; },
  };
}
