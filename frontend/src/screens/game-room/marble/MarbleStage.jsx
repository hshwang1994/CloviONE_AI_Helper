import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";
import { Callout, Segmented } from "../../../ui/kit.jsx";
import { UserAvatar } from "../../../ui/UserAvatar.jsx";
import { avatarImages } from "../../../ui/avatarImage.js";
import { FONT_SIZE, FONT_WEIGHT, NUMERIC, RADIUS } from "../../../ui/theme.js";
import { BoardFrame, useBoardSize } from "../BoardFrame.jsx";
import { personOf } from "../people.js";
import { boardPalette, marbleColor } from "./render/theme.js";
import { cameraTarget, createCamera, focusMarbleIndex, leaderIndex } from "./render/camera.js";
import { drawFrame, MAX_DPR } from "./render/renderer.js";
import { minimapHit, minimapLayout } from "./render/minimap.js";
import { createEffects } from "./render/effects.js";
import { createSpriteCache } from "./render/marbleSprites.js";
import { spawnPosition } from "./engine/layout.js";

/* 구슬 레이스 판 (D-564 · D-578) — 캔버스 하나가 판 틀(`BoardFrame`)을 꽉 채운다. 방장도 참가자도 같은 판 · 같은 경주를 본다.
 *
 * - 대기 중: 참가자 구슬(얼굴)이 출발 격자에 놓인 장면. 설정은 툴바의 [설정](방장)이다.
 * - 진행 중: 서버가 준 seed · started_at · speed 로 이 브라우저가 경주를 계산한다(`useMarbleRoom` → `useMarbleRace`). 카메라는 원본의
 *   규칙으로 따라가고(선두 → 당첨 경계 구슬, 결승 근처 확대), 왼쪽 위 미니맵을 누르거나 끌면 그 자리를 보는 「자유 보기」, 오른쪽 아래
 *   전환으로 「따라가기 | 전체 보기」. 오른쪽 위에 선두 셋(얼굴 · 이름), 결승 근처에서 엔진의 슬로 모션이 걸리면 위 가운데 「슬로 모션」.
 * - 확인 창 · 확정 실패 · 중단 · 오류는 판 위에 뜨는 알림이다(판의 자리를 밀지 않는다).
 * - 종료: 서버가 확정한 결과는 결과 대화 상자(`ResultDialog`)가 발표하고, 판은 결승선 아래 마지막 장면(당첨 구슬 고리)으로 남는다.
 * 전체 화면은 방 루트의 일이다(`useFullscreen`) — 여기서는 판 틀의 크기가 바뀌면 캔버스만 다시 잰다. 워커 · 경주는 그대로다. */

const VIEW_OPTIONS = [{ value: "follow", label: "따라가기" }, { value: "full", label: "전체 보기" }];
const raf = typeof requestAnimationFrame === "function" ? (fn) => requestAnimationFrame(fn) : (fn) => setTimeout(() => fn(Date.now()), 16);
const caf = typeof cancelAnimationFrame === "function" ? (h) => cancelAnimationFrame(h) : (h) => clearTimeout(h);
const now = () => (typeof performance !== "undefined" && performance.now ? performance.now() : Date.now());

/* 선두 셋 — 진행 중엔 실시간 순위, 끝나면 확정 순위의 앞 셋(꼴찌 당첨이면 당첨 구슬). 경주 훅의 tick(≈5Hz)에 맞춰 다시 그린다. */
function LeadChips({ c, palette, boxRef }) {
  const m = c.marble;
  if (m.waiting) return null;
  let order = [];
  if (m.announceable) order = (m.serverResult.winners || []).map((k) => m.byKey.get(k)).filter(Boolean);
  else {
    const snap = m.race.snapshotRef.current;
    if (snap && snap.ranking) order = Array.from(snap.ranking).slice(0, 3).map((i) => m.participants[i]).filter(Boolean);
  }
  order = order.slice(0, 3);
  if (!order.length) return null;
  return (
    <Box component="ol" ref={boxRef} aria-label={m.announceable ? "당첨" : "선두"} data-lead-chips="" sx={(t) => ({
      position: "absolute", top: 10, right: 10, zIndex: 2, listStyle: "none", m: 0, p: 0.75, display: "grid", gap: 0.5,
      maxWidth: "min(15rem, 45%)", borderRadius: `${RADIUS.md}px`, pointerEvents: "none",
      bgcolor: alpha(t.palette.background.paper, t.palette.mode === "dark" ? 0.82 : 0.9),
      boxShadow: `0 0 0 1px ${t.palette.divider}`, backdropFilter: "blur(2px)",
    })}>
      {order.map((p, i) => {
        const person = p.user_id ? personOf(c.people, p.user_id) : null;
        return (
          <Box component="li" key={p.key} sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0 }}>
            <Box component="span" sx={{ width: "1.1rem", flexShrink: 0, textAlign: "center", fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold, color: i === 0 ? "primary.main" : "text.secondary", ...NUMERIC }}>{i + 1}</Box>
            {person ? <UserAvatar person={person} name={p.name} size="xs" /> : (
              <Box component="span" aria-hidden="true" sx={{ width: "1.375rem", height: "1.375rem", borderRadius: "50%", flexShrink: 0, bgcolor: marbleColor(p.hue, palette) }} />
            )}
            <Box component="span" title={p.name} sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: FONT_SIZE.bodySm, fontWeight: i === 0 ? FONT_WEIGHT.bold : FONT_WEIGHT.semibold }}>{p.name}</Box>
          </Box>
        );
      })}
    </Box>
  );
}

