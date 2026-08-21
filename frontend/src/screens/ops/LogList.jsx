import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { KO_WORD_BREAK } from "../../ui/theme.js";

// 이력 목록(최근 작업 오류·최근 주요 변경)의 한 줄 — 시각 / 내용 / 대상 3열, 좁으면 한 열로 접힌다.
export function LogRow({ when, what, children }) {
  return (
    <Box component="li"
      sx={{
        display: "grid", alignItems: "baseline", gap: { xs: 0.25, sm: 1.5 },
        gridTemplateColumns: { xs: "1fr", sm: "12rem minmax(0,1fr) auto" },
      }}>
      <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>{when}</Typography>
      <Typography variant="body2" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>{what}</Typography>
      {children}
    </Box>
  );
}
export function LogList({ children }) {
  return <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>{children}</Box>;
}
