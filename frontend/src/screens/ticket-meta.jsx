import React from "react";
import Stack from "@mui/material/Stack";

import { Badge } from "../ui/kit.jsx";
import { priorityKo, priorityKind } from "../lib/priority.js";
import { TicketSignals } from "../ui/TicketSignals.jsx";
import { PersonLine } from "../ui/UserAvatar.jsx";
import { DateCell } from "../ui/cells.jsx";

/* 티켓의 **속성 줄** — 상세 화면(`Ticket.jsx`)과 미리보기(`TicketPeek.jsx`)가 같은 표를 본다
 * (D-483). 두 곳이 각자 목록을 적으면 한쪽만 새 칸을 얻는 날이 온다.
 *
 * 번호가 없으면 **없다고 말한다.** 예전 폴백은 문자열 `"티켓"` 이었는데, 그 값이 「티켓 번호」
 * 라벨 아래 들어가면 화면이 「티켓 번호: 티켓」이라고 적는다 — 값을 모른다는 사실이 값처럼
 * 읽힌다. `null` 을 주면 `MetaBar` 가 `-` 를 그린다(빈 값의 공통 표현). */
export function ticketId(t) { return (t && t.key) || null; }

/** `MetaBar` 가 받는 항목 배열. `signals` 는 `useTicketSignals()` 가 준 판정이다.
 *
 * 칸마다 `type` 이 붙는다 (C3) — 폭을 여기서 숫자로 적지 않는다. 이름·제목형만 남는 폭을
 * 가져가고 상태·수치·날짜는 자기 내용 폭만 쓴다.
 *
 * `rank` 는 폭이 아니라 **무게**다 (R-90). 티켓을 열었을 때 먼저 판단하는 값은 「지금 어떤
 * 상태이고 · 누가 · 언제까지 · 얼마나 급한가」다 — 그 다섯이 위 줄에 선다. 티켓 번호·난이도·
 * 예상/실제 WD 는 **찾을 때만 읽는** 값이라 아래 압축 띠로 내린다. */
export function ticketMetaItems(t, signals) {
  const ticket = t || {};
  const marks = Array.isArray(signals) ? signals : [];
  return [
    ticket.status ? { key: "status", label: "상태", type: "status", rank: "primary", value: <Badge value={ticket.status} /> } : null,
    /* 신호는 상태와 **다른 칸**이다 (D-349). 같은 칸에 넣으면 「진행 중」과 「차단됨」이
       한 낱말처럼 읽히고, 「지금 어떤 상태인가」에 답이 둘이 된다. 켜진 신호가 하나도
       없으면 이 칸 자체를 안 만든다 — 목록의 대부분이 그 상태다. */
    marks.length
      ? { key: "signals", label: "신호", type: "status", rank: "primary", value: <TicketSignals signals={marks} variant="pill" /> }
      : null,
    ticket.priority ? { key: "priority", label: "우선순위", type: "status", rank: "primary", value: <Badge value={priorityKo(ticket.priority)} kind={priorityKind(ticket.priority)} /> } : null,
    ticket.project ? { key: "project", label: "프로젝트", type: "name", rank: "primary", value: ticket.project } : null,
    /* 담당자는 얼굴과 이름으로. `assignee_people` 은 `assignee_ids` 한 번만 훑어 만든,
       이름·user_id 가 어긋나지 않는 목록이다(`app/tickets/service.py::ticket_view`). */
    (ticket.assignee_people || []).length ? {
      key: "assignee", label: "담당자", type: "name", rank: "primary",
      value: (
        <Stack direction="row" gap={1.25} sx={{ flexWrap: "wrap", alignItems: "center" }}>
          {ticket.assignee_people.map((p) => (
            <PersonLine key={p.user_id || p.name} person={p} name={p.name || p.display_name} size="sm" />
          ))}
        </Stack>
      ),
    } : null,
    ticket.due ? { key: "due", label: "마감", type: "date", rank: "primary", value: ticket.due } : null,
    { key: "tid", label: "티켓 번호", type: "identifier", value: ticketId(ticket) },
    ticket.difficulty ? { key: "difficulty", label: "난이도", type: "enum", value: ticket.difficulty } : null,
    ticket.est_wd != null ? { key: "est", label: "예상 WD", type: "number", value: ticket.est_wd } : null,
    ticket.act_wd != null ? { key: "act", label: "실제 WD", type: "number", value: ticket.act_wd } : null,
    ticket.created_at ? { key: "created_at", label: "생성일", type: "date", value: <DateCell value={ticket.created_at} /> } : null,
  ].filter(Boolean);
}
