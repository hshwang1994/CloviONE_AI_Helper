import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { keyframes } from "@mui/system";
import confetti from "canvas-confetti";
import { api } from "../lib/api.js";
import { Badge, Button, Card, ErrorState, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { MascotPose } from "../ui/Mascot.jsx";
import { FAB_CLEARANCE } from "../ui/theme.js";
import { MISC } from "../lib/assets.js";
import { GAME_LABELS } from "./Games.jsx";

/* 게임방(§5·§6·§13·§16.2). 폴링(1.2초)으로 방 상태·참여자·이벤트를 실시간처럼 흐르게 한다.
 * 결과(당첨자)는 서버가 확정해 내려준다(§13.1) — 클라이언트는 표현만 한다. 게임방 채팅은
 * 순수 내부 DB(n8n 안 거침, §13.2). 방에 들어오면 한 번 자동 입장(가득/진행 중이면 서버가 관전).
 *
 * 2026-08 MUI 재설계: screens.css의 .game-* 규칙 169줄을 화면 안 sx로 옮겼다. 이 화면은 업무
 * 위험이 가장 낮은 화면이라 연출을 조금 더 얹는다 — 승자 확정 순간에 축포 + 축하 일러스트 +
 * 마스코트(love/success)를 함께 띄운다. 다만 **동작 최소화(prefers-reduced-motion)** 를 켠
 * 사용자에게는 JS로 쏘는 축포를 아예 발사하지 않는다(CSS 애니메이션은 theme.js의 전역 규칙이 끈다). */

const STATUS_LABELS = { waiting: "대기 중", playing: "진행 중", finished: "결과 확인 중" };
const STATUS_KIND = { waiting: "info", playing: "warn", finished: "ok" };
const ROLE_LABELS = { host: "방장", player: "참여", spectator: "관전" };

const pop = keyframes`
  0% { transform: scale(.5); opacity: 0; }
  55% { transform: scale(1.14); }
  75% { transform: scale(.96); }
  100% { transform: scale(1); opacity: 1; }
`;
const rise = keyframes`
  from { transform: translateY(12px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
`;
const draw = keyframes`to { stroke-dashoffset: 0; }`;
const pulse = keyframes`
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.12); }
`;

/* 사용자가 OS에서 '동작 최소화'를 켰는지. matchMedia가 없는 환경(jsdom 등)에서는 false로 본다 —
 * 없다고 예외를 던지면 결과 화면 전체가 렌더되지 않는다. */
export function prefersReducedMotion() {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    return !!(mq && mq.matches);
  } catch (e) {
    return false;
  }
}

// 승자 공개 축포. canvas-confetti는 캔버스를 CSSOM 개별 속성으로 스타일링하고 기본은 워커 미사용이라
// CSP(style-src 'self', worker 미허용)에 안전하다.
// 동작 최소화는 두 겹으로 막는다: (1) 여기서 아예 호출하지 않는다 — JS로 켜는 연출은 전역 CSS
// 규칙이 닿지 않으므로 우리가 직접 판단해야 한다. (2) 그래도 라이브러리 옵션을 남겨 둔다.
function celebrate() {
  if (prefersReducedMotion()) return;
  const base = { spread: 74, startVelocity: 45, ticks: 200, origin: { y: 0.55 }, disableForReducedMotion: true };
  confetti({ ...base, particleCount: 90 });
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 60, origin: { x: 0, y: 0.62 } }), 140);
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 120, origin: { x: 1, y: 0.62 } }), 260);
}

// 결과에 '승자'가 있으면 방별 고유 문자열(축포 트리거 키)을, 없으면 null. 값이 바뀔 때만 축포.
function deriveCelebrateKey(data) {
  if (!data || !data.room || data.room.status !== "finished") return null;
  const gt = data.room.game_type;
  const res = (data.state && data.state.result) || null;
  if (!res) return null;
  let sig = null;
  if (gt === "random_draw" && Array.isArray(res) && res.length) sig = "d:" + res.map((w) => w.user_id).join(",");
  else if (gt === "quick_vote" && (res.winners || []).length) sig = "v:" + res.winners.join(",");
  else if (gt === "number" && res.winner) sig = "n:" + res.winner.user_id;
  else if (gt === "rps" && res.mode === "tournament" && res.champion) sig = "t:" + res.champion.user_id;
  else if (gt === "rps" && res.outcome === "win") sig = "r:" + (res.winners || []).map((w) => w.user_id).join(",");
  else if (gt === "quiz" && (res.winners || []).length) sig = "q:" + res.winners.join(",");
  return sig ? data.room.id + sig : null;
}

// 백엔드는 UTC를 tz 표기 없는 isoformat으로 준다(예: "2026-07-29T05:30:00"). Z를 붙여 UTC로
// 파싱해야 브라우저가 로컬(KST)로 오해하지 않는다(lib/format.js와 같은 규칙). 이걸 빼먹으면
// 마감이 9시간 과거로 계산돼 카운트다운이 즉시 0이 되고 가위바위보가 바로 자동 처리되는 버그가 난다.
function toDate(iso) {
  if (!iso) return null;
  const s = String(iso);
  const norm = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(norm);
  return Number.isNaN(d.getTime()) ? null : d;
}

// 채팅 시각(HH:MM). created_at는 UTC — UTC로 파싱한 뒤 브라우저 로컬 시간으로 표시.
function fmtTime(iso) {
  const d = toDate(iso);
  if (!d) return "";
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

// 서버가 준 마감(UTC ISO)까지 남은 초. 없으면 null. 0.25초마다 다시 계산해 부드럽게 줄어든다.
function useCountdown(deadline) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!deadline) return undefined;
    const t = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [deadline]);
  if (!deadline) return null;
  const d = toDate(deadline);
  if (!d) return null;
  return Math.max(0, Math.ceil((d.getTime() - nowMs) / 1000));
}

// 카운트다운 배지. 남은 시간이 적으면 경고색. 무제한(deadline 없음)이면 아무것도 안 그린다.
function Countdown({ remaining }) {
  if (remaining == null) return null;
  const urgent = remaining <= 5;
  return (
    <Box
      aria-live="polite"
      sx={{
        display: "flex", alignItems: "baseline", gap: 0.5, px: 1.5, py: 0.25, borderRadius: 999,
        bgcolor: (t) => alpha(urgent ? t.palette.error.main : t.palette.primary.main, 0.14),
        color: urgent ? "error.main" : "primary.main",
        animation: urgent ? `${pulse} .8s ease-in-out infinite` : "none",
      }}
    >
      <Box component="span" sx={{ fontSize: "1.25rem", fontWeight: 800, fontVariantNumeric: "tabular-nums", minWidth: "1.5rem", textAlign: "center" }}>
        {remaining}
      </Box>
      <Box component="span" sx={{ fontSize: "0.75rem" }}>초</Box>
    </Box>
  );
}

/* 무대 안내문(아직 시작 전 / 관전 중 등). 점선 상자로 '여기가 결과가 나올 자리'임을 보인다. */
function StageHint({ children }) {
  return (
    <Box sx={{
      py: 4, px: 2, textAlign: "center", color: "text.secondary",
      border: 1, borderStyle: "dashed", borderColor: "divider", borderRadius: 3,
    }}>
      {children}
    </Box>
  );
}

