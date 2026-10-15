import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Button, Callout, EmptyState, Card } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { fmtTime } from "./timeUtils.js";
import { useGameRoomLayout } from "./GameRoomLayout.jsx";
import { personOf } from "./people.js";

/* 오른쪽 레일 아래쪽 — 채팅. 새 채팅이 오면 최신으로 따라 내려가는 자동 스크롤은 useGameRoomController의 effect가 맡고,
 * 여기는 chatLogRef를 받아 그 DOM 노드에 꽂기만 한다.
 *
 * 판은 세로 묶음이다 — 머리 · 로그(자라는 칸) · 컴포저(고정). 채움 · 흐름 모드에서는 레일이 준 높이를 로그가 다 먹고(`flex 1 1 auto;
 * minHeight 0`), 모바일에서는 로그가 `min(45vh, 22rem)` 으로 선다. 컴포저는 어느 모드에서도 판 바닥에 있다.
 *
 * chatMsgs에는 대화(kind="chat")뿐 아니라 안내문이 달린 system 이벤트(방장 위임 등, useGameRoomController::isChatFeedEvent)도
 * 섞여 들어온다 — 팀 채팅(ChatPane.jsx)이 시스템 메시지를 가운데 놓는 것과 같은 자리·같은 모양을 쓴다. 보낸 사람의 얼굴은
 * `people`(신원 스냅샷, G5)로 푼다 — 방을 나간 사람의 말도 얼굴이 남는다. */
export function ChatPanel({ chatLogRef, chatMsgs, you, people, draft, setDraft, sendChat, chatPending, chatFailure }) {
  const { mode } = useGameRoomLayout();
  /* 채움 · 흐름에서는 판(Card)이 받은 높이를 로그가 채운다(흐름은 레일 칸이 22rem 로 선다). 모바일만 로그가 제 높이로 선다. */
  const fill = mode !== "mobile";
  return (
    <Card data-chat-panel="" sx={{ display: "flex", flexDirection: "column", flex: "1 1 auto", minHeight: 0, minWidth: 0 }}>
      <Typography component="h2" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 1, flexShrink: 0 }}>채팅</Typography>
      <Box ref={chatLogRef} data-testid="game-chat-log" sx={{
        display: "flex", flexDirection: "column", gap: 1, overflowY: "auto", overscrollBehavior: "contain", px: 0.5, py: 1, mb: 1.25,
        ...(fill ? { flex: "1 1 auto", minHeight: 0 } : { height: "min(45vh, 22rem)", minHeight: "12rem" }),
      }}>
        {chatMsgs.length === 0 ? (
          // VIS-90 — ChatPane.jsx(팀 채팅)의 같은 빈 상태와 아이콘·문구를 맞춘다(둘이 다르면
          // 사용자는 "다른 채팅 기능"이라고 오해한다).
          <EmptyState size="compact" icon="💬" title="아직 메시지가 없습니다" help="먼저 인사해 보세요." />
        ) : chatMsgs.map((e) => {
          if (e.kind === "system") {
            return (
              /* 시스템 안내 줄 — 팀 채팅(`ChatPane`)과 같은 얼굴(가운데 흐린 낱말)이다. */
              <Typography key={e.seq} sx={{ alignSelf: "center", maxWidth: "100%", textAlign: "center", fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
                {e.payload.text}
              </Typography>
            );
          }
          const mine = e.actor_user_id === you.user_id;
          const sender = personOf(people, e.actor_user_id) || { user_id: e.actor_user_id, name: e.payload.name };
          return (
            <Box key={e.seq} sx={{
              display: "flex", gap: 0.75, maxWidth: "88%", minWidth: 0,
              alignSelf: mine ? "flex-end" : "flex-start", flexDirection: mine ? "row-reverse" : "row",
            }}>
              {!mine ? <UserAvatar person={sender} name={e.payload.name} size="sm" sx={{ mt: "1.1rem" }} /> : null}
              <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25, minWidth: 0, alignItems: mine ? "flex-end" : "flex-start" }}>
                {!mine ? (
                  <Box component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", fontWeight: FONT_WEIGHT.semibold, px: 0.5 }}>
                    {e.payload.name}
                  </Box>
                ) : null}
                <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.75, flexDirection: mine ? "row-reverse" : "row", minWidth: 0 }}>
                  <Box component="span" sx={{
                    px: 1.5, py: 1, borderRadius: 3.5, fontSize: FONT_SIZE.body, lineHeight: 1.45, minWidth: 0,
                    ...KO_WORD_BREAK,
                    border: 1, borderColor: mine ? "transparent" : "divider",
                    bgcolor: mine ? "primary.main" : "action.hover",
                    color: mine ? "primary.contrastText" : "text.primary",
                  }}>{e.payload.text}</Box>
                  <Box component="span" sx={{ flexShrink: 0, fontSize: FONT_SIZE.caption, color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
                    {fmtTime(e.created_at)}
                  </Box>
                </Box>
              </Box>
            </Box>
          );
        })}
      </Box>
      {chatFailure ? <Callout tone="danger" compact>{chatFailure}</Callout> : null}
      {/* 입력(34)과 단추(34)가 한 줄에 선다(D-526). 입력 줄은 입력 영역 하나다(`data-form-scope`) — 「보내기」는 이 영역의 채움이라
          놀이 판의 채움(「투표 시작」 같은 진행 단추)과 따로 센다(조합 계약 C-4). */}
      <Stack data-form-scope="" direction="row" gap={1} alignItems="center" sx={{ flexShrink: 0 }}>
        <TextField
          size="small" fullWidth value={draft} placeholder="메시지 입력"
          inputProps={{ maxLength: 500, "aria-label": "메시지 입력" }}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); sendChat(); } }}
        />
        {/* 입력창이 fullWidth라 버튼이 눌려 '보내기'가 두 줄('보내'/'기')로 깨졌다 —
            좁은 레일에서는 버튼이 먼저 양보하지 않게 못 박는다. */}
        <Button variant="primary" onClick={sendChat} disabled={chatPending}
          sx={{ flexShrink: 0, whiteSpace: "nowrap" }}>보내기</Button>
      </Stack>
    </Card>
  );
}
