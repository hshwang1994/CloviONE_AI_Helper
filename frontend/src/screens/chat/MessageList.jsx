import React from "react";
import Box from "@mui/material/Box";
import ArrowDownwardRoundedIcon from "@mui/icons-material/ArrowDownwardRounded";
import { Button, Callout } from "../../ui/kit.jsx";
import { dayKeyKST } from "../chat-helpers.js";
import { THREAD_MAX } from "./layout.js";
import { DaySeparator, Message, TypingBubble } from "./MessageThread.jsx";

/* AI 도우미 메시지 목록 — **전체 화면(`/chat`)과 클로비 패널이 같은 부품이다**(D-557).
 *
 * 목록은 자기 스크롤 칸이다(`overflow-y:auto`, flex 열). 스레드 기둥은 `THREAD_MAX`(52rem)까지이고 가운데에 선다 — 결과 목록과
 * 코드는 기둥 폭을, 글은 그보다 좁은 `ANSWER_TEXT_MAX` 를 쓴다(`MessageThread`).
 *
 * 따라가기: 바닥 근처(`useChat` 의 `stick`)일 때만 새 답에 맞춰 내려가고(긴 답은 그 첫 줄에서 멈춘다), 위를 읽고 있으면
 * 「맨 아래로」 단추가 뜬다. 대화마다 읽던 자리를 기억한다(`useChat`). */
export function MessageList({
  chat, empty, progressLabel, faces, variant = "page", panelDocked = false, selectedAnswerId = null, onShowSources, sx,
}) {
  const {
    items, awaitingReply, stalled, lastMsg, thread, bodyRef, onScroll, stick, setStick,
    retryingRef, doRetry, doRegenerate, regenerating, doDeleteMessage, doFeedback, setResumedAt, threadFailure,
  } = chat;
  const page = variant === "page";
  const hasThread = items.length > 0;

  return (
    <Box
      ref={bodyRef} onScroll={onScroll} data-chat-thread=""
      sx={{
        position: "relative", flex: 1, minHeight: 0, overflowY: "auto", overflowAnchor: "auto",
        px: page ? { xs: 2, sm: 3 } : 2, py: page ? 3 : 2,
        display: "flex", flexDirection: "column", ...sx,
      }}
    >
      {/* flex:1 0 auto — 내용이 짧아도 열이 스크롤 높이를 꽉 채워 환영 화면의 margin:auto 가 세로 가운데를 잡는다. */}
      <Box sx={{ width: "100%", maxWidth: page ? THREAD_MAX : "100%", mx: "auto", flex: "1 0 auto", display: "flex",
                 flexDirection: "column", gap: page ? 3 : 2, minWidth: 0 }}>
        {!hasThread ? empty : (
          <>
            {/* 폴링이 일시 실패해도 읽던 메시지를 지우지 않는다 — 작은 안내만 띄우고 스레드는 유지. */}
            {thread && thread.isError ? (
              <Callout tone="warn" compact sx={{ alignSelf: "center" }}
                action={<Button size="sm" onClick={() => thread.refetch()}>새로고침</Button>}>
                연결이 잠시 끊겼습니다.
              </Callout>
            ) : null}
            {items.map((m, i) => {
              const prev = i > 0 ? items[i - 1] : null;
              const dk = dayKeyKST(m.created_at);
              const showSep = !!dk && (!prev || dayKeyKST(prev.created_at) !== dk);
              const face = faces ? (m.role === "user" ? faces.user : faces.assistant) : null;
              return (
                <React.Fragment key={m.id}>
                  {showSep ? <DaySeparator at={m.created_at} /> : null}
                  <Message m={m} onRetry={doRetry}
                    retrying={retryingRef.current === m.id} isLast={i === items.length - 1}
                    face={face} compact={!page}
                    onRegenerate={doRegenerate} regenerating={regenerating}
                    onDelete={doDeleteMessage} onFeedback={doFeedback}
                    panelDocked={panelDocked} panelSelected={selectedAnswerId === m.id} onShowSources={onShowSources} />
                </React.Fragment>
              );
            })}
            {awaitingReply ? (
              <TypingBubble since={lastMsg && lastMsg.created_at} label={progressLabel} face={faces ? faces.thinking || faces.assistant : null} />
            ) : null}
            {stalled ? (
              <Callout tone="warn" compact sx={{ alignSelf: "flex-start" }}
                action={<Button size="sm" onClick={() => { setResumedAt(Date.now()); thread.refetch(); }}>새로고침</Button>}>
                응답이 지연되고 있습니다.
              </Callout>
            ) : null}
            {threadFailure ? (
              <Callout tone="danger" compact sx={{ alignSelf: "flex-start" }}>{threadFailure}</Callout>
            ) : null}
          </>
        )}
        {/* 스크롤 칸 안에서 sticky 로 뜬다 — 입력창 높이와 무관하게 늘 그 위에 선다. */}
        {hasThread && !stick ? (
          <Box sx={{ position: "sticky", bottom: 0, alignSelf: "center", mt: "auto", pt: 1, zIndex: 5 }}>
            <Button size="sm" onClick={() => setStick(true)} sx={{ boxShadow: 6 }}>
              <ArrowDownwardRoundedIcon aria-hidden="true" sx={{ fontSize: "1rem", mr: 0.5 }} />맨 아래로
            </Button>
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
