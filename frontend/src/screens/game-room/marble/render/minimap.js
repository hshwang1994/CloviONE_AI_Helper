import { ENTITY_GONE, FLAG_GONE } from "../engine/core.js";
import { stageBounds } from "./camera.js";
import { marbleColor } from "./theme.js";

/* 미니맵 — 판 전체를 왼쪽 위 세로 띠로 (D-578, 원본 minimap.ts 의 자리 · 크기). 그리기 전용이다.
 *
 * 띠의 폭은 96px(좁은 판에서는 판 폭의 14%)이고 높이는 판 높이를 넘지 않게 배율을 줄인다. 벽 · 상자 · 원(사라진 깨지는 원은 빼고) ·
 * 결승선 · 구슬(2px 점, 참가자 색) · 지금 보이는 뷰포트(브랜드색 사각)를 그린다. 미니맵을 누르거나 끌면 그 자리를 보는 「자유 보기」가
 * 된다(`minimapHit` 이 화면 좌표를 판 좌표로 바꾼다) — 모드는 엔진에 닿지 않는다. */

export const MINIMAP = { inset: 10, width: 96, minWidth: 44, widthRatio: 0.14 };

/** 띠의 자리와 배율 — `{ x, y, w, h, scale, minX, top }`(화면 픽셀). 판이 너무 작으면 null. */
export function minimapLayout(stage, width, height) {
  const b = stageBounds(stage);
  const units = Math.max(1, b.maxX - b.minX);
  const span = Math.max(1, (stage.goalY || 111) + 2 - b.top);
  const maxW = Math.min(MINIMAP.width, Math.max(MINIMAP.minWidth, Math.round(width * MINIMAP.widthRatio)));
  const maxH = Math.max(0, height - MINIMAP.inset * 2);
  const scale = Math.min(maxW / units, maxH / span);
  if (!(scale > 0) || width < 240 || height < 160) return null;
  return { x: MINIMAP.inset, y: MINIMAP.inset, w: units * scale, h: span * scale, scale, minX: b.minX, top: b.top };
}

/** 화면 좌표(판 캔버스 안, CSS 픽셀) → 판 좌표. 띠 밖이면 null. `slop` 만큼 바깥도 받는다(끄는 손이 띠를 살짝 벗어나도 따라간다). */
export function minimapHit(layout, px, py, slop = 0) {
  if (!layout) return null;
  if (px < layout.x - slop || py < layout.y - slop || px > layout.x + layout.w + slop || py > layout.y + layout.h + slop) return null;
  const cx = Math.min(Math.max(px, layout.x), layout.x + layout.w);
  const cy = Math.min(Math.max(py, layout.y), layout.y + layout.h);
  return { x: layout.minX + (cx - layout.x) / layout.scale, y: layout.top + (cy - layout.y) / layout.scale };
}

/**
 * 미니맵 한 장. ctx 는 CSS 픽셀 좌표(dpr 변환이 걸린 상태)다.
 * frame = { layout, stage, snapshot, marbles([{x,y,gone}]), participants, palette, camera{x,y,zoom}, width, height, active }
 */
export function drawMinimap(ctx, { layout, stage, snapshot, marbles, participants, palette: pal, camera, width, height, active }) {
  if (!layout) return;
  const { x, y, w, h, scale, minX, top } = layout;
  ctx.save();
  // 띠 바탕 — 판 위에 떠 있는 작은 판.
  ctx.fillStyle = pal.minimapBg;
  ctx.strokeStyle = active ? pal.minimapViewport : pal.minimapEdge;
  ctx.lineWidth = 1;
  ctx.beginPath();
  if (typeof ctx.roundRect === "function") ctx.roundRect(x - 4, y - 4, w + 8, h + 8, 6);
  else ctx.rect(x - 4, y - 4, w + 8, h + 8);
  ctx.fill();
  ctx.stroke();
  ctx.beginPath();
  ctx.rect(x - 1, y - 1, w + 2, h + 2);
  ctx.clip();
  ctx.translate(x, y);
  ctx.scale(scale, scale);
  ctx.translate(-minX, -top);
  const thin = 1 / scale;
  const entities = stage.entities || [];
  const gone = snapshot && snapshot.entityFlags;
  ctx.lineJoin = "round";
  for (let i = 0; i < entities.length; i += 1) {
    if (gone && gone[i] & ENTITY_GONE) continue;
    const e = entities[i];
    const s = e.shape;
    if (s.type === "polyline") {
      ctx.beginPath();
      s.points.forEach(([px, py], k) => (k ? ctx.lineTo(e.position.x + px, e.position.y + py) : ctx.moveTo(e.position.x + px, e.position.y + py)));
      ctx.strokeStyle = pal.minimapWall;
      ctx.lineWidth = 1.2 * thin;
      ctx.stroke();
      continue;
    }
    const angle = e.type === "kinematic" && snapshot && snapshot.entityAngles ? snapshot.entityAngles[i] || 0 : 0;
    ctx.save();
    ctx.translate(e.position.x, e.position.y);
    ctx.rotate(angle + (s.rotation || 0));
    ctx.fillStyle = e.type === "kinematic" ? pal.rotor : pal.minimapWall;
    if (s.type === "box") {
      ctx.fillRect(-s.width, -s.height, s.width * 2, Math.max(s.height * 2, 1.2 * thin));
    } else if (s.type === "circle") {
      ctx.beginPath();
      ctx.arc(0, 0, Math.max(s.radius, thin), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }
  // 결승선
  ctx.strokeStyle = pal.finish;
  ctx.lineWidth = 2 * thin;
  ctx.beginPath();
  ctx.moveTo(minX, stage.goalY);
  ctx.lineTo(minX + w / scale, stage.goalY);
  ctx.stroke();
  // 구슬 — 2px 점
  const dot = 1.4 * thin;
  for (let i = 0; i < marbles.length; i += 1) {
    const m = marbles[i];
    if (m.gone || (snapshot && snapshot.flags && snapshot.flags[i] & FLAG_GONE)) continue;
    const p = participants[i];
    ctx.fillStyle = marbleColor(p ? p.hue : 0, pal);
    ctx.beginPath();
    ctx.arc(m.x, m.y, dot, 0, Math.PI * 2);
    ctx.fill();
  }
  // 지금 보이는 뷰포트
  if (camera && camera.zoom > 0) {
    const vw = width / camera.zoom;
    const vh = height / camera.zoom;
    ctx.strokeStyle = pal.minimapViewport;
    ctx.lineWidth = 1.5 * thin;
    ctx.strokeRect(camera.x - vw / 2, camera.y - vh / 2, vw, vh);
  }
  ctx.restore();
}
