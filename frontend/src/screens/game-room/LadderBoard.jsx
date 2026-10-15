import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { draw } from "./constants.js";
import { StageHint } from "./StageShared.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "../../ui/theme.js";
import { personOf } from "./people.js";

/* 사다리(아미다쿠지) 시각화. 서버가 확정한 세로줄·가로줄·도착지를 정직하게 그리고,
 * 위쪽 이름을 누르면 그 사람의 경로를 따라 내려가는 선을 강조한다. 좌표는 열을 균등 분할한
 * 중심(그리드 1fr 칩과 정렬)으로 잡는다. 선은 non-scaling-stroke로 늘려도 굵기 유지.
 *
 * 판으로 설 때(`height` 를 주면) 사다리가 판 높이를 채운다 — 판 아래가 비지 않는다. 열 머리는 얼굴 + 이름이고(D-577), 처음에는
 * 내 경로가 강조돼 있다. 결과 대화 상자의 「사다리」 상세는 높이를 주지 않은 같은 부품이다. */
export function LadderBoard({ result, highlightUserId, people, height }) {
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
  const gridSx = { display: "grid", gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`, gap: 0.5 };
  const chipSx = (on, outcome) => ({
    display: "flex", flexDirection: outcome ? "row" : "column", alignItems: "center", justifyContent: "center", gap: 0.5,
    textAlign: "center", px: 0.5, py: outcome ? 0.75 : 0.625, borderRadius: `${RADIUS.sm}px`,
    border: 1, borderColor: on ? "primary.main" : "divider",
    bgcolor: on ? "primary.main" : (outcome ? "background.inset" : "background.paper"),
    color: on ? "primary.contrastText" : "text.primary",
    font: "inherit", fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, minWidth: 0,
    cursor: outcome ? "default" : "pointer",
    "&:hover": outcome ? undefined : { borderColor: "primary.main" },
  });
  const nameSx = { maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };
  const fill = height != null;

  return (
    <Box data-ladder-board="" sx={{ display: "grid", gap: 1, width: "100%" }}>
      <Box sx={gridSx}>
        {cols.map((c, i) => (
          <Box component="button" type="button" key={c.user_id}
            aria-pressed={sel === i}
            sx={chipSx(sel === i, false)}
            onClick={() => setSel(sel === i ? null : i)}>
            <UserAvatar person={personOf(people, c.user_id) || c} name={c.name} size="sm" />
            <Box component="span" title={c.name} sx={nameSx}>{c.name}</Box>
          </Box>
        ))}
      </Box>
      <Box
        component="svg" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="사다리"
        sx={(t) => ({
          width: "100%", height: fill ? `${Math.max(160, Math.round(height))}px` : { xs: "14rem", md: "18rem", xxl: "22rem" }, display: "block",
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
          <Box component="span" key={i} title={o} sx={chipSx(!!(selPath && selPath.end === i), true)}>
            <Box component="span" sx={nameSx}>{o}</Box>
          </Box>
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
