import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { Card, DotLabel } from "./kit.jsx";
import { TicketSignals } from "./TicketSignals.jsx";
import { PersonLine } from "./UserAvatar.jsx";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "./theme.js";

/* 티켓의 **얼굴**. 칸반 카드 · 논의 줄 · 후보 담당자가 같은 정보를 같은 순서로 본다.
 *
 * 줄은 넷이다. 이름 · 제목 · 프로젝트 · 마감·담당. 여섯째를 더하고 싶어질 때마다 그 정보가
 * **이 자리에서 결정에 쓰이는가**를 먼저 묻는다 — 아니면 상세로 간다.
 *
 * 제목은 두 줄에서 접힌다. `overflow-wrap: anywhere` 로 한글을 글자 단위로 자르지 않는다.
 *
 * ## 칸반 카드의 어휘는 하나다 (핸드오프 D-14 · D-15 · D-18 · README §8)
 *
 * 우선순위와 신호는 **점 + 낱말**이다. 예전에는 신호가 아이콘만이고 우선순위 「긴급」만 면 있는
 * 배지라 한 카드 안에서 어휘가 셋으로 갈렸다. 여백은 12/14, 줄 사이 8, 마감 · WD · 담당자가 서는
 * 발은 위 1px 실선으로 갈린다. 상단 띠 · 색 테두리 · 면 배지는 없다. 이 부품이 서는 자리
 * (작업 보드 · 스프린트 회의)는 개별 리디자인 제외 화면이라 **정보와 순서는 그대로**다 —
 * 바뀐 것은 부품의 얼굴뿐이다. */

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

  const priorityTone = card.priority ? priorityKind(card.priority) : null;
  const head = (
    <Stack direction="row" alignItems="center" sx={{ minWidth: 0, columnGap: 1, rowGap: 0.25, flexWrap: "wrap" }}>
      <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0, fontWeight: FONT_WEIGHT.medium }}>
        {cardKey(card)}
      </Typography>
      {card.priority ? (
        <DotLabel
          label={priorityKo(card.priority)}
          tone={priorityTone === "neutral" ? "neutral" : priorityTone}
          strong={priorityTone === "danger"}
          sx={{ fontSize: FONT_SIZE.caption }}
        />
      ) : null}
      <TicketSignals signals={signals} sx={{ minWidth: 0 }} />
      {actions ? <Box sx={{ flexShrink: 0, marginInlineStart: "auto" }}>{actions}</Box> : null}
    </Stack>
  );
  const title = (
    <Typography
      sx={{
        ...KO_WORD_BREAK,
        display: "-webkit-box",
        WebkitLineClamp: compact ? 1 : 2,
        WebkitBoxOrient: "vertical",
        overflow: "hidden",
        fontSize: compact ? FONT_SIZE.bodySm : FONT_SIZE.body,
        fontWeight: FONT_WEIGHT.semibold,
      }}
    >
      {card.title || "제목 없음"}
    </Typography>
  );
  const project = showProject && card.project ? (
    <Typography variant="caption" color="text.secondary" sx={{ ...KO_WORD_BREAK }}>
      {card.project}
    </Typography>
  ) : null;
  const due = dueLine ? (
    <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
      {dueLine}
    </Typography>
  ) : null;
  const people = <TicketPeople card={card} size={compact ? "inline" : "sm"} />;

  if (compact) {
    return (
      <Box
        sx={{ display: "flex", flexDirection: "column", gap: 0.375, minWidth: 0, ...sx }}
        onClick={onClick ? () => onClick(card) : undefined}
      >
        {head}{title}{project}{due}{people}
      </Box>
    );
  }

  return (
    <Card
      data-card-kind="ticket"
      sx={{
        py: 1.5, px: 1.75, display: "flex", flexDirection: "column", gap: 1,
        cursor: onClick ? "pointer" : "default",
        transition: (t) => `border-color ${t.motionTokens.fast} ${t.motionTokens.ease}, box-shadow ${t.motionTokens.fast} ${t.motionTokens.ease}`,
        "&:hover": (t) => ({ borderColor: t.palette.dividerStrong, boxShadow: t.shadowTokens.overlay }),
        ...sx,
      }}
      onClick={onClick ? () => onClick(card) : undefined}
    >
      {head}
      {title}
      {project}
      {/* 발 — 마감 · WD · 담당자. 위 1px 실선이 「이 카드가 무엇인가」와 「언제 · 누가」를 가른다. */}
      <Box sx={{ display: "grid", rowGap: 0.5, pt: 1, borderTop: 1, borderColor: "rule", minWidth: 0 }}>
        {due}
        {people}
      </Box>
    </Card>
  );
}
