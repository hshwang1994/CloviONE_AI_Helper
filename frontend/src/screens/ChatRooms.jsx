import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { api } from "../lib/api.js";
import { Button, Card, PageHeader, Skeleton, ErrorState, EmptyState, Modal, useToast } from "../ui/kit.jsx";
import { fmtRelative } from "../lib/format.js";
import { personLabel } from "../lib/people.js";

/* 채팅방 목록 — 전체 채팅(고정) + 내가 속한 그룹/1:1. 새 그룹 만들기, 1:1 시작(디렉터리에서 상대
 * 선택). 목록만 폴링(5초)해 안읽음/미리보기를 갱신하고, 실제 대화는 방 페이지(ChatRoom)에서 한다.
 *
 * 치수는 전부 rem이다. 예전 CSS(.tc-roomrow-tag 등)는 px 폰트사이즈가 남아 4K에서 태그만 11px로
 * 쪼그라들어 있었다 — 루트 폰트사이즈 레버(styles/root.css)를 따라야 주변과 같이 커진다. */

function RoomRow({ room, onOpen }) {
  const tag = room.is_global ? "전체" : room.kind === "direct" ? "1:1" : "그룹 " + room.member_count;
  return (
    <Box
      component="button" type="button" onClick={() => onOpen(room.id)}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5, width: "100%", textAlign: "left", minWidth: 0,
        px: 1, py: 1.5, border: 0, borderBottom: 1, borderColor: "divider", borderStyle: "solid",
        background: "none", color: "inherit", font: "inherit", cursor: "pointer",
        "&:last-of-type": { borderBottom: 0 },
        "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
        "&:focus-visible": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
      }}
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25, minWidth: 0, flex: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 700, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "0.9375rem" }}>
            {room.title}
          </Typography>
          <Chip size="small" label={tag} sx={{ flexShrink: 0, height: "1.375rem", fontSize: "0.75rem" }} />
        </Box>
        <Typography sx={{ color: "text.secondary", fontSize: "0.8125rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {room.last_preview || "새 채팅방"}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 0.5, flexShrink: 0 }}>
        {room.last_at ? <Typography sx={{ color: "text.secondary", fontSize: "0.75rem" }}>{fmtRelative(room.last_at)}</Typography> : null}
        {room.unread > 0 ? (
          <Box
            component="span"
            sx={{
              minWidth: "1.375rem", textAlign: "center", px: 0.75, py: "0.0625rem", borderRadius: 999,
              bgcolor: "primary.main", color: "primary.contrastText",
              fontSize: "0.75rem", fontWeight: 750, fontVariantNumeric: "tabular-nums",
            }}
          >
            {room.unread > 99 ? "99+" : room.unread}
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}

function useDirectory(enabled) {
  return useQuery({
    queryKey: ["team-chat-directory"],
    queryFn: () => api("/api/team-chat/directory"),
    enabled,
  });
}

// personLabel 은 lib/people.js 로 옮겼다 — 사람을 보여 주는 자리가 채팅 말고도 여럿인데
// (담당자 선택, 방 멤버 목록, 댓글 작성자) 각자 다른 규칙을 갖고 있었다. 한 곳에서 정한다.

// 모달 안 스크롤 목록(그룹 초대, 1:1 상대) — 목록이 길어도 모달이 화면 밖으로 자라지 않게 한다.
const PICKER_SX = {
  display: "flex", flexDirection: "column", gap: 0.25, maxHeight: "20rem", overflowY: "auto",
  border: 1, borderColor: "divider", borderRadius: 2, p: 0.5,
};

function GroupModal({ open, onClose }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const dir = useDirectory(open);
  const [title, setTitle] = React.useState("");
  const [picked, setPicked] = React.useState({});
  React.useEffect(() => { if (open) { setTitle(""); setPicked({}); } }, [open]);

  const create = useMutation({
    mutationFn: () => api("/api/team-chat/rooms", {
      method: "POST",
      body: { title: title.trim(), member_user_ids: Object.keys(picked).filter((k) => picked[k]) },
    }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["team-chat-rooms"] }); onClose(); nav(`/chat-rooms/${r.room.id}`); },
    onError: (e) => toast((e && e.message) || "방을 만들지 못했습니다.", "error"),
  });

  const users = (dir.data && dir.data.users) || [];
  const canCreate = title.trim().length > 0 && !create.isPending;
  const footer = (
    <>
      <Button onClick={onClose}>취소</Button>
      <Button variant="primary" disabled={!canCreate} onClick={() => create.mutate()}>만들기</Button>
    </>
  );
  return (
    <Modal open={open} onClose={onClose} title="새 그룹 채팅방" footer={footer}>
      <Box sx={{ mb: 2.5 }}>
        <Typography component="label" htmlFor="tc-gtitle" sx={{ display: "block", mb: 0.75, fontSize: "0.8125rem", fontWeight: 700 }}>
          방 이름<Box component="span" sx={{ color: "error.main" }}> *</Box>
        </Typography>
        <Box
          component="input" id="tc-gtitle" maxLength={80} value={title} placeholder="예: 프로젝트 A 팀"
          onChange={(e) => setTitle(e.target.value)}
          sx={{
            width: "100%", px: 1.5, py: 1.125, font: "inherit", fontSize: "0.875rem",
            border: 1, borderColor: "divider", borderRadius: 2, bgcolor: "background.default", color: "text.primary",
            "&:focus": { outline: "none", borderColor: "primary.main" },
          }}
        />
      </Box>
      <Box>
        <Typography sx={{ display: "block", mb: 0.75, fontSize: "0.8125rem", fontWeight: 700 }}>초대할 사람 (선택)</Typography>
        {dir.isPending ? <Skeleton lines={4} />
          : dir.isError ? <ErrorState error={dir.error} onRetry={() => dir.refetch()} />
          : users.length === 0 ? <Typography sx={{ color: "text.secondary", fontSize: "0.8125rem", py: 2, textAlign: "center" }}>초대할 다른 사용자가 없습니다.</Typography>
          : (
            <Box sx={PICKER_SX}>
              {users.map((u) => (
                <Box
                  key={u.user_id} component="label"
                  sx={{
                    display: "flex", alignItems: "center", gap: 1, px: 1, py: 1, borderRadius: 1.5, cursor: "pointer", fontSize: "0.875rem",
                    "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
                    "&:focus-within": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
                  }}
                >
                  <Box component="input" type="checkbox" checked={!!picked[u.user_id]}
                    onChange={(e) => setPicked((p) => ({ ...p, [u.user_id]: e.target.checked }))} sx={{ m: 0 }} />
                  <span>{personLabel(u)}</span>
                </Box>
              ))}
            </Box>
          )}
      </Box>
    </Modal>
  );
}

function DirectModal({ open, onClose }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const dir = useDirectory(open);
  const start = useMutation({
    mutationFn: (userId) => api("/api/team-chat/rooms/direct", { method: "POST", body: { user_id: userId } }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["team-chat-rooms"] }); onClose(); nav(`/chat-rooms/${r.room.id}`); },
    onError: (e) => toast((e && e.message) || "대화를 시작하지 못했습니다.", "error"),
  });
  const users = (dir.data && dir.data.users) || [];
  return (
    <Modal open={open} onClose={onClose} title="1:1 대화 시작" footer={<Button onClick={onClose}>닫기</Button>}>
      {dir.isPending ? <Skeleton lines={5} />
        : dir.isError ? <ErrorState error={dir.error} onRetry={() => dir.refetch()} />
        : users.length === 0 ? <Typography sx={{ color: "text.secondary", fontSize: "0.8125rem", py: 2, textAlign: "center" }}>대화할 다른 사용자가 없습니다.</Typography>
        : (
          <Box sx={PICKER_SX}>
            {users.map((u) => (
              <Box
                key={u.user_id} component="button" type="button"
                disabled={start.isPending} onClick={() => start.mutate(u.user_id)}
                sx={{
                  display: "block", width: "100%", textAlign: "left", px: 1.5, py: 1,
                  border: 0, borderRadius: 1.5, background: "none", color: "text.primary",
                  font: "inherit", fontSize: "0.875rem", cursor: "pointer",
                  "&:hover:not(:disabled)": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
                  "&:focus-visible": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
                  "&:disabled": { opacity: 0.6, cursor: "default" },
                }}
              >
                {personLabel(u)}
              </Box>
            ))}
          </Box>
        )}
    </Modal>
  );
}

