import React, { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import { Button } from "../../ui/kit.jsx";
import {
  copyText, fmtDateSep, fmtTime, msgAgeMs, responseTimeLabel, structuredCards,
  stripDuplicatedTicketLines, ticketPageStart,
} from "../chat-helpers.js";
import { BUBBLE_MAX } from "./layout.js";
import { RichText } from "./RichText.jsx";
import { CardStack } from "./TicketCard.jsx";

// ── 메시지 ──────────────────────────────────────────────────────────────────

export function Message({ m, onChoose, onRetry, sending, retrying, isLast, hideCards }) {
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
  const attachCaveat = "전송 후 이미지 원본은 저장되지 않습니다. 파일 이름만 남습니다.";
  // AI-08: 러너가 돌려주는 실제 처리 시간(structured.timing) — 있을 때만(정상 응답에만 실린다).
  const responseTime = isAssistant ? responseTimeLabel(m) : null;

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
              ? "처리하지 못했습니다. 다시 시도해도 같은 결과가 나올 가능성이 높습니다. 질문을 다르게 표현해 새로 물어보세요."
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
        {/* AI-08: 러너가 이미 계산해 저장까지 해 둔 실제 처리 시간을 화면이 그냥 버리고 있었다. */}
        {responseTime ? (
          <Typography sx={{ fontSize: "0.75rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}
            title="답변 처리 시간">
            {responseTime}
          </Typography>
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
 * 마스코트는 상단바에 있어 스레드 맨 아래를 보고 있는 눈에는 안 들어온다.
 *
 * AI-08: 점 3개가 무한 반복되는 애니메이션 하나뿐이라 1초를 기다리나 1분을 기다리나 화면이
 * 똑같아 보였다("진행 표시가 가짜"). since(대기를 시작한 사용자 메시지의 created_at)가
 * 있으면 1초마다 다시 그려 실제 경과 시간을 함께 보여준다 — 진행률이 아니라 "아직 살아
 * 있다 + 지금까지 이만큼 걸렸다"는 정직한 사실이다(응답이 몇 초 걸릴지는 예측하지 않는다). */
export function TypingBubble({ since }) {
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!since) return undefined;
    const t = window.setInterval(() => forceTick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [since]);
  const elapsedSec = since ? Math.floor(msgAgeMs({ created_at: since }) / 1000) : null;
  return (
    <Paper
      elevation={0}
      sx={{
        alignSelf: "flex-start", px: 2, py: 1.5, borderRadius: 3, borderBottomLeftRadius: "0.375rem",
        bgcolor: "background.paper", border: 1, borderColor: "divider",
      }}
    >
      {/* 초 단위 경과는 매초 바뀌지만 aria-live로 반복 낭독하지 않는다 — 폴링 낭독 과잉(위
          Chat.jsx 주석)과 같은 실수를 여기서 반복하지 않는다, 처음 나타날 때 한 번만 전해진다. */}
      <span className="sr-only">도우미: 답변을 작성하고 있습니다.</span>
      <Box aria-hidden="true" sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
        <Box sx={{ display: "inline-flex", gap: 0.625, alignItems: "center" }}>
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
        {elapsedSec != null ? (
          <Typography sx={{ fontSize: "0.75rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
            {elapsedSec}초
          </Typography>
        ) : null}
      </Box>
    </Paper>
  );
}

/* 스레드 안 날짜 구분선 — 말풍선 라벨은 시:분만 보여줘 사흘 전 15:23과 오늘 15:23이 구분되지
   않았다. 날짜가 바뀌는 지점에만 가운데 칩을 끼워 넣는다. */
export function DaySeparator({ at }) {
  const label = fmtDateSep(at);
  return (
    <Box role="separator" aria-label={label} sx={{ display: "flex", alignItems: "center", gap: 1.5, alignSelf: "stretch", my: 0.5 }}>
      <Box sx={{ flex: 1, height: "1px", bgcolor: "divider" }} />
      <Chip size="small" label={label} sx={{ fontSize: "0.75rem", height: "1.5rem" }} />
      <Box sx={{ flex: 1, height: "1px", bgcolor: "divider" }} />
    </Box>
  );
}
