/* 진행도 지도 — 순위 계산용 (lazygyu/roulette 의 progressMap.ts 를 옮김, MIT · ATTRIBUTION.md).
 *
 * y 좌표만으로 순위를 매기면 옆으로 돌아가거나 위로 올라갔다 내려오는 판에서 순위가 틀어진다. 판을 읽을 때 한 번 0.25 격자를
 * 만들어 결승선에서부터 「벽을 피해 가는 거리」를 퍼뜨려 두고(8방향 Dijkstra, 위로 가는 이동은 회전 장애물 · 튕기는 장애물 근처
 * 밖에서 10배 비용), 매 프레임에는 구슬 주변 3×3 칸만 읽어 남은 거리를 구한다. 결승선과 이어지지 않은 곳은 1e6 − y 다.
 *
 * 결정성: `Math.hypot` 대신 제곱근을 쓴다(`determinism.js`). 이 지도는 **실시간 순위 표시와 미완주 구슬의 마지막 순위**에만 쓰이고
 * 물리에는 닿지 않는다. */

import { hypot } from "./determinism.js";

const CELL = 0.25;
const MARBLE_RADIUS = 0.25;
const INFLATE = Math.max(MARBLE_RADIUS, (CELL * Math.SQRT2) / 2 + 0.001);
const TOP_LIMIT = -30;
const MARGIN = 1;
const UNREACHABLE = 1e6;
const BLOCKED = -1;
const UP_PENALTY = 10;
const LIFT_MARGIN = MARBLE_RADIUS + 0.5;
const BOUNCE_RANGE = 1.5;

function isBlocking(e) {
  if ((e.props.life ?? -1) > 0) return false;
  if (e.type === "kinematic" && e.props.angularVelocity !== 0) return false;
  return true;
}

/* 엔티티 모양의 꼭짓점(원은 외접 사각형) — 경계 상자용. 상자의 width · height 는 반폭 · 반높이(Box2D 의 SetAsBox). */
export function reachPoints(e) {
  const { x, y } = e.position;
  const s = e.shape;
  if (s.type === "polyline") return s.points.map(([px, py]) => [x + px, y + py]);
  if (s.type === "circle") return [[x - s.radius, y - s.radius], [x + s.radius, y + s.radius]];
  const cos = Math.cos(s.rotation);
  const sin = Math.sin(s.rotation);
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sy]) => {
    const lx = sx * s.width;
    const ly = sy * s.height;
    return [x + lx * cos - ly * sin, y + lx * sin + ly * cos];
  });
}

function segmentDistance(px, py, ax, ay, bx, by) {
  const vx = bx - ax;
  const vy = by - ay;
  const len = vx * vx + vy * vy;
  const t = len === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * vx + (py - ay) * vy) / len));
  return hypot(px - (ax + t * vx), py - (ay + t * vy));
}

function shapeDistance(e) {
  const { x: ox, y: oy } = e.position;
  const s = e.shape;
  if (s.type === "circle") return (x, y) => Math.max(0, hypot(x - ox, y - oy) - s.radius);
  if (s.type === "box") {
    const cos = Math.cos(-s.rotation);
    const sin = Math.sin(-s.rotation);
    return (x, y) => {
      const dx = x - ox;
      const dy = y - oy;
      const lx = Math.abs(dx * cos - dy * sin) - s.width;
      const ly = Math.abs(dx * sin + dy * cos) - s.height;
      return hypot(Math.max(lx, 0), Math.max(ly, 0));
    };
  }
  const pts = s.points.map(([px, py]) => [ox + px, oy + py]);
  return (x, y) => {
    let best = Infinity;
    for (let i = 0; i < pts.length - 1; i += 1) {
      best = Math.min(best, segmentDistance(x, y, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]));
    }
    return best;
  };
}

/* 칸 번호를 거리 순으로 꺼내는 이진 힙(중복 push 허용, 낡은 값은 꺼낼 때 버린다). */
class MinHeap {
  constructor(capacity) {
    this.ids = new Int32Array(Math.max(16, capacity));
    this.keys = new Float32Array(Math.max(16, capacity));
    this.size = 0;
  }

  push(id, key) {
    if (this.size === this.ids.length) this.grow();
    let i = this.size;
    this.size += 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (this.keys[p] <= key) break;
      this.ids[i] = this.ids[p];
      this.keys[i] = this.keys[p];
      i = p;
    }
    this.ids[i] = id;
    this.keys[i] = key;
  }

  topKey() { return this.keys[0]; }

  pop() {
    const top = this.ids[0];
    this.size -= 1;
    const lastId = this.ids[this.size];
    const lastKey = this.keys[this.size];
    let i = 0;
    for (;;) {
      const l = 2 * i + 1;
      if (l >= this.size) break;
      const r = l + 1;
      const m = r < this.size && this.keys[r] < this.keys[l] ? r : l;
      if (this.keys[m] >= lastKey) break;
      this.ids[i] = this.ids[m];
      this.keys[i] = this.keys[m];
      i = m;
    }
    this.ids[i] = lastId;
    this.keys[i] = lastKey;
    return top;
  }

  grow() {
    const ids = new Int32Array(this.ids.length * 2);
    const keys = new Float32Array(this.keys.length * 2);
    ids.set(this.ids);
    keys.set(this.keys);
    this.ids = ids;
    this.keys = keys;
  }
}

