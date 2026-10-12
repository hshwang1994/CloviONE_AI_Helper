import { spawnPosition } from "../engine/layout.js";
import { FLAG_FINISHED, FLAG_GONE } from "../engine/core.js";
import { marbleColor } from "./theme.js";

/* Canvas 2D 그리기 — 상태를 바꾸지 않는다 (D-564). 스냅샷 한 장과 팔레트 · 카메라로 한 프레임을 그린다.
 *
 * - DPR ≤ 2(`MAX_DPR`), 뷰포트 밖 엔티티 · 구슬은 건너뛴다(컬링).
 * - 이름 라벨: 30명까지 전부, 60명까지 순위 상위 10 + 카메라 근처, 그 위는 상위 10의 번호 배지만(`labelPlan`).
 * - 결승선 · 당첨 구슬 테두리 · 사라진 구슬(결승 뒤 50스텝)의 잔상은 팔레트 값이다.
 * - 대기 중에는 참가자 구슬을 출발 격자에 놓은 장면이다(`waiting`). */

export const MAX_DPR = 2;
export const MARBLE_RADIUS = 0.25;
export const LABEL_ALL_MAX = 30;
export const LABEL_TOP_MAX = 60;
export const LABEL_TOP = 10;
const LABEL_NEAR_UNITS = 2.5;
const NAME_MAX_CHARS = 8;

export function labelPlan(total) {
  if (total <= LABEL_ALL_MAX) return "all";
  if (total <= LABEL_TOP_MAX) return "top-near";
  return "badge";
}

function shortName(name) {
  const s = String(name || "");
  return s.length > NAME_MAX_CHARS ? s.slice(0, NAME_MAX_CHARS - 1) + "…" : s;
}

/* 참가자별 자리 — 스냅샷이 있으면 그 값, 대기 중이면 출발 격자. */
export function marblePositions(snapshot, total, waiting) {
  const out = new Array(total);
  for (let i = 0; i < total; i += 1) {
    if (!waiting && snapshot && snapshot.positions && snapshot.positions.length >= total * 3) {
      const f = snapshot.flags[i];
      out[i] = {
        x: snapshot.positions[i * 3], y: snapshot.positions[i * 3 + 1], angle: snapshot.positions[i * 3 + 2],
        finished: !!(f & FLAG_FINISHED), gone: !!(f & FLAG_GONE),
      };
    } else {
      const at = spawnPosition(i, total);
      out[i] = { x: at.x, y: at.y, angle: 0, finished: false, gone: false };
    }
  }
  return out;
}

