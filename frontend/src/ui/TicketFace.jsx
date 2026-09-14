import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { Badge, Card } from "./kit.jsx";
import { TicketSignals } from "./TicketSignals.jsx";
import { PersonLine } from "./UserAvatar.jsx";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { FONT_WEIGHT, KO_WORD_BREAK } from "./theme.js";

/* 티켓의 **얼굴**. 칸반 카드 · 논의 줄 · 후보 담당자가 같은 정보를 같은 순서로 본다.
 *
 * 줄은 넷이다. 이름 · 제목 · 프로젝트 · 마감·담당. 여섯째를 더하고 싶어질 때마다 그 정보가
 * **이 자리에서 결정에 쓰이는가**를 먼저 묻는다 — 아니면 상세로 간다.
 *
 * 제목은 두 줄에서 접힌다. `overflow-wrap: anywhere` 로 한글을 글자 단위로 자르지 않는다. */

function cardKey(card) {
  return card.key || card.ticket_id || "이름 없음";
}

/** 담당자 한 줄. 얼굴과 이름을 같이 내고, 나머지는 숫자로 접는다. */
export function TicketPeople({ card, size = "inline" }) {
  const people = Array.isArray(card.assignees) ? card.assignees : [];
  if (!people.length) {
    const unresolved = card.assignee_tokens > 0;
    return (
      <Typography variant="caption" color="text.secondary">
        {unresolved ? "담당자를 읽지 못했습니다." : "담당자 없음"}
      </Typography>
    );
  }
  const first = people[0];
  const rest = people.length - 1;
  return (
    <PersonLine
      person={first}
      name={first.display_name}
      size={size}
      suffix={
        rest > 0 ? (
          <Typography component="span" variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
            {`외 ${rest}명`}
          </Typography>
        ) : null
      }
    />
  );
}

/* `actions` — 머리줄 오른쪽 끝의 **카드 작업** 자리(빠른 수정 · 현재 회차에서 빼기).
 * 카드 전체가 누르면 미리보기이고 끌면 이동이라, 작업 단추는 그 둘을 방해하지 않는
 * 감싸개(`ui/DragDrop.jsx::DragItemActions`)에 넣어서 넘긴다 — 여기서 그 감싸개를 직접
 * 그리지 않는 이유는 이 부품이 끌기 부품을 모르게 두려는 것이다(회의 줄에서도 쓴다). */
export function TicketFace({ card, signals, showProject = true, compact = false, onClick, sx, actions }) {
  const dueLine = [
    card.due ? `마감 ${card.due}` : null,
    card.est_wd != null ? `예상 ${card.est_wd}WD` : null,
    card.direction === "added" ? "들어옴" : card.direction === "removed" ? "빠짐" : null,
  ].filter(Boolean).join("  ");

  const body = (
    <>
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0, fontWeight: FONT_WEIGHT.medium }}>
          {cardKey(card)}
        </Typography>
        {card.priority ? (
          <Badge value={priorityKo(card.priority)} kind={priorityKind(card.priority)} />
        ) : null}
        <TicketSignals signals={signals} variant="mark" sx={{ marginInlineStart: "auto" }} />
        {actions ? <Box sx={{ flexShrink: 0, ml: 0.5 }}>{actions}</Box> : null}
      </Stack>
      <Typography
        variant="body2"
        sx={{
          ...KO_WORD_BREAK,
          display: "-webkit-box",
          WebkitLineClamp: compact ? 1 : 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          fontWeight: FONT_WEIGHT.semibold,
        }}
      >
        {card.title || "제목 없음"}
      </Typography>
      {showProject && card.project ? (
        <Typography variant="caption" color="text.secondary" sx={{ ...KO_WORD_BREAK }}>
          {card.project}
        </Typography>
      ) : null}
      {dueLine ? (
        <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
          {dueLine}
        </Typography>
      ) : null}
      <TicketPeople card={card} size={compact ? "inline" : "sm"} />
    </>
  );

  if (compact) {
    return (
      <Box
        sx={{ display: "flex", flexDirection: "column", gap: 0.375, minWidth: 0, ...sx }}
        onClick={onClick ? () => onClick(card) : undefined}
      >
        {body}
      </Box>
    );
  }

  return (
    <Card
      sx={{ p: 1.25, display: "flex", flexDirection: "column", gap: 0.5, cursor: onClick ? "pointer" : "default", ...sx }}
      onClick={onClick ? () => onClick(card) : undefined}
    >
      {body}
    </Card>
  );
}
