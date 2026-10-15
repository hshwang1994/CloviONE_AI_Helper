import { FLAG_FINISHED } from "../engine/core.js";

/* 카메라 — 그리기 전용이다. 물리 · 지문에 닿지 않는다 (D-564 · D-578).
 *
 * 세 모드:
 *   follow  원본의 규칙 — 아직 아무도 결승을 안 넘었으면 **선두**를, 넘기 시작하면 **당첨 경계 구슬**(정해질 당첨 자리가 n개 남았으면
 *           결승 전 구슬 중 n번째, 꼴찌 당첨이면 맨 뒤)을 따라간다. 선두와 경계 구슬이 뷰 높이의 0.6 안이면 둘의 가운데를 잡아 무리를
 *           함께 보이고, 떨어지는 방향으로 조금 앞을 본다(세로 속도 × 0.25, ±3 단위). 결승(`zoomY`)에 가까워질수록 확대한다 —
 *           `기본 × (1 + 2.2t)`, 결승 근처 ≈ ×3.2, 뷰 높이 6 단위가 바닥. 끝나면 결승선이 화면 위 1/4 에 서는 마지막 장면.
 *   full    판 전체 — 지도처럼 본다.
 *   free    미니맵을 끌어 고른 자리(`freeTarget`) — 기본 × 1.4.
 * 기본 배율은 판 폭과 뷰 높이 26 단위 중 작은 쪽이다 — 넓은 판에서도 길의 생김새가 보이는 높이(원본이 보이는 세로 범위와 비슷하다).
 *
 * 움직임은 **시간 기반** 평활이다: `k = 1 − exp(−dt/τ)`(위치 τ 0.22초 · 배율 τ 0.45초, dt 는 50ms 까지만) — 60Hz 와 120Hz 화면,
 * 탭에서 돌아온 순간이 같은 느낌이다(예전의 프레임당 0.14 보간은 120Hz 에서 두 배 빨랐다). 모드는 엔진에 닿지 않는다. */

export const CAMERA_TAU = { pos: 0.22, zoom: 0.45 };
export const CAMERA_DT_MAX_MS = 50;
/* 따라가기 기본 장면의 세로 단위. 26 이면 가로판에서 트랙이 판의 절반 폭에 서고 구슬이 1366 에서 약 10px 였다(랩 캡처 2026-10-15) —
   18 이면 트랙이 미니맵 오른쪽 자리를 채우고 구슬이 1366 약 13px · 1920 약 23px 이다. 전체 장면은 미니맵 · 「전체 보기」가 맡는다. */
export const VIEW_UNITS = 18;
export const ZOOM_BOOST = 2.2;
export const ZOOM_RANGE = 12;
export const MIN_VIEW_UNITS = 6;

const boundsCache = new WeakMap();

/* 엔티티 모양의 꼭짓점(원은 외접 사각형) — 그리기용. 🔴 `engine/progressMap.js::reachPoints` 를 들여오지 않는다: 그 모듈은
   결정적 수학(`determinism.js`)을 끌고 와 주 스레드의 Math 를 바꾼다(그 설치는 워커와 시험 프로세스의 일이다). */
export function entityReach(e) {
  const { x, y } = e.position;
  const s = e.shape;
  if (s.type === "polyline") return s.points.map(([px, py]) => [x + px, y + py]);
  if (s.type === "circle") return [[x - s.radius, y - s.radius], [x + s.radius, y + s.radius]];
  const c = Math.cos(s.rotation || 0);
  const n = Math.sin(s.rotation || 0);
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sy]) => {
    const lx = sx * s.width;
    const ly = sy * s.height;
    return [x + lx * c - ly * n, y + lx * n + ly * c];
  });
}

/** 판의 좌표 범위(엔티티에서 한 번 계산해 둔다). 상자는 회전한 꼭짓점으로 잰다(세로로 긴 벽의 높이를 폭으로 세지 않는다).
 *  위쪽 여유는 출발 격자(최대 y ≈ −4)보다 조금 위다. */
export function stageBounds(stage) {
  let b = boundsCache.get(stage);
  if (b) return b;
  let minX = Infinity;
  let maxX = -Infinity;
  for (const e of stage.entities || []) {
    for (const [x] of entityReach(e)) {
      if (!Number.isFinite(x)) continue;
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
    }
  }
  if (!Number.isFinite(minX)) { minX = 0; maxX = 27; }
  b = { minX, maxX, top: -9, bottom: (stage.goalY || 111) + 5 };
  boundsCache.set(stage, b);
  return b;
}

/** 당첨 경계에 선 구슬의 참가자 번호. 없으면 -1. (화면의 순위로 고른다 — 그리기 전용) */
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

/** 아직 결승 전인 구슬 중 선두. 없으면 -1. */
export function leaderIndex(snapshot) {
  if (!snapshot || !snapshot.ranking) return -1;
  for (let i = 0; i < snapshot.ranking.length; i += 1) {
    const idx = snapshot.ranking[i];
    if (!(snapshot.flags[idx] & FLAG_FINISHED)) return idx;
  }
  return -1;
}

/** 기본 배율(픽셀/단위) — 판 폭에 맞춘 값과 뷰 높이 26 단위에 맞춘 값 중 작은 쪽. */
export function baseZoomFor(stage, width, height) {
  const b = stageBounds(stage);
  const trackW = b.maxX - b.minX;
  return Math.max(4, Math.min(width / (trackW + 1.5), height / VIEW_UNITS));
}

/** 판 전체가 들어가는 배율. */
export function fullZoomFor(stage, width, height) {
  const b = stageBounds(stage);
  return Math.max(1, Math.min(width / (b.maxX - b.minX + 2), height / (b.bottom - b.top + 2)));
}

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