/* 승자 이름표. 결과가 도착하는 순간 톡 튀어나오게(모션 축소는 theme.js 전역 규칙이 끈다). */
function WinnerName({ children }) {
  return (
    <Box component="span" sx={{
      px: 2, py: 0.75, borderRadius: 999, bgcolor: "primary.main", color: "primary.contrastText",
      fontSize: "1.0625rem", fontWeight: 750, animation: `${pop} .5s cubic-bezier(.34,1.56,.64,1) both`,
    }}>
      {children}
    </Box>
  );
}

/* 결과 무대 — 축하 일러스트 + 마스코트 + 결과 본문.
 * 자산(misc/celebrate-winner.png)과 마스코트 love 포즈는 처음부터 있었는데 어디에도 연결돼
 * 있지 않았다. 승자가 확정된 순간에만 띄운다(무승부·팀 나누기처럼 승자가 없는 결과는 mood="calm"). */
function ResultStage({ mood = "win", label, children }) {
  const celebrating = mood === "win";
  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 3, md: 4 },
        borderColor: celebrating ? "primary.light" : "divider",
        bgcolor: (t) => alpha(t.palette.primary.main, celebrating ? 0.08 : 0.03),
        display: "grid", gap: { xs: 2, md: 4 }, alignItems: "center",
        gridTemplateColumns: { xs: "1fr", md: "auto minmax(0,1fr)" },
      }}
    >
      <Stack direction="row" gap={1} alignItems="center" justifyContent="center">
        {celebrating ? (
          <Box
            component="img" src={MISC.celebrate} alt="" aria-hidden="true" loading="lazy" decoding="async"
            sx={{ display: { xs: "none", sm: "block" }, width: { sm: 120, xxl: 150, uhd: 180 }, height: "auto" }}
          />
        ) : null}
        <MascotPose mode={celebrating ? "love" : "success"} size={72} decorative />
      </Stack>
      <Box sx={{ display: "grid", gap: 1.5, justifyItems: { xs: "center", md: "start" }, minWidth: 0, textAlign: { xs: "center", md: "left" } }}>
        {label ? (
          <Typography variant="body2" sx={{ fontWeight: 700, letterSpacing: "0.06em", color: "primary.main" }}>{label}</Typography>
        ) : null}
        {children}
      </Box>
    </Paper>
  );
}

/* 사다리(아미다쿠지) 시각화. 서버가 확정한 세로줄·가로줄·도착지를 정직하게 그리고,
 * 위쪽 이름을 누르면 그 사람의 경로를 따라 내려가는 선을 강조한다. 좌표는 열을 균등 분할한
 * 중심(그리드 1fr 칩과 정렬)으로 잡는다. 선은 non-scaling-stroke로 늘려도 굵기 유지. */
function LadderBoard({ result, highlightUserId }) {
  const cols = result.columns || [];
  const outcomes = result.outcomes || [];
  const rungs = result.rungs || [];
  const rows = result.rows || 8;
  const n = cols.length;
  const initial = highlightUserId ? cols.findIndex((c) => c.user_id === highlightUserId) : -1;
  const [sel, setSel] = useState(initial >= 0 ? initial : null);
  if (n < 2) return null;

  const colX = (c) => (c + 0.5) * (100 / n);
  const topY = 6, botY = 94;
  const rowY = (r) => topY + ((r + 1) * (botY - topY)) / (rows + 1);
  const rungSet = new Set(rungs.map((g) => g.row + ":" + g.col));

  function pathFor(start) {
    let col = start;
    const pts = [[colX(col), topY]];
    for (let r = 0; r < rows; r++) {
      pts.push([colX(col), rowY(r)]);
      if (rungSet.has(r + ":" + col)) { col += 1; pts.push([colX(col), rowY(r)]); }
      else if (col > 0 && rungSet.has(r + ":" + (col - 1))) { col -= 1; pts.push([colX(col), rowY(r)]); }
    }
    pts.push([colX(col), botY]);
    return { points: pts.map((p) => p[0].toFixed(2) + "," + p[1].toFixed(2)).join(" "), end: col };
  }
  const selPath = sel != null ? pathFor(sel) : null;
  const gridSx = { display: "grid", gridTemplateColumns: `repeat(${n}, 1fr)`, gap: 0.5 };
  const chipSx = (on, outcome) => ({
    display: "block", textAlign: "center", px: 0.5, py: 0.75, borderRadius: 1.5,
    border: 1, borderColor: on ? "primary.main" : "divider",
    bgcolor: on ? "primary.main" : (outcome ? "action.hover" : "background.paper"),
    color: on ? "primary.contrastText" : "text.primary",
    font: "inherit", fontSize: "0.8125rem", fontWeight: 600, minWidth: 0,
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
    cursor: outcome ? "default" : "pointer",
    "&:hover": outcome ? undefined : { borderColor: "primary.main" },
  });

  return (
    <Box sx={{ display: "grid", gap: 1 }}>
      <Box sx={gridSx}>
        {cols.map((c, i) => (
          <Box component="button" type="button" key={c.user_id}
            aria-pressed={sel === i}
            sx={chipSx(sel === i, false)}
            onClick={() => setSel(sel === i ? null : i)}>{c.name}</Box>
        ))}
      </Box>
      <Box
        component="svg" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="사다리"
        sx={(t) => ({
          width: "100%", height: { xs: "14rem", md: "18rem", xxl: "22rem" }, display: "block",
          "& .ladder-v": { stroke: t.palette.divider, strokeWidth: 2 },
          "& .ladder-r": { stroke: t.palette.text.secondary, strokeWidth: 2 },
          "& .ladder-p": {
            stroke: t.palette.primary.main, strokeWidth: 3.5, strokeLinecap: "round", strokeLinejoin: "round",
            strokeDasharray: 100, strokeDashoffset: 100, animation: `${draw} .9s ease forwards`,
          },
        })}
      >
        {cols.map((_, i) => (
          <line key={"v" + i} x1={colX(i)} y1={topY} x2={colX(i)} y2={botY} className="ladder-v" vectorEffect="non-scaling-stroke" />
        ))}
        {rungs.map((g, i) => (
          <line key={"r" + i} x1={colX(g.col)} y1={rowY(g.row)} x2={colX(g.col + 1)} y2={rowY(g.row)} className="ladder-r" vectorEffect="non-scaling-stroke" />
        ))}
        {selPath ? (
          <polyline key={sel} className="ladder-p" points={selPath.points} pathLength="100" vectorEffect="non-scaling-stroke" fill="none" />
        ) : null}
      </Box>
      <Box sx={gridSx}>
        {outcomes.map((o, i) => (
          <Box component="span" key={i} sx={chipSx(!!(selPath && selPath.end === i), true)}>{o}</Box>
        ))}
      </Box>
      {sel != null && selPath ? (
        <Typography sx={{ textAlign: "center" }}>
          {cols[sel].name} <Box component="span" aria-hidden="true">→</Box>{" "}
          <Box component="b" sx={{ color: "primary.main" }}>{outcomes[selPath.end]}</Box>
        </Typography>
      ) : (
        <StageHint>이름을 누르면 사다리 경로가 보입니다.</StageHint>
      )}
    </Box>
  );
}

