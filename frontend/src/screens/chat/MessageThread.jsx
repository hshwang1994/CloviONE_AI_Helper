import React, { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import ThumbDownOutlinedIcon from "@mui/icons-material/ThumbDownOutlined";
import ThumbDownRoundedIcon from "@mui/icons-material/ThumbDownRounded";
import ThumbUpOutlinedIcon from "@mui/icons-material/ThumbUpOutlined";
import ThumbUpRoundedIcon from "@mui/icons-material/ThumbUpRounded";
import { Button, OverflowMenu, Tag } from "../../ui/kit.jsx";
import { Disclosure } from "../../ui/Disclosure.jsx";
import { CHAT } from "../../ui/chat.js";
import { ChatDaySeparator } from "../../ui/ChatDaySeparator.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { objectParticle } from "../../lib/format.js";
import {
  checkedTools, copyText, elapsedLabel, fmtDateSep, fmtTime, msgAgeMs, searchedWords, toolCountLabel,
} from "../chat-helpers.js";
import { ANSWER_TEXT_MAX, USER_BUBBLE_MAX } from "./layout.js";
import { RichText } from "./RichText.jsx";
import { ResultBlock } from "./results/ResultList.jsx";
import {
  SourceList, citesSources, messageSources, panelSources, shownBlocks, visibleSources,
} from "./SourceList.jsx";

/* AI 도우미의 말 한 덩이 — **전체 화면(`/chat`)과 클로비 패널이 같은 부품이다**(D-557).
 *
 * 도우미 답은 채운 말풍선이 아니라 글 기둥이다(AI 채팅 개선 회차): 클로비 얼굴이 첫 줄에 맞춰 서고, 글은 읽기 좋은 폭
 * (`ANSWER_TEXT_MAX`)까지, 결과 목록 · 카드 · 코드는 스레드 폭까지 쓴다. 예전에는 넓은 가운데 칸에서도 답이 72자 말풍선에 몰렸다.
 * 내 말은 오른쪽 Primary 말풍선이다(RULES §9). 시각 · 걸린 시간 · 동작은 본문보다 낮은 강조의 한 줄이고, 삭제는 「더 보기」
 * 안에 있다(실수로 누르지 않게 — 누르면 확인을 받는다). */

/* 「확인한 내용」 한 줄 — 도구 이름과 검색어를 문장으로 말하고, 서버가 센 수가 있으면 뒤에 「(25건 중 8건)」을 붙인다(D-567). */
function checkedLine(tool) {
  const sentence = tool.query
    ? `${tool.label}에서 「${tool.query}」${objectParticle(tool.query)} 찾았습니다.`
    : `${tool.label}${objectParticle(tool.label)} 확인했습니다.`;
  const counted = toolCountLabel(tool);
  return counted ? `${sentence} (${counted})` : sentence;
}

/** 답 동작 줄의 아이콘 단추 — 같은 크기(테마의 작은 아이콘 단추 30)와 같은 간격이다. 이름은 낭독용으로도 쓴다. */
function ActionIcon({ label, tip, onClick, pressed, disabled, children }) {
  return (
    <Tooltip title={tip || label}>
      <span>
        <IconButton size="small" aria-label={label} aria-pressed={pressed} disabled={disabled} onClick={onClick}
          sx={{ color: pressed ? "primary.main" : "text.secondary" }}>
          {children}
        </IconButton>
      </span>
    </Tooltip>
  );
}

const META_SX = { fontSize: FONT_SIZE.caption, color: "text.secondary", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" };

function UserMessage({ m, face, onRetry, retrying, onDelete }) {
  const st = m.structured || {};
  const attachments = Array.isArray(st.attachments) ? st.attachments : [];
  const processing = m.processing_status === "pending" || m.processing_status === "processing";
  const failed = m.processing_status === "failed";
  return (
    <Box data-message-id={m.id} data-message-role="user"
      sx={{ display: "flex", flexDirection: "row-reverse", alignItems: "flex-start", gap: 1, alignSelf: "flex-end",
            maxWidth: USER_BUBBLE_MAX, minWidth: 0,
            "& .msg-menu": { opacity: 0 }, "&:hover .msg-menu, &:focus-within .msg-menu, &:has([aria-expanded='true']) .msg-menu": { opacity: 1 },
            "@media (hover: none)": { "& .msg-menu": { opacity: 1 } } }}>
      {face ? <Box aria-hidden="true" sx={{ flexShrink: 0, pt: "0.125rem" }}>{face}</Box> : null}
      <Box sx={{ display: "grid", justifyItems: "end", gap: 0.5, minWidth: 0 }}>
        <Box sx={{ px: 1.75, py: 1.125, minWidth: 0, maxWidth: "100%", borderRadius: `${CHAT.bubbleRadius}px`,
                   borderStartEndRadius: `${CHAT.bubbleJoinRadius}px`, bgcolor: "primary.main", color: "primary.contrastText" }}>
          <span className="sr-only">나: </span>
          {m.content ? (
            <Typography sx={{ m: 0, fontSize: FONT_SIZE.body, lineHeight: 1.6, whiteSpace: "pre-wrap", ...KO_WORD_BREAK }}>{m.content}</Typography>
          ) : null}
          {attachments.length ? (
            <>
              <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 1 }}>
                {/* 서버는 이미지 바이트를 저장하지 않는다(app/chat/service.py) — 전송 후엔 파일명 칩만 남는다. */}
                {attachments.map((name, i) => (
                  <Tag key={i} label={typeof name === "string" ? name : (name && name.filename) || "첨부"} />
                ))}
              </Stack>
              <Typography sx={{ mt: 0.5, fontSize: FONT_SIZE.caption, opacity: 0.8 }}>
                전송 후 이미지 원본은 저장되지 않습니다. 파일 이름만 남습니다.
              </Typography>
            </>
          ) : null}
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minHeight: "1.875rem" }}>
          {failed ? (
            <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "error.strong" }}>
              처리하지 못했습니다.{" "}
              <Button size="sm" variant="ghost" loading={retrying} onClick={() => { if (!retrying) onRetry(m); }}>다시 시도</Button>
            </Typography>
          ) : null}
          {m.created_at ? <Box component="time" dateTime={m.created_at} sx={META_SX}>{fmtTime(m.created_at)}</Box> : null}
          {onDelete && !processing ? (
            <Box className="msg-menu" sx={{ transition: "opacity .12s ease" }}>
              <OverflowMenu size="sm" ariaLabel="질문 더 보기"
                items={[{ key: "delete", label: "메시지 삭제", tone: "danger", onClick: () => onDelete(m) }]} />
            </Box>
          ) : null}
        </Box>
      </Box>
    </Box>
  );
}

