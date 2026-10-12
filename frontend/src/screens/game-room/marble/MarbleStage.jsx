import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { alpha, useTheme } from "@mui/material/styles";
import { Badge, Button, Callout, FlatBadgeSurface, Modal, useToast } from "../../../ui/kit.jsx";
import { UserAvatar } from "../../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../../../ui/theme.js";
import { ResultPanel } from "../ResultPanel.jsx";
import { useMarbleRace } from "./useMarbleRace.js";
import { boardPalette, marbleColor, participantHue } from "./render/theme.js";
import { cameraTarget, createCamera, focusMarbleIndex, stageBounds } from "./render/camera.js";
import { drawFrame, MAX_DPR } from "./render/renderer.js";
import { STAGES } from "./engine/stages/wheel.js";
import { FLAG_FINISHED } from "./engine/core.js";
import { MarbleSettingsModal } from "./MarbleSettingsModal.jsx";

/* 구슬 레이스 무대 (D-564) — 머리 줄 + 판(캔버스) + 순위 레일. 방장도 참가자도 같은 판 · 같은 경주를 본다.
 *
 * - 대기 중: 참가자 구슬이 출발 격자에 놓인 장면. 방장은 [설정]으로 참가자 · 당첨 인원 · 꼴찌 · 배속을 정한다.
 * - 진행 중: 서버가 준 seed · started_at · speed 로 이 브라우저가 경주를 계산한다(`useMarbleRace`). 늦게 들어와도 같은 논리
 *   시간까지 빨리 감는다. 끝나면 결과를 올린다(방장 finish · 나머지 attest) — 경주당 한 번.
 * - 확인 창: 서버가 제출을 대조하는 동안 「결과를 확인하는 중」이고 발표 · 축포가 없다. 순위 레일은 잠정 표시다.
 * - 종료: 서버가 확정한 결과(`announceable`)만 `ResultPanel` 로 발표한다. `disputed` 는 발표하지 않는다.
 * - 전체 화면: 판 컨테이너를 Fullscreen API 로 올린다. 워커 · 상태는 그대로이고 캔버스 크기만 다시 잰다. */

export const PHASE_LABELS = { idle: "대기 중", running: "진행 중", verifying: "결과 확인 중", finished: "종료", abandoned: "중단" };
export const INTEGRITY_NOTES = {
  confirmed: (n) => `참가자 ${n}명의 화면과 일치한 결과입니다.`,
  host_only: () => "방장 화면의 결과입니다. 대조할 참가자 화면이 없었습니다.",
  host_absent: () => "방장 없이 참가자 다수의 화면이 낸 결과입니다.",
};
export const ATTRIBUTION_TEXT = "구슬 레이스는 lazygyu 의 Marble Roulette(MIT 라이선스)의 물리 규칙, 경주 판, 순위 계산을 바탕으로 했습니다.";
export const ATTRIBUTION_URL = "https://github.com/lazygyu/roulette";

function stepsToSeconds(steps) {
  return `${(Number(steps) * 0.01).toFixed(1)}초`;
}