const cache = new WeakMap();

export class ProgressMap {
  constructor(stage) {
    const entities = (stage.entities || []).filter(isBlocking);
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    for (const e of entities) {
      for (const [x, y] of reachPoints(e)) {
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
      }
    }
    if (!Number.isFinite(minX)) { minX = 0; maxX = 26; minY = 0; }
    this.minX = Math.floor(minX - MARGIN);
    this.minY = Math.floor(Math.max(minY, TOP_LIMIT) - MARGIN);
    const maxY = stage.goalY + MARGIN;
    this.cols = Math.ceil((maxX + MARGIN - this.minX) / CELL) + 1;
    this.rows = Math.ceil((maxY - this.minY) / CELL) + 1;
    this.dist = new Float32Array(this.cols * this.rows).fill(Infinity);
    for (const e of entities) this.rasterize(e);
    this.lift = this.findLiftCells(stage.entities || []);
    this.maxDist = this.propagate(stage.goalY);
  }

  /* 같은 판 객체면 다시 만들지 않는다. */
  static for(stage) {
    let map = cache.get(stage);
    if (!map) {
      map = new ProgressMap(stage);
      cache.set(stage, map);
    }
    return map;
  }

  cellX(col) { return this.minX + col * CELL; }

  cellY(row) { return this.minY + row * CELL; }

  rasterize(e) {
    if (e.shape.type !== "circle") {
      const pts = reachPoints(e);
      const closed = e.shape.type === "box";
      for (let i = 0; i < pts.length - (closed ? 0 : 1); i += 1) {
        const [ax, ay] = pts[i];
        const [bx, by] = pts[(i + 1) % pts.length];
        this.rasterizeSegment(ax, ay, bx, by);
      }
      return;
    }
    const { x, y } = e.position;
    const reach = e.shape.radius + INFLATE;
    const distanceTo = shapeDistance(e);
    const c0 = Math.max(0, Math.floor((x - reach - this.minX) / CELL));
    const c1 = Math.min(this.cols - 1, Math.ceil((x + reach - this.minX) / CELL));
    const r0 = Math.max(0, Math.floor((y - reach - this.minY) / CELL));
    const r1 = Math.min(this.rows - 1, Math.ceil((y + reach - this.minY) / CELL));
    for (let r = r0; r <= r1; r += 1) {
      const cy = this.cellY(r);
      for (let c = c0; c <= c1; c += 1) {
        if (distanceTo(this.cellX(c), cy) < INFLATE) this.dist[r * this.cols + c] = BLOCKED;
      }
    }
  }

  rasterizeSegment(ax, ay, bx, by) {
    const minX = this.minX - INFLATE;
    const maxX = this.minX + (this.cols - 1) * CELL + INFLATE;
    const minY = this.minY - INFLATE;
    const maxY = this.minY + (this.rows - 1) * CELL + INFLATE;
    const dx = bx - ax;
    const dy = by - ay;
    let t0 = 0;
    let t1 = 1;
    for (const [p, q] of [[-dx, ax - minX], [dx, maxX - ax], [-dy, ay - minY], [dy, maxY - ay]]) {
      if (p === 0) {
        if (q < 0) return;
      } else {
        const t = q / p;
        if (p < 0) t0 = Math.max(t0, t);
        else t1 = Math.min(t1, t);
      }
    }
    if (t0 > t1) return;
    const sx = ax + dx * t0;
    const sy = ay + dy * t0;
    const len = hypot(dx, dy) * (t1 - t0);
    const steps = Math.max(1, Math.ceil(len / (CELL / 2)));
    const span = Math.ceil(INFLATE / CELL) + 1;
    for (let k = 0; k <= steps; k += 1) {
      const t = k / steps;
      const c = Math.round((sx + dx * (t1 - t0) * t - this.minX) / CELL);
      const r = Math.round((sy + dy * (t1 - t0) * t - this.minY) / CELL);
      for (let rr = Math.max(0, r - span); rr <= Math.min(this.rows - 1, r + span); rr += 1) {
        for (let cc = Math.max(0, c - span); cc <= Math.min(this.cols - 1, c + span); cc += 1) {
          const i = rr * this.cols + cc;
          if (this.dist[i] === BLOCKED) continue;
          if (segmentDistance(this.cellX(cc), this.cellY(rr), ax, ay, bx, by) < INFLATE) this.dist[i] = BLOCKED;
        }
      }
    }
  }

