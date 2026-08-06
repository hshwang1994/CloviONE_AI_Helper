import React, { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputBase from "@mui/material/InputBase";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { alpha, useTheme } from "@mui/material/styles";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import ArrowDownwardRoundedIcon from "@mui/icons-material/ArrowDownwardRounded";
import AttachFileRoundedIcon from "@mui/icons-material/AttachFileRounded";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import EditRoundedIcon from "@mui/icons-material/EditRounded";
import Inventory2OutlinedIcon from "@mui/icons-material/Inventory2Outlined";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import UnarchiveOutlinedIcon from "@mui/icons-material/UnarchiveOutlined";
import { Badge, Button, Card, EmptyState, ErrorState, PageHeader, Skeleton, statusKind, useConfirm, useToast } from "../ui/kit.jsx";
import { MascotPose } from "../ui/Mascot.jsx";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { useChat } from "./useChat.js";
import {
  MASCOT_PHASE_TEXT, QUICK_PROMPTS, URL_RE,
  copyText, dayKeyKST, fmtDateSep, fmtDue, fmtShort, fmtTime,
  mascotMode, parseBlocks, peopleText, priorityKind, priorityKo, projectToneColor,
  safeNotion, structuredCards, ticketPageStart, stripDuplicatedTicketLines,
} from "./chat-helpers.js";

/* AI 채팅(§6.5) — 대화 목록 + 메시지 스레드 + 입력창 + (초광폭에서) 결과 레일.
 *
 * 이 파일은 **보이는 것만** 담당한다:
 *   - 순수 함수·상수·정규식  → chat-helpers.js
 *   - 쿼리/뮤테이션/폴링/전송 → useChat.js
 * 여기 남은 것은 JSX를 만드는 코드뿐이다(리치텍스트 렌더러 포함 — 헬퍼 모듈은 React를 모른다).
 *
 * 레이아웃(열 개수는 폭이 정한다. MUI Grid는 쓰지 않는다 — MUI 7에서 이름이 바뀌어
 * xs={12} 같은 예전 prop이 아무 말 없이 무시된다. CSS Grid를 직접 쓴다):
 *   < xl(1536)     1열. 대화 목록은 오버레이 서랍(오늘과 같다). 전역 사이드바가 이미 860부터
 *                  서 있어서, 여기서 목록까지 세우면 1024·1366 사내 장비의 대화 폭이 절반 아래가 된다.
 *   xl ~ xxl(2200) 2열. 대화 목록 + 스레드.
 *   ≥ xxl          3열. 대화 목록 + 스레드 + 결과 레일.
 * 서랍/열 경계는 chat-helpers.js의 LIST_DOCK_PX 하나를 훅과 공유한다 — 서랍의 inert·포커스
 * 반환이 그리드와 정확히 같은 지점에서 켜져야 한다.
 * 레일이 생기는 이유: 4K에서 남는 폭을 글줄 길이로 쓰면 안 된다(§ PROSE_MAX_WIDTH). 티켓 카드는
 * 원래 말풍선 안에 끼어 스레드를 밀어내고 있었다 — 폭이 남을 때만 그것을 옆으로 꺼낸다.
 *
 * 이 화면은 앱 셸에서 유일하게 'flush'로 그려진다(app/AppShell.jsx가 pathname==="/chat"만
 * 특별 취급한다). 즉 높이와 스크롤은 이 화면이 직접 소유한다 — 바깥이 잡아 주지 않는다.
 */

// 기존 호출부 호환을 위한 재수출 — 이 화면이 소유하지 않는 어휘(우선순위)와 순수 헬퍼를
// 예전처럼 Chat.jsx에서도 가져다 쓸 수 있게 남긴다. 정의는 각 모듈이 하나씩만 가진다.
export {
  priorityKo, priorityKind, safeNotion, msgAgeMs, classifyLine, parseBlocks,
  pageNumberOrNull, bodyListStart, ticketPageStart, stripDuplicatedTicketLines,
  newClientMessageId,
} from "./chat-helpers.js";

/* 열 폭은 rem이다 — 루트 폰트사이즈 레버(styles/root.css)가 4K에서 18/20px로 올라가면 목록과
 * 레일도 같은 비율로 넓어진다. px로 박아 두면 3840에서 목록이 실처럼 가늘어진다(앱 셸이 겪은 문제). */
const COLUMNS = {
  xs: "minmax(0,1fr)",
  xl: "19rem minmax(0,1fr)",
  xxl: "21rem minmax(0,1fr) 26rem",
  uhd: "23rem minmax(0,1fr) 30rem",
};
/* 스레드 열 자체의 상한. 말풍선 안 글줄은 따로 PROSE_MAX_WIDTH로 더 좁게 잡는다 — 이 값은
 * 카드·구분선이 화면 가운데 기둥처럼 서 있게 하는 바깥 틀일 뿐이다. */
const THREAD_MAX = "min(100%, 76rem)";
// 말풍선 글줄 상한. 남는 폭은 세 번째 열로 가고 줄은 절대 길어지지 않는다.
const BUBBLE_MAX = `min(88%, ${PROSE_MAX_WIDTH})`;

// ── 텍스트 렌더 ─────────────────────────────────────────────────────────────

// allowlist에 걸려 링크로 열 수 없는 외부 URL, 죽은 텍스트처럼 보이지 않도록 클릭하면 주소를
// 복사하는 버튼으로 렌더한다(TicketCard, 관련 문서 폴백에서 공유).
function PlainUrl({ url }) {
  const toast = useToast();
  return (
    <Tooltip title="외부 링크는 열 수 없습니다, 눌러서 주소를 복사합니다.">
      <Box
        component="button"
        type="button"
        onClick={() => copyText(url).then((ok) => toast(ok ? "주소를 복사했습니다." : "복사에 실패했습니다.", ok ? "success" : "error"))}
        sx={{
          font: "inherit", fontSize: "0.8125rem", border: 0, background: "none", p: 0, m: 0,
          textAlign: "left", cursor: "pointer", color: "text.secondary", overflowWrap: "anywhere",
          textDecoration: "underline dotted", textUnderlineOffset: "2px",
          "&:hover, &:focus-visible": { color: "text.primary", textDecorationStyle: "solid" },
        }}
      >
        {url}
      </Box>
    </Tooltip>
  );
}

// Notion 허용 도메인 링크 — 새 탭 고지는 시각(↗)과 낭독(sr-only) 둘 다로 준다.
function NotionLink({ url, children }) {
  return (
    <Link
      href={url} target="_blank" rel="noreferrer noopener" underline="hover"
      sx={{ fontSize: "0.8125rem", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 0.5, overflowWrap: "anywhere" }}
    >
      {children || "Notion에서 열기"}
      <OpenInNewRoundedIcon aria-hidden="true" sx={{ fontSize: "0.9375rem" }} />
      <span className="sr-only"> (새 탭에서 열림)</span>
    </Link>
  );
}

// 답변 프로즈 안에 맨 http(s):// URL이 섞여 있으면(구조화된 notion_url/ticket.url 필드가 아니라
// 그냥 문장 중간의 참조 링크) 이전엔 죽은 평문으로만 보였다, 구조화 필드와 같은 safeNotion 게이트로
// 링크(허용 도메인)/PlainUrl(그 외, 복사 폴백) 처리한다. 텍스트 노드만 쓴다(innerHTML 아님, CLAUDE.md §2).
function linkifyText(text, keyBase) {
  const s = String(text == null ? "" : text);
  const parts = s.split(URL_RE);
  if (parts.length === 1) return s;
  return parts.map((part, i) => (i % 2 === 1)
    ? (safeNotion(part)
        ? <NotionLink key={keyBase + "-u" + i} url={part}>{part}</NotionLink>
        : <PlainUrl key={keyBase + "-u" + i} url={part} />)
    : part);
}

/* 리치 텍스트 — parseBlocks 결과를 머리글/목록/키-값/문단으로 렌더한다(텍스트 노드 전용).
 * 머리글은 본문(0.9375rem)보다 커야 '머리글'로 읽힌다. 크기는 전부 rem이라 4K에서 함께 커진다. */
function RichText({ text }) {
  return (
    <>
      {parseBlocks(text).map((b, bi) => {
        if (b.kind === "head") {
          return (
            <Typography
              key={bi} component="h4"
              sx={{ mt: bi === 0 ? 0 : 1.5, mb: 0.5, fontSize: "1rem", fontWeight: 750, color: "text.primary", lineHeight: 1.4 }}
            >
              {b.text}
              {b.note ? <Box component="span" sx={{ ml: 1, fontWeight: 500, fontSize: "0.8125rem", color: "text.secondary" }}>{b.note}</Box> : null}
            </Typography>
          );
        }
        if (b.kind === "list") {
          return (
            <Box
              key={bi} component="ul" role="list"
              sx={{ listStyle: "none", m: 0, mt: bi === 0 ? 0 : 1, p: 0, display: "grid", gap: 0.5 }}
            >
              {b.items.map((it, ii) => (
                <Box
                  key={ii} component="li"
                  sx={{ display: "grid", gridTemplateColumns: it.marker ? "auto minmax(0,1fr)" : "minmax(0,1fr)", columnGap: 0.75, alignItems: "baseline" }}
                >
                  {it.marker ? (
                    <Box component="span" sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>{it.marker}</Box>
                  ) : null}
                  <Box component="span" sx={{ overflowWrap: "anywhere", "&::before": it.marker ? undefined : { content: '"· "', color: "text.secondary" } }}> {/* clovi-allow-glyph: 목록 글머리표 */}
                    {linkifyText(it.text, "li" + bi + "-" + ii)}
                  </Box>
                  {it.subs.map((s, si) => (
                    <Box
                      key={si} component="span"
                      sx={{ gridColumn: it.marker ? 2 : 1, fontSize: "0.8125rem", color: "text.secondary", overflowWrap: "anywhere" }}
                    >
                      {linkifyText(s, "li" + bi + "-" + ii + "-s" + si)}
                    </Box>
                  ))}
                </Box>
              ))}
            </Box>
          );
        }
        if (b.kind === "kv") {
          return (
            <Box key={bi} component="dl" sx={{ m: 0, mt: bi === 0 ? 0 : 1, display: "grid", gap: 0.25 }}>
              {b.rows.map((r, ri) => (
                <Box key={ri} sx={{ display: "grid", gridTemplateColumns: "minmax(4.5rem,auto) minmax(0,1fr)", columnGap: 1.25, fontSize: "0.875rem" }}>
                  <Box component="dt" sx={{ color: "text.secondary" }}>{r.key}</Box>
                  <Box component="dd" sx={{ m: 0, overflowWrap: "anywhere" }}>{linkifyText(r.text, "kv" + bi + "-" + ri)}</Box>
                </Box>
              ))}
            </Box>
          );
        }
        return (
          <Typography key={bi} sx={{ m: 0, mt: bi === 0 ? 0 : 1, fontSize: "0.9375rem", lineHeight: 1.6, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {linkifyText(b.lines.join("\n"), "p" + bi)}
          </Typography>
        );
      })}
    </>
  );
}

// ── 결과 카드 ───────────────────────────────────────────────────────────────

// 상태 톤 → 카드 왼쪽 색 띠. 배지뿐 아니라 카드 단위로도 상태가 한눈에 읽히게 한다.
const TONE_PALETTE = { ok: "success", danger: "error", warn: "warning", info: "primary" };

function CardRow({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "minmax(4.5rem,auto) minmax(0,1fr)", columnGap: 1, alignItems: "center", justifyItems: "start", fontSize: "0.8125rem" }}>
      <Typography component="span" sx={{ fontSize: "0.8125rem", color: "text.secondary" }}>{label}</Typography>
      <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>{children}</Box>
    </Box>
  );
}

function TicketCard({ t, index, onChoose, isTicket = true, sending }) {
  const theme = useTheme();
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
  // 상태 띠는 진짜 티켓(상태 개념이 있는)에만. 프로젝트/일반 항목 카드엔 붙이지 않는다.
  const tone = isTicket && t.status ? TONE_PALETTE[statusKind(t.status)] : null;
  const toneColor = tone ? theme.palette[tone].main : null;
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.75, display: "grid", gap: 0.5, minWidth: 0,
        borderRadius: 3,
        borderColor: toneColor ? alpha(toneColor, 0.42) : "divider",
        bgcolor: toneColor ? alpha(toneColor, 0.06) : "background.default",
        borderLeftWidth: toneColor ? "0.25rem" : undefined,
        borderLeftColor: toneColor || undefined,
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
      {url || (typeof index === "number" && onChoose) ? (
        <Stack direction="row" flexWrap="wrap" alignItems="center" gap={1.5} sx={{ mt: 0.5 }}>
          {url ? (safeNotion(url) ? <NotionLink url={url} /> : <PlainUrl url={url} />) : null}
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
function CardStack({ payload, startNo, onChoose, sending, gap = 1 }) {
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

// ── 메시지 ──────────────────────────────────────────────────────────────────

function Message({ m, onChoose, onRetry, sending, retrying, isLast, hideCards }) {
  const st = m.structured || {};
  const payload = structuredCards(m);
  const choices = Array.isArray(st.choices) ? st.choices : [];
  const attachments = Array.isArray(st.attachments) ? st.attachments : [];
  const errorNotice = !!st.error_notice; // 오류 안내 말풍선엔 '복사'를 붙이지 않는다.
  const processing = m.processing_status === "pending" || m.processing_status === "processing";
  const failed = m.processing_status === "failed";
  const [copied, setCopied] = useState("");
  const [showAllChoices, setShowAllChoices] = useState(false);
  const isUser = m.role === "user";
  const isAssistant = m.role === "assistant";
  const rawContent = m.content || "";
  // 카드 번호는 반드시 원본 본문(다듬기 전)으로 대조해 매긴다.
  const startNo = isAssistant ? ticketPageStart(st, rawContent) : null;
  // 목록 응답은 티켓을 본문+카드에 두 번 낸다 — 본문의 항목 줄을 걷어내 카드가 상세를 지게 한다.
  // 예전엔 이 제거를 raw st.start_index로 게이트했는데, 카드 번호는 ticketPageStart(context.
  // last_result_start까지 물려받음)로 매겨져, start_index가 없고 context만 있는 응답에선 카드엔
  // 'N번 상세' 버튼이 붙는데 본문 항목은 그대로 남아 이중 표시가 됐다 — 번호와 제거를 같은
  // 출처(startNo)로 통일한다.
  const content = (isAssistant && payload.tickets.length > 1 && startNo !== null && /^\s*\d+\.\s/m.test(rawContent))
    ? stripDuplicatedTicketLines(rawContent)
    : rawContent;
  const showChoices = isLast && isAssistant && !processing && choices.length > 0;
  // 카드의 '상세'도 선택 버튼과 같은 이유로 마지막 어시스턴트 메시지에서만 활성화한다, 스크롤해
  // 올라가 옛 목록의 '상세'를 누르면 'N번 상세'가 지금 맥락의 엉뚱한 티켓을 가리킨다(오작동).
  const cardChoose = isLast ? onChoose : undefined;
  const attachCaveat = "전송 후 이미지 원본은 저장되지 않습니다, 파일 이름만 남습니다.";

  return (
    <Box
      sx={{
        display: "flex", flexDirection: "column", gap: 0.75, minWidth: 0,
        maxWidth: BUBBLE_MAX,
        alignSelf: isUser ? "flex-end" : "flex-start",
        alignItems: isUser ? "flex-end" : "flex-start",
      }}
    >
      <Paper
        elevation={0}
        sx={{
          px: 2, py: 1.5, minWidth: 0, maxWidth: "100%",
          fontSize: "0.9375rem", lineHeight: 1.6, overflowWrap: "anywhere",
          borderRadius: 3,
          ...(isUser
            ? {
                bgcolor: "primary.main", color: "primary.contrastText",
                borderBottomRightRadius: "0.375rem",
                boxShadow: (t) => `0 2px 10px ${alpha(t.palette.primary.main, 0.28)}`,
              }
            : {
                bgcolor: "background.paper", border: 1, borderColor: "divider",
                borderBottomLeftRadius: "0.375rem",
              }),
        }}
      >
        {/* 화자 구분은 색/정렬뿐이라 스크린리더엔 안 들린다, 텍스트로도 알린다. */}
        <span className="sr-only">{isUser ? "나: " : "도우미: "}</span>
        {/* 어시스턴트 답은 머리글, 목록, 키-값으로 구조화(텍스트 노드 전용). 사용자 글은 친 그대로. */}
        {content ? (isAssistant ? <RichText text={content} /> : (
          <Typography sx={{ m: 0, fontSize: "0.9375rem", lineHeight: 1.6, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{content}</Typography>
        )) : null}
        {attachments.length ? (
          <>
            <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 1 }}>
              {/* 서버는 이미지 바이트를 저장하지 않는다(app/chat/service.py) — 전송 후엔 파일명 칩만 남고
                  실제 이미지는 다시 볼 수 없다. */}
              {attachments.map((name, i) => (
                <Chip key={i} size="small" variant="outlined" title={attachCaveat}
                  label={typeof name === "string" ? name : (name && name.filename) || "첨부"}
                  sx={{ height: "1.5rem", fontSize: "0.75rem", maxWidth: "15rem", color: "inherit", borderColor: "currentColor" }} />
              ))}
            </Stack>
            {/* title 툴팁은 hover 전용이라 모바일/터치에선 아예 안 뜬다, 전송 전 미리보기와
                같은 이유로, 보낸 메시지에도 항상 보이는 캡션을 둔다. */}
            <Typography sx={{ mt: 0.5, fontSize: "0.75rem", opacity: 0.75, lineHeight: 1.5 }}>{attachCaveat}</Typography>
          </>
        ) : null}
        {/* 카드는 폭이 남으면(≥xxl) 오른쪽 레일이 진다 — 그때 여기서 한 번 더 그리면 같은 티켓이
            화면에 두 벌 뜨고, '상세' 버튼도 두 개가 된다. hideCards는 그 중복만 막는다(데이터는 같다). */}
        {!hideCards && payload.hasAny ? (
          <Box sx={{ mt: 1.25 }}>
            <CardStack payload={payload} startNo={startNo} onChoose={cardChoose} sending={sending} />
          </Box>
        ) : null}
        {/* 이 자리에 있던 '어시스턴트 메시지 자체가 처리 중'일 때의 점 표시는 죽은 코드였다, 백엔드는
            어시스턴트 role의 Message를 항상 processing_status=done으로만 만든다(chat_message.py). 처리
            중 대기 표시는 스레드 레벨 awaitingReply의 별도 타이핑 말풍선이 이미 전담한다. */}
        {/* assistant_rejected는 서버가 "다시 시도해도 똑같이 실패한다"고 이미 분류해 준 경우다
            (app/jobs/handlers/chat_message.py on_failure), assistant_timeout/assistant_error와 같은
            '눌러볼 만한' 링크로 보이면, 이미 안 될 걸 아는데도 계속 누르게 만든다. */}
        {failed ? (
          <Typography sx={{ mt: 1, fontSize: "0.8125rem", color: isUser ? "inherit" : "error.main" }}>
            {m.error_code === "assistant_rejected"
              ? "처리하지 못했습니다, 다시 시도해도 같은 결과가 나올 가능성이 높습니다. 질문을 다르게 표현해 새로 물어보세요."
              : (
                <>
                  처리하지 못했습니다.{" "}
                  <Box component="button" type="button" disabled={retrying}
                    onClick={() => { if (!retrying) onRetry(m); }}
                    sx={{ font: "inherit", fontWeight: 750, border: 0, background: "none", p: 0, cursor: "pointer", color: "inherit", textDecoration: "underline" }}>
                    {retrying ? "재시도 중…" : "다시 시도"}
                  </Box>
                </>
              )}
          </Typography>
        ) : null}
      </Paper>

      {/* 원탭 선택은 가장 최근 어시스턴트 메시지에만. 옛 미리보기의 '등록해줘'가 살아 있으면
          스크롤해 올라가 눌렀을 때 지나간 맥락의 작업을 보낼 수 있다(오작동). */}
      {showChoices ? (
        <Stack direction="row" flexWrap="wrap" gap={1}>
          {(showAllChoices ? choices : choices.slice(0, 6)).map((c, i) => c && c.send ? (
            <Chip key={i} clickable color="primary" variant="outlined" disabled={sending}
              label={c.label || c.send} onClick={() => onChoose(c.send)}
              sx={{ fontSize: "0.8125rem", fontWeight: 700, height: "2rem" }} />
          ) : null)}
          {/* 7개 이상은 예전엔 조용히 잘려 나갔다 — '더 있다'는 사실만 알리고 실제로 꺼내 볼 방법은
              없었다. 이제 눌러서 나머지를 펼칠 수 있다. */}
          {!showAllChoices && choices.length > 6 ? (
            <Button size="sm" variant="ghost" onClick={() => setShowAllChoices(true)}>+{choices.length - 6}개 더 보기</Button>
          ) : null}
        </Stack>
      ) : null}

      <Stack direction="row" alignItems="center" gap={1}>
        {isAssistant && m.content && !processing && !errorNotice ? (
          <>
            <Button size="sm" variant="ghost"
              onClick={() => copyText(m.content).then((ok) => { setCopied(ok ? "복사됨" : "복사 실패"); setTimeout(() => setCopied(""), 1500); })}>
              {copied === "복사됨"
                ? <CheckRoundedIcon aria-hidden="true" sx={{ fontSize: "1rem", mr: 0.5 }} />
                : <ContentCopyRoundedIcon aria-hidden="true" sx={{ fontSize: "0.9375rem", mr: 0.5 }} />}
              {copied || "복사"}
            </Button>
            {/* 복사 결과는 버튼 라벨만 바뀌어 스크린리더가 못 듣는다, 라이브 영역으로도 알린다. */}
            <span className="sr-only" role="status" aria-live="polite">{copied}</span>
          </>
        ) : null}
        {/* 시각 라벨은 말풍선, 액션(선택 버튼, 복사) 뭉치 뒤 맨 끝에 둔다, 예전엔 말풍선과 선택 버튼
            사이에 끼어 있어 복사 버튼이 메시지에서 멀찍이 떨어지고, 시각이 버블→액션 묶음을 갈랐다. */}
        {m.created_at ? (
          <Typography sx={{ fontSize: "0.75rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>{fmtTime(m.created_at)}</Typography>
        ) : null}
      </Stack>
    </Box>
  );
}

/* 답변 대기 타이핑 말풍선 — 마스코트가 '생각 중' 포즈를 잡는 동안 스레드에도 같은 사실을 둔다.
 * 마스코트는 상단바에 있어 스레드 맨 아래를 보고 있는 눈에는 안 들어온다. */
function TypingBubble() {
  return (
    <Paper
      elevation={0}
      sx={{
        alignSelf: "flex-start", px: 2, py: 1.5, borderRadius: 3, borderBottomLeftRadius: "0.375rem",
        bgcolor: "background.paper", border: 1, borderColor: "divider",
      }}
    >
      <span className="sr-only">도우미: 답변을 작성하고 있습니다.</span>
      <Box aria-hidden="true" sx={{ display: "inline-flex", gap: 0.625, alignItems: "center" }}>
        {[0, 1, 2].map((i) => (
          <Box
            key={i}
            sx={{
              width: "0.4375rem", height: "0.4375rem", borderRadius: "50%", bgcolor: "primary.main",
              animation: "chat-bounce 1.3s ease-in-out infinite both",
              animationDelay: i * 0.16 + "s",
              "@keyframes chat-bounce": {
                "0%, 70%, 100%": { transform: "translateY(0)", opacity: 0.45 },
                "35%": { transform: "translateY(-0.375rem)", opacity: 1 },
              },
            }}
          />
        ))}
      </Box>
    </Paper>
  );
}

/* 스레드 안 날짜 구분선 — 말풍선 라벨은 시:분만 보여줘 사흘 전 15:23과 오늘 15:23이 구분되지
   않았다. 날짜가 바뀌는 지점에만 가운데 칩을 끼워 넣는다. */
function DaySeparator({ at }) {
  const label = fmtDateSep(at);
  return (
    <Box role="separator" aria-label={label} sx={{ display: "flex", alignItems: "center", gap: 1.5, alignSelf: "stretch", my: 0.5 }}>
      <Box sx={{ flex: 1, height: "1px", bgcolor: "divider" }} />
      <Chip size="small" label={label} sx={{ fontSize: "0.75rem", height: "1.5rem" }} />
      <Box sx={{ flex: 1, height: "1px", bgcolor: "divider" }} />
    </Box>
  );
}

/* 시작 예시 칩, 누르면 그 문장을 컴포저에 채운다(빈 화면 막다른 길 방지). */
function QuickPrompts({ onPick, busy }) {
  return (
    <Stack direction="row" flexWrap="wrap" gap={1} justifyContent="center" role="group" aria-label="시작 예시" sx={{ mt: 2 }}>
      {QUICK_PROMPTS.map((p, i) => (
        <Chip key={i} clickable disabled={busy} label={p} onClick={() => onPick(p)} variant="outlined"
          sx={{ fontSize: "0.8125rem", height: "2rem", "&:hover": { borderColor: "primary.main", color: "primary.main" } }} />
      ))}
    </Stack>
  );
}

/* 빈 화면 — 마스코트는 여기서 장식(decorative)이다. 상태를 말하는 마스코트는 상단바에 하나뿐이고,
   같은 상태를 두 번 낭독시키지 않는다. */
function Welcome({ title, help, onPick, busy, mode }) {
  return (
    <Box sx={{ m: "auto", textAlign: "center", color: "text.secondary", maxWidth: "38rem", px: 2, py: 4 }}>
      <Box sx={{ display: "grid", justifyItems: "center", mb: 1 }}>
        <MascotPose mode={mode} size="6rem" decorative />
      </Box>
      <Typography variant="h5" component="h2" color="text.primary" sx={{ fontSize: "1.375rem", mb: 1 }}>{title}</Typography>
      <Typography sx={{ fontSize: "0.9375rem", lineHeight: 1.6 }}>{help}</Typography>
      <QuickPrompts onPick={onPick} busy={busy} />
    </Box>
  );
}

// ── 대화 목록 ───────────────────────────────────────────────────────────────

/* 대화 목록 항목 — 호버 시 이름 변경(인라인)·보관·삭제. 빈 '새 대화'가 쌓여도 정리 가능.
 * 터치(호버 없음) 기기에서는 hover가 절대 안 일어나 액션에 영영 닿을 수 없으므로 항상 노출한다. */
function ConvItem({ c, active, onOpen, onRename, onDelete, onArchive }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(c.title || "");
  const label = c.title || "새 대화";
  // 이전엔 mutation 결과와 무관하게 setEditing(false)를 먼저 불러 입력을 닫았다 — PATCH가 실패하면
  // (422·네트워크 오류·409 등) 입력창이 조용히 닫히고 사이드바가 옛 제목으로 되돌아가, 사용자가 방금
  // 친 내용이 사라져도 눈에 잘 안 띄는 토스트 하나로만 알렸다. onRename이 돌려주는 프라미스가 성공할
  // 때만 편집 모드를 닫고, 실패하면 입력을 그대로 열어 둬 재시도/복사할 수 있게 한다.
  function commit() {
    const t = val.trim();
    if (!t || t === (c.title || "")) { setEditing(false); return; }
    Promise.resolve(onRename(t)).then(() => setEditing(false)).catch(() => {});
  }
  if (editing) {
    return (
      <Box sx={{ px: 0.5, py: 0.5 }}>
        <InputBase
          fullWidth autoFocus value={val} inputProps={{ maxLength: 200, "aria-label": "이름 변경: " + label }}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.nativeEvent.isComposing || e.keyCode === 229) return; if (e.key === "Enter") { e.preventDefault(); commit(); } if (e.key === "Escape") { setEditing(false); setVal(c.title || ""); } }}
          onBlur={commit}
          sx={{ px: 1, py: 0.5, fontSize: "0.875rem", border: 1, borderColor: "primary.main", borderRadius: 1.5, bgcolor: "background.paper" }}
        />
      </Box>
    );
  }
  const act = (title, ariaLabel, icon, onClick) => (
    <Tooltip title={title}>
      <IconButton size="small" aria-label={ariaLabel} onClick={onClick}
        sx={{ minWidth: "2rem", minHeight: "2rem", color: "text.secondary" }}>{icon}</IconButton>
    </Tooltip>
  );
  return (
    <Box
      sx={{
        display: "flex", alignItems: "center", borderRadius: 2, minWidth: 0,
        opacity: c.archived ? 0.65 : 1,
        bgcolor: active ? (t) => alpha(t.palette.primary.main, 0.12) : "transparent",
        transition: "background .12s ease",
        "&:hover, &:focus-within": { bgcolor: (t) => alpha(t.palette.primary.main, active ? 0.16 : 0.08) },
        "&:hover .chat-conv-actions, &:focus-within .chat-conv-actions": { display: "flex" },
        "&:hover .chat-conv-time, &:focus-within .chat-conv-time": { display: "none" },
        "@media (hover: none)": { "& .chat-conv-actions": { display: "flex" }, "& .chat-conv-time": { display: "none" } },
      }}
    >
      <Box
        component="button" type="button" onClick={onOpen}
        sx={{
          flex: 1, minWidth: 0, textAlign: "left", border: 0, background: "none", cursor: "pointer",
          px: 1.5, py: 1, borderRadius: 2, font: "inherit", fontSize: "0.875rem",
          fontWeight: active ? 700 : 400,
          color: active ? "primary.main" : "text.primary",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}
      >
        {label}
      </Box>
      {/* 보관됨은 호버 아이콘만으로는 쉼 상태에서 구분되지 않는다, 항상 보이는 태그로 표시한다. */}
      {c.archived ? <Badge value="archived" /> : null}
      {c.updated_at ? (
        <Typography className="chat-conv-time" sx={{ flexShrink: 0, ml: "auto", pr: 1, fontSize: "0.6875rem", color: "text.secondary", whiteSpace: "nowrap" }}>
          {fmtShort(c.updated_at)}
        </Typography>
      ) : null}
      {/* 목록에 같은 버튼이 대화 수만큼 있어서, '삭제'만으로는 스크린리더 사용자가 어느 대화의
          삭제 버튼인지 알 수 없다, 대화 제목을 라벨에 포함한다. */}
      <Box className="chat-conv-actions" sx={{ display: "none", flexShrink: 0, pr: 0.5 }}>
        {act("이름 변경", "이름 변경: " + label, <EditRoundedIcon sx={{ fontSize: "1rem" }} />, () => { setVal(c.title || ""); setEditing(true); })}
        {act(c.archived ? "보관 해제" : "보관", (c.archived ? "보관 해제: " : "보관: ") + label,
          c.archived ? <UnarchiveOutlinedIcon sx={{ fontSize: "1rem" }} /> : <Inventory2OutlinedIcon sx={{ fontSize: "1rem" }} />,
          () => onArchive(!c.archived))}
        {act("삭제", "대화 삭제: " + label, <DeleteOutlineRoundedIcon sx={{ fontSize: "1rem" }} />, onDelete)}
      </Box>
    </Box>
  );
}

// ── 마스코트 상태 표시 ──────────────────────────────────────────────────────

/* 마스코트를 대화 단계에 붙인다 — 지금까지 이 컴포넌트는 어디서나 'listening' 한 포즈로 고정돼
 * 있어서, 상태를 전한다고 주장하면서 아무 상태도 전하지 않는 장식이었다. 포즈 결정은 순수 함수
 * mascotMode(chat-helpers.js)가 하고 여기서는 그리기만 한다(그래야 매핑을 테스트할 수 있다).
 * 그림만으로 상태를 전하지 않는다 — 옆의 한 줄 문구가 같은 정보를 글자로 준다. */
function MascotStatus({ mode }) {
  return (
    <Stack direction="row" alignItems="center" gap={1} sx={{ flexShrink: 0, minWidth: 0 }}>
      <MascotPose mode={mode} size="2.5rem" />
      <Typography
        role="status" aria-live="polite"
        sx={{ display: { xs: "none", lg: "block" }, fontSize: "0.8125rem", color: "text.secondary", whiteSpace: "nowrap" }}
      >
        {MASCOT_PHASE_TEXT[mode]}
      </Typography>
    </Stack>
  );
}

// ── 화면 ────────────────────────────────────────────────────────────────────

export function Chat() {
  const confirm = useConfirm();
  const theme = useTheme();
  // 세 번째 열(결과 레일)은 폭이 실제로 남을 때만 존재한다. 같은 판정을 CSS와 JS 두 곳에서 하면
  // 반드시 어긋나므로(카드가 두 벌 뜨거나 아예 사라진다) 여기 한 곳에서만 정한다.
  const railOpen = useMediaQuery(theme.breakpoints.up("xxl"));
  const ch = useChat();
  const {
    cid, setCid, convs, convFilter, setConvFilter, showArchived, setShowArchived,
    setComposingNew, activeTitle, renameConv, archiveConv, deleteConv,
    thread, items, busy, awaitingReply, stalled, justAnswered, answerAnnounce, lastMsg, setResumedAt,
    text, setText, pending, setPending, composerFocused, setComposerFocused,
    maintenanceNotice, setMaintenanceNotice, rateLimitNotice, setRateLimitNotice,
    send, createConv, retryingRef,
    doSend, doRetry, pickFiles, clearDraft, prefillFromPrompt,
    composerLocked, sending, inputDisabled,
    stick, setStick, onScroll, sideOpen, setSideOpen, closeSideDrawer, listIsDrawer,
    bodyRef, fileRef, textareaRef, asideRef, sideToggleRef,
  } = ch;

  const convItems = (convs.data && convs.data.items) || [];
  const starting = send.isPending || createConv.isPending;

  /* 레일이 지는 것은 '마지막으로 결과를 들고 온 어시스턴트 메시지' 하나다. 스레드를 거슬러
   * 올라가며 처음 만나는 것을 쓴다 — 대화가 이어지면 사용자가 마지막으로 요청한 결과가
   * 계속 오른쪽에 남아 있어야 티켓 번호를 보며 다음 문장을 칠 수 있다. */
  const railMsg = railOpen
    ? [...items].reverse().find((m) => m.role === "assistant" && structuredCards(m).hasAny) || null
    : null;
  const railPayload = railMsg ? structuredCards(railMsg) : null;
  const railIsLast = !!railMsg && !!lastMsg && railMsg.id === lastMsg.id;

  /* 마스코트 단계 — 앱이 실제로 있는 상태만 넘긴다(mascotMode 주석 참고).
   * failed는 '지금 사용자가 갇혀 있는' 상태 셋을 합친다: 마지막 메시지가 실패했거나, 응답이
   * 임계 시간을 넘겨 지연됐거나, 폴링이 끊겨 스레드를 못 읽고 있거나. */
  const mascot = mascotMode({
    failed: (!!lastMsg && lastMsg.processing_status === "failed") || stalled || thread.isError,
    blocked: composerLocked,
    sending: starting,
    awaitingReply, busy,
    justAnswered,
    hasResult: !!lastMsg && structuredCards(lastMsg).hasAny,
    composerFocused,
  });

  const listPane = (
    <>
      <Button variant="primary" onClick={() => { clearDraft(); setComposingNew(true); setCid(null); setSideOpen(false); textareaRef.current && textareaRef.current.focus(); }}>
        <AddRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem", mr: 0.5 }} />새 대화
      </Button>
      <Box component="label" sx={{ display: "flex", alignItems: "center", gap: 1, fontSize: "0.8125rem", color: "text.secondary", cursor: "pointer" }}>
        <Box component="input" type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} sx={{ m: 0 }} />
        보관된 대화 보기
      </Box>
      {/* 대화가 쌓일수록 스크롤만으로 찾기 어렵다 — 이미 불러온 전체 목록을 제목 부분일치로
          클라이언트에서만 좁힌다(백엔드 변경 불필요). */}
      {convItems.length > 0 ? (
        <Paper variant="outlined" sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.25, borderRadius: 2 }}>
          <SearchRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem", color: "text.secondary" }} />
          <InputBase
            type="search" fullWidth placeholder="대화 제목 검색" value={convFilter}
            onChange={(e) => setConvFilter(e.target.value)}
            inputProps={{ "aria-label": "대화 목록 검색" }}
            sx={{ fontSize: "0.875rem" }}
          />
        </Paper>
      ) : null}
      {/* 대화 목록만 스크롤한다(사이드바 전체가 아니라) — '새 대화' 버튼과 보관 토글은 항상 위에
          고정되고, 목록이 사이드바 높이를 넘칠 때만 이 안에서 스크롤된다. */}
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25, flex: 1, minHeight: 0, overflowY: "auto", pr: 0.5, scrollbarGutter: "stable" }}>
        {convs.isLoading ? <Skeleton lines={4} />
          : convs.isError ? <ErrorState error={convs.error} onRetry={() => convs.refetch()} />
          : !convItems.length
            /* 빈 상태는 kit `EmptyState` 로. 회색 한 줄은 로딩 중인지·보관 필터 때문인지·
               정말 없는 건지 구분해 주지 않는다(E계열 지적, `GroupedTickets` 와 같은 수정).
               `.k-empty` + `role="status"` 가 따라오는 것도 이득이다 — 낭독되고, 기준 대조
               도구가 "데이터가 없어 카드가 0" 인 화면을 디자인 불일치로 세지 않게 된다. */
            ? (showArchived
                ? <EmptyState title="보관된 대화가 없습니다"
                    help="대화를 보관하면 여기에 모입니다. 위 체크를 풀면 진행 중인 대화가 보입니다." />
                : <EmptyState title="아직 대화가 없습니다"
                    help="위의 '새 대화'를 눌러 시작하세요. 지금 보고 있는 화면을 기준으로 물어볼 수 있습니다." />)
            : (() => {
                const q = convFilter.trim().toLowerCase();
                const filtered = q ? convItems.filter((c) => (c.title || "새 대화").toLowerCase().includes(q)) : convItems;
                return filtered.length ? filtered.map((c) => (
                  <ConvItem key={c.id} c={c} active={c.id === cid}
                    onOpen={() => { if (c.id !== cid) clearDraft(); setCid(c.id); setComposingNew(false); setSideOpen(false); textareaRef.current && textareaRef.current.focus(); }}
                    onRename={(title) => renameConv.mutateAsync({ id: c.id, title })}
                    onArchive={(archived) => archiveConv.mutate({ id: c.id, archived })}
                    onDelete={async () => { if (await confirm("이 대화를 삭제할까요? 되돌릴 수 없습니다.", { danger: true, confirmLabel: "대화 삭제" })) deleteConv.mutate(c.id); }} />
                )) : <Typography sx={{ fontSize: "0.8125rem", color: "text.secondary", px: 1 }}>검색 결과가 없습니다.</Typography>;
              })()}
      </Box>
    </>
  );

  /* AI 도우미도 다른 화면과 **같은 언어**로 그린다 (사용자 지적 S3, "지금은 너무 안이쁘다").
   *
   * 예전에는 이 화면만 제목도 빵 부스러기도 없이 맨바닥에 두 칸이 놓여 있었다. 앱의 다른
   * 화면은 전부 `c-screen` + `PageHeader` + 카드 표면 위에 있는데 여기만 아니라서, 들어오는
   * 순간 "덜 만든 화면" 으로 읽혔다. 방금 통합한 채팅방 껍데기(S1)와도 같은 모양으로 맞춘다.
   *
   * 격자 자체(열 수·서랍 전환·xxl 3열)는 건드리지 않는다 — 그 상태 기계는 테스트가 없고,
   * 지금 고치려는 것은 '어떻게 담기는가' 이지 '어떻게 동작하는가' 가 아니다. */
  return (
    <Box className="c-screen">
      <PageHeader crumbRoot="도우미" area="AI 도우미" title="AI 도우미" />
      <Card
        sx={{
          p: 0, overflow: "hidden",
          height: { xs: "calc(100vh - 12rem)", md: "calc(100vh - 13rem)" },
          minHeight: "30rem",
          display: "grid",
        }}
      >
    <Box
      sx={{
        position: "relative", width: "100%", height: "100%", minHeight: 0,
        display: "grid", gridTemplateColumns: COLUMNS, bgcolor: "background.default",
      }}
    >
      {/* 대화 목록. 좁은 폭에서는 오버레이 서랍(오늘과 같은 동작 — Esc·백드롭·포커스 이동·inert),
          xl 이상에서는 열로 상주한다. inert는 '서랍인데 닫혀 있을 때'에만 건다 — 상주 상태에
          걸면 목록 전체가 키보드/스크린리더에서 사라진다. */}
      <Box
        component="aside" id="chat-conv-drawer" ref={asideRef}
        {...(listIsDrawer && !sideOpen ? { inert: "", "aria-hidden": "true" } : {})}
        sx={{
          position: { xs: "absolute", xl: "static" },
          top: 0, left: 0, bottom: 0, zIndex: 20,
          width: { xs: "18.75rem", xl: "auto" }, maxWidth: { xs: "85%", xl: "none" },
          borderRight: 1, borderColor: "divider", bgcolor: "background.paper",
          display: "flex", flexDirection: "column", gap: 1.5, p: 1.5, minHeight: 0, minWidth: 0, overflowY: "auto",
          transform: { xs: sideOpen ? "none" : "translateX(-100%)", xl: "none" },
          transition: "transform .2s ease",
          boxShadow: { xs: sideOpen ? 8 : 0, xl: 0 },
        }}
      >
        {listPane}
      </Box>
      {sideOpen && listIsDrawer ? (
        <Box onClick={closeSideDrawer} aria-hidden="true"
          sx={{ position: "absolute", inset: 0, zIndex: 15, bgcolor: (t) => alpha(t.palette.common.black, 0.4) }} />
      ) : null}

      {/* 스레드 열 — 높이와 스크롤은 이 화면이 직접 소유한다(셸이 flush로 넘긴다). */}
      <Box
        component="section"
        {...(sideOpen && listIsDrawer ? { inert: "", "aria-hidden": "true" } : {})}
        sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, position: "relative" }}
      >
        {/* 대화 제목 헤더 — 특히 좁은 폭(서랍이 닫혀 어느 대화인지 모른다)에서 현재 대화를 알린다. */}
        <Paper
          elevation={0} square
          sx={{ display: "flex", alignItems: "center", gap: 1.5, px: { xs: 2, lg: 3 }, py: 1.25, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}
        >
          {/* 앱 셸의 햄버거와 같은 방식으로 aria-expanded/aria-controls를 실제 토글 상태에 맞춘다,
              이전엔 '열기' 전용 편도 트리거라 열린 뒤에도 라벨, 상태가 안 바뀌었다.
              xl 이상에서는 목록이 상주하므로 이 버튼 자체가 필요 없다.
              키트의 Button이 아니라 MUI IconButton을 쓰는 이유: 서랍을 닫을 때 포커스를 이 버튼으로
              되돌려야 하는데(closeSideDrawer) 키트 Button은 ref를 전달하지 않아 sideToggleRef가
              영원히 null이 된다 — 포커스가 문서 맨 앞으로 튕기는 조용한 접근성 회귀가 된다. */}
          <IconButton
            ref={sideToggleRef} aria-controls="chat-conv-drawer" aria-expanded={sideOpen}
            aria-label={sideOpen ? "대화 목록 닫기" : "대화 목록 열기"}
            onClick={() => (sideOpen ? closeSideDrawer() : setSideOpen(true))}
            sx={{ display: { xs: "inline-flex", xl: "none" }, flexShrink: 0 }}
          >
            {sideOpen ? <CloseRoundedIcon aria-hidden="true" /> : <MenuRoundedIcon aria-hidden="true" />}
          </IconButton>
          {/* cid가 없어도(첫 방문, 새 대화 시작 직후) 빈 막대 대신 화면 이름을 보여준다. */}
          <Typography
            component="h1"
            sx={{ flex: 1, minWidth: 0, fontSize: "0.9375rem", fontWeight: 750, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {cid ? activeTitle : "채팅"}
          </Typography>
          <MascotStatus mode={mascot} />
        </Paper>

        {/* 스레드 전체를 aria-live로 감싸면 1.5초 폴링마다 대화가 통째로 다시 낭독된다.
            스레드에서 aria-live를 걷어내고, 일시 상태만 이 작은 라이브 영역에서 알린다. */}
        <div className="sr-only" role="status" aria-live="polite">{busy ? "답변을 처리하고 있습니다." : ""}</div>
        <div className="sr-only" role="status" aria-live="polite">{answerAnnounce}</div>

        <Box ref={bodyRef} onScroll={onScroll} sx={{ position: "relative", flex: 1, minHeight: 0, overflowY: "auto", px: { xs: 2, sm: 3 }, py: 3, display: "flex", flexDirection: "column" }}>
          {/* flex:1 0 auto — 내용이 짧아도 열이 스크롤 높이를 꽉 채워 환영 화면의 margin:auto가
              실제로 세로 가운데를 잡는다. shrink는 0이라 길어지면 그대로 스크롤된다. */}
          <Box sx={{ width: "100%", maxWidth: THREAD_MAX, mx: "auto", flex: "1 0 auto", display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
            {!cid ? (
              // 대화 목록 조회가 실패/로딩 중이면 환영 화면 대신 그 상태를 보여준다, 좁은 폭에선 목록이
              // 닫힌 서랍 안에 있어 그 안의 오류/재시도가 안 보이므로, 여기(본문)에도 같은 신호가 있어야 한다.
              convs.isLoading ? <Skeleton lines={3} />
              : convs.isError ? <ErrorState error={convs.error} onRetry={() => convs.refetch()} />
              : (
                <Welcome mode={mascot} title="무엇을 도와드릴까요?" busy={starting} onPick={prefillFromPrompt}
                  help="대화 한 줄이면 티켓 생성, 조회, 요약까지 처리합니다. 아래 예시를 눌러 바로 시작해 보세요." />
              )
            ) : thread.isLoading ? <Skeleton lines={3} />
              : thread.isError && !items.length ? <ErrorState error={thread.error} onRetry={() => thread.refetch()} />
              : items.length === 0 ? (
                <Welcome mode={mascot} title="새 대화" busy={starting} onPick={prefillFromPrompt}
                  help="아래에 메시지를 입력하거나, 예시를 눌러 시작하세요." />
              )
              : (<>
                  {/* 폴링이 일시 실패해도 읽던 메시지를 지우지 않는다, 작은 안내만 띄우고 스레드는 유지. */}
                  {thread.isError ? (
                    <Alert severity="warning" variant="outlined" role="status" sx={{ alignSelf: "center", fontSize: "0.8125rem", py: 0 }}
                      action={<Button size="sm" variant="ghost" onClick={() => thread.refetch()}>새로고침</Button>}>
                      연결이 잠시 끊겼습니다.
                    </Alert>
                  ) : null}
                  {items.map((m, i) => {
                    // 앞 메시지와 KST 기준 날짜가 다르면(또는 첫 메시지면) 그 앞에 날짜 구분선을 끼운다.
                    const prev = i > 0 ? items[i - 1] : null;
                    const dk = dayKeyKST(m.created_at);
                    const showSep = !!dk && (!prev || dayKeyKST(prev.created_at) !== dk);
                    return (
                      <React.Fragment key={m.id}>
                        {showSep ? <DaySeparator at={m.created_at} /> : null}
                        {/* retrying은 이 메시지가 지금 재시도 중인지만 본다 — 뮤테이션의 전역 isPending을
                            그대로 쓰면 스레드의 다른 실패 메시지의 '다시 시도'까지 함께 잠긴다(과잉 제한).
                            sending은 선택 버튼·카드 '상세'를 눌러도 되는지다(useChat이 한 값으로 계산). */}
                        <Message m={m} onChoose={doSend} onRetry={doRetry} sending={sending}
                          retrying={retryingRef.current === m.id} isLast={i === items.length - 1}
                          hideCards={!!railMsg && railMsg.id === m.id} />
                      </React.Fragment>
                    );
                  })}
                  {/* 답변 대기 중이면 왼쪽에 어시스턴트 타이핑 말풍선(사용자 말풍선 안이 아니라). awaitingReply
                      자체가 이미 stalled를 제외하므로 별도 조건이 필요 없다. */}
                  {awaitingReply ? <TypingBubble /> : null}
                  {/* 응답이 임계 시간을 넘겨 지연되면 무한 대기 대신 수동 새로고침을 제공한다. 새로고침은 단순
                      재조회가 아니라 폴링 재시작 기준선(resumedAt)도 지금 시각으로 옮긴다, 안 그러면 created_at이
                      그대로라 재조회 직후 다시 즉시 stalled로 재계산돼 자동 폴링이 재개되지 않는 막다른 길이 된다. */}
                  {stalled ? (
                    <Alert severity="warning" variant="outlined" role="status" sx={{ alignSelf: "flex-start", fontSize: "0.8125rem" }}
                      action={<Button size="sm" variant="ghost" onClick={() => { setResumedAt(Date.now()); thread.refetch(); }}>새로고침</Button>}>
                      응답이 지연되고 있습니다.
                    </Alert>
                  ) : null}
                </>)}
            {/* 스크롤 컨테이너 안에서 sticky로 띄운다, 예전엔 열 기준(컴포저 바로 위 고정 거리)이라,
                여러 줄 초안+첨부 미리보기+글자 수로 컴포저가 커지면 이 버튼이 컴포저 안/뒤로 파묻혔다.
                스크롤 영역에 붙이면 컴포저 높이와 무관하게 항상 그 위에 뜬다. */}
            {!stick ? (
              <Box sx={{ position: "sticky", bottom: 0, alignSelf: "flex-end", mt: "auto", pt: 1, zIndex: 5 }}>
                <Button variant="primary" size="sm" onClick={() => setStick(true)} sx={{ borderRadius: "999px", boxShadow: 6 }}>
                  <ArrowDownwardRoundedIcon aria-hidden="true" sx={{ fontSize: "1rem", mr: 0.5 }} />맨 아래로
                </Button>
              </Box>
            ) : null}
          </Box>
        </Box>

        {/* 전폭 배경 띠 — 초광폭에서 상단 헤더는 전폭 구분선인데 컴포저만 카드 폭으로 떠 좌우에
            페이지 배경 여백이 생겨 미완성처럼 보였다. 띠로 감싸고 안쪽 내용만 스레드와 같은 폭으로
            가운데 정렬해 헤더가 콘텐츠를 감싸는 방식과 맞춘다. */}
        <Paper elevation={0} square sx={{ borderTop: 1, borderColor: "divider", flexShrink: 0 }}>
          <Box sx={{ width: "100%", maxWidth: THREAD_MAX, mx: "auto", px: { xs: 2, sm: 3 }, py: 1.5, display: "grid", gap: 1 }}>
            {pending.length ? (
              <>
                {/* Chip의 onDelete는 쓰지 않는다 — MUI가 삭제 아이콘을 tabIndex=-1로 만들어 키보드
                    사용자가 첨부를 뺄 방법이 사라진다. 이름이 붙은 진짜 버튼을 직접 둔다. */}
                <Stack direction="row" flexWrap="wrap" gap={0.75}>
                  {pending.map((a, i) => (
                    <Paper key={i} variant="outlined"
                      sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, pl: 0.5, pr: 0.25, py: 0.25, borderRadius: "999px", maxWidth: "18rem" }}>
                      {/* 보낼 이미지를 텍스트 칩이 아니라 실제 썸네일로 확인시킨다(로컬 data URL). */}
                      <Box component="img" src={"data:" + (a.media_type || "image/png") + ";base64," + a.data} alt=""
                        sx={{ width: "1.75rem", height: "1.75rem", objectFit: "cover", borderRadius: "50%", flexShrink: 0 }} />
                      <Typography sx={{ fontSize: "0.75rem", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.filename}</Typography>
                      <IconButton size="small" aria-label={"첨부 제거: " + a.filename}
                        onClick={() => setPending((p) => p.filter((_, j) => j !== i))}
                        sx={{ minWidth: "1.75rem", minHeight: "1.75rem", flexShrink: 0 }}>
                        <CloseRoundedIcon sx={{ fontSize: "0.9375rem" }} />
                      </IconButton>
                    </Paper>
                  ))}
                </Stack>
                {/* hover-only 툴팁은 모바일/터치에서 아예 안 보인다, 전송 전에 눈에 보이는 문장으로도 알린다. */}
                <Typography sx={{ fontSize: "0.75rem", color: "text.secondary" }}>전송 후에는 이미지 원본이 저장되지 않습니다, 파일 이름만 남습니다.</Typography>
              </>
            ) : null}
            {/* 글자 수는 입력이 있으면 늘 옅게 보여준다 — 상한이 갑자기 닥치지 않게(바닐라도 항상 표시).
                textarea의 maxLength=5000은 UTF-16 코드 유닛 기준이라, 서로게이트 쌍(이모지 등)이 섞이면
                Array.from(코드 포인트) 기준 길이는 실제 입력 가능 한도보다 작게 세어져 두 숫자가 어긋난다 —
                text.length(코드 유닛)로 맞춘다. */}
            {text.length > 0 ? (
              <Typography sx={{ textAlign: "right", fontSize: "0.75rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>{text.length}/5000</Typography>
            ) : null}
            {/* 유지보수 모드 차단 안내 — 폴링 경고와 같은 지속 배너 패턴(사라지는 토스트 하나에만
                기대지 않는다). '다시 시도'를 눌러야 컴포저 잠금이 풀린다. */}
            {maintenanceNotice ? (
              <Alert severity="warning" role="status" sx={{ fontSize: "0.8125rem" }}
                action={<Button size="sm" variant="ghost" onClick={() => setMaintenanceNotice(null)}>다시 시도</Button>}>
                {maintenanceNotice}
              </Alert>
            ) : null}
            {rateLimitNotice ? (
              <Alert severity="warning" role="status" sx={{ fontSize: "0.8125rem" }}
                action={<Button size="sm" variant="ghost" onClick={() => setRateLimitNotice(null)}>닫기</Button>}>
                {rateLimitNotice}
              </Alert>
            ) : null}
            {/* 답변을 기다리는 동안 textarea는 계속 활성이라(placeholder는 'Enter 전송'을 약속) 입력이
                막혔다는 신호가 없어, Enter를 쳐도 사라지는 토스트로만 알렸다, 유지보수·속도제한 배너처럼
                지속되는 수동 힌트를 컴포저 위에 둔다. */}
            {(busy || awaitingReply) && !composerLocked ? (
              <Typography role="status" sx={{ textAlign: "center", fontSize: "0.75rem", color: "text.secondary" }}>
                답변을 기다리는 중입니다, 답변이 도착하면 다시 입력할 수 있습니다.
              </Typography>
            ) : null}
            <Box component="footer" sx={{ display: "flex", gap: 1, alignItems: "flex-end" }}>
              <Box component="input" ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" multiple
                aria-hidden="true" tabIndex={-1} onChange={(e) => pickFiles(e.target.files)} sx={{ display: "none" }} />
              {/* 전송과 같은 '어시스턴트가 아직 작업 중' 가드를 쓴다, 이전엔 이 버튼만 그 상태에서도
                  눌려, 첨부를 골라도 어차피 이번 턴엔 보낼 수 없는데 활성으로 보였다. */}
              <Tooltip title="이미지 첨부(PNG, JPEG, WebP)">
                <Box component="span" sx={{ flexShrink: 0 }}>
                  <IconButton aria-label="이미지 첨부" disabled={inputDisabled}
                    onClick={() => fileRef.current && fileRef.current.click()}
                    sx={{ border: 1, borderColor: "divider", borderRadius: 2.5, width: "2.75rem", height: "2.75rem", minWidth: "2.75rem", minHeight: "2.75rem" }}>
                    <AttachFileRoundedIcon sx={{ fontSize: "1.25rem" }} />
                  </IconButton>
                </Box>
              </Tooltip>
              {/* 네이티브 textarea를 유지한다 — 자동 높이(useChat의 useLayoutEffect)가 이 노드의
                  style.height를 직접 만진다. MUI의 다중행 입력은 자기 나름의 리사이즈를 또 하므로
                  둘이 겹치면 첫 글자에서 높이가 튄다. */}
              <Box
                component="textarea" ref={textareaRef} rows={1} value={text} maxLength={5000}
                aria-label="메시지 입력" disabled={composerLocked}
                placeholder="메시지를 입력하세요 (Enter 전송, Shift+Enter 줄바꿈)"
                onChange={(e) => setText(e.target.value)}
                onFocus={() => setComposerFocused(true)}
                onBlur={() => setComposerFocused(false)}
                onKeyDown={(e) => { if (e.nativeEvent.isComposing || e.keyCode === 229) return; if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); } }}
                sx={{
                  flex: 1, minWidth: 0, resize: "none", minHeight: "2.75rem", maxHeight: "10rem", boxSizing: "border-box",
                  font: "inherit", fontSize: "0.9375rem", lineHeight: 1.5, px: 1.75, py: 1.25,
                  border: 1, borderColor: "divider", borderRadius: 2.5,
                  bgcolor: "background.default", color: "text.primary",
                  transition: "border-color .15s ease, box-shadow .15s ease",
                  "&:focus": { outline: "none", borderColor: "primary.main", boxShadow: (t) => `0 0 0 3px ${alpha(t.palette.primary.main, 0.16)}` },
                  "&:disabled": { opacity: 0.6 },
                }}
              />
              <Button variant="primary" onClick={() => doSend()} disabled={inputDisabled || (!text.trim() && !pending.length)}
                sx={{ flexShrink: 0, minHeight: "2.75rem" }}>
                <SendRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem", mr: 0.5 }} />전송
              </Button>
            </Box>
          </Box>
        </Paper>
      </Box>

      {/* 컨텍스트 레일(≥xxl) — 러너가 돌려준 구조화 결과. 예전엔 말풍선 안에 끼어 스레드를 밀어냈다.
          폭이 남을 때만 존재하고, 그 아래에서는 지금까지처럼 말풍선 안에 그린다(같은 CardStack). */}
      {railOpen ? (
        <Box
          component="aside" aria-label="결과"
          sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, borderLeft: 1, borderColor: "divider", bgcolor: "background.paper" }}
        >
          <Box sx={{ px: 3, py: 1.25, borderBottom: 1, borderColor: "divider", display: "flex", alignItems: "center", gap: 1, flexShrink: 0 }}>
            <Typography component="h2" sx={{ flex: 1, minWidth: 0, fontSize: "0.9375rem", fontWeight: 750 }}>결과</Typography>
            {railMsg && railMsg.created_at ? (
              <Typography sx={{ fontSize: "0.75rem", color: "text.secondary" }}>{fmtTime(railMsg.created_at)}</Typography>
            ) : null}
          </Box>
          <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", p: 3 }}>
            {railPayload ? (
              <>
                {/* 순번과 '상세' 원탭은 스레드와 정확히 같은 규칙으로 준다 — 마지막 어시스턴트
                    메시지일 때만 살아 있다(옛 결과의 'N번 상세'는 지금 맥락의 엉뚱한 티켓을 가리킨다). */}
                <CardStack payload={railPayload} startNo={ticketPageStart(railMsg.structured, railMsg.content || "")}
                  onChoose={railIsLast ? doSend : undefined} sending={sending} gap={1.5} />
                {!railIsLast ? (
                  <Typography sx={{ mt: 2, fontSize: "0.75rem", color: "text.secondary" }}>
                    대화가 이어져 이 결과는 지난 답변의 것입니다. 새 결과를 받으면 여기가 바뀝니다.
                  </Typography>
                ) : null}
              </>
            ) : (
              <Box sx={{ display: "grid", justifyItems: "center", textAlign: "center", gap: 1, color: "text.secondary", py: 4 }}>
                <MascotPose mode="sleep" size="4.5rem" decorative />
                <Typography sx={{ fontSize: "0.875rem" }}>아직 표시할 결과가 없습니다.</Typography>
                <Typography sx={{ fontSize: "0.8125rem", maxWidth: "24rem", lineHeight: 1.6 }}>
                  티켓, 프로젝트를 조회하면 그 결과 카드가 여기에 모입니다. 스레드는 대화만 남습니다.
                </Typography>
              </Box>
            )}
          </Box>
        </Box>
      ) : null}
    </Box>
      </Card>
    </Box>
  );
}