/* 순위 레일 — 진행 중엔 실시간 순위(완주한 구슬 먼저), 종료 뒤엔 확정 순위. */
function RankRail({ participants, snapshot, finalRanking, memberById, winnerKeys, provisional, palette, you, fullscreen }) {
  let order;
  if (finalRanking) {
    const byKey = new Map(participants.map((p) => [p.key, p]));
    order = finalRanking.map((k) => byKey.get(k)).filter(Boolean);
  } else if (snapshot && snapshot.ranking && snapshot.ranking.length) {
    order = Array.from(snapshot.ranking).map((i) => participants[i]).filter(Boolean);
  } else {
    order = participants;
  }
  const finishedOf = (p) => (finalRanking ? true : !!(snapshot && snapshot.flags && (snapshot.flags[p.index] & FLAG_FINISHED)));
  return (
    <Paper variant="outlined" component="section" aria-label="순위" data-marble-rail sx={{
      display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, p: 1.5,
      ...(fullscreen ? { bgcolor: (t) => alpha(t.palette.background.paper, 0.9) } : null),
    }}>
      <Stack direction="row" gap={1} alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold }}>순위</Typography>
        {provisional ? <Badge value="잠정" kind="warn" /> : null}
      </Stack>
      <FlatBadgeSurface>
        <Box component="ol" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5, overflowY: "auto", minHeight: 0, maxHeight: fullscreen ? "none" : "22rem" }}>
          {order.map((p, i) => {
            const member = p.user_id ? memberById[p.user_id] : null;
            const isMe = you && p.user_id === you.user_id;
            const won = winnerKeys && winnerKeys.has(p.key);
            return (
              <Box component="li" key={p.key} sx={{
                display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, borderRadius: RADIUS.sm, minWidth: 0,
                bgcolor: (t) => (won ? alpha(t.palette.primary.main, 0.12) : isMe ? alpha(t.palette.primary.main, 0.06) : "transparent"),
              }}>
                <Box component="span" sx={{ width: "1.5rem", flexShrink: 0, color: "text.secondary", fontVariantNumeric: "tabular-nums", fontSize: FONT_SIZE.bodySm }}>{i + 1}</Box>
                <Box component="span" aria-hidden="true" sx={{ width: 12, height: 12, borderRadius: "50%", flexShrink: 0, bgcolor: marbleColor(p.hue, palette), boxShadow: (t) => `inset 0 0 0 1px ${alpha(t.palette.common.black, 0.25)}` }} />
                {member ? <UserAvatar person={member} name={p.name} size="sm" /> : null}
                <Box component="span" title={p.name} sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: won ? FONT_WEIGHT.bold : FONT_WEIGHT.regular }}>{p.name}</Box>
                {won ? <Badge value="당첨" kind="info" /> : finishedOf(p) ? <Badge value="완주" kind="ok" /> : null}
              </Box>
            );
          })}
        </Box>
      </FlatBadgeSurface>
    </Paper>
  );
}

