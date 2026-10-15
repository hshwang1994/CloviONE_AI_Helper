import { marbleColor } from "./theme.js";

/* 구슬 그림(스프라이트) — 참가자의 얼굴이 구슬이 된다 (D-577 · D-578). 그리기 전용이다(물리 반지름 0.25 는 그대로).
 *
 * 참가자마다 화면 밖 캔버스 하나에 미리 그려 두고 프레임마다 `drawImage` 한 번(+ 구르는 각)으로 붙인다 — 100개를 매 프레임 원 ·
 * 그림 · 글자로 다시 그리지 않는다. 한 장의 모양: 원으로 자른 얼굴(사람 참가자 — `AvatarImageCache` 의 그림, DOM 의 `UserAvatar` 와
 * 같은 얼굴) 또는 참가자 색 + 머리글자(자유 이름 · 그림 실패) → 참가자 색 고리 2px → 가장자리 선 → 왼쪽 위 하이라이트.
 *
 * 크기는 칸(버킷)으로 고른다: `ceil(2r × 배율 × dpr / 8) × 8` 픽셀. 확대 · 축소 중 크기가 조금 바뀔 때마다 다시 그리지 않고, 칸이 바뀌거나
 * 테마 · 그림 상태가 바뀔 때만 다시 그린다(참가자 100명까지). 머리글자는 61명부터 번호(참가자 번호 + 1)로 바뀐다 — 라벨 계획과 같은 문턱. */

export const SPRITE_BUCKET = 8;
export const SPRITE_MIN = 16;
export const SPRITE_MAX = 256;
export const INITIAL_MAX_TOTAL = 60;

export function spriteBucket(radius, zoom, dpr) {
  const px = Math.ceil((2 * radius * zoom * dpr) / SPRITE_BUCKET) * SPRITE_BUCKET;
  return Math.max(SPRITE_MIN, Math.min(SPRITE_MAX, px));
}

function initialOf(name) {
  const s = String(name || "").trim();
  return s ? Array.from(s)[0] : "?";
}

function makeCanvas(size) {
  if (typeof OffscreenCanvas === "function") return new OffscreenCanvas(size, size);
  if (typeof document !== "undefined") {
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    return c;
  }
  return null;
}

/** 스프라이트 한 장을 그린다. `img` 가 있으면 얼굴, 없으면 색 + 글자. */
export function paintSprite(canvas, { size, color, img, label, palette, ring = true }) {
  const ctx = canvas.getContext && canvas.getContext("2d");
  if (!ctx) return;
  const r = size / 2;
  const ringW = Math.max(2, Math.round(size * 0.09));
  ctx.clearRect(0, 0, size, size);
  ctx.save();
  ctx.beginPath();
  ctx.arc(r, r, r - 0.5, 0, Math.PI * 2);
  ctx.closePath();
  ctx.clip();
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, size, size);
  if (img) {
    // 얼굴 — 고리 안쪽 원을 덮는 「cover」 맞춤.
    const inner = size - ringW * 2;
    const iw = img.naturalWidth || img.width || inner;
    const ih = img.naturalHeight || img.height || inner;
    const k = Math.max(inner / iw, inner / ih);
    const w = iw * k;
    const h = ih * k;
    ctx.save();
    ctx.beginPath();
    ctx.arc(r, r, r - ringW, 0, Math.PI * 2);
    ctx.clip();
    ctx.fillStyle = palette.spriteFace;
    ctx.fillRect(0, 0, size, size);
    try { ctx.drawImage(img, r - w / 2, r - h / 2, w, h); } catch (e) { /* 그림이 막혔다(CORS 등) — 색 원으로 남는다 */ }
    ctx.restore();
  } else if (label) {
    ctx.fillStyle = "#FFFFFF";
    ctx.font = `800 ${Math.round(size * (label.length > 2 ? 0.34 : 0.46))}px ${palette.fontFamily}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.shadowColor = "rgba(0,0,0,.35)";
    ctx.shadowBlur = Math.max(1, size * 0.04);
    ctx.fillText(label, r, r + size * 0.03);
    ctx.shadowBlur = 0;
  }
  // 하이라이트 — 왼쪽 위에서 비치는 빛.
  const g = ctx.createRadialGradient(r * 0.62, r * 0.55, 0, r * 0.62, r * 0.55, r * 0.95);
  g.addColorStop(0, palette.highlight);
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  ctx.restore();
  if (ring) {
    ctx.beginPath();
    ctx.arc(r, r, r - ringW / 2 - 0.5, 0, Math.PI * 2);
    ctx.lineWidth = ringW;
    ctx.strokeStyle = color;
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.arc(r, r, r - 0.75, 0, Math.PI * 2);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = palette.marbleEdge;
  ctx.stroke();
}

/**
 * 참가자별 스프라이트 저장소. `get(i, participant, bucket, palette)` → 캔버스(그릴 수 없으면 null).
 * `imageOf(participant)` 는 `{ img, status }` 를 준다(`AvatarImageCache.get` 에 사람 신원을 넘긴 것) — 없으면 자유 이름 구슬이다.
 */
export function createSpriteCache({ imageOf, total = 0 } = {}) {
  const store = new Map(); // index → { canvas, sig }
  return {
    clear() { store.clear(); },
    get(i, p, bucket, palette) {
      const entry = imageOf && p && p.user_id ? imageOf(p) : { img: null, status: "none" };
      const ready = entry && entry.status === "ready" && entry.img;
      const label = total > INITIAL_MAX_TOTAL ? String(i + 1) : initialOf(p && p.name);
      const color = marbleColor(p ? p.hue : 0, palette);
      const sig = `${bucket}|${palette.mode}|${color}|${ready ? "img" : label}|${entry ? entry.status : "none"}`;
      const hit = store.get(i);
      if (hit && hit.sig === sig) return hit.canvas;
      const canvas = hit && hit.canvas && hit.canvas.width === bucket ? hit.canvas : makeCanvas(bucket);
      if (!canvas) return null;
      paintSprite(canvas, { size: bucket, color, img: ready ? entry.img : null, label, palette });
      store.set(i, { canvas, sig });
      return canvas;
    },
  };
}