export function ChatRooms() {
  const nav = useNavigate();
  const [groupOpen, setGroupOpen] = React.useState(false);
  const [directOpen, setDirectOpen] = React.useState(false);
  const q = useQuery({
    queryKey: ["team-chat-rooms"],
    queryFn: () => api("/api/team-chat/rooms"),
    refetchInterval: 5000,
  });

  // 합계 안읽음(전체 채팅 포함)은 서버가 같은 응답(unread_total)에 실어 준다 — 배지 하나
  // 때문에 폴링을 하나 더 만들지 않는다. 사이드바 '채팅방' 항목 배지도 이 값을 쓸 자리다.
  const unreadTotal = (q.data && q.data.unread_total) || 0;
  const actions = (
    <>
      {unreadTotal > 0 ? (
        <Chip size="small" color="primary" label={`안 읽음 ${unreadTotal > 99 ? "99+" : unreadTotal}`}
          sx={{ height: "1.5rem", fontSize: "0.75rem", fontWeight: 700, alignSelf: "center" }} />
      ) : null}
      <Button onClick={() => setDirectOpen(true)}>1:1 대화</Button>
      <Button variant="primary" onClick={() => setGroupOpen(true)}>새 그룹</Button>
    </>
  );

  const glob = q.data && q.data.global;
  const items = (q.data && q.data.items) || [];

  return (
    <Box className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="채팅방" title="채팅방" actions={actions} />
      {q.isPending ? <Card><Skeleton lines={6} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (
          <Card sx={{ p: { xs: 1.5, sm: 2 } }}>
            <Paper variant="outlined" sx={{ display: "flex", flexDirection: "column", borderRadius: 2, overflow: "hidden", border: 0 }}>
              {glob ? <RoomRow room={glob} onOpen={(id) => nav(`/chat-rooms/${id}`)} /> : null}
              {items.length === 0 ? (
                <EmptyState title="참여 중인 채팅방이 없습니다"
                  help="위의 '새 그룹' 또는 '1:1 대화'로 대화를 시작하세요. 전체 채팅은 누구나 참여할 수 있습니다." />
              ) : items.map((r) => <RoomRow key={r.id} room={r} onOpen={(id) => nav(`/chat-rooms/${id}`)} />)}
            </Paper>
          </Card>
        )}
      <GroupModal open={groupOpen} onClose={() => setGroupOpen(false)} />
      <DirectModal open={directOpen} onClose={() => setDirectOpen(false)} />
    </Box>
  );
}
