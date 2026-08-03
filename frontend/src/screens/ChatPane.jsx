import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputBase from "@mui/material/InputBase";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import { api } from "../lib/api.js";
import { fmtTimeShort } from "../lib/format.js";

/* 팀 채팅 핵심 창(폴링 로그 + 입력). 방 페이지와 홈 위젯이 공유한다. 놀이(GameRoom) 폴링 패턴 이식:
 * since=0 로 최근 메시지를 받아 seq 커서로 따라오고, 내 메시지는 오른쪽 말풍선. 탭이 숨으면 폴링을
 * 늦춰(위젯이 모든 페이지에서 도는 부담 완화) SQLite 쓰기/읽기 압박을 줄인다.
 *
 * 말풍선 규격은 AI 채팅(Chat.jsx)과 같은 언어를 쓴다 — 같은 앱에서 '채팅'이 두 벌 다르게 생기면
 * 사용자는 둘을 다른 기능으로 읽는다. 크기는 전부 rem이다: 예전 CSS(.tc-*)는 px 폰트사이즈가
 * 남아 있어 4K에서 글자만 그대로 남고 주변이 커졌다(.tc-roomrow-tag가 11px로 잡힌 그 문제).
 *
 * 마스코트는 여기에 두지 않는다 — 클로비는 AI 도우미이고 이 화면은 사람끼리의 대화다.
 * 상태와 무관한 자리에 붙이는 순간 마스코트는 다시 장식이 된다.
 */

let _cseq = 0;

// 로그 높이 — 방 페이지는 크게, 홈 위젯은 작게. vh로 화면 비율을 따르되 상·하한은 rem이라
// 루트 폰트사이즈 레버(styles/root.css)를 따라 4K에서 함께 커진다.
const LOG_SX = {
  full: { height: "56vh", minHeight: "18.75rem", maxHeight: "45rem" },
  compact: { height: "18.75rem", minHeight: "12.5rem", maxHeight: "25rem" },
};

export function ChatPane({ roomId, compact = false, interval = 2000 }) {
  const qc = useQueryClient();
  const logRef = React.useRef(null);
  const prevCountRef = React.useRef(0);
  const [draft, setDraft] = React.useState("");
  const [hidden, setHidden] = React.useState(() => document.hidden);

  React.useEffect(() => {
    const onVis = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const q = useQuery({
    queryKey: ["team-chat-msgs", roomId],
    queryFn: () => api(`/api/team-chat/rooms/${roomId}/messages?since=0`),
    enabled: !!roomId,
    refetchInterval: hidden ? false : interval,
    retry: false,
  });

  const send = useMutation({
    mutationFn: (body) => api(`/api/team-chat/rooms/${roomId}/messages`, {
      method: "POST", body: { body, client_message_id: "c" + Date.now() + "-" + (++_cseq) },
    }),
    onSuccess: () => { setDraft(""); q.refetch(); },
  });
  const read = useMutation({
    mutationFn: (seq) => api(`/api/team-chat/rooms/${roomId}/read`, { method: "POST", body: { seq } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["team-chat-rooms"] }),
  });

  const data = q.data || {};
  const msgs = data.messages || [];
  const you = data.you || {};
  const seq = data.seq || 0;

  // 새 메시지가 오면 맨 아래(최신) 근처일 때만 따라 내려간다.
  React.useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    const first = prevCountRef.current === 0;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (first || near) el.scrollTop = el.scrollHeight;
    prevCountRef.current = msgs.length;
  }, [msgs.length]);

  // 방을 열었거나 새 메시지가 왔을 때, 멤버 방이면 읽음 처리(전체 채팅 방은 서버가 무시).
  React.useEffect(() => {
    if (seq > 0 && you.is_member && (you.last_read_seq || 0) < seq) read.mutate(seq);
  }, [seq]); // eslint-disable-line react-hooks/exhaustive-deps

  const doSend = () => { const t = draft.trim(); if (t && !send.isPending) send.mutate(t); };
  const note = (msg) => <Typography sx={{ color: "text.secondary", fontSize: "0.8125rem", py: 2, textAlign: "center" }}>{msg}</Typography>;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
      <Box
        ref={logRef}
        sx={{
          display: "flex", flexDirection: "column", gap: 1, overflowY: "auto",
          mb: 1.25, px: 0.5, py: 1, minWidth: 0,
          ...(compact ? LOG_SX.compact : LOG_SX.full),
        }}
      >
        {q.isPending ? note("불러오는 중…")
          : q.isError ? note("불러오지 못했습니다.")
          : msgs.length === 0 ? note("아직 메시지가 없습니다. 먼저 인사해 보세요.")
          : msgs.map((m) => {
            if (m.kind === "system") {
              return <Chip key={m.seq} size="small" label={m.body} sx={{ alignSelf: "center", fontSize: "0.75rem", height: "1.5rem", maxWidth: "100%" }} />;
            }
            const mine = m.sender_user_id === you.user_id;
            return (
              <Box
                key={m.seq}
                sx={{
                  display: "flex", flexDirection: "column", gap: 0.25, maxWidth: "85%", minWidth: 0,
                  alignSelf: mine ? "flex-end" : "flex-start",
                  alignItems: mine ? "flex-end" : "flex-start",
                }}
              >
                {!mine ? (
                  <Typography sx={{ fontWeight: 600, color: "text.secondary", fontSize: "0.75rem", px: 0.5 }}>
                    {m.sender_name || "알 수 없음"}
                  </Typography>
                ) : null}
                <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.75, flexDirection: mine ? "row-reverse" : "row", minWidth: 0 }}>
                  <Paper
                    elevation={0}
                    sx={{
                      px: 1.5, py: 1, borderRadius: 2.5, minWidth: 0,
                      fontSize: "0.875rem", lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-word",
                      ...(mine
                        ? {
                            bgcolor: "primary.main", color: "primary.contrastText",
                            borderBottomRightRadius: "0.375rem",
                            boxShadow: (t) => `0 2px 10px ${alpha(t.palette.primary.main, 0.28)}`,
                          }
                        : { bgcolor: "background.default", border: 1, borderColor: "divider", borderBottomLeftRadius: "0.375rem" }),
                    }}
                  >
                    {m.body}
                  </Paper>
                  <Typography sx={{ flexShrink: 0, fontSize: "0.6875rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
                    {fmtTimeShort(m.created_at)}
                  </Typography>
                </Box>
              </Box>
            );
          })}
      </Box>
      <Paper
        variant="outlined"
        sx={{ display: "flex", alignItems: "center", gap: 1, pl: 1.75, pr: 0.75, py: 0.5, borderRadius: 999 }}
      >
        <InputBase
          fullWidth value={draft} placeholder="메시지 입력"
          inputProps={{ maxLength: 2000, "aria-label": "메시지 입력" }}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); doSend(); } }}
          sx={{ fontSize: "0.875rem" }}
        />
        <IconButton color="primary" aria-label="보내기" onClick={doSend} disabled={send.isPending || !draft.trim()} sx={{ flexShrink: 0 }}>
          <SendRoundedIcon sx={{ fontSize: "1.25rem" }} />
        </IconButton>
      </Paper>
    </Box>
  );
}
