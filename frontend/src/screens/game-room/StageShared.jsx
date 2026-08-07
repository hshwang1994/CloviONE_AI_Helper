import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { MascotPose } from "../../ui/Mascot.jsx";
import { MISC } from "../../lib/assets.js";
import { pop, pulse } from "./constants.js";

/* 무대 공용 프레젠테이션 컴포넌트(카운트다운/안내문/승자 이름표/결과 무대) —
 * GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로 옮겼다. */

// 카운트다운 배지. 남은 시간이 적으면 경고색. 무제한(deadline 없음)이면 아무것도 안 그린다.
export function Countdown({ remaining }) {
  if (remaining == null) return null;
  const urgent = remaining <= 5;
  return (
    <Box
      aria-live="polite"
      sx={{
        display: "flex", alignItems: "baseline", gap: 0.5, px: 1.5, py: 0.25, borderRadius: "999px",
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
export function StageHint({ children }) {
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
export function WinnerName({ children }) {
  return (
    <Box component="span" sx={{
      px: 2, py: 0.75, borderRadius: "999px", bgcolor: "primary.main", color: "primary.contrastText",
      fontSize: "1.0625rem", fontWeight: 750, animation: `${pop} .5s cubic-bezier(.34,1.56,.64,1) both`,
    }}>
      {children}
    </Box>
  );
}

/* 결과 무대 — 축하 일러스트 + 마스코트 + 결과 본문.
 * 자산(misc/celebrate-winner.png)과 마스코트 love 포즈는 처음부터 있었는데 어디에도 연결돼
 * 있지 않았다. 승자가 확정된 순간에만 띄운다(무승부·팀 나누기처럼 승자가 없는 결과는 mood="calm"). */
export function ResultStage({ mood = "win", label, children }) {
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
