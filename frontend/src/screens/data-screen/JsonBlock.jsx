import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { FONT_SIZE } from "../../ui/theme.js";

/* 상세 패널의 원문 블록과 키/값 줄 — 예전에는 <JsonBlock> 과
 * .c-kv/.c-kv-k/.c-kv-v 를 열다섯 곳에 손으로 흩어 두었다. 규칙이 CSS 파일에만 있어서
 * 새 상세 필드를 만들 때마다 클래스 이름을 외워 붙여야 했고, 한 곳만 빠뜨려도 조용히
 * 스타일이 없는 채로 떴다. 컴포넌트 두 개로 모아 그 규칙을 코드에 둔다. */
export function JsonBlock({ children }) {
  return (
    <Box component="pre" sx={{
      m: 0, p: 1.5, borderRadius: 1.5, border: 1, borderColor: "divider",
      bgcolor: "background.default", overflowX: "auto", whiteSpace: "pre-wrap",
      overflowWrap: "anywhere", fontSize: FONT_SIZE.bodySm, lineHeight: 1.6,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    }}>{children}</Box>
  );
}

export function KeyValueRow({ label, children }) {
  return (
    <Box sx={{
      display: "grid", gridTemplateColumns: { xs: "1fr", sm: "10rem minmax(0,1fr)" },
      gap: { xs: 0.25, sm: 1.5 }, py: 0.75, borderBottom: 1, borderColor: "divider", minWidth: 0,
    }}>
      <Typography variant="body2" color="text.secondary" sx={{ wordBreak: "break-all" }}>{label}</Typography>
      <Box sx={{ minWidth: 0, overflowWrap: "anywhere", fontSize: FONT_SIZE.body }}>{children}</Box>
    </Box>
  );
}
