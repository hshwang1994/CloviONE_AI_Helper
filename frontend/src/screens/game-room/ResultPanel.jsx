import React from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { keyframes } from "@mui/system";
import { Badge, Button, useToast } from "../../ui/kit.jsx";
import { MascotPose } from "../../ui/Mascot.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../../ui/theme.js";
import { pop, rise } from "./constants.js";

/* 게임 결과 틀 하나 (D-563) — 머리 · 당첨자 자리 · 게임별 결과 자리 · 동작 줄.
 *
 * 틀(머리 · 발표 연출 · 당첨자 · 동작)은 공통이고, 당첨자 수 · 순위의 뜻 · 게임 고유 정보(`detail`)는 게임마다 다르다 —
 * 순위가 없는 추첨에 1 · 2 · 3등을 만들지 않는다(`ranked`). 승자가 없는 결과(팀 나누기 · 무승부)는 `mood="calm"` 이다.
 *
 * 발표 순서: 「게임 종료」 배지 → 짧은 발표 전환(`ANNOUNCE_MS`) → 당첨자 공개 → **그 순간** `onReveal(revealKey)` → 효과가
 * 끝나도 결과 유지. 발표 단위는 `revealKey`(방 id + 결과 번호)이고, 같은 열쇠에는 다시 돌지 않는다(폴링 · 리렌더 · 창 크기 ·
 * 테마 전환 · 상세 열고 닫기). `instant` 면 전환 없이 바로 결과다 — 이미 끝난 방에 늦게 들어왔거나 새로고침한 사람은 「발표」를
 * 본 것이 아니므로 축포도 없다(`onReveal` 을 부르지 않는다).
 *
 * 축포는 표현이다 — 결과 표시를 늦추지 않고, 축포가 실패해도 결과는 보인다(`onReveal` 안의 일이다). */

export const ANNOUNCE_MS = 800;

const blink = keyframes`
  0%, 80%, 100% { opacity: .2; }
  40% { opacity: 1; }
`;

export function useReveal(revealKey, { instant = false, onReveal } = {}) {
  const [phase, setPhase] = React.useState(() => (!revealKey ? "none" : instant ? "revealed" : "announcing"));
  const seenRef = React.useRef(instant ? revealKey : null);
  const onRevealRef = React.useRef(onReveal);
  onRevealRef.current = onReveal;
  React.useEffect(() => {
    if (!revealKey) { seenRef.current = null; setPhase("none"); return undefined; }
    if (seenRef.current === revealKey) return undefined; // 같은 결과 — 다시 돌지 않는다
    seenRef.current = revealKey;
    if (instant) { setPhase("revealed"); return undefined; }
    setPhase("announcing");
    const t = setTimeout(() => {
      setPhase("revealed");
      if (onRevealRef.current) {
        try { onRevealRef.current(revealKey); } catch (e) { /* 축포 실패는 결과를 막지 않는다 */ }
      }
    }, ANNOUNCE_MS);
    return () => clearTimeout(t);
  }, [revealKey, instant]);
  return phase;
}

function initialOf(name) {
  const s = String(name || "").trim();
  return s ? Array.from(s)[0] : "?";
}

/* 당첨자 얼굴 — 실제 사용자는 제품의 얼굴(`UserAvatar`), 자유 이름(구슬 레이스)은 구슬 색 점 + 머리글자. */
function WinnerFace({ w, size }) {
  if (w.user_id || w.person) {
    return <UserAvatar person={w.person || { user_id: w.user_id, name: w.name }} userId={w.user_id} name={w.name} size={size} />;
  }
  const px = size === "xl" ? "4.5rem" : "2.5rem";
  return (
    <Box aria-hidden="true" sx={{
      width: px, height: px, borderRadius: "50%", flexShrink: 0,
      bgcolor: w.color || "primary.main", color: "primary.contrastText",
      display: "grid", placeItems: "center", fontWeight: FONT_WEIGHT.bold,
      boxShadow: (t) => `inset 0 0 0 2px ${alpha(t.palette.common.white, 0.35)}`,
    }}>
      {initialOf(w.name)}
    </Box>
  );
}

const NAME_CLAMP = {
  ...KO_WORD_BREAK, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
  lineHeight: 1.2, maxWidth: "100%",
};

