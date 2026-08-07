import Box from "@mui/material/Box";
import { FAB_CLEARANCE } from "../../ui/theme.js";
import { MembersList } from "./MembersList.jsx";
import { ChatPanel } from "./ChatPanel.jsx";

/* 오른쪽 레일(참여자 + 채팅) 래퍼. GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로
 * 옮겼다. 넓은 화면에서는 화면 높이에 고정하고 참여자 목록은 상한 높이로 접어(자체 스크롤)
 * 아무리 많아도 채팅을 밀어내지 않게 한다. 채팅이 남는 공간을 꽉 채운다.
 *
 * FAB_CLEARANCE 를 함께 빼지 않으면 레일 맨 아래의 '보내기'가 마스코트 FAB 밑에 깔려 눌리지
 * 않는다(클릭이 FAB에 가로채짐). 실제로 그랬다. */
export function RoomSidebar({ c }) {
  return (
    <Box component="aside" sx={{
      display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0,
      position: { md: "sticky" }, top: { md: 0 },
      height: { md: `calc(100vh - 14rem - ${FAB_CLEARANCE})` },
    }}>
      <MembersList
        members={c.members} room={c.room} you={c.you}
        submissionActive={c.submissionActive} submittedSet={c.submittedSet}
      />
      <ChatPanel
        chatLogRef={c.chatLogRef} chatMsgs={c.chatMsgs} you={c.you}
        draft={c.draft} setDraft={c.setDraft} sendChat={c.sendChat}
        chatPending={c.mutations.chat.isPending}
      />
    </Box>
  );
}