function AnswerMessage({
  m, face, isLast, compact, onRetry, retrying, onRegenerate, regenerating, onDelete, onFeedback,
  panelDocked, panelSelected, onShowSources,
}) {
  const st = m.structured || {};
  const errorNotice = !!st.error_notice;
  const processing = m.processing_status === "pending" || m.processing_status === "processing";
  const failed = m.processing_status === "failed";
  const [copied, setCopied] = useState("");
  const [showChecked, setShowChecked] = useState(false);
  const content = m.content || "";
  /* 답 안의 링크와 티켓 키는 **이 답의 출처에 있는 것만** 링크가 된다(D-538 · D-569) — 모델이 지어낸 경로나 키는 글자로 남는다. */
  const sources = !errorNotice ? messageSources(st) : [];
  const linkable = visibleSources(sources);
  const keyLinks = new Map(linkable.filter((s) => s.type === "ticket" && s.key).map((s) => [s.key, s.route]));
  const routeLinks = new Set(linkable.map((s) => s.route));
  const blocks = !errorNotice ? shownBlocks(st) : [];
  const panel = !errorNotice ? panelSources(st) : [];
  /* 답이 아무 출처도 쓰지 않았으면(찾지 못함 · 뜻만 가까운 문서) 「참고 자료」가 아니라 접힌 「찾아본 자료」다(P-133). */
  const searchedOnly = linkable.length > 0 && !citesSources(st);
  const tools = !errorNotice ? checkedTools(st) : [];
  const words = st.notice === "no_results" ? searchedWords(st) : [];
  const elapsed = !errorNotice ? elapsedLabel(st) : null;
  const canAct = !!content && !processing && !errorNotice;
  const menu = [
    tools.length ? { key: "checked", label: showChecked ? "확인한 내용 접기" : "확인한 내용 보기", onClick: () => setShowChecked((v) => !v) } : null,
    onDelete && !processing ? { key: "delete", label: "메시지 삭제", tone: "danger", onClick: () => onDelete(m) } : null,
  ].filter(Boolean);

  return (
    <Box data-message-id={m.id} data-message-role="assistant"
      sx={{ display: "grid", gridTemplateColumns: face ? "2.125rem minmax(0,1fr)" : "minmax(0,1fr)", columnGap: 1.25,
            alignItems: "start", width: "100%", minWidth: 0 }}>
      {face ? <Box aria-hidden="true" sx={{ display: "flex", justifyContent: "center" }}>{face}</Box> : null}
      <Box sx={{ minWidth: 0, display: "grid", gap: 1.25 }}>
        {/* 답은 말풍선이 아니라 글 기둥이다 — 이 자리는 칠한 AI 면이 아니라고 프로브(`scripts/ui_qa/brand.py`)에 선언한다. */}
        <Box data-brand-role="none"
          sx={{ maxWidth: ANSWER_TEXT_MAX, minWidth: 0, pt: face ? "0.3125rem" : 0, ...(errorNotice ? { color: "text.secondary" } : null) }}>
          <span className="sr-only">도우미: </span>
          {content ? <RichText text={content} keyLinks={keyLinks} routeLinks={routeLinks} /> : null}
        </Box>
        {/* 「찾지 못함」은 정상 답이다(오류색이 아니다) — 무엇을 찾았는데 없었는지와 다음 길을 함께 둔다. */}
        {words.length ? (
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
            찾아본 검색어는 {words.join(", ")}입니다.{" "}
            <Box component="a" href={"#/ai?q=" + encodeURIComponent(words[0])} sx={{ color: "primary.main" }}>문서에서 찾기</Box>
          </Typography>
        ) : null}
        {st.mode === "search_only" && !errorNotice ? (
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
            도구를 쓸 수 없어 검색 결과로만 답했습니다.
          </Typography>
        ) : null}
        {blocks.map((block) => (
          <ResultBlock key={block.id} block={block} messageId={m.id} compact={compact} />
        ))}
        {!panelDocked && panel.length ? (
          <Disclosure title={`참고 자료 ${panel.length}개`} sx={{ "& .k-disclosure-panel": { pt: 0.75 } }}>
            <SourceList sources={panel} title={null} limit={8} />
          </Disclosure>
        ) : null}
        {searchedOnly ? (
          <Disclosure title={`찾아본 자료 ${linkable.length}개`} sx={{ "& .k-disclosure-panel": { pt: 0.75 } }}>
            <SourceList sources={sources} title={null} note="답을 찾는 동안 살펴봤지만 답에는 쓰지 않은 자료입니다." />
          </Disclosure>
        ) : null}
        {showChecked && tools.length ? (
          <Box component="ul" role="list" aria-label="확인한 내용" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.25 }}>
            {tools.map((tool, i) => (
              <Box key={i} component="li" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
                {checkedLine(tool)}
              </Box>
            ))}
          </Box>
        ) : null}
        {failed ? (
          <Typography sx={{ fontSize: FONT_SIZE.bodySm, color: "error.strong" }}>
            처리하지 못했습니다.{" "}
            <Button size="sm" variant="ghost" loading={retrying} onClick={() => { if (!retrying) onRetry(m); }}>다시 시도</Button>
          </Typography>
        ) : null}
        {/* 동작 줄 — 같은 크기 · 같은 간격의 아이콘 단추와 「더 보기」(삭제 · 확인한 내용)가 한 덩어리이고, 오른쪽에 낮은 강조의 걸린
            시간 · 시각이 선다. 좁은 폭에서는 시각 쪽이 다음 줄로 내려간다(「더 보기」 하나만 떨어져 내려가지 않는다). */}
        <Box role="group" aria-label="답 동작"
          sx={{ display: "flex", alignItems: "center", gap: 0.25, flexWrap: "wrap", minHeight: "1.875rem", ml: "-0.375rem" }}>
          {canAct ? (
            <>
              <ActionIcon label={copied === "복사했습니다" ? "복사했습니다" : "답 복사"}
                onClick={() => copyText(m.content).then((ok) => { setCopied(ok ? "복사했습니다" : "복사하지 못했습니다"); setTimeout(() => setCopied(""), 1500); })}>
                {copied === "복사했습니다" ? <CheckRoundedIcon sx={{ fontSize: "1rem" }} /> : <ContentCopyRoundedIcon sx={{ fontSize: "0.9375rem" }} />}
              </ActionIcon>
              <span className="sr-only" role="status" aria-live="polite">{copied}</span>
              {/* 다시 만들기는 대화의 마지막 답에서만 — 중간 차례를 바꾸면 그 뒤 맥락과 어긋난다(백엔드 _is_last_turn 과 대칭). */}
              {isLast && onRegenerate ? (
                <ActionIcon label="답 다시 만들기" disabled={!!regenerating} onClick={onRegenerate}>
                  <RefreshRoundedIcon sx={{ fontSize: "1rem" }} />
                </ActionIcon>
              ) : null}
              {onFeedback ? (
                <>
                  <ActionIcon label="좋은 답변" tip={m.feedback === "up" ? "좋은 답변 표시 취소" : "좋은 답변"} pressed={m.feedback === "up"}
                    onClick={() => onFeedback(m, "up")}>
                    {m.feedback === "up" ? <ThumbUpRoundedIcon sx={{ fontSize: "1rem" }} /> : <ThumbUpOutlinedIcon sx={{ fontSize: "1rem" }} />}
                  </ActionIcon>
                  <ActionIcon label="아쉬운 답변" tip={m.feedback === "down" ? "아쉬운 답변 표시 취소" : "아쉬운 답변"} pressed={m.feedback === "down"}
                    onClick={() => onFeedback(m, "down")}>
                    {m.feedback === "down" ? <ThumbDownRoundedIcon sx={{ fontSize: "1rem", color: "error.main" }} /> : <ThumbDownOutlinedIcon sx={{ fontSize: "1rem" }} />}
                  </ActionIcon>
                </>
              ) : null}
              {panelDocked && panel.length && onShowSources ? (
                <Button size="sm" variant="ghost" aria-pressed={!!panelSelected} onClick={() => onShowSources(m.id)}
                  sx={{ ml: 0.5, ...(panelSelected ? { color: "primary.main", fontWeight: FONT_WEIGHT.semibold } : null) }}>
                  참고 자료 {panel.length}
                </Button>
              ) : null}
            </>
          ) : null}
          {menu.length ? <OverflowMenu size="sm" ariaLabel="답 더 보기" items={menu} /> : null}
          <Box sx={{ flex: 1, minWidth: "0.5rem" }} />
          {/* 걸린 시간은 서버가 잰 한 차례의 시간이다(`structured.elapsed_ms`). 시각과 붙어 한 덩어리로 읽히지 않게 이름을 붙인다. */}
          <Box component="span" sx={{ display: "inline-flex", alignItems: "center", ml: "auto" }}>
            {elapsed ? <Typography component="span" sx={{ ...META_SX, mr: 1 }} title="답을 만드는 데 걸린 시간">{elapsed} 걸림</Typography> : null}
            {m.created_at ? <Box component="time" dateTime={m.created_at} sx={{ ...META_SX, mr: 0.5 }}>{fmtTime(m.created_at)}</Box> : null}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

