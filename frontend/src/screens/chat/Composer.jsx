import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import AttachFileRoundedIcon from "@mui/icons-material/AttachFileRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import { Button, Callout } from "../../ui/kit.jsx";
import { CONTROL, FONT_SIZE, ICON, RADIUS, remPx } from "../../ui/theme.js";
import { CHAT } from "../../ui/chat.js";
import { unavailableHelp } from "./WelcomeStatus.jsx";

/* AI 도우미 입력창 — **전체 화면(`/chat`)과 클로비 패널이 같은 부품이다**(D-557).
 *
 * 예전에는 둘이 각자 입력창을 그렸다. 패널 쪽은 입력 칸 최소 높이가 44 인데 보내기 단추는 34 라 `align-items:flex-end`
 * 에서 단추가 아래로 처졌고, 안내 문구는 placeholder 뿐이라 글자 수 · 기다리는 중 · 한도 줄이 없었다. 한 줄 높이는
 * 컨트롤 높이(34, D-526)다 — 입력 칸 한 줄 = 단추 자리 = 34 라 한 줄일 때 둘의 세로 중심이 맞고, 입력이 여러 줄로
 * 자라면 단추는 마지막 줄 옆에 남는다(채팅 입력의 관례).
 *
 * 글자 높이: 0.9375rem 글자 · 1.375rem 줄 간격 + 위아래 5px + 테두리 1px = 34px. 자동 늘어남은 `useChat` 의
 * `textareaRef` 레이아웃 효과가 맡는다(최대 160px).
 *
 * 입력은 답을 기다리는 동안에도 열어 둔다(전체 화면과 같다) — 다음 질문을 미리 칠 수 있고, 막힌 것은 보내기 단추와
 * 안내 줄이 말한다. 잠그는 것은 점검 · 속도 제한 · 쓸 수 없음뿐이다. */

export const COMPOSER_LINE = remPx(CONTROL.control);
export const MAX_CHARS = 5000;
/* 글자 수는 상한이 가까워질 때부터 보인다 — 늘 보이면 한 줄짜리 질문에도 숫자가 서서 입력창이 시끄럽다. */
export const COUNT_FROM = 4500;

