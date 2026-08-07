import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Button } from "../../ui/kit.jsx";
import { fmtTime } from "./timeUtils.js";

/* 오른쪽 레일 아래쪽 — 채팅. GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로 옮겼다.
 * 새 채팅이 오면 최신으로 따라 내려가는 자동 스크롤은 useGameRoomController의 effect가 맡고,
 * 여기는 chatLogRef를 받아 그 DOM 노드에 꽂기만 한다.
 *
 * chatMsgs에는 이제 대화(kind="chat")뿐 아니라 안내문이 달린 system 이벤트(방장 위임 등,
 * useGameRoomController::isChatFeedEvent)도 섞여 들어온다 — 팀 채팅(ChatPane.jsx)이 시스템
 * 메시지를 Chip으로 가운데 놓는 것과 같은 자리·같은 모양을 쓴다(같은 앱에서 '안내문'이 두 벌
 * 다르게 생기지 않게). */
export function ChatPanel({ chatLogRef, chatMsgs, you, draft, setDraft, sendChat, chatPending }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, display: "flex", flexDirection: "column", flex: { md: "1 1 auto" }, minHeight: { md: 0 } }}>
      <Typography variant="body2" sx={{ fontWeight: 700, mb: 1 }}>채팅</Typography>
      <Box ref={chatLogRef} sx={{
        display: "flex", flexDirection: "column", gap: 1, overflowY: "auto", px: 0.5, py: 1, mb: 1.25,
        height: { xs: "45vh", md: "auto" }, minHeight: { xs: "16rem", md: 0 },
        maxHeight: { xs: "45rem", md: "none" }, flex: { md: "1 1 auto" },
      }}>
        {chatMsgs.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 2 }}>
            아직 메시지가 없습니다. 먼저 인사해 보세요.
          </Typography>
        ) : chatMsgs.map((e) => {
          if (e.kind === "system") {
            return (
              <Chip key={e.seq} size="small" label={e.payload.text}
                sx={{ alignSelf: "center", fontSize: "0.75rem", height: "1.5rem", maxWidth: "100%" }} />
            );
          }
          const mine = e.actor_user_id === you.user_id;
          return (
            <Box key={e.seq} sx={{
              display: "flex", flexDirection: "column", gap: 0.25, maxWidth: "85%",
              alignSelf: mine ? "flex-end" : "flex-start", alignItems: mine ? "flex-end" : "flex-start",
            }}>
              {!mine ? (
                <Box component="span" sx={{ fontSize: "0.75rem", color: "text.secondary", fontWeight: 600, px: 0.5 }}>
                  {e.payload.name}
                </Box>
              ) : null}
              <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.75, flexDirection: mine ? "row-reverse" : "row" }}>
                <Box component="span" sx={{
                  px: 1.5, py: 1, borderRadius: 3.5, fontSize: "0.875rem", lineHeight: 1.45,
                  wordBreak: "break-word",
                  border: 1, borderColor: mine ? "transparent" : "divider",
                  bgcolor: mine ? "primary.main" : "action.hover",
                  color: mine ? "primary.contrastText" : "text.primary",
                }}>{e.payload.text}</Box>
                <Box component="span" sx={{ flexShrink: 0, fontSize: "0.75rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
                  {fmtTime(e.created_at)}
                </Box>
              </Box>
            </Box>
          );
        })}
      </Box>
      <Stack direction="row" gap={1}>
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
    </Paper>
  );
}