function drawEntities(ctx, stage, snapshot, pal, zoom, viewTop, viewBottom) {
  const entities = stage.entities || [];
  const thin = 1.5 / zoom;
  for (let i = 0; i < entities.length; i += 1) {
    const e = entities[i];
    const s = e.shape;
    const px = e.position.x;
    const py = e.position.y;
    if (s.type === "polyline") {
      ctx.beginPath();
      let began = false;
      for (const [x, y] of s.points) {
        if (!began) { ctx.moveTo(px + x, py + y); began = true; } else ctx.lineTo(px + x, py + y);
      }
      ctx.lineWidth = 2.5 / zoom;
      ctx.strokeStyle = pal.wall;
      ctx.lineJoin = "round";
      ctx.stroke();
      continue;
    }
    const reach = s.type === "circle" ? s.radius : Math.max(s.width || 0, s.height || 0) * 1.5;
    if (py + reach < viewTop || py - reach > viewBottom) continue;
    const kinematic = e.type === "kinematic";
    const bodyAngle = kinematic && snapshot && snapshot.entityAngles ? (snapshot.entityAngles[i] || 0) : 0;
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(bodyAngle + (s.rotation || 0));
    ctx.fillStyle = kinematic ? pal.rotor : pal.obstacle;
    ctx.strokeStyle = kinematic ? pal.rotorEdge : pal.obstacleEdge;
    ctx.lineWidth = thin;
    if (s.type === "box") {
      ctx.beginPath();
      ctx.rect(-s.width, -s.height, s.width * 2, s.height * 2);
      ctx.fill();
      ctx.stroke();
    } else if (s.type === "circle") {
      ctx.beginPath();
      ctx.arc(0, 0, s.radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();
  }
}

function drawFinishLine(ctx, stage, bounds, pal, zoom) {
  const y = stage.goalY;
  ctx.save();
  ctx.setLineDash([0.6, 0.35]);
  ctx.lineWidth = 2.5 / zoom;
  ctx.strokeStyle = pal.finish;
  ctx.beginPath();
  ctx.moveTo(bounds.minX, y);
  ctx.lineTo(bounds.maxX, y);
  ctx.stroke();
  ctx.restore();
}

function drawMarbles(ctx, marbles, participants, pal, zoom, winnerSet, viewTop, viewBottom) {
  const r = MARBLE_RADIUS;
  const edge = 1 / zoom;
  for (let i = 0; i < marbles.length; i += 1) {
    const m = marbles[i];
    if (m.y + r < viewTop || m.y - r > viewBottom) continue;
    const p = participants[i];
    ctx.save();
    if (m.gone) ctx.globalAlpha = pal.goneAlpha;
    // 그림자 한 단계
    ctx.beginPath();
    ctx.arc(m.x + 0.06, m.y + 0.08, r, 0, Math.PI * 2);
    ctx.fillStyle = pal.shadow;
    ctx.fill();
    // 몸
    ctx.beginPath();
    ctx.arc(m.x, m.y, r, 0, Math.PI * 2);
    ctx.fillStyle = marbleColor(p ? p.hue : 0, pal);
    ctx.fill();
    ctx.lineWidth = edge;
    ctx.strokeStyle = pal.marbleEdge;
    ctx.stroke();
    // 하이라이트
    ctx.beginPath();
    ctx.arc(m.x - r * 0.35, m.y - r * 0.35, r * 0.3, 0, Math.PI * 2);
    ctx.fillStyle = pal.highlight;
    ctx.fill();
    if (winnerSet && winnerSet.has(i)) {
      ctx.beginPath();
      ctx.arc(m.x, m.y, r + 0.12, 0, Math.PI * 2);
      ctx.lineWidth = 3 / zoom;
      ctx.strokeStyle = pal.winnerRing;
      ctx.stroke();
    }
    ctx.restore();
  }
}

const LABEL_MIN_GAP_PX = 44; // 출발 격자 간격 0.6 단위가 이보다 좁으면 라벨이 겹친다

function drawLabels(ctx, marbles, participants, snapshot, pal, cam, width, height, focusIndex, waiting) {
  const total = participants.length;
  if (waiting && cam.zoom * 0.6 < LABEL_MIN_GAP_PX) return;
  const plan = labelPlan(total);
  let chosen;
  if (plan === "all") {
    chosen = marbles.map((_, i) => i);
  } else {
    const top = [];
    const ranking = snapshot && snapshot.ranking ? snapshot.ranking : null;
    for (let i = 0; ranking && i < ranking.length && top.length < LABEL_TOP; i += 1) top.push(ranking[i]);
    if (!ranking) for (let i = 0; i < Math.min(total, LABEL_TOP); i += 1) top.push(i);
    chosen = new Set(top);
    if (plan === "top-near" && focusIndex >= 0) {
      const f = marbles[focusIndex];
      for (let i = 0; i < marbles.length; i += 1) {
        const m = marbles[i];
        if (Math.abs(m.x - f.x) <= LABEL_NEAR_UNITS && Math.abs(m.y - f.y) <= LABEL_NEAR_UNITS) chosen.add(i);
      }
    }
    chosen = Array.from(chosen);
  }
  ctx.save();
  ctx.font = `600 12px ${pal.fontFamily}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  ctx.lineJoin = "round";
  const rankOf = new Map();
  if (snapshot && snapshot.ranking) for (let i = 0; i < snapshot.ranking.length; i += 1) rankOf.set(snapshot.ranking[i], i + 1);
  for (const i of chosen) {
    const m = marbles[i];
    if (m.gone) continue;
    const sx = (m.x - cam.x) * cam.zoom + width / 2;
    const sy = (m.y - cam.y) * cam.zoom + height / 2 - MARBLE_RADIUS * cam.zoom - 3;
    if (sx < -40 || sx > width + 40 || sy < -20 || sy > height + 20) continue;
    const p = participants[i];
    const text = plan === "badge" ? String(rankOf.get(i) || i + 1) : shortName(p && p.name);
    ctx.lineWidth = 3;
    ctx.strokeStyle = pal.labelHalo;
    ctx.strokeText(text, sx, sy);
    ctx.fillStyle = pal.label;
    ctx.fillText(text, sx, sy);
  }
  ctx.restore();
}

function drawFinishLabel(ctx, stage, bounds, pal, cam, width, height) {
  const sy = (stage.goalY - cam.y) * cam.zoom + height / 2;
  if (sy < -20 || sy > height + 20) return;
  const sx = (bounds.maxX - cam.x) * cam.zoom + width / 2;
  ctx.save();
  ctx.font = `700 12px ${pal.fontFamily}`;
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.lineWidth = 3;
  ctx.strokeStyle = pal.labelHalo;
  ctx.strokeText("결승", sx - 4, sy - 4);
  ctx.fillStyle = pal.finishText;
  ctx.fillText("결승", sx - 4, sy - 4);
  ctx.restore();
}

/**
 * 한 프레임. `frame` = { width, height, dpr, palette, stage, bounds, snapshot, participants[{name, hue}], camera{x,y,zoom},
 *                      winnerSet(Set<번호>), focusIndex, waiting }
 */
export function drawFrame(ctx, frame) {
  const { width, height, dpr, palette: pal, stage, bounds, snapshot, participants, camera: cam, winnerSet, focusIndex, waiting } = frame;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = pal.board;
  ctx.fillRect(0, 0, width, height);
  const viewTop = cam.y - height / cam.zoom / 2 - 2;
  const viewBottom = cam.y + height / cam.zoom / 2 + 2;
  const marbles = marblePositions(snapshot, participants.length, waiting);
  ctx.save();
  ctx.translate(width / 2, height / 2);
  ctx.scale(cam.zoom, cam.zoom);
  ctx.translate(-cam.x, -cam.y);
  drawEntities(ctx, stage, snapshot, pal, cam.zoom, viewTop, viewBottom);
  drawFinishLine(ctx, stage, bounds, pal, cam.zoom);
  drawMarbles(ctx, marbles, participants, pal, cam.zoom, winnerSet, viewTop, viewBottom);
  ctx.restore();
  drawLabels(ctx, marbles, participants, snapshot, pal, cam, width, height, focusIndex, waiting);
  drawFinishLabel(ctx, stage, bounds, pal, cam, width, height);
  return marbles;
}