function RankBadge({ rank }) {
  const top = rank <= 3;
  return (
    <Box component="span" aria-label={`${rank}등`} sx={{
      flexShrink: 0, minWidth: "1.75rem", height: "1.75rem", px: 0.75, borderRadius: RADIUS.full,
      display: "inline-grid", placeItems: "center", fontVariantNumeric: "tabular-nums",
      fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold,
      bgcolor: top ? "primary.main" : "action.hover", color: top ? "primary.contrastText" : "text.secondary",
    }}>
      {rank}
    </Box>
  );
}

function WinnersBlock({ winners, ranked, fullscreen, label }) {
  if (!winners.length) return null;
  if (winners.length === 1) {
    const w = winners[0];
    return (
      <Box data-result-winners="single" sx={{ display: "grid", justifyItems: "center", gap: 1, textAlign: "center", animation: `${pop} .5s cubic-bezier(.34,1.56,.64,1) both` }}>
        <WinnerFace w={w} size="xl" />
        <Typography component="p" title={w.name} sx={{ ...NAME_CLAMP, fontSize: FONT_SIZE.statValue, fontWeight: FONT_WEIGHT.extrabold }}>
          {w.name}
        </Typography>
        {w.note ? <Typography variant="body2" color="text.secondary">{w.note}</Typography> : null}
        <Badge value={label} kind="info" emphasis="strong" />
      </Box>
    );
  }
  if (ranked) {
    return (
      <Box component="ol" data-result-winners="ranked" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
        {winners.map((w, i) => (
          <Paper component="li" key={w.id} variant="outlined" sx={{
            display: "flex", alignItems: "center", gap: 1.5, px: 1.5, py: 0.75, animation: `${rise} .38s ease both`,
            borderColor: i === 0 ? "primary.main" : "divider",
            bgcolor: (t) => (i === 0 ? alpha(t.palette.primary.main, 0.1) : t.palette.background.paper),
          }}>
            <RankBadge rank={w.rank || i + 1} />
            <WinnerFace w={w} size="lg" />
            <Typography component="span" title={w.name} sx={{ ...NAME_CLAMP, flex: 1, minWidth: 0, fontWeight: FONT_WEIGHT.bold, fontSize: i === 0 ? FONT_SIZE.pageTitle : FONT_SIZE.sectionTitle }}>
              {w.name}
            </Typography>
            {w.note ? <Typography variant="body2" color="text.secondary" sx={{ flexShrink: 0 }}>{w.note}</Typography> : null}
          </Paper>
        ))}
      </Box>
    );
  }
  /* 같은 무게의 당첨자 카드 격자 — 전부 보인다(일부만 보이는 구조 없음). 많으면 목록으로. */
  const asList = winners.length > 12;
  return (
    <Box component="ul" data-result-winners="grid" sx={{
      listStyle: "none", m: 0, p: 0, display: "grid", gap: 1,
      gridTemplateColumns: asList ? "1fr" : { xs: "repeat(2, minmax(0,1fr))", sm: `repeat(auto-fit, minmax(${fullscreen ? "12rem" : "9rem"}, 1fr))` },
    }}>
      {winners.map((w) => (
        <Paper component="li" key={w.id} variant="outlined" sx={{
          display: "flex", flexDirection: asList ? "row" : "column", alignItems: "center", gap: 1, p: 1.5, minWidth: 0,
          textAlign: asList ? "left" : "center", animation: `${rise} .38s ease both`,
          borderColor: "primary.light", bgcolor: (t) => alpha(t.palette.primary.main, 0.08),
        }}>
          <WinnerFace w={w} size="lg" />
          <Typography component="span" title={w.name} sx={{ ...NAME_CLAMP, fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle }}>
            {w.name}
          </Typography>
          {w.note ? <Typography variant="body2" color="text.secondary">{w.note}</Typography> : null}
        </Paper>
      ))}
    </Box>
  );
}

/**
 * props
 *  - game: 게임 이름(머리) · headline: 발표 제목 · lead: 한 문장 · note: 결과의 사실(예: 방장 화면 결과)
 *  - winners: [{ id, name, user_id?, person?, color?, rank?, note? }] · ranked: 순위가 있는 결과인가 · winnerLabel: 당첨자 표식(「당첨」 · 「우승」)
 *  - mood: "win" | "calm" · revealKey · instant · onReveal · detail(게임별 결과 노드) · detailLabel · detailDefaultOpen
 *  - copyText(결과 복사 글) · actions(동작 줄 노드) · overlay(게임판 위에 겹침) · fullscreen
 */
