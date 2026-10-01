import React, { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import ThumbDownOutlinedIcon from "@mui/icons-material/ThumbDownOutlined";
import ThumbDownRoundedIcon from "@mui/icons-material/ThumbDownRounded";
import ThumbUpOutlinedIcon from "@mui/icons-material/ThumbUpOutlined";
import ThumbUpRoundedIcon from "@mui/icons-material/ThumbUpRounded";
import { Button, Tag } from "../../ui/kit.jsx";
import { CHAT } from "../../ui/chat.js";
import { ChatDaySeparator } from "../../ui/ChatDaySeparator.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";
import { objectParticle } from "../../lib/format.js";
import {
  checkedTools, copyText, elapsedLabel, fmtDateSep, fmtTime, msgAgeMs, searchedWords,
} from "../chat-helpers.js";
import { BUBBLE_MAX } from "./layout.js";
import { RichText } from "./RichText.jsx";
import { SourceList, messageSources, safeSourceRoute } from "./SourceList.jsx";

// ── 메시지 ──────────────────────────────────────────────────────────────────

export function Message({
  m, onRetry, retrying, isLast, showSources = true,
  onRegenerate, regenerating, onDelete, onFeedback,
}) {
  const st = m.structured || {};
  const attachments = Array.isArray(st.attachments) ? st.attachments : [];
  const errorNotice = !!st.error_notice; // 오류 안내 말풍선엔 '복사'를 붙이지 않는다.
  const processing = m.processing_status === "pending" || m.processing_status === "processing";
  const failed = m.processing_status === "failed";
  const [copied, setCopied] = useState("");
  const [showChecked, setShowChecked] = useState(false);
  const isUser = m.role === "user";
  const isAssistant = m.role === "assistant";
  const content = m.content || "";
  /* 도우미 답의 구조(D-535) — 출처 · 확인한 내용 · 걸린 시간은 서버가 잰 값만 보인다. 옛 답(근거 검색 시절)의 인용은
     문서 출처로 옮겨 그린다(`messageSources`). */
  const sources = isAssistant && !errorNotice ? messageSources(st) : [];
  const keyLinks = new Map(sources
    .filter((s) => s.type === "ticket" && s.key && safeSourceRoute(s.route))
    .map((s) => [s.key, s.route]));
  const tools = isAssistant && !errorNotice ? checkedTools(st) : [];
  const words = isAssistant && st.notice === "no_results" ? searchedWords(st) : [];
  const elapsed = isAssistant && !errorNotice ? elapsedLabel(st) : null;
  const attachCaveat = "전송 후 이미지 원본은 저장되지 않습니다. 파일 이름만 남습니다.";

  return (
    <Box
      sx={{
        display: "flex", flexDirection: "column", gap: 0.75, minWidth: 0,
        maxWidth: BUBBLE_MAX,
        alignSelf: isUser ? "flex-end" : "flex-start",
        alignItems: isUser ? "flex-end" : "flex-start",
      }}
    >
      {/* 말풍선 — 화자 구분은 정렬과 면이다(내 말은 강조색 면, 도우미 말은 안쪽 면). 반지름은 채팅 전용 규격
          (`ui/chat.js::CHAT`)을 채팅방과 함께 쓴다. */}
      <Box
        sx={{
          px: 2, py: 1.5, minWidth: 0, maxWidth: "100%",
          fontSize: FONT_SIZE.body, lineHeight: 1.6, ...KO_WORD_BREAK,
          borderRadius: `${CHAT.bubbleRadius}px`,
          ...(isUser
            ? { bgcolor: "primary.main", color: "primary.contrastText" }
            : { bgcolor: "background.inset" }),
        }}
      >
        {/* 화자 구분은 색/정렬뿐이라 스크린리더엔 안 들린다, 텍스트로도 알린다. */}
        <span className="sr-only">{isUser ? "나: " : "도우미: "}</span>
        {/* 도우미 답은 머리글, 목록, 키-값으로 구조화(텍스트 노드 전용). 글 속 티켓 키는 그 답의 출처에 있을 때만 링크다. */}
        {content ? (isAssistant ? <RichText text={content} keyLinks={keyLinks} /> : (
          <Typography sx={{ m: 0, fontSize: FONT_SIZE.body, lineHeight: 1.6, whiteSpace: "pre-wrap", ...KO_WORD_BREAK }}>{content}</Typography>
        )) : null}
        {attachments.length ? (
          <>
            <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 1 }}>
              {/* 서버는 이미지 바이트를 저장하지 않는다(app/chat/service.py) — 전송 후엔 파일명 칩만 남는다. */}
              {attachments.map((name, i) => (
                <Tag key={i} label={typeof name === "string" ? name : (name && name.filename) || "첨부"} />
              ))}
            </Stack>
            <Typography sx={{ mt: 0.5, fontSize: FONT_SIZE.caption, opacity: 0.75, lineHeight: 1.5 }}>{attachCaveat}</Typography>
          </>
        ) : null}
        {/* 「찾지 못함」은 정상 답이다(오류색이 아니다) — 무엇을 찾았는데 없었는지와 다음 길을 함께 둔다. */}
        {words.length ? (
          <Typography sx={{ mt: 1, fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
            찾아본 검색어는 {words.join(", ")}입니다.{" "}
            <Box component="a" href={"#/ai?q=" + encodeURIComponent(words[0])} sx={{ color: "primary.main" }}>문서에서 찾기</Box>
          </Typography>
        ) : null}
        {isAssistant && st.mode === "search_only" && !errorNotice ? (
          <Typography sx={{ mt: 1, fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
            도구를 쓸 수 없어 검색 결과로만 답했습니다.
          </Typography>
        ) : null}
        {showSources && sources.length ? (
          <Box sx={{ mt: 1.5, pt: 1.25, borderTop: 1, borderColor: "divider" }}>
            <SourceList sources={sources} />
          </Box>
        ) : null}
        {tools.length ? (
          <Box sx={{ mt: 1 }}>
            <Button size="sm" variant="ghost" aria-expanded={showChecked} onClick={() => setShowChecked((v) => !v)}>
              {showChecked ? "확인한 내용 접기" : "확인한 내용 보기"}
            </Button>
            {showChecked ? (
              <Box component="ul" role="list" sx={{ listStyle: "none", m: 0, mt: 0.5, p: 0, display: "grid", gap: 0.25 }}>
                {tools.map((tool, i) => (
                  <Box key={i} component="li" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
                    {tool.query
                      ? `${tool.label}에서 「${tool.query}」${objectParticle(tool.query)} 찾았습니다.`
                      : `${tool.label}${objectParticle(tool.label)} 확인했습니다.`}
                  </Box>
                ))}
              </Box>
            ) : null}
          </Box>
        ) : null}
        {failed ? (
          <Typography sx={{ mt: 1, fontSize: FONT_SIZE.bodySm, color: isUser ? "inherit" : "error.main" }}>
            처리하지 못했습니다.{" "}
            {/* 다시 시도는 30 단추다 — 진행 중에는 라벨을 그대로 두고 앞에 진행 표시를 붙인다(라벨 바꿔치기 금지). */}
            <Button size="sm" variant="ghost" loading={retrying}
              onClick={() => { if (!retrying) onRetry(m); }}>
              다시 시도
            </Button>
          </Typography>
        ) : null}
      </Box>

      <Stack direction="row" alignItems="center" gap={0.25}>
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
        {/* 재생성은 대화의 마지막 답변에서만 — 중간 턴을 바꾸면 그 뒤 맥락과 어긋난다(백엔드 _is_last_turn 과 대칭). */}
        {isAssistant && isLast && m.content && !processing && !errorNotice && onRegenerate ? (
          <Tooltip title="다시 생성">
            <span>
              <IconButton size="small" aria-label="답변 다시 생성" disabled={!!regenerating} onClick={onRegenerate}>
                <RefreshRoundedIcon sx={{ fontSize: "1rem" }} />
              </IconButton>
            </span>
          </Tooltip>
        ) : null}
        {/* 피드백 — 같은 값을 다시 누르면 취소한다(doFeedback의 toggle 판정). */}
        {isAssistant && m.content && !processing && !errorNotice && onFeedback ? (
          <>
            <Tooltip title={m.feedback === "up" ? "좋은 답변 표시 취소" : "좋은 답변이에요"}>
              <IconButton size="small" aria-label="좋은 답변" aria-pressed={m.feedback === "up"}
                onClick={() => onFeedback(m, "up")}>
                {m.feedback === "up"
                  ? <ThumbUpRoundedIcon sx={{ fontSize: "1rem", color: "primary.main" }} />
                  : <ThumbUpOutlinedIcon sx={{ fontSize: "1rem" }} />}
              </IconButton>
            </Tooltip>
            <Tooltip title={m.feedback === "down" ? "아쉬운 답변 표시 취소" : "아쉬운 답변이에요"}>
              <IconButton size="small" aria-label="아쉬운 답변" aria-pressed={m.feedback === "down"}
                onClick={() => onFeedback(m, "down")}>
                {m.feedback === "down"
                  ? <ThumbDownRoundedIcon sx={{ fontSize: "1rem", color: "error.main" }} />
                  : <ThumbDownOutlinedIcon sx={{ fontSize: "1rem" }} />}
              </IconButton>
            </Tooltip>
          </>
        ) : null}
        {/* 걸린 시간은 서버가 잰 한 차례의 시간이다(`structured.elapsed_ms`). */}
        {elapsed ? (
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", fontVariantNumeric: "tabular-nums" }}
            title="답을 만드는 데 걸린 시간">
            {/* 이름을 붙인다 — 바로 옆의 보낸 시각과 붙어 「4.2초 오전 11:56」 한 덩어리로 읽혔다(P9 캡처). */}
            걸린 시간 {elapsed}
          </Typography>
        ) : null}
        {m.created_at ? (
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>{fmtTime(m.created_at)}</Typography>
        ) : null}
        {/* 삭제 — 내 대화 안이면 화자와 무관하게 지울 수 있다(소유권은 대화 단위). */}
        {onDelete && !processing && !errorNotice ? (
          <Tooltip title="메시지 삭제">
            <IconButton size="small" aria-label="메시지 삭제" onClick={() => onDelete(m)}>
              <DeleteOutlineRoundedIcon sx={{ fontSize: "1rem" }} />
            </IconButton>
          </Tooltip>
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
export function TypingBubble({ since, label }) {
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!since) return undefined;
    const t = window.setInterval(() => forceTick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [since]);
  const elapsedSec = since ? Math.floor(msgAgeMs({ created_at: since }) / 1000) : null;
  return (
    <Box
      sx={{
        /* 입력 중 말풍선도 말풍선 모서리(12)다 — 도우미 말풍선과 같은 모양이어야 「이 자리에 답이 온다」로 읽힌다(예전 24 는 `CHAT` 토큰 밖). */
        alignSelf: "flex-start", px: 2, py: 1.5, borderRadius: `${CHAT.bubbleRadius}px`, borderEndStartRadius: `${CHAT.bubbleJoinRadius}px`,
        bgcolor: "background.paper", border: 1, borderColor: "divider",
      }}
    >
      {/* 초 단위 경과는 매초 바뀌지만 aria-live로 반복 낭독하지 않는다 — 폴링 낭독 과잉(위
          Chat.jsx 주석)과 같은 실수를 여기서 반복하지 않는다, 처음 나타날 때 한 번만 전해진다. */}
      <span className="sr-only">{"도우미: " + (label || "답변을 작성하고 있습니다.")}</span>
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
        {/* 진행 문구는 서버가 도구마다 적는다(「사내 문서를 찾고 있습니다.」, D-535) — 그 문장과 경과 초를 함께 둔다. */}
        {label ? (
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>{label}</Typography>
        ) : null}
        {elapsedSec != null ? (
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
            {elapsedSec}초
          </Typography>
        ) : null}
      </Box>
    </Box>
  );
}

/* 스레드 안 날짜 구분선 — 말풍선 라벨은 시:분만 보여줘 사흘 전 15:23과 오늘 15:23이 구분되지
   않았다. 날짜가 바뀌는 지점에만 가운데 칩을 끼워 넣는다. */
export function DaySeparator({ at }) {
  /* 팀 채팅(`ChatPane`)과 **같은 부품**이다(`ui/ChatDaySeparator.jsx` — 선 `rule` · 0.75rem/600 · 가운데 28rem). 예전에는 이 화면만
     선 색(`divider`)과 글자(0.8125rem)가 달랐다(UI 3차 조합 계약 C-6). */
  return <ChatDaySeparator label={fmtDateSep(at)} />;
}
