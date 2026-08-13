import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import { rise } from "./constants.js";

/* 순위표(퀴즈). 번호는 CSS 카운터로 — 마크업에 순번 텍스트를 넣지 않는다.
 * GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로 옮겼다. */
export function Scoreboard({ rows }) {
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
          <Box component="span" sx={{ flexShrink: 0, fontWeight: 700, color: "primary.dark", fontVariantNumeric: "tabular-nums" }}>{s.value}</Box>
        </Paper>
      ))}
    </Box>
  );
}
