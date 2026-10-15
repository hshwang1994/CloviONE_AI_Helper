import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import { alpha } from "@mui/material/styles";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, NUMERIC } from "../../ui/theme.js";
import { rise } from "./constants.js";

/* 순위표(퀴즈). 번호는 CSS 카운터로 — 마크업에 순번 텍스트를 넣지 않는다.
 * 줄마다 얼굴이 선다(D-577 — `person` 이 있으면). 우승한 줄(`win`)은 브랜드 테두리와 옅은 면이다. */
export function Scoreboard({ rows, maxWidth = "28rem" }) {
  return (
    <Box component="ol" sx={{
      listStyle: "none", m: 0, p: 0, counterReset: "rank", display: "grid", gap: 0.5,
      width: "100%", maxWidth,
    }}>
      {rows.map((s, i) => (
        <Paper component="li" key={s.key || i} variant="outlined" data-score-row={s.win ? "winner" : ""} sx={(t) => ({
          display: "flex", alignItems: "center", gap: 1.25, px: 1.5, py: 0.75,
          animation: `${rise} .38s ease both`,
          borderColor: s.win ? "primary.main" : "divider",
          bgcolor: s.win ? alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.2 : 0.08) : t.palette.background.paper,
          "&::before": {
            counterIncrement: "rank", content: "counter(rank)", flexShrink: 0, width: "1.5rem",
            color: "text.secondary", ...NUMERIC, fontSize: FONT_SIZE.bodySm,
          },
        })}>
          {s.person || s.user_id ? <UserAvatar person={s.person || { user_id: s.user_id, name: s.name }} name={s.name} size="sm" /> : null}
          <Box component="span" title={s.name} sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: s.win ? FONT_WEIGHT.bold : FONT_WEIGHT.regular }}>{s.name}</Box>
          <Box component="span" sx={{ flexShrink: 0, fontWeight: FONT_WEIGHT.bold, color: "primary.dark", ...NUMERIC }}>{s.value}</Box>
        </Paper>
      ))}
    </Box>
  );
}
