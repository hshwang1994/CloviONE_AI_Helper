import { spawnPosition } from "../engine/layout.js";
import { ENTITY_GONE, FLAG_FINISHED, FLAG_GONE } from "../engine/core.js";
import { marbleColor } from "./theme.js";
import { spriteBucket } from "./marbleSprites.js";
import { drawMinimap } from "./minimap.js";

/* Canvas 2D 그리기 — 상태를 바꾸지 않는다 (D-564 · D-578). 스냅샷 한 장과 팔레트 · 카메라로 한 프레임을 그린다.
 *
 * - DPR ≤ 2(`MAX_DPR`), 뷰포트 밖 엔티티 · 구슬은 건너뛴다(컬링). 깨져 사라진 장애물(`entityFlags`)도 건너뛴다.
 * - 구슬은 참가자 스프라이트(얼굴 · 색 원 + 머리글자, `marbleSprites.js`)를 구르는 각으로 붙인다. 스프라이트를 못 만드는 환경에서는
 *   예전처럼 원 · 하이라이트를 그린다.
 * - 이름 라벨: 30명까지 전부(12px), 60명까지 순위 상위 10 + 카메라 근처(11px), 그 위는 상위 10의 번호 배지만(`labelPlan`). 이름은
 *   12자까지(`NAME_MAX_CHARS`). 몰린 구슬의 라벨은 겹치지 않게 앞선 순서대로만 선다(`placeLabels`).
 * - 결승선 · 당첨 구슬 고리(어두운 테마에선 글로, 30개 이하) · 사라진 구슬(결승 뒤 50스텝)의 잔상 · 효과(`effects.js`) · 미니맵.
 * - 대기 중에는 참가자 구슬을 출발 격자에 놓은 장면이다(`waiting`). */

export const MAX_DPR = 2;
export const MARBLE_RADIUS = 0.25;
export const LABEL_ALL_MAX = 30;
export const LABEL_TOP_MAX = 60;
export const LABEL_TOP = 10;
export const NAME_MAX_CHARS = 12;
const LABEL_NEAR_UNITS = 2.5;

export function labelPlan(total) {
  if (total <= LABEL_ALL_MAX) return "all";
  if (total <= LABEL_TOP_MAX) return "top-near";
  return "badge";
}

