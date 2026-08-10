import React, { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Badge, Button } from "../../ui/kit.jsx";
import {
  fmtDue, peopleText, priorityKind, priorityKo, projectToneColor, safeNotion,
} from "../chat-helpers.js";
import { NotionLink, PlainUrl } from "./links.jsx";

// ── 결과 카드 ───────────────────────────────────────────────────────────────

/* 여기 있던 TONE_PALETTE 는 상태에 따라 카드의 왼쪽에 0.25rem 색 띠를 두르고 테두리·바탕까지
 * 물들이던 표다. 지웠다.
 *
 * 기준선(design/baseline/preview-standalone.html:216)의 카드는 상태와 무관하게 언제나
 *     .kanban-card { background: var(--surface); border: 1px solid var(--border); }
 * 이고, 상태를 색으로 말하는 자리는 칩(.chip.ok/.warn/.danger/.info) 하나뿐이다.
 * 기준선 전체에 상태를 뜻하는 border-left 는 없다. 사용자도 그 색 띠를 쓰지 말자고 했다.
 * 상태 정보 자체는 아래 <Badge value={t.status}> 가 그대로 전한다 — 지운 것은 색이지 정보가 아니다. */

function CardRow({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "minmax(4.5rem,auto) minmax(0,1fr)", columnGap: 1, alignItems: "center", justifyItems: "start", fontSize: "0.8125rem" }}>
      <Typography component="span" sx={{ fontSize: "0.8125rem", color: "text.secondary" }}>{label}</Typography>
      <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>{children}</Box>
    </Box>
  );
}

/* export 인 이유: 카드의 겉모습(테두리·바탕)이 기준선을 벗어나지 않는지 시험이 직접 본다
 * (chat-card-chrome.test.jsx). 화면 전체를 띄워서 보면 실패했을 때 원인이 카드인지
 * 스레드인지 알 수 없다. */
export function TicketCard({ t, index, onChoose, isTicket = true, sending }) {
  const [showAllProjects, setShowAllProjects] = useState(false);
  const url = t.url || t.notion_url || t.link;
  // 담당자, 정/부는 배열(이름 또는 {name})이 올 수 있다, peopleText로 어떤 모양이든 안전하게.
  // "미할당" 폴백은 진짜 티켓(단일 담당자 개념이 있는)에만 붙인다, 프로젝트/결과/일반 항목 카드는
  // 애초에 단일 담당자 개념이 없어 항상 '담당자: 미할당'을 보여주면 없는 데이터를 있는 것처럼 오도한다.
  const assigneeRaw = peopleText(t.assignees) || (typeof t.assignee === "string" ? t.assignee : "");
  const assignee = assigneeRaw || (isTicket ? "미할당" : "");
  const primary = peopleText(t.primary_names || t.primary);
  const secondary = peopleText(t.secondary_names || t.secondary);
  const projects = Array.isArray(t.project_names)
    ? t.project_names.filter(Boolean)
    : (typeof t.project === "string" && t.project ? [t.project] : []);
  const openTickets = typeof t.open_tickets === "number" ? t.open_tickets + "건" : "";
  const priority = typeof t.priority === "string" || typeof t.priority === "number" ? t.priority : "";
  const due = t.due_date || t.deadline;
  const title = t.title || t.name || t.subject || (isTicket ? "티켓" : "(제목 없음)");
  // 순번(N.)은 오직 '상세' 원탭이 실제로 동작하는(cardChoose가 살아 있는, 즉 마지막 어시스턴트
  // 메시지의) 카드에만 붙인다, 스크롤해 올라간 옛 카드까지 번호를 달면, 더는 안 눌리는 버튼을
  // 여전히 클릭 가능한 것처럼 훈련시킨 그 번호 라벨이 계속 남아 사용자를 오도한다.
  const prefix = typeof index === "number" && onChoose ? index + ". " : (t.number ? "#" + t.number + ", " : "");
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.75, display: "grid", gap: 0.5, minWidth: 0,
        borderRadius: 3,
        /* 네 변이 같은 중립 테두리다 — 상태는 아래 배지가 말한다(기준선 .kanban-card). */
        borderColor: "divider",
        bgcolor: "background.default",
        transition: "box-shadow .15s ease",
        "&:hover": { boxShadow: 1 },
      }}
    >
      <Typography sx={{ fontWeight: 750, fontSize: "0.9375rem", lineHeight: 1.4, overflowWrap: "anywhere" }}>
        {prefix}{title}
      </Typography>
      {t.status ? <CardRow label="상태"><Badge value={t.status} /></CardRow> : null}
      {assignee ? <CardRow label="담당자">{assignee}</CardRow> : null}
      {primary ? <CardRow label="담당자(정)">{primary}</CardRow> : null}
      {secondary ? <CardRow label="담당자(부)">{secondary}</CardRow> : null}
      {openTickets ? <CardRow label="진행 중">{openTickets}</CardRow> : null}
      {priority !== "" ? <CardRow label="우선순위"><Badge value={priorityKo(priority)} kind={priorityKind(priority)} /></CardRow> : null}
      {due ? <CardRow label="마감">{fmtDue(due)}</CardRow> : null}
      {projects.length ? (
        <CardRow label="프로젝트">
          <Box sx={{ display: "inline-flex", flexWrap: "wrap", gap: 0.5 }}>
            {/* 색 점은 label 안에 직접 넣는다 — Chip의 icon 슬롯은 MUI가 자기 마진·색을 덮어써
                프로젝트 색(projectToneColor)이 조용히 사라진다. */}
            {(showAllProjects ? projects : projects.slice(0, 3)).map((p, i) => (
              <Chip
                key={i} size="small" variant="outlined"
                label={
                  <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.625 }}>
                    <Box component="span" aria-hidden="true" sx={{ width: "0.4375rem", height: "0.4375rem", borderRadius: "50%", bgcolor: projectToneColor(p), flexShrink: 0 }} />
                    {String(p)}
                  </Box>
                }
                sx={{ height: "1.375rem", fontSize: "0.75rem", maxWidth: "100%" }}
              />
            ))}
            {/* 예전엔 4개 이상이면 나머지가 아무 표시 없이 조용히 잘렸다 — choices의 '+N개 더 보기'와
                같은 패턴으로, 숨겨진 개수를 알리고 눌러서 펼칠 수 있게 한다. */}
            {!showAllProjects && projects.length > 3 ? (
              <Chip
                size="small" variant="outlined" clickable color="primary"
                label={"+" + (projects.length - 3)}
                onClick={() => setShowAllProjects(true)}
                sx={{ height: "1.375rem", fontSize: "0.75rem", fontWeight: 750 }}
              />
            ) : null}
          </Box>
        </CardRow>
      ) : null}
      {url || (isTicket && t.id) || (typeof index === "number" && onChoose) ? (
        <Stack direction="row" flexWrap="wrap" alignItems="center" gap={1.5} sx={{ mt: 0.5 }}>
          {url ? (safeNotion(url) ? <NotionLink url={url} /> : <PlainUrl url={url} />) : null}
          {/* AI-41: 결과 카드에서 Notion 외부 링크만 있고 앱 내 티켓 상세로 가는 길이 없었다
              (AssistantPanel.jsx의 같은 카드는 이미 #/tickets/{id}로 간다) — 같은 패턴을 쓴다. */}
          {isTicket && t.id ? <Link href={"#/tickets/" + t.id} underline="hover" sx={{ fontSize: "0.8125rem", fontWeight: 700 }}>앱에서 보기</Link> : null}
          {typeof index === "number" && onChoose ? (
            <Button size="sm" disabled={sending} onClick={() => onChoose(index + "번 상세 보여줘")}>상세</Button>
          ) : null}
        </Stack>
      ) : null}
    </Paper>
  );
}

