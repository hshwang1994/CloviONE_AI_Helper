import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { draw } from "./constants.js";
import { StageHint } from "./StageShared.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../../ui/theme.js";

/* GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로 옮겼다. */
/* 사다리(아미다쿠지) 시각화. 서버가 확정한 세로줄·가로줄·도착지를 정직하게 그리고,
 * 위쪽 이름을 누르면 그 사람의 경로를 따라 내려가는 선을 강조한다. 좌표는 열을 균등 분할한
 * 중심(그리드 1fr 칩과 정렬)으로 잡는다. 선은 non-scaling-stroke로 늘려도 굵기 유지. */
export function LadderBoard({ result, highlightUserId }) {
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
    font: "inherit", fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, minWidth: 0,
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
          <Box component="b" sx={{ color: "primary.dark" }}>{outcomes[selPath.end]}</Box>
        </Typography>
      ) : (
        <StageHint>이름을 누르면 사다리 경로가 보입니다.</StageHint>
      )}
    </Box>
  );
}