export function MarbleStage({ c }) {
  const { room, gstate, you, members, isHost, serverNow, mutations, revealPlan, celebrateOnReveal } = c;
  const theme = useTheme();
  const toast = useToast();
  const narrow = useMediaQuery(theme.breakpoints.down("sm"));
  /* 순위 레일은 넓은 화면(xl)에서만 판 옆이다 — 그 아래에서는 판이 폭을 다 쓰고 결과 판 → 레일 순으로 아래에 선다. */
  const sideRail = useMediaQuery(theme.breakpoints.up("xl"));
  const palette = useMemo(() => boardPalette(theme), [theme]);
  const phase = gstate.phase || "idle";
  const waiting = room.status === "waiting" || phase === "idle";
  const config = gstate.config || {};
  const memberById = useMemo(() => Object.fromEntries((members || []).map((m) => [m.user_id, m])), [members]);

  /* 참가자 — 진행 중 · 종료는 경주에 박힌 목록, 대기 중은 설정의 목록(없으면 지금 있는 구성원). */
  const participants = useMemo(() => {
    let list;
    if (!waiting && Array.isArray(gstate.participants) && gstate.participants.length) list = gstate.participants;
    else if (Array.isArray(config.participants) && config.participants.length) list = config.participants;
    else list = (members || []).filter((m) => m.role !== "spectator" && m.present !== false).map((m) => ({ key: `u:${m.user_id}`, name: m.name, user_id: m.user_id }));
    return list.map((p, i) => ({ ...p, index: i, hue: participantHue(i, list.length) }));
  }, [waiting, gstate.participants, config.participants, members]);
  const byKey = useMemo(() => new Map(participants.map((p) => [p.key, p])), [participants]);
  const winnersN = waiting ? (config.winners || 1) : (gstate.winners_n || 1);
  const pickLast = waiting ? !!config.pick_last : !!gstate.pick_last;
  const speed = waiting ? (config.speed || 1) : (gstate.speed || 1);
  const stage = STAGES[(waiting ? config.map : gstate.map) || "wheel"] || STAGES.wheel;
  const bounds = stageBounds(stage);

  /* 결과 제출 — 경주당 한 번(훅이 보장), 방 안의 사람만, 아직 안 올렸을 때만, 확정 전일 때만. */
  const latest = useRef({ gstate, you, isHost, mutations });
  latest.current = { gstate, you, isHost, mutations };
  const onFinished = useCallback((result) => {
    const { gstate: g, you: y, isHost: host, mutations: m } = latest.current;
    if (!y || !y.in_room || g.you_submitted || g.finalized_at) return;
    const body = { race_id: g.race_id, ranking: result.ranking, finish_steps: result.finish_steps, digest: result.digest };
    (host ? m.marbleFinish : m.marbleAttest).mutate(body);
  }, []);

  const race = useMarbleRace({
    raceId: gstate.race_id, seed: gstate.seed, startedAt: gstate.started_at, speed: gstate.speed,
    participants: gstate.participants, winners: gstate.winners_n, pickLast: !!gstate.pick_last, stageKey: gstate.map,
    serverNow, active: !waiting && phase !== "abandoned" && Array.isArray(gstate.participants) && gstate.participants.length >= 2,
    onFinished,
  });

  const serverResult = phase === "finished" && gstate.result ? gstate.result : null;
  const announceable = !!(gstate.announceable && serverResult);
  const integrity = gstate.integrity || {};
  const winnerKeys = useMemo(() => new Set(announceable ? serverResult.winners || [] : []), [announceable, serverResult]);
  const winnerSet = useMemo(() => new Set(Array.from(winnerKeys).map((k) => byKey.get(k)).filter(Boolean).map((p) => p.index)), [winnerKeys, byKey]);
  const verifying = !waiting && phase !== "finished" && phase !== "abandoned" && (phase === "verifying" || race.status === "finished");

  /* 캔버스 — 크기는 ResizeObserver 로, DPR ≤ 2. 그리기는 스냅샷마다(구독) + 팔레트 · 크기 · 상태가 바뀔 때. */
  const canvasRef = useRef(null);
  const boxRef = useRef(null);
  const rootRef = useRef(null);
  const sizeRef = useRef({ w: 0, h: 0, dpr: 1 });
  const cameraRef = useRef(createCamera());
  const frameRef = useRef(null);
  frameRef.current = { palette, stage, bounds, participants, winnerSet, waiting, winnersN, pickLast };
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext && canvas.getContext("2d");
    if (!ctx) return;
    const { w, h, dpr } = sizeRef.current;
    if (!w || !h) return;
    const f = frameRef.current;
    const snap = f.waiting ? null : race.snapshotRef.current;
    const focus = focusMarbleIndex(snap, f.winnersN, f.pickLast);
    cameraRef.current.follow(cameraTarget({ stage: f.stage, snapshot: snap, width: w, height: h, focusIndex: focus, waiting: f.waiting }));
    drawFrame(ctx, {
      width: w, height: h, dpr, palette: f.palette, stage: f.stage, bounds: f.bounds, snapshot: snap, participants: f.participants,
      camera: cameraRef.current.state(), winnerSet: f.winnerSet, focusIndex: focus, waiting: f.waiting,
    });
  }, [race.snapshotRef]);

  useEffect(() => {
    const box = boxRef.current;
    const canvas = canvasRef.current;
    if (!box || !canvas) return undefined;
    const measure = () => {
      const r = box.getBoundingClientRect();
      const w = Math.max(0, Math.round(r.width));
      const h = Math.max(0, Math.round(r.height));
      const dpr = Math.min(MAX_DPR, (typeof window !== "undefined" && window.devicePixelRatio) || 1);
      if (!w || !h) return;
      sizeRef.current = { w, h, dpr };
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      draw();
    };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(box);
    return () => ro.disconnect();
  }, [draw]);
  useEffect(() => race.subscribe(draw), [race.subscribe, draw]);
  useEffect(() => { cameraRef.current.reset(); }, [gstate.race_id]);
  useEffect(() => { draw(); }, [draw, palette, waiting, participants, winnerSet, race.status]);

  /* 전체 화면 — 판 컨테이너만 올린다. 워커 · 상태는 그대로다. */
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const onChange = () => setFullscreen(!!document.fullscreenElement && document.fullscreenElement === rootRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (rootRef.current && rootRef.current.requestFullscreen) await rootRef.current.requestFullscreen();
      else throw new Error("unsupported");
    } catch (e) {
      toast && toast("브라우저가 전체 화면을 막았습니다.", "error");
    }
  };

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);

  /* 결과 판 — 서버가 확정한 결과만. */
  const winners = announceable
    ? (serverResult.winners || []).map((key) => {
      const p = byKey.get(key);
      return { id: key, name: p ? p.name : key, user_id: p ? p.user_id : null, person: p && p.user_id ? memberById[p.user_id] : null, color: p ? marbleColor(p.hue, palette) : undefined };
    })
    : [];
  const fullRanking = announceable ? serverResult.ranking || [] : null;
  const finishSteps = announceable ? serverResult.finish_steps || [] : [];
  const detail = announceable ? (
    <Box component="ol" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
      {fullRanking.map((key, i) => {
        const p = byKey.get(key);
        const won = winnerKeys.has(key);
        return (
          <Box component="li" key={key} sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, borderRadius: RADIUS.sm, bgcolor: (t) => (won ? alpha(t.palette.primary.main, 0.1) : "transparent") }}>
            <Box component="span" sx={{ width: "1.75rem", flexShrink: 0, color: "text.secondary", fontVariantNumeric: "tabular-nums", fontSize: FONT_SIZE.bodySm }}>{i + 1}</Box>
            <Box component="span" aria-hidden="true" sx={{ width: 12, height: 12, borderRadius: "50%", flexShrink: 0, bgcolor: p ? marbleColor(p.hue, palette) : "divider" }} />
            <Box component="span" sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: won ? FONT_WEIGHT.bold : FONT_WEIGHT.regular }}>{p ? p.name : key}</Box>
            <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>{stepsToSeconds(finishSteps[i])}</Typography>
          </Box>
        );
      })}
    </Box>
  ) : null;
  const copyText = announceable
    ? ["구슬 레이스 결과", `당첨: ${winners.map((w) => w.name).join(", ")}`, ...fullRanking.map((key, i) => `${i + 1}. ${byKey.get(key) ? byKey.get(key).name : key} (${stepsToSeconds(finishSteps[i])})`)].join("\n")
    : null;
  const noteOf = INTEGRITY_NOTES[integrity.status];
  const resultPanel = announceable ? (
    <ResultPanel
      game="구슬 레이스"
      headline={winners.length > 1 ? "당첨자를 발표합니다" : "당첨자를 발표합니다"}
      lead={pickLast ? `꼴찌로 들어온 ${winners.length}명이 당첨입니다.` : `먼저 결승선에 닿은 ${winners.length}명이 당첨입니다.`}
      note={noteOf ? noteOf(integrity.agree || 0) : undefined}
      winners={winners} ranked={winners.length > 1} winnerLabel="당첨" mood="win"
      revealKey={revealPlan ? revealPlan.key : null} instant={revealPlan ? revealPlan.instant : true} onReveal={celebrateOnReveal}
      detail={detail} detailLabel="전체 순위" copyText={copyText}
      overlay={fullscreen} fullscreen={fullscreen}
    />
  ) : null;

  const statusText = `${participants.length}명 참가, 당첨 ${winnersN}명${pickLast ? " (꼴찌)" : ""}, ${speed}배속`;
  const finishedCount = race.snapshotRef.current ? race.snapshotRef.current.finishedCount : 0;
  const canvasAspect = narrow ? "4 / 3" : "16 / 9";

  return (
    <Box data-marble-stage={phase} sx={{ display: "grid", gap: 1.5, minWidth: 0 }}>
      <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
        <Badge value={PHASE_LABELS[phase] || phase} kind={phase === "running" ? "warn" : phase === "finished" ? "ok" : "info"} />
        <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>{statusText}</Typography>
        {!waiting && phase !== "finished" ? (
          <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>완주 {finishedCount}/{participants.length}</Typography>
        ) : null}
        <Stack direction="row" gap={1} sx={{ ml: "auto" }}>
          {isHost && waiting ? <Button size="sm" onClick={() => setSettingsOpen(true)}>설정</Button> : null}
          <Button size="sm" onClick={() => setInfoOpen(true)}>정보</Button>
          <Button size="sm" onClick={toggleFullscreen} aria-pressed={fullscreen}>{fullscreen ? "전체 화면 해제" : "전체 화면"}</Button>
        </Stack>
      </Stack>

      {race.status === "error" ? (
        <Callout tone="danger" compact detail={race.error ? String(race.error.message || race.error) : undefined}>
          경주를 그리지 못했습니다. 새로고침하면 같은 경주를 다시 계산합니다.
        </Callout>
      ) : null}
      {verifying ? (
        <Callout tone="info" compact>결과를 확인하는 중입니다. 다른 참가자의 화면과 대조하고 있습니다.</Callout>
      ) : null}
      {phase === "finished" && integrity.status === "disputed" ? (
        <Callout tone="warn" compact>브라우저 간 결과가 달라 확정하지 못했습니다. 이 경주의 당첨자는 없습니다. 방장이 다시 시작할 수 있습니다.</Callout>
      ) : null}
      {phase === "abandoned" ? (
        <Callout tone="warn" compact>결과가 올라오지 않아 경주를 중단했습니다. 방장이 다시 시작할 수 있습니다.</Callout>
      ) : null}

      <Box ref={rootRef} data-marble-fullscreen={fullscreen ? "on" : "off"} sx={{
        display: "grid", gap: 1.5, minWidth: 0,
        gridTemplateColumns: { xs: "1fr", xl: "minmax(0,1fr) 14rem" },
        ...(fullscreen ? { bgcolor: "background.default", p: 2, height: "100%", gridTemplateColumns: "minmax(0,1fr) 16rem", gridTemplateRows: "minmax(0,1fr)" } : null),
      }}>
        <Box ref={boxRef} sx={{
          /* 🔴 `aspect-ratio` 가 있는 격자 항목은 `justify-self` 기본값이 start 라 min-height 에서 폭을 끌어내 옆 칸을 덮는다 — 칸을 채우게 못박는다. */
          position: "relative", minWidth: 0, width: "100%", justifySelf: "stretch", alignSelf: "stretch",
          borderRadius: RADIUS.md, overflow: "hidden",
          border: 1, borderColor: "divider", bgcolor: palette.board,
          ...(fullscreen ? { height: "100%" } : { aspectRatio: canvasAspect, minHeight: narrow ? "18rem" : "26rem" }),
        }}>
          <canvas ref={canvasRef} role="img" aria-label={waiting ? "출발 자리에 놓인 구슬" : "경주 중인 구슬"} style={{ display: "block", width: "100%", height: "100%" }} />
          {race.status === "loading" ? (
            <Typography variant="body2" sx={{ position: "absolute", top: 8, left: 12, color: "text.secondary" }}>경주를 준비하는 중입니다.</Typography>
          ) : null}
          {fullscreen ? resultPanel : null}
        </Box>
        {!sideRail && !fullscreen ? resultPanel : null}
        <RankRail
          participants={participants} snapshot={waiting ? null : race.snapshotRef.current} finalRanking={fullRanking}
          memberById={memberById} winnerKeys={winnerKeys} provisional={verifying} palette={palette} you={you} fullscreen={fullscreen}
        />
      </Box>
      {sideRail && !fullscreen ? resultPanel : null}

      {isHost ? (
        <MarbleSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} config={config} members={members} mutations={mutations} />
      ) : null}
      <Modal open={infoOpen} onClose={() => setInfoOpen(false)} title="구슬 레이스 정보" size="sm">
        <Box sx={{ display: "grid", gap: 1.5 }}>
          <Typography sx={KO_WORD_BREAK}>{ATTRIBUTION_TEXT}</Typography>
          <Typography sx={KO_WORD_BREAK}>
            원본 저장소: <a href={ATTRIBUTION_URL} target="_blank" rel="noreferrer noopener">{ATTRIBUTION_URL}</a>
          </Typography>
          <Typography sx={KO_WORD_BREAK}>
            모든 브라우저가 같은 seed 로 같은 경주를 계산하고, 서버는 올라온 결과를 서로 대조해 확정합니다. 「확인됨」은 서로 다른 화면의 결과가 일치했다는 뜻이고, 계산이 조작되지 않았다는 증명은 아닙니다.
          </Typography>
        </Box>
      </Modal>
    </Box>
  );
}
