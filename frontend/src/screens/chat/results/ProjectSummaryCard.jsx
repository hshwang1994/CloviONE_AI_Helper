import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Button, Surface } from "../../../ui/kit.jsx";
import { ProgressBar } from "../../../ui/charts/ProgressBar.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../../ui/theme.js";
import { fmtDateTime, fmtListStamp } from "../../../lib/format.js";
import { safeSourceRoute } from "../../chat-helpers.js";

/* 프로젝트 현황 카드 — `project_activity` · `get_project_summary` 를 도우미가 보여 주기로 했을 때(결과 블록 `project_summary`).
 * 진행률 · 기간 · 건강 · 상태별 티켓 수 · 열림 · 지연 · 막힘 · 최근 끝낸 일 셋 · 연결 문서를 서버가 센 값 그대로 그린다(모델이 옮겨
 * 적은 수가 아니다). 연결 문서는 답이 「표시했다」고 말하는 그 목록이다(랩 2026-10-15 — 카드에 없는데 표시했다고 말했다). 도구가 싣지 않은 칸은 그리지 않는다 — `get_project_summary` 에는 티켓 수가 없다(빈 칸에 「-」 셋을 세우지 않는다).
 * 숫자는 고정폭 숫자다(RULES §5). */

const STATUS_ORDER = ["계획", "진행", "검증", "보류", "완료", "취소"];

/** 카드 안의 짧은 목록 — 머리(「N건 중 M건」) · 줄마다 앞 글(키) · 제목 링크 · 오른쪽 날짜. 끝낸 일과 연결 문서가 같이 쓴다. */
function CardRows({ heading, total, rows, lead, stamp }) {
  if (!rows.length) return null;
  return (
    <Box sx={{ display: "grid", gap: 0.5 }}>
      <Typography component="h5" sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold, color: "text.secondary" }}>
        {heading}{total > rows.length ? ` (${total}건 중 ${rows.length}건)` : ""}
      </Typography>
      <Box component="ul" role="list" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.25 }}>
        {rows.map((row, i) => {
          const href = safeSourceRoute(row.route);
          const at = stamp(row);
          const front = lead ? lead(row) : null;
          return (
            <Box key={i} component="li" sx={{ display: "flex", gap: 1, alignItems: "baseline", fontSize: FONT_SIZE.bodySm, minWidth: 0 }}>
              {front ? <Box component="span" sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>{front}</Box> : null}
              {href ? <Box component="a" href={"#" + href} sx={{ color: "text.primary", minWidth: 0, ...KO_WORD_BREAK, "&:hover": { color: "primary.main" } }}>{row.title}</Box>
                : <Box component="span" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>{row.title}</Box>}
              {at ? (
                <Box component="time" dateTime={at} title={fmtDateTime(at)}
                  sx={{ ml: "auto", flexShrink: 0, fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
                  {fmtListStamp(at)}
                </Box>
              ) : null}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

function Figure({ label, value, tone }) {
  return (
    <Box sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
      <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{label}</Typography>
      <Typography component="span"
        sx={{ fontSize: FONT_SIZE.cardTitle, fontWeight: FONT_WEIGHT.bold, fontVariantNumeric: "tabular-nums",
              color: tone === "warn" && value ? "warning.strong" : "text.primary" }}>
        {value == null ? "-" : value}
      </Typography>
    </Box>
  );
}

export function ProjectSummaryCard({ project, compact = false }) {
  const route = safeSourceRoute(project.route);
  const percent = project.progress && typeof project.progress.percent === "number" ? project.progress.percent : null;
  const tickets = project.tickets || {};
  const counts = tickets.status_counts || {};
  const statusLine = STATUS_ORDER.filter((s) => counts[s]).map((s) => `${s} ${counts[s]}`)
    .concat(Object.keys(counts).filter((s) => !STATUS_ORDER.includes(s) && counts[s]).map((s) => `${s} ${counts[s]}`));
  const health = project.health || {};
  const done = Array.isArray(project.recent_completed) ? project.recent_completed.slice(0, 3) : [];
  const documents = project.documents && Array.isArray(project.documents.items) ? project.documents : null;
  const docRows = documents ? documents.items : [];
  const figures = [
    { key: "health", label: "건강도", value: health.score },
    { key: "open", label: "열린 티켓", value: tickets.open },
    { key: "overdue", label: "마감 지남", value: tickets.overdue_open, tone: "warn" },
    { key: "blocked", label: "막힘", value: tickets.blocked, tone: "warn" },
  ].filter((f) => f.value != null);
  const period = project.starts_on || project.ends_on ? `${project.starts_on || ""} ~ ${project.ends_on || ""}` : null;
  return (
    <Surface tone="inset" component="section" aria-label={`${project.name} 프로젝트 현황`} data-result-card="project"
      sx={{ p: compact ? 1.25 : 1.75, display: "grid", gap: 1.25, minWidth: 0 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
        <Typography component="h4" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold, ...KO_WORD_BREAK }}>{project.name}</Typography>
        {project.code ? <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{project.code}</Typography> : null}
        {project.status ? <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{project.status}</Typography> : null}
        <Box sx={{ flex: 1 }} />
        {route ? <Button size="sm" variant="ghost" href={"#" + route}>프로젝트 열기</Button> : null}
      </Box>
      {percent != null ? (
        <Box sx={{ display: "grid", gap: 0.5 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
            <span>진행률</span>
            <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, color: "text.primary", fontVariantNumeric: "tabular-nums" }}>
              {Math.round(percent * 10) / 10}%
              {project.progress && project.progress.counted_tasks ? ` (${project.progress.done_tasks}/${project.progress.counted_tasks})` : ""}
            </Box>
          </Box>
          <ProgressBar percent={percent} height={6} />
        </Box>
      ) : null}
      {figures.length ? (
        <Box sx={{ display: "grid", gridTemplateColumns: compact ? "repeat(2, minmax(0,1fr))" : "repeat(4, minmax(0,1fr))", gap: 1 }}>
          {figures.map((f) => <Figure key={f.key} label={f.label} value={f.value} tone={f.tone} />)}
        </Box>
      ) : null}
      {period ? (
        <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
          기간 {period}
        </Typography>
      ) : null}
      {statusLine.length ? (
        <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
          상태별 티켓 {statusLine.join(", ")}
        </Typography>
      ) : null}
      {health.reasons && health.reasons.length ? (
        <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
          건강도 근거: {health.reasons.join(", ")}
        </Typography>
      ) : null}
      <CardRows heading="최근 끝낸 일" total={project.recent_completed_total || 0} rows={done}
        lead={(t) => t.key} stamp={(t) => t.completed_at} />
      <CardRows heading="연결 문서" total={(documents && documents.total) || 0} rows={docRows}
        stamp={(d) => d.updated_at} />
    </Surface>
  );
}