const T_RPS_LABELS = ["가위", "바위", "보"];
const T_RPS_EMOJI = ["✌️", "✊", "✋"];

function MatchTag({ done, winner, submitted, bye }) {
  if (bye) return <Badge value="부전승" kind="info" />;
  if (done) return winner ? <Badge value="승" kind="ok" /> : <Badge value="패" kind="neutral" />;
  return submitted ? <Badge value="제출" kind="ok" /> : <Badge value="대기" kind="warn" />;
}

/* 가위바위보 선택 버튼(손 이모지 + 라벨). */
function RpsChoices({ labels, emojis, chosen, disabled, onPick }) {
  return (
    <Stack direction="row" gap={1} justifyContent="center" flexWrap="wrap">
      {labels.map((label, i) => (
        <Box
          key={i} component="button" type="button"
          aria-pressed={chosen === i}
          disabled={disabled}
          onClick={() => onPick(i)}
          sx={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 0.5,
            px: 2, py: 1, minWidth: "5.25rem", borderRadius: 2, cursor: "pointer",
            border: 1, borderColor: chosen === i ? "primary.main" : "divider",
            bgcolor: (t) => (chosen === i ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
            color: "text.primary", font: "inherit",
            transition: "transform .12s ease, border-color .12s ease",
            "&:hover:not(:disabled)": { borderColor: "primary.main", transform: "translateY(-2px)" },
            "&:disabled": { cursor: "default", opacity: 0.6 },
          }}
        >
          <Box component="span" aria-hidden="true" sx={{ fontSize: "2.125rem", lineHeight: 1 }}>{emojis[i]}</Box>
          <Box component="span" sx={{ fontSize: "0.8125rem", fontWeight: 600 }}>{label}</Box>
        </Box>
      ))}
    </Stack>
  );
}

const bracketListSx = { listStyle: "none", m: 0, p: 0, display: "grid", gap: 1, width: "100%", maxWidth: "30rem" };

/* 가위바위보 토너먼트 진행 화면: 라운드 대진표 + (내 대진이면) 선택 버튼. 상대 선택은 감춘다. */
function RpsTournamentLive({ gstate, onPick, pending, canPlay }) {
  const ym = gstate.your_match;
  return (
    <Box sx={{ display: "grid", gap: 1.5, justifyItems: "center", width: "100%" }}>
      <Typography variant="body2" color="text.secondary">라운드 {(gstate.round_idx || 0) + 1}</Typography>
      <Box component="ul" sx={bracketListSx}>
        {(gstate.matches || []).map((m, i) => (
          <Paper component="li" key={i} variant="outlined" sx={{
            display: "grid", gridTemplateColumns: "minmax(0,1fr) auto minmax(0,1fr)", alignItems: "center", gap: 1,
            px: 1.5, py: 1, bgcolor: m.done ? "action.hover" : "background.paper",
            animation: `${rise} .35s ease both`,
          }}>
            <Stack direction="row" gap={0.75} alignItems="center" minWidth={0}>
              <Box component="span" sx={{
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                fontWeight: m.done && m.winner_name === m.a_name ? 700 : 400,
                color: m.done && m.winner_name === m.a_name ? "primary.main" : "inherit",
              }}>{m.a_name}</Box>
              <MatchTag done={m.done} winner={m.winner_name === m.a_name} submitted={m.a_submitted} />
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ px: 0.5 }}>{m.bye ? "부전승" : "vs"}</Typography>
            <Stack direction="row" gap={0.75} alignItems="center" minWidth={0} justifyContent="flex-end">
              <Box component="span" sx={{
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                fontWeight: m.done && m.winner_name === m.b_name ? 700 : 400,
                color: m.done && m.winner_name === m.b_name ? "primary.main" : "inherit",
              }}>{m.b_name || "-"}</Box>
              {!m.bye ? <MatchTag done={m.done} winner={m.winner_name === m.b_name} submitted={m.b_submitted} /> : null}
            </Stack>
          </Paper>
        ))}
      </Box>
      {ym ? (
        <Box sx={{ display: "grid", gap: 1, justifyItems: "center", width: "100%", pt: 1, borderTop: 1, borderStyle: "dashed", borderColor: "divider" }}>
          <Typography sx={{ fontWeight: 700, fontSize: "1.0625rem" }}>내 상대: {ym.opponent}</Typography>
          {canPlay ? (
            <RpsChoices labels={T_RPS_LABELS} emojis={T_RPS_EMOJI} chosen={ym.your_choice} disabled={pending} onPick={onPick} />
          ) : null}
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
            {ym.you_submitted
              ? `낸 것 ${T_RPS_LABELS[ym.your_choice]} (다시 누르면 변경). 상대가 내면 바로 판정됩니다.`
              : "가위, 바위, 보 중 하나를 내세요."}
          </Typography>
        </Box>
      ) : (
        <StageHint>이번 라운드 대진에 없습니다. 다음 라운드를 기다려 주세요.</StageHint>
      )}
    </Box>
  );
}

