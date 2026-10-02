import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Button, Card, HeadRow } from "../../ui/kit.jsx";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, ICON, LINE_HEIGHT, RADIUS, KO_WORD_BREAK } from "../../ui/theme.js";
import { StatusIcon } from "./ChecklistRow.jsx";

/* 초기 설정 요약 띠 (D-534).
 *
 * 카드 규율의 「요약」 자리 하나다(F7) — 아이콘, 지금 상태 한 문장(h2), 필수 진행과 다음 할 일 한 문장, 비율 막대, 그리고 이 화면의
 * **유일한 주 동작**(지금 할 항목을 고치는 화면으로 간다). 두 문장은 서버가 만든다(`headline` · `subline`) — 화면이 수를 다시 세어
 * 다른 문장을 만들면 배너 · 진단과 말이 갈린다.
 *
 * 선택 항목에 할 일이나 문제가 있어도 필수가 끝났으면 「기본 설정이 끝났습니다」이고 아이콘은 완료다. 그 사실은 둘째 문장이 말한다.
 */
export function bandStatus(data) {
  const required = ((data && data.items) || []).filter((i) => i.required !== false);
  if (required.some((i) => i.status === "problem")) return "problem";
  if (required.some((i) => i.status !== "done" && i.status !== "skipped")) return "todo";
  return "done";
}

export function SetupSummary({ data, primary }) {
  const total = Number(data.required_total) || 0;
  const done = Math.min(Number(data.required_done) || 0, total);
  const pct = total ? Math.round((done / total) * 100) : 0;
  const status = bandStatus(data);
  return (
    <Card component="section" aria-labelledby="setup-headline" data-testid="setup-summary" data-band-status={status}>
      <HeadRow
        lead={<StatusIcon status={status} size="hero" />}
        leadPx={ICON.hero}
        lineHeightPx={22}
        actionPx={CONTROL.control}
        action={primary || null}
      >
        <Box sx={{ display: "grid", rowGap: 0.5, minWidth: 0 }}>
          <Typography
            id="setup-headline"
            component="h2"
            sx={{ m: 0, fontSize: FONT_SIZE.cardTitle, lineHeight: LINE_HEIGHT.title, fontWeight: FONT_WEIGHT.bold, ...KO_WORD_BREAK }}
          >
            {data.headline}
          </Typography>
          {data.subline ? (
            <Typography sx={{ m: 0, fontSize: FONT_SIZE.bodySm, lineHeight: LINE_HEIGHT.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}>
              {data.subline}
            </Typography>
          ) : null}
          {total ? (
            <Box
              role="progressbar"
              aria-label="필수 설정 진행"
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={done}
              aria-valuetext={`필수 ${total}개 중 ${done}개`}
              sx={{ mt: 0.75, width: "100%", maxWidth: "24rem", height: "0.375rem", borderRadius: `${RADIUS.full}px`, bgcolor: "rule", overflow: "hidden" }}
            >
              <Box
                data-progress-fill=""
                sx={{ width: `${pct}%`, height: "100%", borderRadius: "inherit", bgcolor: status === "done" ? "success.main" : "primary.main" }}
              />
            </Box>
          ) : null}
        </Box>
      </HeadRow>
    </Card>
  );
}

export default SetupSummary;
