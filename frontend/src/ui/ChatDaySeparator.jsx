import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { CHAT } from "./chat.js";
import { FONT_SIZE, FONT_WEIGHT } from "./theme.js";

/* 대화 스레드의 날짜 구분선 — 채팅방(`ChatPane`)과 AI 도우미(`chat/MessageThread`)가 같이 쓴다 (UI 3차 조합 계약 C-6).
 *
 * 규격은 핸드오프 RULES §9 「날짜 구분선(1px 실선 + 0.75rem/600)」이고, 선은 판 안 가는 선 토큰(`rule`)이다. 스레드
 * 가운데 28rem 폭에 선다(`CHAT.daySeparatorWidth`) — 전폭으로 그으면 넓은 화면에서 선이 말풍선보다 길게 달려 대화를
 * 칸막이로 자른다. 예전에는 두 화면이 구분선을 따로 그려 선 색(`rule` · `divider`)과 글자(0.75 · 0.8125rem)가 갈렸다.
 *
 * `day` 는 KST 달력일 키(`YYYY-MM-DD`)다 — `data-day-separator` 로 실어 시험 · 조합 검사가 구분선을 찾는다. */
export function ChatDaySeparator({ label, day }) {
  return (
    <Box
      role="separator"
      aria-label={label}
      data-day-separator={day || ""}
      sx={{
        display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto minmax(0, 1fr)", alignItems: "center", columnGap: 1.5,
        width: "100%", maxWidth: CHAT.daySeparatorWidth, alignSelf: "center", mx: "auto", my: 1, flexShrink: 0,
      }}
    >
      <Box aria-hidden="true" sx={{ height: "1px", bgcolor: "rule" }} />
      <Typography component="span" sx={{ fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, color: "text.secondary", whiteSpace: "nowrap" }}>
        {label}
      </Typography>
      <Box aria-hidden="true" sx={{ height: "1px", bgcolor: "rule" }} />
    </Box>
  );
}
