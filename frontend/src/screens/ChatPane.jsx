import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputBase from "@mui/material/InputBase";
import Paper from "@mui/material/Paper";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import MoodRoundedIcon from "@mui/icons-material/MoodRounded";
import { api } from "../lib/api.js";
import { fmtTimeShort } from "../lib/format.js";
import { EMOJI_GROUPS, imageFromClipboard, imageRejectReason, insertAtCursor } from "./chat-compose.js";

/* 팀 채팅 핵심 창(폴링 로그 + 입력). 방 페이지와 홈 위젯이 공유한다. 놀이(GameRoom) 폴링 패턴 이식:
 * since=0 로 최근 메시지를 받아 seq 커서로 따라오고, 내 메시지는 오른쪽 말풍선. 탭이 숨으면 폴링을
 * 늦춰(위젯이 모든 페이지에서 도는 부담 완화) SQLite 쓰기/읽기 압박을 줄인다.
 *
 * 말풍선 규격은 AI 채팅(Chat.jsx)과 같은 언어를 쓴다 — 같은 앱에서 '채팅'이 두 벌 다르게 생기면
 * 사용자는 둘을 다른 기능으로 읽는다. 크기는 전부 rem이다: 예전 CSS(.tc-*)는 px 폰트사이즈가
 * 남아 있어 4K에서 글자만 그대로 남고 주변이 커졌다(.tc-roomrow-tag가 11px로 잡힌 그 문제).
 *
 * 이모지는 유니코드 글자만 쓴다(스프라이트·외부 폰트 없음 — CSP/오프라인). 이미지는 첨부
 * 버튼이 아니라 **Ctrl+V 붙여넣기**로 들어오고, 말풍선 안에 인라인으로 그려진다. 이미지 주소는
 * 게시판 첨부(`/api/board/attachments/...`)가 아니라 방 접근 검사를 하는 팀 채팅 전용
 * 경로다 — 게시판 경로를 재사용하면 1:1 DM 사진이 전사 공개가 된다.
 *
 * 마스코트는 여기에 두지 않는다 — 클로비는 AI 도우미이고 이 화면은 사람끼리의 대화다.
 * 상태와 무관한 자리에 붙이는 순간 마스코트는 다시 장식이 된다.
 */

let _cseq = 0;
const nextClientId = () => "c" + Date.now() + "-" + (++_cseq);

// 로그 높이 — 방 페이지는 크게, 홈 위젯은 작게. vh로 화면 비율을 따르되 상·하한은 rem이라
// 루트 폰트사이즈 레버(styles/root.css)를 따라 4K에서 함께 커진다.
const LOG_SX = {
  full: { height: "56vh", minHeight: "18.75rem", maxHeight: "45rem" },
  compact: { height: "18.75rem", minHeight: "12.5rem", maxHeight: "25rem" },
};