export function Message(props) {
  return props.m.role === "user" ? <UserMessage {...props} /> : <AnswerMessage {...props} />;
}

/* 답을 기다리는 동안 — 답이 설 자리(클로비 얼굴 옆)에 서버의 진행 문구와 경과 초를 둔다. 진행 문구는 「질문을 살펴보고 있습니다」
 * → 「내 문서를 확인하고 있습니다」 같은 도구별 문장 → 「찾은 내용으로 답을 정리하고 있습니다」 순이다(도구 이름은 보이지 않는다).
 * 경과는 진행률이 아니라 「아직 살아 있다 + 이만큼 걸렸다」는 사실이다. */
export function TypingBubble({ since, label, face = null }) {
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!since) return undefined;
    const t = window.setInterval(() => forceTick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [since]);
  const elapsedSec = since ? Math.floor(msgAgeMs({ created_at: since }) / 1000) : null;
  return (
    <Box data-typing-indicator=""
      sx={{ display: "grid", gridTemplateColumns: face ? "2.125rem minmax(0,1fr)" : "minmax(0,1fr)", columnGap: 1.25,
            alignItems: "center", width: "100%" }}>
      {face ? <Box aria-hidden="true" sx={{ display: "flex", justifyContent: "center" }}>{face}</Box> : null}
      <Box data-brand-role="none" sx={{ display: "inline-flex", alignItems: "center", gap: 1, minWidth: 0, minHeight: "2.125rem" }}>
        {/* 초 단위 경과는 매초 바뀌지만 aria-live 로 되풀이해 읽지 않는다 — 처음 나타날 때 한 번만 전해진다. */}
        <span className="sr-only">{"도우미: " + (label || "답변을 작성하고 있습니다.")}</span>
        <Box aria-hidden="true" sx={{ display: "inline-flex", gap: 0.625, alignItems: "center" }}>
          {[0, 1, 2].map((i) => (
            <Box key={i}
              sx={{
                width: "0.4375rem", height: "0.4375rem", borderRadius: "50%", bgcolor: "primary.main",
                animation: "chat-bounce 1.3s ease-in-out infinite both", animationDelay: i * 0.16 + "s",
                "@keyframes chat-bounce": {
                  "0%, 70%, 100%": { transform: "translateY(0)", opacity: 0.45 },
                  "35%": { transform: "translateY(-0.375rem)", opacity: 1 },
                },
              }}
            />
          ))}
        </Box>
        <Box aria-hidden="true" sx={{ display: "inline-flex", alignItems: "baseline", gap: 1, minWidth: 0 }}>
          {label ? <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}>{label}</Typography> : null}
          {elapsedSec != null ? <Typography component="span" sx={META_SX}>{elapsedSec}초</Typography> : null}
        </Box>
      </Box>
    </Box>
  );
}

/* 스레드 안 날짜 구분선 — 팀 채팅(`ChatPane`)과 **같은 부품**이다(`ui/ChatDaySeparator.jsx`). */
export function DaySeparator({ at }) {
  return <ChatDaySeparator label={fmtDateSep(at)} />;
}