export function ResultPanel({
  game, headline, lead, note, winners = [], ranked = false, winnerLabel = "당첨", mood = "win",
  revealKey, instant = false, onReveal, detail, detailLabel = "전체 결과", detailDefaultOpen = false,
  copyText, actions, overlay = false, fullscreen = false, sx,
}) {
  const toast = useToast();
  const phase = useReveal(revealKey, { instant, onReveal });
  const [open, setOpen] = React.useState(!!detailDefaultOpen);
  const win = mood === "win" && winners.length > 0;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(copyText);
      toast && toast("결과를 복사했습니다.", "success");
    } catch (e) {
      toast && toast("복사하지 못했습니다. 글을 직접 선택해 복사하세요.", "error");
    }
  };
  return (
    <Paper
      variant="outlined"
      role="region"
      aria-label={`${game} 결과`}
      data-result-panel={phase}
      data-result-mood={mood}
      sx={(t) => ({
        p: overlay ? 2 : { xs: 2, md: 3 }, display: "grid", gap: overlay ? 1.25 : 2, alignContent: "start", minWidth: 0,
        borderColor: win ? "primary.light" : "divider",
        bgcolor: win ? alpha(t.palette.primary.main, overlay ? 0.1 : 0.06) : t.palette.background.paper,
        animation: `${rise} .38s ease both`,
        ...(overlay ? {
          position: "absolute", left: 0, right: 0, bottom: 0, zIndex: 2,
          maxHeight: open ? "100%" : "72%", overflowY: "auto",
          bgcolor: alpha(t.palette.background.paper, 0.94), backdropFilter: "blur(2px)",
          borderWidth: "1px 0 0 0", borderRadius: 0, boxShadow: t.shadows[8],
        } : null),
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
    >
      <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
        <Badge value="게임 종료" kind="ok" />
        <Typography variant="body2" color="text.secondary">{game}</Typography>
      </Stack>
      {phase === "announcing" ? (
        <Box data-result-phase="announcing" aria-live="polite" sx={{ display: "grid", justifyItems: "center", gap: 1, py: 2 }}>
          <MascotPose mode="success" place="gameCelebrate" decorative />
          <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle }}>
            결과를 발표합니다
            {[0, 1, 2].map((i) => (
              <Box key={i} component="span" aria-hidden="true" sx={{ display: "inline-block", animation: `${blink} 1.2s ${i * 0.2}s infinite` }}>.</Box>
            ))}
          </Typography>
        </Box>
      ) : (
        <>
          <Box sx={{ display: "grid", gap: 0.5, textAlign: fullscreen ? "center" : "left" }}>
            <Typography component="h2" sx={{ fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.extrabold, ...KO_WORD_BREAK }}>{headline}</Typography>
            {lead ? <Typography color="text.secondary" sx={KO_WORD_BREAK}>{lead}</Typography> : null}
            {note ? <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{note}</Typography> : null}
          </Box>
          {win ? (
            <Stack direction={{ xs: "column", md: winners.length === 1 ? "row" : "column" }} gap={2} alignItems="center" justifyContent="center">
              {winners.length === 1 ? <MascotPose mode="love" place="gameCelebrate" decorative /> : null}
              <Box sx={{ minWidth: 0, width: winners.length === 1 ? "auto" : "100%" }}>
                <WinnersBlock winners={winners} ranked={ranked} fullscreen={fullscreen} label={winnerLabel} />
              </Box>
            </Stack>
          ) : null}
          {detail ? (
            <Box data-result-detail={open ? "open" : "closed"}>
              <Collapse in={open}>
                <Box sx={{ pt: 0.5 }}>{detail}</Box>
              </Collapse>
            </Box>
          ) : null}
          {(detail || copyText || actions) ? (
            <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
              {detail ? (
                <Button size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
                  {open ? `${detailLabel} 접기` : `${detailLabel} 보기`}
                </Button>
              ) : null}
              {copyText ? <Button size="sm" onClick={copy}>결과 복사</Button> : null}
              {actions}
            </Stack>
          ) : null}
        </>
      )}
    </Paper>
  );
}
