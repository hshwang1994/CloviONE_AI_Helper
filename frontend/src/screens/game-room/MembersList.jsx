import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { Badge } from "../../ui/kit.jsx";
import { ROLE_LABELS } from "./constants.js";

/* 오른쪽 레일 위쪽 — 참여자 목록. GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로
 * 옮겼다. 상한 높이로 접어(자체 스크롤) 아무리 많아도 채팅을 밀어내지 않는다. */
export function MembersList({ members, room, you, submissionActive, submittedSet }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, flexShrink: 0 }}>
      <Typography variant="body2" sx={{ fontWeight: 700, mb: 1 }}>참여자 {members.length}명</Typography>
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5, maxHeight: "13rem", overflowY: "auto" }}>
        {members.map((m) => {
          // 부서를 직책보다 먼저 그린다 — lib/people.js::affiliation / lib/format.js::affiliationOf /
          // app/core/people.py::affiliation 이 전부 "부서 직책"(예: "개발본부 팀장") 순서를 쓴다.
          // 이 화면만 손으로 [title, dept] 순서를 만들어 같은 두 값이 게임방에서만 뒤집혀 보였다.
          const sub = [m.dept, m.title].filter(Boolean);
          const isHostRow = m.user_id === room.host_user_id;
          const isMe = m.user_id === you.user_id;
          return (
            <Box component="li" key={m.user_id} sx={{
              display: "flex", alignItems: "center", gap: 1.25, p: 1, borderRadius: 2,
              border: 1, borderColor: isMe ? "primary.light" : "transparent",
              bgcolor: (t) => (isMe ? alpha(t.palette.primary.main, 0.1) : "transparent"),
            }}>
              <Box component="span" aria-hidden="true" sx={{
                flexShrink: 0, width: "2.25rem", height: "2.25rem", borderRadius: "50%",
                display: "grid", placeItems: "center", fontWeight: 700, fontSize: "0.875rem",
                bgcolor: isHostRow ? "primary.main" : "action.hover",
                color: isHostRow ? "primary.contrastText" : "text.primary",
              }}>
                {(m.name || "?").slice(0, 1)}
              </Box>
              <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
                <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 600 }}>
                  {m.name}{isMe ? <Box component="span" sx={{ color: "text.secondary", fontWeight: 400, fontSize: "0.8125rem" }}> (나)</Box> : null}
                </Box>
                {sub.length ? (
                  <Box component="span" sx={{
                    display: "flex", gap: 1, fontSize: "0.75rem", color: "text.secondary",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {m.dept ? <Box component="span">{m.dept}</Box> : null}
                    {m.title ? <Box component="span" sx={{ color: "primary.main", fontWeight: 600 }}>{m.title}</Box> : null}
                  </Box>
                ) : null}
              </Box>
              <Stack direction="row" gap={0.5} alignItems="center" sx={{ ml: "auto", flexShrink: 0 }}>
                {/* 명단엔 남아 있어도(active) 90초 넘게 폴링이 없으면 추첨·팀나누기·사다리·
                    투표 대상 풀에서는 빠진다(app/games/service.py::_present_players,
                    step 9 #7) - 그 어긋남을 결과가 나오기 전에 미리 알린다. */}
                {m.present === false ? <Badge value="자리 비움" kind="neutral" /> : null}
                {isHostRow
                  ? <Badge value="방장" kind="info" />
                  : <Badge value={ROLE_LABELS[m.role] || m.role} kind="neutral" />}
                {submissionActive && m.role !== "spectator"
                  ? (submittedSet.has(m.user_id)
                    ? <Badge value="제출" kind="ok" />
                    : <Badge value="대기" kind="warn" />)
                  : (m.role === "player" && m.ready ? <Badge value="준비" kind="ok" /> : null)}
              </Stack>
            </Box>
          );
        })}
      </Box>
    </Paper>
  );
}