/* 구조화 결과 묶음 — 말풍선 안(좁은 폭)과 컨텍스트 레일(≥xxl) 두 곳이 **같은 코드**를 쓴다.
 * 예전엔 이 목록이 말풍선 렌더 안에 인라인으로 펼쳐져 있어서, 레일을 만들려면 통째로 복제해야
 * 했다 — 복제하면 순번 규칙(어느 카드에 'N.'을 붙이는가)이 반드시 한쪽만 고쳐진다. */
export function CardStack({ payload, startNo, onChoose, sending, gap = 1 }) {
  const { ticketsArr, tickets, projects, listItems, results, notionUrl, notionUnsafe, hasCards } = payload;
  return (
    <Box sx={{ display: "grid", gap, minWidth: 0 }}>
      {/* 순번(index)은 본문 목록과 짝이 맞는 tickets 배열분에만 붙인다, 그 뒤에 이어붙은 단일 ticket은
          번호 없이(비순번) 렌더해, 본문에 없는 'N번' 라벨과 어긋난 '상세' 클릭을 막는다. */}
      {tickets.map((t, i) => (
        <TicketCard key={"t" + i} t={t} isTicket sending={sending}
          index={startNo !== null && startNo !== undefined && i < ticketsArr.length ? startNo + i : undefined}
          onChoose={onChoose} />
      ))}
      {/* projects/listItems/results는 본문 번호 목록과 대응하는 개념이 없다, index를 안 주므로
          TicketCard의 '상세' 원탭 버튼도 뜨지 않는다(onChoose는 그 버튼에만 쓰이므로 함께 뺀다). */}
      {projects.map((t, i) => <TicketCard key={"p" + i} t={t} isTicket={false} sending={sending} />)}
      {listItems.map((t, i) => <TicketCard key={"i" + i} t={t} isTicket={false} sending={sending} />)}
      {results.map((t, i) => <TicketCard key={"r" + i} t={t} isTicket={false} sending={sending} />)}
      {!hasCards && (notionUrl || notionUnsafe) ? (
        <Paper variant="outlined" sx={{ p: 1.75, borderRadius: 3, bgcolor: "background.default", display: "grid", gap: 0.75 }}>
          <Typography sx={{ fontWeight: 750, fontSize: "0.9375rem" }}>관련 문서</Typography>
          {notionUrl ? <NotionLink url={notionUrl} /> : <PlainUrl url={notionUnsafe} />}
        </Paper>
      ) : null}
    </Box>
  );
}