export function ChatPane({ roomId, compact = false, interval = 2000 }) {
  const qc = useQueryClient();
  const logRef = React.useRef(null);
  const inputRef = React.useRef(null);
  const prevCountRef = React.useRef(0);
  const [draft, setDraft] = React.useState("");
  const [hidden, setHidden] = React.useState(() => document.hidden);
  const [emojiAnchor, setEmojiAnchor] = React.useState(null);
  const [pasteError, setPasteError] = React.useState("");

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
      method: "POST", body: { body, client_message_id: nextClientId() },
    }),
    onSuccess: () => { setDraft(""); q.refetch(); },
  });
  const read = useMutation({
    mutationFn: (seq) => api(`/api/team-chat/rooms/${roomId}/read`, { method: "POST", body: { seq } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["team-chat-rooms"] }),
  });
  // 붙여넣은 이미지 업로드 — FormData 라 api()가 JSON으로 감싸지 않는다(lib/api.js).
  const sendImage = useMutation({
    mutationFn: (file) => {
      const fd = new FormData();
      fd.append("file", file, file.name || "paste.png");
      fd.append("client_message_id", nextClientId());
      return api(`/api/team-chat/rooms/${roomId}/images`, { method: "POST", body: fd });
    },
    onSuccess: () => { setPasteError(""); q.refetch(); },
    onError: (e) => setPasteError((e && e.message) || "이미지를 보내지 못했습니다."),
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

  // 방을 열었거나 새 메시지가 왔을 때 읽음 처리. 전체 채팅 방(is_member=false)도 이제
  // 개인 읽음 커서가 있어 여기서 기록한다 — 예전엔 서버가 무시해 안읽음이 영영 0이었다.
  // last_read_seq 는 멤버 방이면 멤버 행, 전체 채팅이면 커서에서 온다. 이 비교 덕분에
  // 폴링이 계속 돌아도 새로 읽을 게 없으면 POST 자체가 나가지 않는다.
  React.useEffect(() => {
    if (seq > 0 && (you.last_read_seq || 0) < seq) read.mutate(seq);
  }, [seq]); // eslint-disable-line react-hooks/exhaustive-deps

  const doSend = () => { const t = draft.trim(); if (t && !send.isPending) send.mutate(t); };
  const note = (msg) => <Typography sx={{ color: "text.secondary", fontSize: "0.8125rem", py: 2, textAlign: "center" }}>{msg}</Typography>;

  // 이모지 삽입 — 커서 자리에 넣고 포커스·커서를 그 뒤로 되돌린다(피커를 닫아도 이어 쓸 수 있게).
  const insertEmoji = (emoji) => {
    const el = inputRef.current;
    const { text, caret } = insertAtCursor(draft, emoji, el && el.selectionStart, el && el.selectionEnd);
    setDraft(text);
    setEmojiAnchor(null);
    window.requestAnimationFrame(() => {
      const node = inputRef.current;
      if (!node) return;
      node.focus();
      if (typeof node.setSelectionRange === "function") node.setSelectionRange(caret, caret);
    });
  };

  // Ctrl+V 이미지 붙여넣기. 텍스트 붙여넣기는 건드리지 않는다(preventDefault 하지 않음).
  const onPaste = (e) => {
    const file = imageFromClipboard(e.clipboardData);
    if (!file) return;
    e.preventDefault();
    const reason = imageRejectReason(file);
    if (reason) { setPasteError(reason); return; }
    if (sendImage.isPending) return;
    setPasteError("");
    sendImage.mutate(file);
  };

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
                    {/* 이미지 메시지: 말풍선 안에 인라인. body(파일명)는 alt 로만 쓴다 —
                        말풍선에 파일명과 그림을 같이 두면 그림이 캡션 달린 첨부처럼 보인다. */}
                    {m.kind === "image" && (m.images || []).length > 0
                      ? (m.images || []).map((img) => (
                        <Box
                          key={img.id} component="img" src={img.url} alt={img.filename || "붙여넣은 이미지"}
                          loading="lazy"
                          sx={{
                            display: "block", maxWidth: "100%", maxHeight: "18rem",
                            width: "auto", height: "auto", borderRadius: 1.5,
                          }}
                        />
                      ))
                      : m.body}
                  </Paper>
                  <Typography sx={{ flexShrink: 0, fontSize: "0.6875rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
                    {fmtTimeShort(m.created_at)}
                  </Typography>
                </Box>
              </Box>
            );
          })}
      </Box>
      {/* 붙여넣기 실패·업로드 중 안내 — 컴포저 바로 위에 둬야 원인과 결과가 붙어 보인다. */}
      {sendImage.isPending || pasteError ? (
        <Typography
          role={pasteError ? "alert" : undefined}
          sx={{ mb: 0.75, px: 0.5, fontSize: "0.75rem", color: pasteError ? "error.main" : "text.secondary" }}
        >
          {pasteError || "이미지를 보내는 중…"}
        </Typography>
      ) : null}
      <Paper
        variant="outlined"
        sx={{ display: "flex", alignItems: "center", gap: 0.5, pl: 0.75, pr: 0.75, py: 0.5, borderRadius: 999 }}
      >
        <IconButton
          aria-label="이모지 넣기" aria-haspopup="dialog" aria-expanded={!!emojiAnchor}
          onClick={(e) => setEmojiAnchor(e.currentTarget)}
          sx={{ flexShrink: 0, color: "text.secondary" }}
        >
          <MoodRoundedIcon sx={{ fontSize: "1.25rem" }} />
        </IconButton>
        <InputBase
          fullWidth value={draft} placeholder="메시지 입력 (이미지는 Ctrl+V로 붙여넣기)"
          inputRef={inputRef}
          inputProps={{ maxLength: 2000, "aria-label": "메시지 입력" }}
          onChange={(e) => setDraft(e.target.value)}
          onPaste={onPaste}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); doSend(); } }}
          sx={{ fontSize: "0.875rem" }}
        />
        <IconButton color="primary" aria-label="보내기" onClick={doSend} disabled={send.isPending || !draft.trim()} sx={{ flexShrink: 0 }}>
          <SendRoundedIcon sx={{ fontSize: "1.25rem" }} />
        </IconButton>
      </Paper>
      <Popover
        open={!!emojiAnchor} anchorEl={emojiAnchor} onClose={() => setEmojiAnchor(null)}
        anchorOrigin={{ vertical: "top", horizontal: "left" }}
        transformOrigin={{ vertical: "bottom", horizontal: "left" }}
        slotProps={{ paper: { sx: { p: 1.25, maxWidth: "20rem" }, "aria-label": "이모지 고르기" } }}
      >
        {EMOJI_GROUPS.map((g) => (
          <Box key={g.label} sx={{ mb: 1, "&:last-of-type": { mb: 0 } }}>
            <Typography sx={{ mb: 0.5, fontSize: "0.6875rem", fontWeight: 700, color: "text.secondary" }}>{g.label}</Typography>
            {/* MUI Grid 대신 Box + sx 그리드 — 프로젝트 규약. */}
            <Box sx={{ display: "grid", gridTemplateColumns: "repeat(10, 1fr)", gap: 0.25 }}>
              {g.emojis.map((emoji) => (
                <Box
                  key={emoji} component="button" type="button" aria-label={"이모지 " + emoji}
                  onClick={() => insertEmoji(emoji)}
                  sx={{
                    border: 0, background: "none", cursor: "pointer", p: 0.25, borderRadius: 1,
                    fontSize: "1.125rem", lineHeight: 1.2, color: "inherit",
                    "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.12) },
                    "&:focus-visible": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
                  }}
                >
                  {emoji}
                </Box>
              ))}
            </Box>
          </Box>
        ))}
      </Popover>
    </Box>
  );
}
