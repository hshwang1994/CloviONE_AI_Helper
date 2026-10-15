import { FLAG_FINISHED } from "../engine/core.js";
import { marbleColor } from "./theme.js";

/* 경주 효과 — 그리기 전용 (D-578). 엔진 · 지문에 닿지 않고, 무작위(`Math.random`)도 여기서만 쓴다(화면마다 달라도 되는 것들).
 *
 *   결승 통과   새로 결승선을 넘은 구슬마다 참가자 색 네모 36개가 튀고, 결승선 위에 「결승 통과」가 0.8초 떠오른다.
 *   선두 교체   새 선두 구슬 둘레에 0.6초 맥박 고리.
 *   당첨 공개   발표할 수 있는 결과가 오면 당첨 구슬에 고리 + 글로(어두운 테마, 구슬 30개 이하일 때만 — 글로는 비싸다).
 * 효과가 살아 있는 동안만 그림 루프가 돈다(`alive`). 한 번에 떠 있는 조각은 600개까지 — 100명이 몰려 들어와도 프레임을 지킨다. */

export const BURST_COUNT = 36;
export const BURST_MS = 900;
export const FLASH_MS = 800;
export const PULSE_MS = 600;
export const MAX_PARTICLES = 600;
export const GLOW_MAX_MARBLES = 30;

export function createEffects() {
  let particles = [];
  let flashes = [];
  let pulses = [];
  let lastFinished = null; // Uint8Array — 지난 스냅샷의 완주 표시
  let lastLeader = -1;
  let lastStep = -1;

  return {
    reset() {
      particles = [];
      flashes = [];
      pulses = [];
      lastFinished = null;
      lastLeader = -1;
      lastStep = -1;
    },
    /** 스냅샷이 바뀔 때마다 — 새 완주 · 선두 교체를 찾아 효과를 만든다. 처음 본 스냅샷(늦은 입장 · 새로고침)은 기억만 한다. */
    observe(snapshot, participants, palette, now, leader) {
      if (!snapshot || !snapshot.flags) return;
      if (snapshot.step === lastStep) return;
      const first = lastFinished == null || snapshot.step < lastStep;
      lastStep = snapshot.step;
      const flags = snapshot.flags;
      if (!first) {
        for (let i = 0; i < flags.length; i += 1) {
          if ((flags[i] & FLAG_FINISHED) && !(lastFinished[i] & FLAG_FINISHED)) {
            const p = participants[i];
            const color = marbleColor(p ? p.hue : 0, palette);
            const x = snapshot.positions[i * 3];
            const y = snapshot.positions[i * 3 + 1];
            const room = Math.max(0, MAX_PARTICLES - particles.length);
            const n = Math.min(BURST_COUNT, room);
            for (let k = 0; k < n; k += 1) {
              const ang = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.2;
              const speed = 2.5 + Math.random() * 5;
              particles.push({ x, y, vx: Math.cos(ang) * speed, vy: Math.sin(ang) * speed, born: now, color, size: 0.09 + Math.random() * 0.08, spin: Math.random() * Math.PI });
            }
            flashes.push({ born: now, name: p ? p.name : "" });
            if (flashes.length > 3) flashes.shift();
          }
        }
        if (leader >= 0 && lastLeader >= 0 && leader !== lastLeader) pulses.push({ index: leader, born: now });
      }
      lastFinished = Uint8Array.from(flags);
      lastLeader = leader;
    },
    alive(now) {
      return particles.length > 0 || flashes.some((f) => now - f.born < FLASH_MS) || pulses.some((p) => now - p.born < PULSE_MS);
    },
    /** 판 좌표의 효과(조각 · 맥박) — 카메라 변환이 걸린 상태에서 부른다. */
    drawWorld(ctx, { now, zoom, marbles, palette }) {
      const keep = [];
      for (const p of particles) {
        const t = (now - p.born) / 1000;
        if (t * 1000 > BURST_MS) continue;
        keep.push(p);
        const x = p.x + p.vx * t;
        const y = p.y + p.vy * t + 4.5 * t * t;
        ctx.save();
        ctx.globalAlpha = Math.max(0, 1 - (t * 1000) / BURST_MS);
        ctx.translate(x, y);
        ctx.rotate(p.spin + t * 6);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size, -p.size, p.size * 2, p.size * 2);
        ctx.restore();
      }
      particles = keep;
      pulses = pulses.filter((p) => now - p.born < PULSE_MS);
      for (const p of pulses) {
        const m = marbles[p.index];
        if (!m || m.gone) continue;
        const k = (now - p.born) / PULSE_MS;
        ctx.save();
        ctx.globalAlpha = 1 - k;
        ctx.strokeStyle = palette.winnerRing;
        ctx.lineWidth = 2.5 / zoom;
        ctx.beginPath();
        ctx.arc(m.x, m.y, 0.25 + 0.15 + k * 0.6, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    },
    /** 화면 좌표의 효과(「결승 통과」 글자) — 결승선 위에 떠오른다. */
    drawScreen(ctx, { now, goalScreenY, width, palette }) {
      flashes = flashes.filter((f) => now - f.born < FLASH_MS);
      if (!flashes.length) return;
      const f = flashes[flashes.length - 1];
      const k = (now - f.born) / FLASH_MS;
      const y = Math.min(Math.max(goalScreenY - 18 - k * 16, 28), 10_000);
      ctx.save();
      ctx.globalAlpha = k < 0.15 ? k / 0.15 : 1 - Math.max(0, (k - 0.6) / 0.4);
      ctx.font = `800 15px ${palette.fontFamily}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.lineJoin = "round";
      ctx.lineWidth = 4;
      ctx.strokeStyle = palette.labelHalo;
      ctx.strokeText("결승 통과", width / 2, y);
      ctx.fillStyle = palette.finish;
      ctx.fillText("결승 통과", width / 2, y);
      ctx.restore();
    },
  };
}