  findLiftCells(all) {
    const lift = new Uint8Array(this.cols * this.rows);
    const mark = (x0, x1, y0, y1, inside) => {
      const c0 = Math.max(0, Math.floor((x0 - this.minX) / CELL));
      const c1 = Math.min(this.cols - 1, Math.ceil((x1 - this.minX) / CELL));
      const r0 = Math.max(0, Math.floor((y0 - this.minY) / CELL));
      const r1 = Math.min(this.rows - 1, Math.ceil((y1 - this.minY) / CELL));
      for (let r = r0; r <= r1; r += 1) {
        for (let c = c0; c <= c1; c += 1) {
          if (inside(this.cellX(c), this.cellY(r))) lift[r * this.cols + c] = 1;
        }
      }
    };
    for (const e of all) {
      if (e.type === "kinematic" && e.props.angularVelocity !== 0) {
        const { x: ox, y: oy } = e.position;
        const reach = Math.max(...reachPoints(e).map(([x, y]) => hypot(x - ox, y - oy))) + LIFT_MARGIN;
        mark(ox - reach, ox + reach, oy - reach, oy + reach, (x, y) => hypot(x - ox, y - oy) <= reach);
      }
      if (e.props.restitution > 1) {
        const pts = reachPoints(e);
        const distanceTo = shapeDistance(e);
        mark(
          Math.min(...pts.map((p) => p[0])) - BOUNCE_RANGE, Math.max(...pts.map((p) => p[0])) + BOUNCE_RANGE,
          Math.min(...pts.map((p) => p[1])) - BOUNCE_RANGE, Math.max(...pts.map((p) => p[1])) + BOUNCE_RANGE,
          (x, y) => distanceTo(x, y) <= BOUNCE_RANGE,
        );
      }
    }
    return lift;
  }

  propagate(goalY) {
    const { cols, rows, dist } = this;
    const heap = new MinHeap(cols * rows);
    const goalRow = Math.max(0, Math.min(rows - 1, Math.ceil((goalY - this.minY) / CELL)));
    for (let r = goalRow; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const i = r * cols + c;
        if (dist[i] === BLOCKED) continue;
        dist[i] = 0;
        heap.push(i, 0);
      }
    }
    const D = CELL * Math.SQRT2;
    const steps = [[-1, 0, CELL], [1, 0, CELL], [0, -1, CELL], [0, 1, CELL], [-1, -1, D], [1, -1, D], [-1, 1, D], [1, 1, D]];
    let maxDist = 0;
    while (heap.size > 0) {
      const d = heap.topKey();
      const i = heap.pop();
      if (d > dist[i]) continue;
      maxDist = d;
      const r = (i / cols) | 0;
      const c = i - r * cols;
      for (const [dc, dr, w] of steps) {
        const nc = c + dc;
        const nr = r + dr;
        if (nc < 0 || nc >= cols || nr < 0 || nr >= rows) continue;
        const j = nr * cols + nc;
        const cur = dist[j];
        if (cur === BLOCKED) continue;
        if (dc && dr && (dist[r * cols + nc] === BLOCKED || dist[nr * cols + c] === BLOCKED)) continue;
        const up = dr > 0 && !this.lift[i] && !this.lift[j];
        const nd = d + (up ? w * UP_PENALTY : w);
        if (nd < cur) {
          dist[j] = nd;
          heap.push(j, nd);
        }
      }
    }
    return maxDist;
  }

  /* (x, y) 에서 결승까지 남은 거리. 작을수록 앞선다. */
  distanceAt(x, y) {
    let extra = 0;
    let qy = y;
    if (qy < this.minY) {
      extra = this.minY - qy;
      qy = this.minY;
    }
    const col = Math.round((x - this.minX) / CELL);
    const row = Math.round((qy - this.minY) / CELL);
    if (row >= this.rows) return 0;
    let best = Infinity;
    for (let radius = 1; radius <= 3 && best === Infinity; radius += 1) {
      for (let dr = -radius; dr <= radius; dr += 1) {
        const r = row + dr;
        if (r < 0 || r >= this.rows) continue;
        for (let dc = -radius; dc <= radius; dc += 1) {
          const c = col + dc;
          if (c < 0 || c >= this.cols) continue;
          const d = this.dist[r * this.cols + c];
          if (d < 0 || d === Infinity) continue;
          const cand = d + hypot(x - this.cellX(c), qy - this.cellY(r));
          if (cand < best) best = cand;
        }
      }
    }
    if (best === Infinity) return UNREACHABLE - y;
    return best + extra;
  }
}