export function shortName(name) {
  const chars = Array.from(String(name || ""));
  return chars.length > NAME_MAX_CHARS ? chars.slice(0, NAME_MAX_CHARS - 1).join("") + "…" : chars.join("");
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
  const gone = snapshot && snapshot.entityFlags;
  for (let i = 0; i < entities.length; i += 1) {
    if (gone && gone[i] & ENTITY_GONE) continue;
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
    const breakable = (e.props && e.props.life) > 0;
    const bodyAngle = kinematic && snapshot && snapshot.entityAngles ? (snapshot.entityAngles[i] || 0) : 0;
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(bodyAngle + (s.rotation || 0));
    ctx.fillStyle = breakable ? pal.bubble : kinematic ? pal.rotor : pal.obstacle;
    ctx.strokeStyle = breakable ? pal.bubbleEdge : kinematic ? pal.rotorEdge : pal.obstacleEdge;
    ctx.lineWidth = breakable ? 2 / zoom : thin;
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
      if (breakable && s.radius * zoom > 10) {
        // 비눗방울의 빛 — 깨지는 장애물이라는 표지.
        ctx.beginPath();
        ctx.arc(-s.radius * 0.35, -s.radius * 0.35, s.radius * 0.28, 0, Math.PI * 2);
        ctx.fillStyle = pal.highlight;
        ctx.fill();
      }
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

function drawMarbles(ctx, marbles, participants, pal, cam, dpr, winnerSet, viewTop, viewBottom, sprites, glow) {
  const r = MARBLE_RADIUS;
  const zoom = cam.zoom;
  const edge = 1 / zoom;
  const bucket = sprites ? spriteBucket(r, zoom, dpr) : 0;
  for (let i = 0; i < marbles.length; i += 1) {
    const m = marbles[i];
    if (m.y + r < viewTop || m.y - r > viewBottom) continue;
    const p = participants[i];
    const won = !!(winnerSet && winnerSet.has(i));
    ctx.save();
    /* 결승 뒤 세계에서 빠진 구슬은 잔상으로 — 당첨 구슬만은 시상대의 주인공이라 또렷하게 남는다. */
    if (m.gone && !won) ctx.globalAlpha = pal.goneAlpha;
    // 그림자 한 단계
    ctx.beginPath();
    ctx.arc(m.x + 0.06, m.y + 0.08, r, 0, Math.PI * 2);
    ctx.fillStyle = pal.shadow;
    ctx.fill();
    if (won && glow) {
      ctx.shadowColor = pal.winnerGlow;
      ctx.shadowBlur = 18 * dpr;
    }
    const sprite = sprites ? sprites.get(i, p, bucket, pal) : null;
    if (sprite) {
      ctx.translate(m.x, m.y);
      ctx.rotate(m.angle || 0);
      ctx.drawImage(sprite, -r, -r, r * 2, r * 2);
      ctx.rotate(-(m.angle || 0));
      ctx.translate(-m.x, -m.y);
    } else {
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
    }
    ctx.shadowBlur = 0;
    if (won) {
      ctx.beginPath();
      ctx.arc(m.x, m.y, r + 0.12, 0, Math.PI * 2);
      ctx.lineWidth = 3 / zoom;
      ctx.strokeStyle = pal.winnerRing;
      ctx.stroke();
    }
    ctx.restore();
  }
}

const LABEL_MIN_GAP_PX = 40; // 출발 격자 간격 0.6 단위가 이보다 좁으면 라벨이 겹친다(한글 세 글자 12px ≈ 36px)
const LABEL_WIDTH_CACHE_MAX = 512;
const labelWidthCache = new Map();

function labelWidth(ctx, text) {
  const key = `${ctx.font}|${text}`;
  let w = labelWidthCache.get(key);
  if (w == null) {
    w = ctx.measureText(text).width;
    if (labelWidthCache.size >= LABEL_WIDTH_CACHE_MAX) labelWidthCache.clear();
    labelWidthCache.set(key, w);
  }
  return w;
}

/** 라벨 자리 고르기 — 우선순위 순서대로 놓되 이미 놓은 라벨과 겹치는 라벨은 건너뛴다. 구슬이 몰리면(결승 앞 깔때기) 이름이 서로
 *  덮여 아무것도 읽히지 않았다 — 이제 앞선 구슬의 이름만 읽히게 선다(건너뛴 구슬의 이름은 선두 칩 · 순위 레일이 말한다).
 *  items = [{ x, y, w, h }] — x 는 가운데, y 는 아랫변(화면 픽셀). `blocked` 는 판 위를 덮는 자리([{l,t,r,b}] — 미니맵 · 선두 칩 ·
 *  카메라 고르기)라 그 밑의 라벨은 처음부터 놓지 않는다. 놓을 항목을 같은 순서로 돌려준다. */
export function placeLabels(items, blocked = []) {
  const placed = blocked.map((r) => ({ l: r.l, r: r.r, t: r.t, b: r.b }));
  const out = [];
  for (const it of items) {
    const l = it.x - it.w / 2;
    const r = it.x + it.w / 2;
    const t = it.y - it.h;
    const b = it.y;
    let hit = false;
    for (const q of placed) {
      if (l < q.r && q.l < r && t < q.b && q.t < b) { hit = true; break; }
    }
    if (hit) continue;
    placed.push({ l, r, t, b });
    out.push(it);
  }
  return out;
}

function drawLabels(ctx, marbles, participants, snapshot, pal, cam, width, height, focusIndex, waiting, winnerSet, blocked) {
  const total = participants.length;
  if (waiting && cam.zoom * 0.6 < LABEL_MIN_GAP_PX) return;
  const plan = labelPlan(total);
  const rankOf = new Map();
  if (snapshot && snapshot.ranking) for (let i = 0; i < snapshot.ranking.length; i += 1) rankOf.set(snapshot.ranking[i], i + 1);
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
  // 당첨 구슬은 결승 뒤 세계에서 빠져도(잔상) 또렷하게 남으므로 이름도 남긴다 — 마지막 장면의 주인공이다.
  const won = (i) => !!(winnerSet && winnerSet.has(i));
  if (winnerSet) for (const i of winnerSet) if (!chosen.includes(i)) chosen.push(i);
  // 우선순위: 당첨 → 카메라가 따라가는 구슬 → 순위 → 나머지(참가자 순서).
  const prio = (i) => (won(i) ? -2 : i === focusIndex ? -1 : rankOf.has(i) ? rankOf.get(i) : 1e6 + i);
  chosen.sort((a, b) => prio(a) - prio(b));
  const fontPx = plan === "all" ? 12 : 11;
  ctx.save();
  ctx.font = `600 ${fontPx}px ${pal.fontFamily}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  ctx.lineJoin = "round";
  const items = [];
  for (const i of chosen) {
    const m = marbles[i];
    if (!m || (m.gone && !won(i))) continue;
    const sx = (m.x - cam.x) * cam.zoom + width / 2;
    const sy = (m.y - cam.y) * cam.zoom + height / 2 - MARBLE_RADIUS * cam.zoom - 3;
    if (sx < -40 || sx > width + 40 || sy < -20 || sy > height + 20) continue;
    const p = participants[i];
    const text = plan === "badge" ? String(rankOf.get(i) || i + 1) : shortName(p && p.name);
    items.push({ x: sx, y: sy, w: labelWidth(ctx, text) + 6, h: fontPx + 3, text });
  }
  for (const it of placeLabels(items, blocked)) {
    ctx.lineWidth = 3;
    ctx.strokeStyle = pal.labelHalo;
    ctx.strokeText(it.text, it.x, it.y);
    ctx.fillStyle = pal.label;
    ctx.fillText(it.text, it.x, it.y);
  }
  ctx.restore();
}

/** 결승 글자의 자리 — 결승선 오른쪽 끝 위. 판 위 DOM 컨트롤(`reserve`, 오른쪽 아래 카메라 고르기)과 겹치면 그 왼쪽으로 비킨다.
 *  반환은 글자의 오른쪽 끝 x(오른쪽 정렬). */
export function finishLabelX(rightX, labelY, textW, textH, reserve = []) {
  let x = rightX;
  for (const r of reserve) {
    const l = x - textW;
    if (l < r.r && r.l < x && labelY - textH < r.b && r.t < labelY) x = r.l - 6;
  }
  return x;
}

function drawFinishLabel(ctx, stage, bounds, pal, cam, width, height, reserve) {
  const sy = (stage.goalY - cam.y) * cam.zoom + height / 2;
  if (sy < -20 || sy > height + 20) return;
  const sx = Math.min((bounds.maxX - cam.x) * cam.zoom + width / 2, width - 12);
  ctx.save();
  ctx.font = `700 12px ${pal.fontFamily}`;
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.lineWidth = 3;
  ctx.strokeStyle = pal.labelHalo;
  const x = finishLabelX(sx - 4, sy - 4, labelWidth(ctx, "결승") + 4, 15, reserve);
  ctx.strokeText("결승", x, sy - 4);
  ctx.fillStyle = pal.finishText;
  ctx.fillText("결승", x, sy - 4);
  ctx.restore();
}

/**
 * 한 프레임. `frame` = { width, height, dpr, palette, stage, bounds, snapshot, participants[{name, hue, user_id}], camera{x,y,zoom},
 *                      winnerSet(Set<번호>), focusIndex, waiting, sprites?, effects?, now?, minimap?{layout, active},
 *                      reserve?[{l,t,r,b}] — 판 위 DOM 컨트롤(카메라 고르기 · 선두 칩 · 슬로 모션 표지)이 덮는 자리(CSS 픽셀) }
 */
export function drawFrame(ctx, frame) {
  const { width, height, dpr, palette: pal, stage, bounds, snapshot, participants, camera: cam, winnerSet, focusIndex, waiting, sprites, effects, now = 0, minimap, reserve } = frame;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = pal.board;
  ctx.fillRect(0, 0, width, height);
  const viewTop = cam.y - height / cam.zoom / 2 - 2;
  const viewBottom = cam.y + height / cam.zoom / 2 + 2;
  const marbles = marblePositions(snapshot, participants.length, waiting);
  const glow = pal.mode === "dark" && participants.length <= 30;
  ctx.save();
  ctx.translate(width / 2, height / 2);
  ctx.scale(cam.zoom, cam.zoom);
  ctx.translate(-cam.x, -cam.y);
  drawEntities(ctx, stage, snapshot, pal, cam.zoom, viewTop, viewBottom);
  drawFinishLine(ctx, stage, bounds, pal, cam.zoom);
  drawMarbles(ctx, marbles, participants, pal, cam, dpr, winnerSet, viewTop, viewBottom, sprites, glow);
  if (effects) effects.drawWorld(ctx, { now, zoom: cam.zoom, marbles, palette: pal });
  ctx.restore();
  /* 판 위를 덮는 자리 — 미니맵(캔버스에 마지막으로 그린다)과 DOM 컨트롤(`reserve`). 그 밑의 이름은 가려지므로 놓지 않는다. */
  const blocked = [...(reserve || [])];
  if (minimap && minimap.layout) {
    const L = minimap.layout;
    blocked.push({ l: L.x - 4, t: L.y - 4, r: L.x + L.w + 4, b: L.y + L.h + 4 });
  }
  drawLabels(ctx, marbles, participants, snapshot, pal, cam, width, height, focusIndex, waiting, winnerSet, blocked);
  drawFinishLabel(ctx, stage, bounds, pal, cam, width, height, reserve);
  if (effects) effects.drawScreen(ctx, { now, goalScreenY: (stage.goalY - cam.y) * cam.zoom + height / 2, width, palette: pal });
  if (minimap && minimap.layout) {
    drawMinimap(ctx, { layout: minimap.layout, stage, snapshot: waiting ? null : snapshot, marbles, participants, palette: pal, camera: cam, width, height, active: minimap.active });
  }
  return marbles;
}