function clampCenter(target, b, width, height) {
  const viewW = width / target.zoom;
  const viewH = height / target.zoom;
  const cx = (b.minX + b.maxX) / 2;
  const x = viewW >= b.maxX - b.minX ? cx : clamp(target.x, b.minX + viewW / 2, b.maxX - viewW / 2);
  const minY = b.top + viewH / 2;
  const maxY = b.bottom - viewH / 2;
  const y = maxY <= minY ? (b.top + b.bottom) / 2 : clamp(target.y, minY, maxY);
  return { x, y, zoom: target.zoom };
}

/**
 * 목표 장면. `snapshot` 은 엔진 스냅샷(대기 중이면 null), `focusIndex` · `leader` 는 참가자 번호, `velocityY` 는 따라가는 구슬의 세로 속도
 * (단위/초 — 부르는 쪽이 앞 스냅샷과의 차로 잰다), `freeTarget` 은 미니맵에서 고른 자리.
 */
export function cameraTarget(args) {
  /* `insetLeft` — 판 왼쪽을 덮는 미니맵 띠의 폭(CSS 픽셀). 카메라는 그 오른쪽 자리를 화면으로 삼아 장면을 맞추고, 중심을 그만큼 왼쪽으로
     옮겨 따라가는 구슬과 트랙이 미니맵 밑에 숨지 않게 한다. 물리 · 결과와 무관한 그리기 값이다(D-578). */
  const inset = Math.max(0, Math.min(Number(args.insetLeft) || 0, args.width * 0.4));
  const target = sceneTarget({ ...args, width: Math.max(1, args.width - inset) });
  return inset ? { ...target, x: target.x - inset / (2 * target.zoom) } : target;
}

function sceneTarget({ stage, snapshot, width, height, focusIndex, leader = -1, waiting, mode = "follow", freeTarget, velocityY = 0, spawnCenter }) {
  const b = stageBounds(stage);
  const base = baseZoomFor(stage, width, height);
  if (mode === "full") {
    return { x: (b.minX + b.maxX) / 2, y: (b.top + b.bottom) / 2, zoom: fullZoomFor(stage, width, height) };
  }
  if (mode === "free" && freeTarget) {
    return clampCenter({ x: freeTarget.x, y: freeTarget.y, zoom: base * 1.4 }, b, width, height);
  }
  if (waiting || !snapshot) {
    /* 출발 장면 — 출발 격자가 여백 3 단위와 함께 들어오는 배율(기본보다 작아지지 않는다). 원본의 시작 장면과 같은 구도다. */
    const c = spawnCenter || { x: (b.minX + b.maxX) / 2, y: 1.5, w: 1, h: 1 };
    const fit = Math.min(width / ((c.w || 1) + 6), height / ((c.h || 1) + 6), height / MIN_VIEW_UNITS);
    return clampCenter({ x: c.x, y: c.y, zoom: Math.max(base, fit) }, b, width, height);
  }
  const zoomY = Number.isFinite(stage.zoomY) ? stage.zoomY : stage.goalY;
  if (snapshot.finished) {
    // 마지막 장면 — 결승선이 화면 위쪽 1/4 에 서고 그 아래에 들어온 구슬들이 보인다.
    const zoom = Math.min(base * 1.6, height / MIN_VIEW_UNITS);
    const viewH = height / zoom;
    return clampCenter({ x: (b.minX + b.maxX) / 2, y: (stage.goalY || 111) + viewH * 0.25, zoom }, b, width, height);
  }
  const anchor = snapshot.finishedCount > 0 ? focusIndex : leader;
  const at = (i) => (i >= 0 ? { x: snapshot.positions[i * 3], y: snapshot.positions[i * 3 + 1] } : null);
  const a = at(anchor >= 0 ? anchor : focusIndex);
  if (!a) return clampCenter({ x: (b.minX + b.maxX) / 2, y: 1.5, zoom: base }, b, width, height);
  const t = clamp(1 - Math.abs(zoomY - a.y) / ZOOM_RANGE, 0, 1);
  const zoom = Math.min(base * (1 + ZOOM_BOOST * t), height / MIN_VIEW_UNITS);
  const viewH = height / zoom;
  let x = a.x;
  let y = a.y;
  const l = at(leader);
  if (l && anchor !== leader && Math.abs(l.y - a.y) < viewH * 0.6) {
    x = (l.x + a.x) / 2;
    y = (l.y + a.y) / 2;
  }
  y += clamp(velocityY * 0.25, -3, 3);
  return clampCenter({ x, y, zoom }, b, width, height);
}

export function createCamera() {
  const cam = { x: 13, y: 1.5, zoom: 24, ready: false };
  return {
    state() { return { x: cam.x, y: cam.y, zoom: cam.zoom }; },
    jump(target) {
      cam.x = target.x; cam.y = target.y; cam.zoom = target.zoom; cam.ready = true;
    },
    /** 시간 기반 평활 — `dtMs` 는 지난 그림과의 간격(50ms 까지). */
    follow(target, dtMs = 16) {
      if (!cam.ready) { this.jump(target); return; }
      const dt = clamp(dtMs, 0, CAMERA_DT_MAX_MS) / 1000;
      const kp = 1 - Math.exp(-dt / CAMERA_TAU.pos);
      const kz = 1 - Math.exp(-dt / CAMERA_TAU.zoom);
      cam.x += (target.x - cam.x) * kp;
      cam.y += (target.y - cam.y) * kp;
      cam.zoom += (target.zoom - cam.zoom) * kz;
    },
    reset() { cam.ready = false; },
  };
}