/* 토너먼트 최종 결과: 우승자 + 라운드별 대진 히스토리. */
function RpsTournamentResult({ result }) {
  return (
    <Box sx={{ display: "grid", gap: 2, justifyItems: "center", width: "100%" }}>
      <ResultStage mood={result.champion ? "win" : "calm"} label="우승">
        {result.champion
          ? <WinnerName>🏆 {result.champion.name}</WinnerName>
          : <Typography color="text.secondary">우승자가 없습니다.</Typography>}
      </ResultStage>
      <Box sx={{ display: "grid", gap: 1.5, width: "100%", maxWidth: "30rem" }}>
        {(result.rounds || []).map((rnd, ri) => (
          <Box key={ri} sx={{ display: "grid", gap: 0.5 }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>라운드 {ri + 1}</Typography>
            <Box component="ul" sx={bracketListSx}>
              {rnd.map((m, i) => (
                <Paper component="li" key={i} variant="outlined" sx={{
                  display: "grid", gridTemplateColumns: "minmax(0,1fr) auto minmax(0,1fr)", alignItems: "center", gap: 1,
                  px: 1.5, py: 1, bgcolor: "action.hover",
                }}>
                  <Box component="span" sx={{
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    fontWeight: m.winner_name === m.a_name ? 700 : 400,
                    color: m.winner_name === m.a_name ? "primary.main" : "inherit",
                  }}>{m.a_name}</Box>
                  <Typography variant="caption" color="text.secondary">{m.b_name ? "vs" : "부전승"}</Typography>
                  <Box component="span" sx={{
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "right",
                    fontWeight: m.winner_name === m.b_name ? 700 : 400,
                    color: m.winner_name === m.b_name ? "primary.main" : "inherit",
                  }}>{m.b_name || "-"}</Box>
                </Paper>
              ))}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

/* 순위표(퀴즈). 번호는 CSS 카운터로 — 마크업에 순번 텍스트를 넣지 않는다. */
function Scoreboard({ rows }) {
  return (
    <Box component="ol" sx={{
      listStyle: "none", m: 0, p: 0, counterReset: "rank", display: "grid", gap: 0.5,
      width: "100%", maxWidth: "24rem",
    }}>
      {rows.map((s, i) => (
        <Paper component="li" key={s.key || i} variant="outlined" sx={{
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1.5, px: 1.5, py: 0.75,
          animation: `${rise} .38s ease both`,
          "&::before": {
            counterIncrement: "rank", content: "counter(rank)", flexShrink: 0, width: "1.75rem",
            color: "text.secondary", fontVariantNumeric: "tabular-nums", fontSize: "0.8125rem",
          },
        }}>
          <Box component="span" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</Box>
          <Box component="span" sx={{ flexShrink: 0, fontWeight: 700, color: "primary.main", fontVariantNumeric: "tabular-nums" }}>{s.value}</Box>
        </Paper>
      ))}
    </Box>
  );
}

const stageColumnSx = { display: "grid", gap: 1.5, justifyItems: "center", width: "100%" };

export function GameRoom() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const joinedRef = useRef(false);
  const chatLogRef = useRef(null);
  const prevChatCountRef = useRef(0);    // 자동 스크롤 판단(첫 로드/맨아래 근처일 때만 따라감)
  const goneRef = useRef(false);
  const [draft, setDraft] = useState("");
  const [numDraft, setNumDraft] = useState("");

  const state = useQuery({
    queryKey: ["game-room", id],
    queryFn: () => api(`/api/games/rooms/${id}/state?since=0`),
    refetchInterval: 1200,
  });

  const join = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/join`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "입장하지 못했습니다.", "error"),
  });
  // 방에 처음 들어오면 자동 입장. 서버가 대기 중·자리 있으면 참여자로, 아니면 관전자로 배정.
  useEffect(() => {
    if (!joinedRef.current && state.data && !state.data.you.in_room) {
      joinedRef.current = true;
      join.mutate();
    }
  }, [state.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const ready = useMutation({
    mutationFn: (v) => api(`/api/games/rooms/${id}/ready`, { method: "POST", body: { ready: v } }),
    onSuccess: () => state.refetch(),
  });
  const start = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/start`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "게임을 시작하지 못했습니다.", "error"),
  });
  const vote = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/vote`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "투표하지 못했습니다.", "error"),
  });
  const finish = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/finish`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "게임을 종료하지 못했습니다.", "error"),
  });
  const pick = useMutation({
    mutationFn: (value) => api(`/api/games/rooms/${id}/pick`, { method: "POST", body: { value } }),
    onSuccess: () => { setNumDraft(""); state.refetch(); },
    onError: (e) => toast((e && e.message) || "숫자를 내지 못했습니다.", "error"),
  });
  const rps = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/rps`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "내지 못했습니다.", "error"),
  });
  const quizAnswer = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/quiz-answer`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "답을 내지 못했습니다.", "error"),
  });
  const reveal = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/reveal`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "정답을 공개하지 못했습니다.", "error"),
  });
  const nextQ = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/next`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "다음으로 넘어가지 못했습니다.", "error"),
  });
  const reset = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/reset`, { method: "POST" }),
    onSuccess: () => state.refetch(),
  });
  const leave = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/leave`, { method: "POST" }),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["games-rooms"] }); nav("/games"); },
  });
  const disband = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/disband`, { method: "POST" }),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["games-rooms"] }); nav("/games"); },
  });
  const chat = useMutation({
    mutationFn: (text) => api(`/api/games/rooms/${id}/chat`, { method: "POST", body: { text } }),
    onSuccess: () => { setDraft(""); state.refetch(); },
    onError: (e) => toast((e && e.message) || "메시지를 보내지 못했습니다.", "error"),
  });

  // 승자가 확정되면(폴링으로 결과가 처음 도착하는 순간) 축포를 한 번 터뜨린다. celebrateKey는
  // 결과 내용이 바뀔 때만 값이 달라지므로 폴링마다 재발화하지 않는다. 훅 순서 유지를 위해
  // 조기 return 위에 둔다(무승부·팀나누기·사다리처럼 '승자'가 없는 결과는 제외).
  const celebrateKey = deriveCelebrateKey(state.data);
  useEffect(() => { if (celebrateKey) celebrate(); }, [celebrateKey]);

  // 방이 사라지면(방장이 파함 → 404, 또는 closed 표시) 목록으로 돌려보낸다. 한 번만.
  const notFound = state.isError && state.error && state.error.status === 404;
  const closed = state.data && state.data.room && state.data.room.closed;
  useEffect(() => {
    if ((notFound || closed) && !goneRef.current) {
      goneRef.current = true;
      toast("방이 사라졌습니다.", "info");
      qc.invalidateQueries({ queryKey: ["games-rooms"] });
      nav("/games");
    }
  }, [notFound, closed]); // eslint-disable-line react-hooks/exhaustive-deps

  // 새 채팅이 오면 최신으로 따라 내려간다 — 단, 위로 올려 옛 대화를 읽는 중이면 끌어내리지 않는다
  // (첫 로드이거나 이미 맨 아래 근처에 있을 때만 스크롤). 상대·나 구분 없이 동작한다.
  const chatCount = (state.data?.events || []).filter((e) => e.kind === "chat").length;
  useEffect(() => {
    const el = chatLogRef.current;
    if (!el) return;
    const firstLoad = prevChatCountRef.current === 0;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    if (firstLoad || nearBottom) el.scrollTop = el.scrollHeight;
    prevChatCountRef.current = chatCount;
  }, [chatCount]);

  // 카운트다운(진행 중 타이머 게임). 훅 순서 유지를 위해 조기 return 위에서 계산한다.
  const liveDeadline = state.data && state.data.room && state.data.room.status === "playing"
    ? (state.data.state && state.data.state.deadline) || null
    : null;
  const remaining = useCountdown(liveDeadline);

  // 마감(deadline)은 이제 서버가 폴링 진입마다 강제한다(service.maybe_autoresolve) — 방장 브라우저에
  // 의존하지 않으므로 클라이언트 자동 진행은 두지 않는다. 카운트다운이 0이 되면 다음 폴링(1.2초)에서
  // 서버가 확정하고, 그 결과가 폴링으로 내려온다.

  if (state.isError && !notFound) return <div className="c-screen"><ErrorState error={state.error} onRetry={() => state.refetch()} /></div>;
  if (state.isPending) return <div className="c-screen"><Card><Skeleton lines={6} /></Card></div>;

  const { room, you, members } = state.data;
  const gstate = state.data.state || {};
  const chatMsgs = (state.data.events || []).filter((e) => e.kind === "chat");
  const isVote = room.game_type === "quick_vote";
  const isTeam = room.game_type === "team_split";
  const isDraw = room.game_type === "random_draw";
  const isNumber = room.game_type === "number";
  const isLadder = room.game_type === "ladder";
  const isRps = room.game_type === "rps";
  const isQuiz = room.game_type === "quiz";
  const isHost = you.is_host;
  const canReady = isDraw && you.in_room && you.role === "player" && room.status === "waiting";
  const canVote = isVote && room.status === "playing" && you.in_room && you.role !== "spectator";
  const canPick = isNumber && room.status === "playing" && you.in_room && you.role !== "spectator";
  const canRps = isRps && room.status === "playing" && you.in_room && you.role !== "spectator";

  // 랜덤 추첨 결과(당첨자 이름) / 팀 나누기 결과(팀별 명단) / 빠른 투표 결과(집계).
  const drawWinners = isDraw ? (gstate.result || []) : [];
  const teams = isTeam ? (gstate.result?.teams || []) : [];
  const ladderAssignments = isLadder ? (gstate.result?.assignments || []) : [];
  // 숫자 눈치: 진행 중엔 서버가 남의 선택을 감춘다(min/max/제출수/내 선택만). 종료 후 result 공개.
  const numResult = isNumber ? (gstate.result || null) : null;
  const rpsResult = isRps ? (gstate.result || null) : null;
  const isTournament = isRps && (gstate.mode === "tournament" || (rpsResult && rpsResult.mode === "tournament"));
  const RPS_LABELS = ["가위", "바위", "보"];
  const RPS_EMOJI = ["✌️", "✊", "✋"];
  const rpsEmoji = (label) => RPS_EMOJI[RPS_LABELS.indexOf(label)] || "";
  // 실시간 퀴즈: 진행 중엔 gstate가 라운드/문제/보기/내 답/점수(정답은 revealed에서만). 종료 후 result.
  const quizResult = isQuiz ? (gstate.result || null) : null;
  const quizPlaying = isQuiz && room.status === "playing" ? gstate : null;
  const canQuizAnswer = isQuiz && room.status === "playing" && gstate.phase === "answering" && you.in_room && you.role !== "spectator";
  const nameOf = {};
  members.forEach((m) => { nameOf[m.user_id] = m.name; });
  const liveScores = (quizPlaying?.scores || []).map((s) => ({ name: nameOf[s.user_id] || "?", score: s.score }));
  const voteResult = isVote ? (gstate.result || null) : null;
  // 빠른 투표 진행 중: state.votes(uid→선택지 index)로 라이브 집계 + 내 선택 표시.
  const voteOptions = isVote ? (gstate.options || voteResult?.options || []) : [];
  const votes = (isVote && gstate.votes) || {};
  const liveCounts = voteOptions.map((_, i) => Object.values(votes).filter((v) => v === i).length);
  const myVote = votes[you.user_id];
  const maxCount = voteResult ? Math.max(0, ...(voteResult.counts || [])) : Math.max(0, ...liveCounts);

  // 진행 중 제출 현황(누가 냈고 누가 안 냈는지). rps/number/quiz는 서버가 submitted(uid 목록)를,
  // 빠른 투표는 votes 키를 준다. 이걸로 참여자 목록에 제출/대기 배지를 달고 대기자를 안내한다.
  const submittedSet = new Set(
    room.status === "playing" ? (isVote ? Object.keys(votes) : (gstate.submitted || [])) : []
  );
  const submissionActive = room.status === "playing"
    && (isVote || isNumber || (isRps && !isTournament) || (isQuiz && gstate.phase === "answering"));
  const activePlayers = members.filter((m) => m.role !== "spectator");
  const waitingNames = submissionActive
    ? activePlayers.filter((m) => !submittedSet.has(m.user_id)).map((m) => m.name)
    : [];
  const submittedCount = submissionActive ? activePlayers.filter((m) => submittedSet.has(m.user_id)).length : 0;

  const sendChat = () => { const t = draft.trim(); if (t && !chat.isPending) chat.mutate(t); };

  const voteOptionSx = (mine, correct, preview) => ({
    width: "100%", display: "flex", alignItems: "center", gap: 1.5, textAlign: "left",
    px: 2, py: 1.5, borderRadius: 2, cursor: preview ? "default" : "pointer",
    border: 1, borderColor: correct ? "success.main" : mine ? "primary.main" : "divider",
    bgcolor: (t) => (correct ? alpha(t.palette.success.main, 0.12)
      : mine ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
    color: preview ? "text.secondary" : "text.primary", font: "inherit",
    "&:hover:not(:disabled)": preview ? undefined : { borderColor: "primary.main" },
    "&:disabled": { cursor: "default" },
  });

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="놀이" title={room.title}
        actions={<Button onClick={() => leave.mutate()} disabled={leave.isPending}>나가기</Button>} />

      {/* 무대(왼쪽) + 참여자·채팅 레일(오른쪽). 좁은 화면에서는 한 열로 흐른다. */}
      <Box sx={{
        display: "grid", gap: 2, alignItems: "start",
        gridTemplateColumns: { xs: "1fr", md: "minmax(0,1fr) 22rem", xxl: "minmax(0,1fr) 26rem" },
      }}>
        <Box component="section" sx={{ display: "grid", gap: 2, minWidth: 0 }}>
          <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
            <Badge value={GAME_LABELS[room.game_type] || room.game_type} kind="neutral" />
            <Badge value={STATUS_LABELS[room.status] || room.status} kind={STATUS_KIND[room.status] || "neutral"} />
            <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
              참여 {room.player_count}/{room.max_players}
            </Typography>
            {you.role === "spectator" ? <Typography variant="body2" color="text.secondary">관전 중</Typography> : null}
          </Stack>

          {/* 진행 현황: 카운트다운 + 제출/대기(모든 제출형 게임 공통) */}
          {submissionActive || remaining != null ? (
            <Paper variant="outlined" sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", px: 1.5, py: 1.25 }}>
              <Countdown remaining={remaining} />
              {submissionActive ? (
                <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
                  <Typography variant="body2" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                    제출 {submittedCount}/{activePlayers.length}
                  </Typography>
                  {waitingNames.length > 0
                    ? <Typography variant="body2" color="text.secondary">대기 {waitingNames.join(", ")}</Typography>
                    : <Typography variant="body2" color="success.main" sx={{ fontWeight: 600 }}>모두 제출했습니다</Typography>}
                </Stack>
              ) : null}
            </Paper>
          ) : null}

          {/* 무대: 게임 종류·상태별 화면 */}
          {isDraw && room.status === "finished" && drawWinners.length > 0 ? (
            <ResultStage label="당첨">
              <Stack direction="row" gap={1} flexWrap="wrap" justifyContent={{ xs: "center", md: "flex-start" }}>
                {drawWinners.map((w) => <WinnerName key={w.user_id}>{w.name}</WinnerName>)}
              </Stack>
            </ResultStage>
          ) : isTeam && room.status === "finished" && teams.length > 0 ? (
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fit, minmax(14rem, 1fr))" } }}>
              {teams.map((team, ti) => (
                <Paper key={ti} variant="outlined" sx={{ p: 2, animation: `${rise} .38s ease both` }}>
                  <Typography sx={{ fontWeight: 700, mb: 1 }}>
                    {ti + 1}팀 <Box component="span" sx={{ color: "text.secondary", fontWeight: 400, fontSize: "0.8125rem" }}>{team.length}명</Box>
                  </Typography>
                  <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
                    {team.map((m) => <li key={m.user_id}>{m.name}</li>)}
                  </Box>
                </Paper>
              ))}
            </Box>
          ) : isLadder && room.status === "finished" && ladderAssignments.length > 0 ? (
            gstate.result && gstate.result.columns ? (
              <LadderBoard result={gstate.result} highlightUserId={you.user_id} />
            ) : (
              <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
                {ladderAssignments.map((a) => (
                  <Paper component="li" key={a.user_id} variant="outlined" sx={{
                    display: "flex", alignItems: "center", gap: 1.5, px: 1.5, py: 1, animation: `${rise} .38s ease both`,
                  }}>
                    <Box component="span" sx={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{a.name}</Box>
                    <Box component="span" aria-hidden="true" sx={{ color: "text.secondary" }}>→</Box>
                    <Box component="span" sx={{ fontWeight: 700, color: "primary.main" }}>{a.outcome}</Box>
                  </Paper>
                ))}
              </Box>
            )
          ) : (isDraw || isTeam || isLadder) && room.status === "waiting" ? (
            <StageHint>
              {isTeam ? "참여자가 모이면 방장이 팀을 나눕니다."
                : isLadder ? "참여자가 모이면 방장이 사다리를 탑니다."
                  : "참여자가 모이면 방장이 추첨을 시작합니다."}
            </StageHint>
          ) : isVote ? (
            <Box sx={{ display: "grid", gap: 2 }}>
              <Typography sx={{ fontWeight: 700, fontSize: "1.0625rem", textAlign: "center" }}>
                {voteResult?.question || gstate.question || room.title}
              </Typography>
              {room.status === "finished" && voteResult ? (
                <>
                  <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
                    {(voteResult.options || []).map((opt, i) => {
                      const c = (voteResult.counts || [])[i] || 0;
                      const win = (voteResult.winners || []).includes(opt);
                      return (
                        <Box component="li" key={i} sx={{
                          display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr) auto", sm: "10rem minmax(0,1fr) auto" },
                          alignItems: "center", gap: 1.5,
                        }}>
                          <Box component="span" sx={{
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            fontWeight: win ? 700 : 400,
                          }}>{opt}</Box>
                          <Box sx={{
                            display: { xs: "none", sm: "block" }, height: "0.875rem", borderRadius: 999,
                            bgcolor: "action.hover", overflow: "hidden",
                          }}>
                            <Box sx={{
                              display: "block", height: "100%", borderRadius: 999,
                              bgcolor: win ? "primary.main" : "primary.light",
                              width: (maxCount ? (c / maxCount) * 100 : 0) + "%",
                            }} />
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>{c}표</Typography>
                        </Box>
                      );
                    })}
                  </Box>
                  {(voteResult.winners || []).length > 0 ? (
                    <ResultStage label="결과">
                      <Stack direction="row" gap={1} flexWrap="wrap" justifyContent={{ xs: "center", md: "flex-start" }}>
                        {voteResult.winners.map((w) => <WinnerName key={w}>{w}</WinnerName>)}
                      </Stack>
                    </ResultStage>
                  ) : <StageHint>투표한 사람이 없습니다.</StageHint>}
                </>
              ) : room.status === "playing" ? (
                <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
                  {voteOptions.map((opt, i) => (
                    <li key={i}>
                      <Box component="button" type="button" sx={voteOptionSx(myVote === i, false, false)}
                        aria-pressed={myVote === i}
                        disabled={!canVote || vote.isPending} onClick={() => canVote && vote.mutate(i)}>
                        <Box component="span" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{opt}</Box>
                        <Box component="span" sx={{ flexShrink: 0, minWidth: "1.75rem", textAlign: "center", fontWeight: 700, color: "primary.main", fontVariantNumeric: "tabular-nums" }}>
                          {liveCounts[i]}
                        </Box>
                      </Box>
                    </li>
                  ))}
                </Box>
              ) : (
                <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
                  {voteOptions.map((opt, i) => (
                    <li key={i}><Box sx={voteOptionSx(false, false, true)}>{opt}</Box></li>
                  ))}
                </Box>
              )}
              {room.status === "playing" && !canVote && you.role === "spectator" ? (
                <StageHint>관전 중: 투표는 참여자만 할 수 있습니다.</StageHint>
              ) : null}
            </Box>
          ) : isNumber ? (
            <Box sx={stageColumnSx}>
              {room.status === "finished" && numResult ? (
                <>
                  <ResultStage mood={numResult.winner ? "win" : "calm"} label="가장 낮은 유일 숫자">
                    {numResult.winner
                      ? <WinnerName>{numResult.winner.name} ({numResult.winner.number})</WinnerName>
                      : <Typography color="text.secondary">유일한 숫자가 없어 승자가 없습니다.</Typography>}
                  </ResultStage>
                  <Stack direction="row" gap={1.5} flexWrap="wrap" justifyContent="center">
                    {(numResult.picks || []).map((p) => {
                      const win = numResult.winner && numResult.winner.user_id === p.user_id;
                      return (
                        <Paper key={p.user_id} variant="outlined" sx={{
                          display: "grid", justifyItems: "center", gap: 0.25, px: 1.5, py: 1, minWidth: "5.25rem",
                          borderColor: win ? "primary.main" : "divider",
                          bgcolor: (t) => (win ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
                        }}>
                          <Box component="span" sx={{ fontSize: "1.5rem", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{p.number}</Box>
                          <Box component="span" sx={{ fontSize: "0.8125rem", color: "text.secondary" }}>{p.name}</Box>
                        </Paper>
                      );
                    })}
                  </Stack>
                </>
              ) : room.status === "playing" ? (
                <>
                  <Typography sx={{ fontWeight: 700, fontSize: "1.0625rem", textAlign: "center" }}>
                    {gstate.min || 1} ~ {gstate.max || 10} 중 하나를 몰래 내세요
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                    가장 낮은 ‘유일한’ 숫자를 낸 사람이 이깁니다. 지금 {gstate.submitted_count || 0}명 제출.
                  </Typography>
                  {canPick ? (
                    <Stack direction="row" gap={1} alignItems="center">
                      <TextField
                        size="small"
                        type="number"
                        value={numDraft}
                        placeholder={(gstate.min || 1) + "~" + (gstate.max || 10)}
                        inputProps={{ min: gstate.min || 1, max: gstate.max || 10, "aria-label": "낼 숫자" }}
                        onChange={(e) => setNumDraft(e.target.value)}
                        sx={{ width: "8rem", "& input": { textAlign: "center", fontVariantNumeric: "tabular-nums" } }}
                      />
                      <Button variant="primary" disabled={pick.isPending || numDraft === ""}
                        sx={{ flexShrink: 0, whiteSpace: "nowrap" }}
                        onClick={() => { const v = Number(numDraft); if (Number.isInteger(v)) pick.mutate(v); }}>제출</Button>
                    </Stack>
                  ) : null}
                  {canPick && gstate.you_submitted ? (
                    <Typography variant="body2" color="text.secondary">내가 낸 숫자: {gstate.your_pick} (다시 내면 변경됩니다)</Typography>
                  ) : null}
                  {you.role === "spectator" ? (
                    <StageHint>관전 중: 참여자만 숫자를 낼 수 있습니다.</StageHint>
                  ) : null}
                </>
              ) : (
                <StageHint>참여자가 모이면 방장이 숫자 눈치를 시작합니다.</StageHint>
              )}
            </Box>
          ) : isRps ? (
            <Box sx={stageColumnSx}>
              {room.status === "finished" && rpsResult && rpsResult.mode === "tournament" ? (
                <RpsTournamentResult result={rpsResult} />
              ) : room.status === "playing" && isTournament ? (
                <RpsTournamentLive gstate={gstate} onPick={(i) => rps.mutate(i)}
                  pending={rps.isPending} canPlay={you.in_room && you.role !== "spectator"} />
              ) : room.status === "finished" && rpsResult ? (
                <>
                  {rpsResult.outcome === "win" ? (
                    <ResultStage label={`${rpsResult.win_choice} 승리`}>
                      <Stack direction="row" gap={1} flexWrap="wrap" justifyContent={{ xs: "center", md: "flex-start" }}>
                        {(rpsResult.winners || []).map((w) => <WinnerName key={w.user_id}>{w.name}</WinnerName>)}
                      </Stack>
                    </ResultStage>
                  ) : (
                    <ResultStage mood="calm" label="무승부">
                      <Typography color="text.secondary">같은 손만 나왔거나 셋이 다 나왔습니다.</Typography>
                    </ResultStage>
                  )}
                  <Stack direction="row" gap={1.5} flexWrap="wrap" justifyContent="center">
                    {(rpsResult.reveal || []).map((p) => {
                      const win = (rpsResult.winners || []).some((w) => w.user_id === p.user_id);
                      return (
                        <Paper key={p.user_id} variant="outlined" sx={{
                          display: "grid", justifyItems: "center", gap: 0.25, px: 1.5, py: 1, minWidth: "5.25rem",
                          borderColor: win ? "primary.main" : "divider",
                          bgcolor: (t) => (win ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
                        }}>
                          <Box component="span" aria-hidden="true" sx={{ fontSize: "2.75rem", lineHeight: 1 }}>{rpsEmoji(p.choice)}</Box>
                          <Box component="span" sx={{ fontSize: "0.8125rem", fontWeight: 700 }}>{p.choice}</Box>
                          <Box component="span" sx={{ fontSize: "0.8125rem", color: "text.secondary" }}>{p.name}</Box>
                        </Paper>
                      );
                    })}
                  </Stack>
                </>
              ) : room.status === "playing" ? (
                <>
                  <Typography sx={{ fontWeight: 700, fontSize: "1.0625rem", textAlign: "center" }}>가위, 바위, 보 중 하나를 몰래 내세요</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                    방장이 공개하면 판정합니다. 지금 {gstate.submitted_count || 0}명 제출.
                  </Typography>
                  {canRps ? (
                    <RpsChoices labels={RPS_LABELS} emojis={RPS_EMOJI} chosen={gstate.your_choice}
                      disabled={rps.isPending} onPick={(i) => rps.mutate(i)} />
                  ) : null}
                  {canRps && gstate.you_submitted ? (
                    <Typography variant="body2" color="text.secondary">낸 것: {RPS_LABELS[gstate.your_choice]} (다시 누르면 변경)</Typography>
                  ) : null}
                  {you.role === "spectator" ? (
                    <StageHint>관전 중: 참여자만 낼 수 있습니다.</StageHint>
                  ) : null}
                </>
              ) : (
                <StageHint>참여자가 모이면 방장이 가위바위보를 시작합니다.</StageHint>
              )}
            </Box>
          ) : isQuiz ? (
            <Box sx={stageColumnSx}>
              {room.status === "finished" && quizResult ? (
                <>
                  <ResultStage mood={(quizResult.winners || []).length ? "win" : "calm"} label="최종 순위">
                    {(quizResult.winners || []).length > 0 ? (
                      <Stack direction="row" gap={1} flexWrap="wrap" justifyContent={{ xs: "center", md: "flex-start" }}>
                        {quizResult.winners.map((w) => <WinnerName key={w}>{w}</WinnerName>)}
                      </Stack>
                    ) : (
                      <Typography color="text.secondary">맞힌 사람이 없습니다.</Typography>
                    )}
                  </ResultStage>
                  <Scoreboard rows={(quizResult.scoreboard || []).map((s) => ({
                    key: s.user_id, name: s.name, value: `${s.score} / ${quizResult.total_rounds}`,
                  }))} />
                </>
              ) : quizPlaying ? (
                <>
                  <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
                    문제 {(quizPlaying.round || 0) + 1} / {quizPlaying.total}
                  </Typography>
                  <Typography sx={{ fontWeight: 700, fontSize: "1.0625rem", textAlign: "center" }}>{quizPlaying.question}</Typography>
                  <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1, width: "100%", maxWidth: "30rem" }}>
                    {(quizPlaying.options || []).map((opt, i) => {
                      const mine = quizPlaying.your_answer === i;
                      const isAnswer = quizPlaying.phase === "revealed" && quizPlaying.answer === i;
                      return (
                        <li key={i}>
                          <Box component="button" type="button" sx={voteOptionSx(mine, isAnswer, false)}
                            aria-pressed={mine}
                            disabled={!canQuizAnswer || quizAnswer.isPending}
                            onClick={() => canQuizAnswer && quizAnswer.mutate(i)}>
                            <Box component="span" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{opt}</Box>
                            {isAnswer ? (
                              <Box component="span" sx={{ flexShrink: 0, fontWeight: 700, color: "success.main" }}>정답</Box>
                            ) : null}
                          </Box>
                        </li>
                      );
                    })}
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                    {quizPlaying.phase === "answering"
                      ? `${quizPlaying.submitted_count || 0}명 응답. 방장이 정답을 공개하면 채점합니다.`
                      : quizPlaying.your_answer == null ? "이번 문제에 응답하지 않았습니다."
                        : quizPlaying.your_correct ? "정답입니다! 🎉" : "아쉽지만 오답이에요."}
                  </Typography>
                  {liveScores.length > 0 ? (
                    <Scoreboard rows={liveScores.map((s, i) => ({ key: "s" + i, name: s.name, value: s.score }))} />
                  ) : null}
                </>
              ) : (
                <StageHint>참여자가 모이면 방장이 퀴즈를 시작합니다.</StageHint>
              )}
            </Box>
          ) : null}

          <Stack direction="row" gap={1} flexWrap="wrap">
            {canReady ? (
              <Button variant={you.ready ? "default" : "primary"} onClick={() => ready.mutate(!you.ready)} disabled={ready.isPending}>
                {you.ready ? "준비 해제" : "준비"}
              </Button>
            ) : null}
            {isHost && room.status === "waiting" ? (
              <Button variant="primary" onClick={() => start.mutate()} disabled={start.isPending}>{isVote ? "투표 시작" : isTeam ? "팀 나누기" : isNumber ? "숫자 눈치 시작" : isLadder ? "사다리 타기" : isRps ? "가위바위보 시작" : isQuiz ? "퀴즈 시작" : "추첨 시작"}</Button>
            ) : null}
            {isHost && (isVote || isNumber || isRps) && room.status === "playing" ? (
              <Button variant="primary" onClick={() => finish.mutate()} disabled={finish.isPending}>{isVote ? "투표 종료" : isTournament ? "이 라운드 마감" : "결과 공개"}</Button>
            ) : null}
            {isHost && isQuiz && room.status === "playing" && quizPlaying?.phase === "answering" ? (
              <Button variant="primary" onClick={() => reveal.mutate()} disabled={reveal.isPending}>정답 공개</Button>
            ) : null}
            {isHost && isQuiz && room.status === "playing" && quizPlaying?.phase === "revealed" ? (
              <Button variant="primary" onClick={() => nextQ.mutate()} disabled={nextQ.isPending}>
                {(quizPlaying.round || 0) + 1 >= quizPlaying.total ? "결과 보기" : "다음 문제"}
              </Button>
            ) : null}
            {isHost && room.status === "finished" ? (
              <Button variant="primary" onClick={() => reset.mutate()} disabled={reset.isPending}>다시 하기</Button>
            ) : null}
            {isHost ? (
              <Button variant="danger" disabled={disband.isPending}
                onClick={async () => {
                  const ok = await confirm("방을 파하면 모두 나가지고 방이 사라집니다. 계속할까요?",
                    { title: "방 파하기", confirmLabel: "방 파하기", danger: true });
                  if (ok) disband.mutate();
                }}>방 파하기</Button>
            ) : null}
          </Stack>
        </Box>

        {/* 오른쪽 레일 — 넓은 화면에서는 화면 높이에 고정하고 참여자 목록은 상한 높이로 접어(자체
            스크롤) 아무리 많아도 채팅을 밀어내지 않게 한다. 채팅이 남는 공간을 꽉 채운다. */}
        <Box component="aside" sx={{
          display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0,
          position: { md: "sticky" }, top: { md: 0 },
          // FAB_CLEARANCE 를 함께 빼지 않으면 레일 맨 아래의 '보내기'가 마스코트 FAB 밑에
          // 깔려 눌리지 않는다(클릭이 FAB에 가로채짐). 실제로 그랬다.
          height: { md: `calc(100vh - 14rem - ${FAB_CLEARANCE})` },
        }}>
          <Paper variant="outlined" sx={{ p: 1.5, flexShrink: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 700, mb: 1 }}>참여자 {members.length}명</Typography>
            <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5, maxHeight: "13rem", overflowY: "auto" }}>
              {members.map((m) => {
                const sub = [m.title, m.dept].filter(Boolean);
                const isHostRow = m.user_id === room.host_user_id;
                const isMe = m.user_id === you.user_id;
                return (
                  <Box component="li" key={m.user_id} sx={{
                    display: "flex", alignItems: "center", gap: 1.25, p: 1, borderRadius: 2,
                    border: 1, borderColor: isMe ? "primary.light" : "transparent",
                    bgcolor: (t) => (isMe ? alpha(t.palette.primary.main, 0.1) : "transparent"),
                  }}>
                    <Box component="span" aria-hidden="true" sx={{
                      flexShrink: 0, width: "2.25rem", height: "2.25rem", borderRadius: "50%",
                      display: "grid", placeItems: "center", fontWeight: 700, fontSize: "0.875rem",
                      bgcolor: isHostRow ? "primary.main" : "action.hover",
                      color: isHostRow ? "primary.contrastText" : "text.primary",
                    }}>
                      {(m.name || "?").slice(0, 1)}
                    </Box>
                    <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
                      <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 600 }}>
                        {m.name}{isMe ? <Box component="span" sx={{ color: "text.secondary", fontWeight: 400, fontSize: "0.8125rem" }}> (나)</Box> : null}
                      </Box>
                      {sub.length ? (
                        <Box component="span" sx={{
                          display: "flex", gap: 1, fontSize: "0.75rem", color: "text.secondary",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}>
                          {m.title ? <Box component="span" sx={{ color: "primary.main", fontWeight: 600 }}>{m.title}</Box> : null}
                          {m.dept ? <Box component="span">{m.dept}</Box> : null}
                        </Box>
                      ) : null}
                    </Box>
                    <Stack direction="row" gap={0.5} alignItems="center" sx={{ ml: "auto", flexShrink: 0 }}>
                      {isHostRow
                        ? <Badge value="방장" kind="info" />
                        : <Badge value={ROLE_LABELS[m.role] || m.role} kind="neutral" />}
                      {submissionActive && m.role !== "spectator"
                        ? (submittedSet.has(m.user_id)
                          ? <Badge value="제출" kind="ok" />
                          : <Badge value="대기" kind="warn" />)
                        : (m.role === "player" && m.ready ? <Badge value="준비" kind="ok" /> : null)}
                    </Stack>
                  </Box>
                );
              })}
            </Box>
          </Paper>

          <Paper variant="outlined" sx={{ p: 1.5, display: "flex", flexDirection: "column", flex: { md: "1 1 auto" }, minHeight: { md: 0 } }}>
            <Typography variant="body2" sx={{ fontWeight: 700, mb: 1 }}>채팅</Typography>
            <Box ref={chatLogRef} sx={{
              display: "flex", flexDirection: "column", gap: 1, overflowY: "auto", px: 0.5, py: 1, mb: 1.25,
              height: { xs: "45vh", md: "auto" }, minHeight: { xs: "16rem", md: 0 },
              maxHeight: { xs: "45rem", md: "none" }, flex: { md: "1 1 auto" },
            }}>
              {chatMsgs.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 2 }}>
                  아직 메시지가 없습니다. 먼저 인사해 보세요.
                </Typography>
              ) : chatMsgs.map((e) => {
                const mine = e.actor_user_id === you.user_id;
                return (
                  <Box key={e.seq} sx={{
                    display: "flex", flexDirection: "column", gap: 0.25, maxWidth: "85%",
                    alignSelf: mine ? "flex-end" : "flex-start", alignItems: mine ? "flex-end" : "flex-start",
                  }}>
                    {!mine ? (
                      <Box component="span" sx={{ fontSize: "0.75rem", color: "text.secondary", fontWeight: 600, px: 0.5 }}>
                        {e.payload.name}
                      </Box>
                    ) : null}
                    <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.75, flexDirection: mine ? "row-reverse" : "row" }}>
                      <Box component="span" sx={{
                        px: 1.5, py: 1, borderRadius: 3.5, fontSize: "0.875rem", lineHeight: 1.45,
                        wordBreak: "break-word",
                        border: 1, borderColor: mine ? "transparent" : "divider",
                        bgcolor: mine ? "primary.main" : "action.hover",
                        color: mine ? "primary.contrastText" : "text.primary",
                      }}>{e.payload.text}</Box>
                      <Box component="span" sx={{ flexShrink: 0, fontSize: "0.75rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
                        {fmtTime(e.created_at)}
                      </Box>
                    </Box>
                  </Box>
                );
              })}
            </Box>
            <Stack direction="row" gap={1}>
              <TextField
                size="small" fullWidth value={draft} placeholder="메시지 입력"
                inputProps={{ maxLength: 500, "aria-label": "메시지 입력" }}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); sendChat(); } }}
              />
              {/* 입력창이 fullWidth라 버튼이 눌려 '보내기'가 두 줄('보내'/'기')로 깨졌다 —
                  좁은 레일에서는 버튼이 먼저 양보하지 않게 못 박는다. */}
              <Button variant="primary" onClick={sendChat} disabled={chat.isPending}
                sx={{ flexShrink: 0, whiteSpace: "nowrap" }}>보내기</Button>
            </Stack>
          </Paper>
        </Box>
      </Box>
    </div>
  );
}
