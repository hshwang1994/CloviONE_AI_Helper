import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, NUMERIC, RADIUS, remPx } from "../../ui/theme.js";
import { pulse } from "./constants.js";

/* 판 공용 프레젠테이션 — 카운트다운 · 안내 한 줄.
 *
 * 결과 무대(`ResultStage`) · 승자 이름표(`WinnerName`)는 결과 대화 상자(`ResultDialog.jsx`, D-576)로 옮겨 가며 걷었다 — 결과의
 * 얼굴은 한 자리에서만 그린다. */

/* 카운트다운 — 툴바 한 줄에 서는 알약(22px). 남은 시간이 5초 이하면 위험색으로 맥박친다. 무제한(마감 없음)이면 그리지 않는다.
   예전에는 판 위 진행 띠에 28px 숫자로 섰다 — 그 띠가 툴바로 들어오며(G2) 줄 높이(34)를 넘지 않는 알약이 됐다. */
export function Countdown({ remaining }) {
  if (remaining == null) return null;
  const urgent = remaining <= 5;
  return (
    <Box
      component="span"
      aria-live="polite"
      data-countdown={urgent ? "urgent" : "normal"}
      sx={{
        display: "inline-flex", alignItems: "center", gap: 0.5, height: remPx(CONTROL.pill), px: 1,
        borderRadius: `${RADIUS.xs}px`, flexShrink: 0,
        bgcolor: (t) => alpha(urgent ? t.palette.error.main : t.palette.primary.main, 0.12),
        color: urgent ? "error.strong" : "primary.dark",
        fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold, ...NUMERIC,
        animation: urgent ? `${pulse} .8s ease-in-out infinite` : "none",
      }}
    >
      남은 시간 {remaining}초
    </Box>
  );
}

/* 판 안의 안내 한 줄(관전 중 · 다음 라운드 대기 등). 판 자체가 자리를 말하므로 점선 상자를 두르지 않는다 — 예전 점선 상자는 판이
   없던 시절 「여기가 결과 자리」를 대신 말하던 모양이다. */
export function StageHint({ children }) {
  return (
    <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", ...KO_WORD_BREAK }}>
      {children}
    </Typography>
  );
}
