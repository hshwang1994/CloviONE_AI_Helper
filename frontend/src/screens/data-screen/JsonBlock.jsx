import React from "react";
import Box from "@mui/material/Box";
import { FONT_SIZE } from "../../ui/theme.js";

/* 상세 패널의 원문 블록 — 예전에는 <JsonBlock> 과 .c-kv/.c-kv-k/.c-kv-v 를 열다섯 곳에
 * 손으로 흩어 두었다. 규칙이 CSS 파일에만 있어서 새 상세 필드를 만들 때마다 클래스 이름을
 * 외워 붙여야 했고, 한 곳만 빠뜨려도 조용히 스타일이 없는 채로 떴다.
 * 키/값 줄은 여기 있던 `KeyValueRow` 가 아니라 `kit.jsx::DetailRow` 다(D-457) — 같은 줄이
 * 네 벌이었고, 사용자 화면(`/profile`)과 관리자 상세가 같은 부품을 쓴다. */
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
