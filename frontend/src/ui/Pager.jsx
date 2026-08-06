import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Button } from "./kit.jsx";

/* 서버 페이지네이션 목록의 페이지 이동 줄.
 *
 * 문서 목록 안에만 있던 것을 올렸다. 티켓 목록도 서버가 페이지를 자르기 시작했고(기본 20건),
 * 그 순간부터 페이저가 없는 화면은 **21번째 티켓이 있다는 사실 자체를 감춘다** — 사용자는
 * 목록이 다 보인다고 믿는다. 같은 부품을 쓰면 두 화면의 '총 N건' 문구도 갈라지지 않는다.
 *
 * 페이지가 하나뿐이면 아무것도 안 그린다. 누를 수 없는 이전·다음만 남는 줄은 자리만 먹는다. */
export function Pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil((total || 0) / (pageSize || 20)));
  if (pages <= 1) return null;
  return (
    <Box component="nav" aria-label="페이지 이동"
      sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, pt: 2, mt: 1, borderTop: 1, borderColor: "divider" }}>
      <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>이전</Button>
      <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ minWidth: "8rem", textAlign: "center" }}>
        {page} / {pages}{total != null ? `, 총 ${total}건` : ""}
      </Typography>
      <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>다음</Button>
    </Box>
  );
}
