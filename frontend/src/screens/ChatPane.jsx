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
import AlternateEmailRoundedIcon from "@mui/icons-material/AlternateEmailRounded";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import { api } from "../lib/api.js";
import { fmtTimeShort } from "../lib/format.js";
import { useConfirm } from "../ui/kit.jsx";
import { EMOJI_GROUPS, imageFromClipboard, imageRejectReason, insertAtCursor } from "./chat-compose.js";
import { ChatBubbleText } from "./ChatBubbleText.jsx";
import { mentionNames } from "./chat-text.js";

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
  const confirm = useConfirm();
  const logRef = React.useRef(null);
  const inputRef = React.useRef(null);
  const prevCountRef = React.useRef(0);
  const [draft, setDraft] = React.useState("");
  const [hidden, setHidden] = React.useState(() => document.hidden);
  const [emojiAnchor, setEmojiAnchor] = React.useState(null);
  const [mentionAnchor, setMentionAnchor] = React.useState(null);
  // 컴포저 위 한 줄 안내 — 붙여넣기 실패와 삭제 실패가 같은 자리를 쓴다
  // (원인과 결과가 붙어 보이는 자리는 하나뿐이고, 둘이 동시에 날 일이 없다).
  const [composerError, setComposerError] = React.useState("");

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
    onSuccess: () => { setComposerError(""); q.refetch(); },
    onError: (e) => setComposerError((e && e.message) || "이미지를 보내지 못했습니다."),
  });
  // 내 메시지 지우기. 서버가 툼스톤 시스템 메시지로 event_seq 를 올리므로, 같은 방을 열어 둔
  // 다른 사람의 폴링도 다음 주기에 변경을 받는다(그냥 행만 지우면 그 사람 화면엔 그대로 남는다).
  const del = useMutation({
    mutationFn: (msgSeq) => api(`/api/team-chat/rooms/${roomId}/messages/${msgSeq}/delete`, { method: "POST" }),
    onSuccess: () => { q.refetch(); qc.invalidateQueries({ queryKey: ["team-chat-rooms"] }); },
    onError: (e) => setComposerError((e && e.message) || "메시지를 지우지 못했습니다."),
  });

  const data = q.data || {};
  const msgs = data.messages || [];
  const you = data.you || {};
  const room = data.room || {};
  const members = data.members || [];
  const seq = data.seq || 0;

  /* `@`로 부를 수 있는 이름 — **서버와 같은 출처를 본다**(app/team_chat/service.py의
   * _mention_candidates): 전체 채팅은 전사 디렉터리, 그 외는 그 방의 참여자.
   * 출처가 어긋나면 밑줄은 그어졌는데 알림은 안 가는(또는 그 반대) 상태가 된다.
   * 디렉터리는 전체 채팅에서만, 그리고 react-query 캐시를 ChatRooms 화면과 공유해 받는다. */
  const dir = useQuery({
    queryKey: ["team-chat-directory"],
    queryFn: () => api("/api/team-chat/directory"),
    enabled: !!room.is_global,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const dirUsers = (dir.data && dir.data.users) || [];
  // 렌더용 — 아무도 빼지 않는다. **남이 나를 부른 말**에도 강조가 붙어야 한다.
  const names = React.useMemo(
    () => mentionNames({ isGlobal: !!room.is_global, members, directory: dirUsers }),
    [room.is_global, members, dir.data] // eslint-disable-line react-hooks/exhaustive-deps
  );
  // 고르기 버튼용 — 나를 뺀다. 자기를 부르면 서버가 알림을 만들지 않아 죽은 선택지가 된다.
  const pickable = React.useMemo(
    () => mentionNames({ isGlobal: !!room.is_global, members, directory: dirUsers, meId: you.user_id }),
    [room.is_global, members, dir.data, you.user_id] // eslint-disable-line react-hooks/exhaustive-deps
  );

  /* 1:1 읽음 표시. 상대의 읽음 위치는 서버가 참여자 행에 실어 준다(members[].last_read_seq).
   * **내가 마지막으로 보낸 말 한 줄에만** 붙인다 — 모든 말풍선에 붙이면 대화가 상태 라벨로
   * 뒤덮이고, 정작 궁금한 것은 "방금 한 말을 봤나"다. 1:1이 아니면 그리지 않는다(여러 명이면
   * '읽음'이 누구 기준인지 말할 수 없다). */
  const peers = room.kind === "direct" ? members.filter((m) => m.user_id !== you.user_id) : [];
  // 상대가 아직 응답에 없으면(첫 렌더·비정상 방) 아무 말도 하지 않는다 — 모르는 것을
  // '안 읽음'으로 단정하면 그것도 거짓말이다.
  const peerReadSeq = peers.length ? Math.min(...peers.map((m) => m.last_read_seq || 0)) : null;
  const myLastSeq = React.useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i -= 1) {
      if (msgs[i].sender_user_id && msgs[i].sender_user_id === you.user_id) return msgs[i].seq;
    }
    return null;
  }, [msgs, you.user_id]);

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

  // 커서 자리에 글자를 끼워 넣고 포커스·커서를 그 뒤로 되돌린다(피커를 닫아도 이어 쓸 수 있게).
  // 이모지와 멘션이 같은 경로를 쓴다 — 삽입 규칙이 두 벌이 되면 한쪽만 커서를 잃는다.
  const insertText = (text, close) => {
    const el = inputRef.current;
    const { text: next, caret } = insertAtCursor(draft, text, el && el.selectionStart, el && el.selectionEnd);
    setDraft(next);
    close();
    window.requestAnimationFrame(() => {
      const node = inputRef.current;
      if (!node) return;
      node.focus();
      if (typeof node.setSelectionRange === "function") node.setSelectionRange(caret, caret);
    });
  };
  const insertEmoji = (emoji) => insertText(emoji, () => setEmojiAnchor(null));
  // 멘션은 이름 뒤에 공백을 붙인다 — 붙여 쓰면 다음 글자가 이름의 일부가 되어(최장 일치)
  // 서버가 그 사람을 못 찾는다.
  const insertMention = (name) => insertText("@" + name + " ", () => setMentionAnchor(null));

  const askDelete = async (msgSeq) => {
    const ok = await confirm("이 메시지를 지웁니다. 대화에는 ‘메시지를 삭제했습니다’ 기록이 남고 되돌릴 수 없습니다.",
      { title: "메시지 지우기", confirmLabel: "지우기", danger: true });
    if (ok) del.mutate(msgSeq);
  };

  // Ctrl+V 이미지 붙여넣기. 텍스트 붙여넣기는 건드리지 않는다(preventDefault 하지 않음).
  const onPaste = (e) => {
    const file = imageFromClipboard(e.clipboardData);
    if (!file) return;
    e.preventDefault();
    const reason = imageRejectReason(file);
    if (reason) { setComposerError(reason); return; }
    if (sendImage.isPending) return;
    setComposerError("");
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
            // 읽음 표시는 1:1에서 내가 마지막으로 보낸 말 한 줄에만(위 주석 참고).
            const receipt = mine && peerReadSeq !== null && m.seq === myLastSeq
              ? (peerReadSeq >= m.seq ? "읽음" : "안 읽음")
              : null;
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
                      // 나를 부른 말은 눈에 띄어야 한다 — 알림은 갔는데 대화에서 어느 줄인지
                      // 찾을 수 없으면 알림만 시끄럽고 쓸모가 없다. 판정은 서버가 한다(mentions_me).
                      ...(m.mentions_me
                        ? { borderLeft: 3, borderLeftColor: "warning.main", borderLeftStyle: "solid" }
                        : null),
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
                      : <ChatBubbleText body={m.body} names={names} mine={mine} />}
                  </Paper>
                  <Box sx={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: mine ? "flex-end" : "flex-start", gap: 0.25 }}>
                    {receipt ? (
                      <Typography sx={{ fontSize: "0.625rem", fontWeight: 700, color: receipt === "읽음" ? "primary.main" : "text.disabled" }}>
                        {receipt}
                      </Typography>
                    ) : null}
                    <Typography sx={{ fontSize: "0.6875rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
                      {fmtTimeShort(m.created_at)}
                    </Typography>
                  </Box>
                  {/* 지우기는 내 말에만. 서버가 소유권을 다시 검사하므로 이 게이팅은 UX 일 뿐이다. */}
                  {mine ? (
                    <IconButton
                      size="small" aria-label={`메시지 지우기 (${fmtTimeShort(m.created_at)})`}
                      disabled={del.isPending}
                      onClick={() => askDelete(m.seq)}
                      sx={{ flexShrink: 0, color: "text.disabled", "&:hover": { color: "error.main" } }}
                    >
                      <DeleteOutlineRoundedIcon sx={{ fontSize: "1rem" }} />
                    </IconButton>
                  ) : null}
                </Box>
              </Box>
            );
          })}
      </Box>
      {/* 붙여넣기 실패·업로드 중 안내 — 컴포저 바로 위에 둬야 원인과 결과가 붙어 보인다. */}
      {sendImage.isPending || composerError ? (
        <Typography
          role={composerError ? "alert" : undefined}
          sx={{ mb: 0.75, px: 0.5, fontSize: "0.75rem", color: composerError ? "error.main" : "text.secondary" }}
        >
          {composerError || "이미지를 보내는 중…"}
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
        {/* 멘션 고르기 — 자동완성 대신 목록에서 고른다. 이름은 **정확히** 맞아야 알림이 가는데
            (부분 일치를 허용하면 엉뚱한 사람에게 간다) 사람이 손으로 정확히 치기는 어렵다.
            입력 중 팝업을 띄우면 Enter(전송)와 키보드가 겹치므로, 이모지와 같은 방식으로
            버튼에서 고른다 — 전송 동작을 건드리지 않는 가장 안전한 자리다. */}
        {pickable.length > 0 ? (
          <IconButton
            aria-label="언급할 사람 고르기" aria-haspopup="dialog" aria-expanded={!!mentionAnchor}
            onClick={(e) => setMentionAnchor(e.currentTarget)}
            sx={{ flexShrink: 0, color: "text.secondary" }}
          >
            <AlternateEmailRoundedIcon sx={{ fontSize: "1.25rem" }} />
          </IconButton>
        ) : null}
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
      <Popover
        open={!!mentionAnchor} anchorEl={mentionAnchor} onClose={() => setMentionAnchor(null)}
        anchorOrigin={{ vertical: "top", horizontal: "left" }}
        transformOrigin={{ vertical: "bottom", horizontal: "left" }}
        slotProps={{ paper: { sx: { p: 0.75, maxWidth: "18rem", maxHeight: "16rem" }, "aria-label": "언급할 사람 고르기" } }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
          {pickable.map((name) => (
            <Box
              key={name} component="button" type="button" onClick={() => insertMention(name)}
              sx={{
                border: 0, background: "none", color: "inherit", font: "inherit", fontSize: "0.875rem",
                textAlign: "left", px: 1, py: 0.75, borderRadius: 1, cursor: "pointer",
                "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.12) },
                "&:focus-visible": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
              }}
            >
              @{name}
            </Box>
          ))}
        </Box>
      </Popover>
    </Box>
  );
}