export function MarbleStage({ c }) {
  const theme = useTheme();
  const size = useBoardSize();
  const palette = useMemo(() => boardPalette(theme), [theme]);
  const m = c.marble;
  const { race, participants, waiting, stage, bounds, winnersN, pickLast, winnerSet, phase, integrity } = m;

  const [viewMode, setViewMode] = useState("follow");
  const [freeTarget, setFreeTarget] = useState(null);
  const [dragging, setDragging] = useState(false);
  const canvasRef = useRef(null);
  const cameraRef = useRef(createCamera());
  const effectsRef = useRef(createEffects());
  const sizeRef = useRef({ w: 0, h: 0, dpr: 1 });
  const lastDrawRef = useRef(0);
  const anchorRef = useRef({ index: -1, y: 0, step: -1, vy: 0 });
  const rafRef = useRef(0);
  const camCtlRef = useRef(null);
  const chipsRef = useRef(null);
  const slowRef = useRef(null);

  /* 스프라이트 — 참가자 얼굴(사람) · 색 원 + 머리글자(자유 이름). 참가자 · 신원이 바뀌면 새로 만든다. */
  const sprites = useMemo(() => createSpriteCache({
    total: participants.length,
    imageOf: (p) => avatarImages.get(personOf(c.people, p.user_id) || { user_id: p.user_id, name: p.name }),
  }), [participants, c.people]);

  const frameRef = useRef(null);
  frameRef.current = { palette, stage, bounds, participants, winnerSet, waiting, winnersN, pickLast, viewMode, freeTarget, dragging, sprites };

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return false;
    const ctx = canvas.getContext && canvas.getContext("2d");
    if (!ctx) return false;
    const { w, h, dpr } = sizeRef.current;
    if (!w || !h) return false;
    const f = frameRef.current;
    const t = now();
    const dt = lastDrawRef.current ? t - lastDrawRef.current : 16;
    lastDrawRef.current = t;
    const snap = f.waiting ? null : race.snapshotRef.current;
    const focus = focusMarbleIndex(snap, f.winnersN, f.pickLast);
    const leader = leaderIndex(snap);
    /* 따라가는 구슬의 세로 속도(단위/물리초) — 앞 스냅샷과의 차. 카메라가 떨어지는 방향을 조금 앞서 본다. */
    const anchor = snap && snap.finishedCount > 0 ? focus : leader;
    let vy = 0;
    if (snap && anchor >= 0) {
      const a = anchorRef.current;
      const y = snap.positions[anchor * 3 + 1];
      if (a.index === anchor && snap.step > a.step) vy = (y - a.y) / ((snap.step - a.step) * 0.01);
      else if (a.index === anchor) vy = a.vy;
      anchorRef.current = { index: anchor, y, step: snap.step, vy };
    }
    const total = f.participants.length;
    const cols = Math.min(total, 10);
    const rows = Math.ceil(total / 10);
    const first = total ? spawnPosition(0, total) : null;
    const lastCol = total ? spawnPosition(cols - 1, total) : null;
    const lastRow = total ? spawnPosition((rows - 1) * 10, total) : null;
    const spawnCenter = total ? {
      x: (first.x + lastCol.x) / 2, y: (first.y + lastRow.y) / 2,
      w: Math.abs(lastCol.x - first.x), h: Math.abs(first.y - lastRow.y),
    } : null;
    const mini = minimapLayout(f.stage, w, h);
    const target = cameraTarget({
      stage: f.stage, snapshot: snap, width: w, height: h, focusIndex: focus, leader, waiting: f.waiting,
      mode: f.viewMode, freeTarget: f.freeTarget, velocityY: vy, spawnCenter,
      insetLeft: mini ? mini.x + mini.w + 10 : 0,
    });
    const cam = cameraRef.current;
    cam.follow(target, dt);
    if (snap) effectsRef.current.observe(snap, f.participants, f.palette, t, leader);
    const camState = cam.state();
    /* 판 위의 DOM 컨트롤이 덮는 자리 — 오른쪽 아래 카메라 고르기 · 오른쪽 위 선두 칩 · 왼쪽 위 슬로 모션 표지. 결승 글자는 비켜
       그리고, 그 밑의 구슬 이름은 놓지 않는다(가려져 반쯤 보이던 이름). */
    const reserve = [];
    const ctl = camCtlRef.current;
    if (ctl && ctl.offsetWidth) reserve.push({ l: w - 10 - ctl.offsetWidth, t: h - 10 - ctl.offsetHeight, r: w - 10, b: h - 10 });
    const chips = chipsRef.current;
    if (chips && chips.offsetWidth) reserve.push({ l: w - 10 - chips.offsetWidth, t: 10, r: w - 10, b: 10 + chips.offsetHeight });
    const pill = slowRef.current;
    if (pill && pill.offsetWidth) reserve.push({ l: pill.offsetLeft, t: pill.offsetTop, r: pill.offsetLeft + pill.offsetWidth, b: pill.offsetTop + pill.offsetHeight });
    drawFrame(ctx, {
      width: w, height: h, dpr, palette: f.palette, stage: f.stage, bounds: f.bounds, snapshot: snap, participants: f.participants,
      camera: camState, winnerSet: f.winnerSet, focusIndex: focus, waiting: f.waiting, sprites: f.sprites,
      effects: effectsRef.current, now: t, minimap: { layout: mini, active: f.viewMode === "free" || f.dragging }, reserve,
    });
    /* 카메라가 아직 목표로 가는 중이거나 효과가 살아 있으면 다음 프레임도 그린다(스냅샷이 오지 않는 대기 · 종료 장면에서도). */
    const moving = Math.abs(camState.x - target.x) > 0.01 || Math.abs(camState.y - target.y) > 0.01 || Math.abs(camState.zoom - target.zoom) > 0.05;
    return moving || effectsRef.current.alive(t);
  }, [race.snapshotRef]);

  const schedule = useCallback(() => {
    if (rafRef.current) return;
    rafRef.current = raf(() => {
      rafRef.current = 0;
      if (draw()) schedule();
    });
  }, [draw]);

  /* 캔버스 크기 — 판 틀이 잰 값(ResizeObserver 하나)을 그대로 받는다. DPR ≤ 2. */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !size.width || !size.height) return;
    const dpr = Math.min(MAX_DPR, (typeof window !== "undefined" && window.devicePixelRatio) || 1);
    sizeRef.current = { w: size.width, h: size.height, dpr };
    canvas.width = Math.round(size.width * dpr);
    canvas.height = Math.round(size.height * dpr);
    canvas.style.width = `${size.width}px`;
    canvas.style.height = `${size.height}px`;
    if (draw()) schedule();
  }, [size.width, size.height, draw, schedule]);
  useEffect(() => race.subscribe(() => { if (draw()) schedule(); }), [race.subscribe, draw, schedule]);
  useEffect(() => avatarImages.subscribe(() => schedule()), [schedule]);
  useEffect(() => { cameraRef.current.reset(); effectsRef.current.reset(); anchorRef.current = { index: -1, y: 0, step: -1, vy: 0 }; schedule(); }, [c.gstate.race_id, schedule]);
  useEffect(() => { schedule(); }, [schedule, palette, waiting, participants, winnerSet, race.status, viewMode, freeTarget, dragging, sprites]);
  useEffect(() => () => { if (rafRef.current) caf(rafRef.current); }, []);

  /* 미니맵 — 누르거나 끌면 그 자리를 보는 자유 보기. */
  const pointToWorld = (e, slop) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const r = canvas.getBoundingClientRect();
    const layout = minimapLayout(stage, sizeRef.current.w, sizeRef.current.h);
    return minimapHit(layout, e.clientX - r.left, e.clientY - r.top, slop);
  };
  const onPointerDown = (e) => {
    const hit = pointToWorld(e, 0);
    if (!hit) return;
    e.preventDefault();
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* 오래된 브라우저 */ }
    setDragging(true);
    setViewMode("free");
    setFreeTarget(hit);
  };
  const onPointerMove = (e) => {
    if (!dragging) return;
    const hit = pointToWorld(e, 400);
    if (hit) setFreeTarget(hit);
  };
  const onPointerUp = () => setDragging(false);

  const snap = waiting ? null : race.snapshotRef.current;
  const slow = !!(snap && !snap.finished && snap.timeScale != null && snap.timeScale < 1);
  const disputed = phase === "finished" && integrity.status === "disputed";
  let notice = null;
  if (race.status === "error") {
    notice = <Callout tone="danger" compact detail={race.error ? String(race.error.message || race.error) : undefined}>경주를 그리지 못했습니다. 새로고침하면 같은 경주를 다시 계산합니다.</Callout>;
  } else if (disputed) {
    notice = <Callout tone="warn" compact>브라우저 간 결과가 달라 확정하지 못했습니다. 이 경주의 당첨자는 없습니다. 방장이 다시 시작할 수 있습니다.</Callout>;
  } else if (phase === "abandoned") {
    notice = <Callout tone="warn" compact>결과가 올라오지 않아 경주를 중단했습니다. 방장이 다시 시작할 수 있습니다.</Callout>;
  } else if (m.verifying) {
    notice = <Callout tone="info" compact>결과를 확인하는 중입니다. 다른 참가자의 화면과 대조하고 있습니다.</Callout>;
  }
  const miniLayout = size.width && size.height ? minimapLayout(stage, size.width, size.height) : null;
  const segValue = viewMode === "free" ? "free" : viewMode;
  const segOptions = viewMode === "free" ? [...VIEW_OPTIONS, { value: "free", label: "자유 보기" }] : VIEW_OPTIONS;

  return (
    <Box data-marble-stage={phase} sx={{ position: "absolute", inset: 0, bgcolor: palette.board }}>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={waiting ? "출발 자리에 놓인 구슬" : "경주 중인 구슬"}
        data-marble-canvas=""
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        style={{ display: "block", width: "100%", height: "100%", touchAction: dragging ? "none" : "auto" }}
      />
      {race.status === "loading" ? (
        <BoardFrame.Notice><Typography variant="body2" color="text.secondary">경주를 준비하는 중입니다.</Typography></BoardFrame.Notice>
      ) : notice ? <BoardFrame.Notice>{notice}</BoardFrame.Notice> : null}
      {/* 슬로 모션 표지 — 미니맵 오른쪽 위. 가운데에 두면 좁은 판(390)에서 오른쪽 위 선두 칩과 겹쳤다. */}
      {slow && !notice ? (
        <Box component="span" ref={slowRef} data-slowmo="" sx={(t) => ({
          position: "absolute", top: 10, left: (miniLayout ? miniLayout.w + 22 : 12), zIndex: 2,
          display: "inline-flex", alignItems: "center", gap: 0.5, px: 1.25, height: "1.625rem", borderRadius: `${RADIUS.full}px`,
          bgcolor: alpha(t.palette.background.paper, 0.9), color: "primary.main", fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold,
          boxShadow: `0 0 0 1px ${alpha(t.palette.primary.main, 0.35)}`, pointerEvents: "none",
        })}>
          슬로 모션
        </Box>
      ) : null}
      {/* 판 위 알림(확인 중 · 확정 실패 · 중단 · 오류)이 서면 선두 칩을 걷는다 — 둘이 위쪽에서 겹치지 않게 알림이 이긴다. */}
      {!notice ? <LeadChips c={c} palette={palette} boxRef={chipsRef} /> : null}
      <Box ref={camCtlRef} sx={{ position: "absolute", right: 10, bottom: 10, zIndex: 2 }}>
        <Segmented ariaLabel="카메라" value={segValue} onChange={(v) => { if (v !== "free") { setViewMode(v); setFreeTarget(null); } }} options={segOptions}
          sx={{ boxShadow: (t) => `inset 0 0 0 1px ${t.palette.divider}, 0 1px 3px ${alpha(t.palette.common.black, 0.12)}` }} />
      </Box>
    </Box>
  );
}