export function Composer({
  chat, unavailable, assistant, ariaLabel = "메시지 입력", placeholder = "메시지를 입력하세요",
  attach = true, quotaLine = null, showUnavailableNotice = false,
}) {
  const {
    text, setText, pending, setPending, textareaRef, fileRef, pickFiles, doSend,
    inputDisabled, composerLocked, busy, awaitingReply,
    maintenanceNotice, setMaintenanceNotice, rateLimitNotice, setRateLimitNotice,
    composerFailure, setComposerFocused,
  } = chat;
  const canSend = !inputDisabled && !unavailable && (!!text.trim() || pending.length > 0);
  const admin = !!(assistant && assistant.can_configure);

  return (
    <Box sx={{ display: "grid", gap: 1 }}>
      {pending.length ? (
        <>
          {/* Chip 의 onDelete 는 쓰지 않는다 — 삭제 아이콘이 tabIndex=-1 이라 키보드로 첨부를 못 뗀다. 이름 붙은 단추를 둔다. */}
          <Stack direction="row" flexWrap="wrap" gap={0.75}>
            {pending.map((a, i) => (
              <Box key={i}
                sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, pl: 0.5, pr: 0.25, py: 0.25, borderRadius: RADIUS.full, maxWidth: "18rem", border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
                <Box component="img" src={"data:" + (a.media_type || "image/png") + ";base64," + a.data} alt=""
                  sx={{ width: "1.75rem", height: "1.75rem", objectFit: "cover", borderRadius: "50%", flexShrink: 0 }} />
                <Typography sx={{ fontSize: FONT_SIZE.caption, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.filename}</Typography>
                <IconButton size="small" aria-label={"첨부 제거: " + a.filename}
                  onClick={() => setPending((p) => p.filter((_, j) => j !== i))}
                  sx={{ flexShrink: 0 }}>
                  <CloseRoundedIcon sx={{ fontSize: "0.9375rem" }} />
                </IconButton>
              </Box>
            ))}
          </Stack>
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>전송 후에는 이미지 원본이 저장되지 않습니다. 파일 이름만 남습니다.</Typography>
        </>
      ) : null}
      {quotaLine}
      {maintenanceNotice ? (
        <Callout tone="warn" compact action={<Button size="sm" onClick={() => setMaintenanceNotice(null)}>다시 시도</Button>}>
          {maintenanceNotice}
        </Callout>
      ) : null}
      {rateLimitNotice ? (
        <Callout tone="warn" compact action={<Button size="sm" onClick={() => setRateLimitNotice(null)}>닫기</Button>}>
          {rateLimitNotice}
        </Callout>
      ) : null}
      {composerFailure ? <Callout tone="danger" compact>{composerFailure}</Callout> : null}
      {/* 대화를 보는 중에 AI 를 쓸 수 없게 되면 스레드는 그대로 두고 입력 칸 위에서 까닭을 말한다. */}
      {showUnavailableNotice && unavailable && assistant ? (
        <Callout tone="warn" compact action={admin ? <Button size="sm" href="#/ai-connection">AI 연결 열기</Button> : null}>
          {assistant.notice} {unavailableHelp(assistant)}
        </Callout>
      ) : null}
      <Box
        component="form"
        onSubmit={(e) => { e.preventDefault(); if (canSend) doSend(); }}
        sx={{ display: "flex", gap: 1, alignItems: "flex-end" }}
      >
        {attach ? (
          <>
            <Box component="input" ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" multiple
              aria-hidden="true" tabIndex={-1} onChange={(e) => pickFiles(e.target.files)} sx={{ display: "none" }} />
            {/* 첨부는 입력창 도구라 30 이다. 입력 한 줄(34) 안에서 가운데에 선다 — 입력이 여러 줄로 자라도 보내기와 같은 아래 줄에 남는다. */}
            <Tooltip title="이미지 첨부(PNG, JPEG, WebP)">
              <Box component="span" sx={{ flexShrink: 0, height: COMPOSER_LINE, display: "flex", alignItems: "center" }}>
                <IconButton size="small" aria-label="이미지 첨부" disabled={inputDisabled || unavailable}
                  onClick={() => fileRef.current && fileRef.current.click()}
                  sx={{ width: remPx(CHAT.tool), height: remPx(CHAT.tool), border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px` }}>
                  <AttachFileRoundedIcon sx={{ fontSize: remPx(ICON.action) }} />
                </IconButton>
              </Box>
            </Tooltip>
          </>
        ) : null}
        {/* 네이티브 textarea — 자동 높이가 이 노드의 style.height 를 직접 만진다. MUI 다중행 입력과 겹치면 첫 글자에서 높이가 튄다. */}
        <Box
          component="textarea" ref={textareaRef} rows={1} value={text} maxLength={MAX_CHARS}
          aria-label={ariaLabel} disabled={composerLocked || unavailable}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setComposerFocused && setComposerFocused(true)}
          onBlur={() => setComposerFocused && setComposerFocused(false)}
          onKeyDown={(e) => {
            if (e.nativeEvent.isComposing || e.keyCode === 229) return;
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (canSend) doSend(); }
          }}
          sx={{
            flex: 1, minWidth: 0, resize: "none", minHeight: COMPOSER_LINE, maxHeight: "10rem", boxSizing: "border-box",
            font: "inherit", fontSize: "0.9375rem", lineHeight: "1.375rem", px: 1.5, py: "5px",
            border: 1, borderColor: "divider", borderRadius: `${CHAT.composerRadius}px`,
            bgcolor: "background.default", color: "text.primary",
            transition: "border-color .15s ease, box-shadow .15s ease",
            "&:focus": { outline: "none", borderColor: "primary.main", boxShadow: (t) => `0 0 0 3px ${alpha(t.palette.primary.main, 0.16)}` },
            "&:disabled": { opacity: 0.6 },
          }}
        />
        {/* 보내기도 입력창 도구와 같은 30 단추(채움)다 — 입력 한 줄(34) 안에서 가운데. */}
        <Box component="span" sx={{ flexShrink: 0, height: COMPOSER_LINE, display: "flex", alignItems: "center" }}>
          <Button type="submit" variant="primary" size="sm" disabled={!canSend} aria-label="질문 전송">
            <SendRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem", mr: 0.5 }} />전송
          </Button>
        </Box>
      </Box>
      {/* 보조 줄 — 조작법은 placeholder 가 아니라 늘 보이는 글이다(placeholder 는 글자를 치는 순간 사라진다). 글자 수는 상한이
          가까울 때만, 기다리는 중은 그 사실을 말한다(입력은 열려 있어도 보내기는 막힌다). */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 1, minHeight: "1rem", fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
        <Box component="span">Enter 전송, Shift+Enter 줄바꿈</Box>
        {(busy || awaitingReply) && !composerLocked ? (
          <Box component="span" role="status">답변을 기다리는 중입니다.</Box>
        ) : text.length >= COUNT_FROM ? (
          <Box component="span" sx={{ fontVariantNumeric: "tabular-nums" }}>{text.length}/{MAX_CHARS}</Box>
        ) : null}
      </Box>
    </Box>
  );
}
