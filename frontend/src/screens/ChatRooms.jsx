import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { api } from "../lib/api.js";
import { Button, Card, PageHeader, Skeleton, ErrorState, EmptyState, Modal, useConfirm, useToast } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "../ui/theme.js";
import { fmtRelative } from "../lib/format.js";
import { personLabel } from "../lib/people.js";
import { RoomDetailPanel } from "./ChatRoom.jsx";

/* 채팅방 목록 — 전체 채팅(고정) + 내가 속한 그룹/1:1. 새 그룹 만들기, 1:1 시작(디렉터리에서 상대
 * 선택). 목록만 폴링(5초)해 안읽음/미리보기를 갱신하고, 실제 대화는 방 페이지(ChatRoom)에서 한다.
 *
 * 치수는 전부 rem이다. 예전 CSS(.tc-roomrow-tag 등)는 px 폰트사이즈가 남아 4K에서 태그만 11px로
 * 쪼그라들어 있었다 — 루트 폰트사이즈 레버(styles/root.css)를 따라야 주변과 같이 커진다. */

function RoomRow({ room, onOpen, active }) {
  // 팀 방은 그룹 방과 종류가 같아서(department_id 로만 구분된다) 태그로 성격을 알린다.
  const tag = room.is_global ? "전체"
    : room.department_id ? "내 팀"
    : room.kind === "direct" ? "1:1"
    : "그룹 " + room.member_count;
  return (
    <Box
      component="button" type="button" onClick={() => onOpen(room.id)}
      aria-current={active ? "true" : undefined}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5, width: "100%", textAlign: "left", minWidth: 0,
        px: 1.5, py: 1.5, border: 0, borderBottom: 1, borderColor: "divider", borderStyle: "solid",
        background: "none", color: "inherit", font: "inherit", cursor: "pointer",
        // 지금 보고 있는 방을 목록에서 표시한다 — 두 칸이 나란히 있으니 "어느 것을 보고
        // 있는지" 가 목록에도 보여야 한다. 왼쪽 띠 + 옅은 배경으로, 색만으로 알리지 않는다.
        borderLeft: 3, borderLeftStyle: "solid",
        borderLeftColor: active ? "primary.main" : "transparent",
        bgcolor: (t) => (active ? alpha(t.palette.primary.main, 0.08) : "transparent"),
        "&:last-of-type": { borderBottom: 0 },
        "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, active ? 0.12 : 0.06) },
        "&:focus-visible": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
      }}
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25, minWidth: 0, flex: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.bold, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "0.9375rem" }}>
            {room.title}
          </Typography>
          <Chip size="small" label={tag} sx={{ flexShrink: 0, height: "1.375rem", fontSize: FONT_SIZE.caption }} />
        </Box>
        <Typography sx={{ color: "text.secondary", fontSize: FONT_SIZE.bodySm, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {room.last_preview || "새 채팅방"}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 0.5, flexShrink: 0 }}>
        {room.last_at ? <Typography sx={{ color: "text.secondary", fontSize: FONT_SIZE.caption }}>{fmtRelative(room.last_at)}</Typography> : null}
        {room.unread > 0 ? (
          <Box
            component="span"
            sx={{
              minWidth: "1.375rem", textAlign: "center", px: 0.75, py: "0.0625rem", borderRadius: RADIUS.full,
              bgcolor: "primary.main", color: "primary.contrastText",
              fontSize: FONT_SIZE.caption, fontWeight: 750, fontVariantNumeric: "tabular-nums",
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

export function GroupModal({ open, onClose }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
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
    onError: (e) => toast((e && e.message) || "방을 추가하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const users = (dir.data && dir.data.users) || [];
  const canCreate = title.trim().length > 0 && !create.isPending;
  // 방 이름을 쳤거나 초대할 사람을 골랐으면 Esc·바깥 클릭·X·'취소' 전부에서 확인을 받는다
  // (VIS-88). `Modal`의 `dirty` prop은 Esc/바깥클릭/X만 지킨다 — 하단 '취소' 버튼은 onClose를
  // 직접 불러 그 가드를 우회하므로(Games.jsx가 이미 겪은 문제) 여기서도 requestClose로 감싼다.
  const dirty = title.trim().length > 0 || Object.values(picked).some(Boolean);
  async function requestClose() {
    if (!dirty) { onClose(); return; }
    const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?",
      { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
    if (ok) onClose();
  }
  const footer = (
    <>
      <Button onClick={requestClose}>취소</Button>
      <Button variant="primary" disabled={!canCreate} onClick={() => create.mutate()}>추가</Button>
    </>
  );
  return (
    <Modal open={open} onClose={onClose} title="새 그룹 채팅방" dirty={dirty} footer={footer}>
      <Box sx={{ mb: 2.5 }}>
        <Typography component="label" htmlFor="tc-gtitle" sx={{ display: "block", mb: 0.75, fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold }}>
          방 이름<Box component="span" sx={{ color: "error.main" }}> *</Box>
        </Typography>
        {/* maxLength는 서버(app/team_chat/schemas.py::MAX_TITLE)와 같은 값이어야 한다 — 여기가
            더 짧으면 서버는 받아 줄 이름을 화면이 미리 못 치게 막는 것이 된다. */}
        <Box
          component="input" id="tc-gtitle" maxLength={200} value={title} placeholder="예: 프로젝트 A 팀"
          onChange={(e) => setTitle(e.target.value)}
          sx={{
            width: "100%", px: 1.5, py: 1.125, font: "inherit", fontSize: FONT_SIZE.body,
            border: 1, borderColor: "divider", borderRadius: 2, bgcolor: "background.default", color: "text.primary",
            "&:focus": { outline: "none", borderColor: "primary.main" },
          }}
        />
      </Box>
      <Box>
        <Typography sx={{ display: "block", mb: 0.75, fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold }}>초대할 사람 (선택)</Typography>
        {dir.isPending ? <Skeleton lines={4} />
          : dir.isError ? <ErrorState error={dir.error} onRetry={() => dir.refetch()} />
          : users.length === 0 ? <EmptyState size="compact" title="초대할 다른 사용자가 없습니다" />
          : (
            <Box sx={PICKER_SX}>
              {users.map((u) => (
                <Box
                  key={u.user_id} component="label"
                  sx={{
                    display: "flex", alignItems: "center", gap: 1, px: 1, py: 1, borderRadius: 1.5, cursor: "pointer", fontSize: FONT_SIZE.body,
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
    onError: (e) => toast((e && e.message) || "대화를 시작하지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const users = (dir.data && dir.data.users) || [];
  return (
    <Modal open={open} onClose={onClose} title="1:1 대화 시작" footer={<Button onClick={onClose}>닫기</Button>}>
      {dir.isPending ? <Skeleton lines={5} />
        : dir.isError ? <ErrorState error={dir.error} onRetry={() => dir.refetch()} />
        : users.length === 0 ? <EmptyState size="compact" title="대화할 다른 사용자가 없습니다" />
        : (
          <Box sx={PICKER_SX}>
            {users.map((u) => (
              <Box
                key={u.user_id} component="button" type="button"
                disabled={start.isPending} onClick={() => start.mutate(u.user_id)}
                sx={{
                  display: "block", width: "100%", textAlign: "left", px: 1.5, py: 1,
                  border: 0, borderRadius: 1.5, background: "none", color: "text.primary",
                  font: "inherit", fontSize: FONT_SIZE.body, cursor: "pointer",
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

/* 채팅방 — **한 껍데기 안에 왼쪽 목록 + 오른쪽 대화** (사용자 지적 S1).
 *
 * 예전에는 목록(`/chat-rooms`)과 방(`/chat-rooms/:id`)이 **다른 라우트**라 방을 고를 때마다
 * 화면이 통째로 바뀌고, 다른 방으로 옮기려면 '목록' 버튼으로 되돌아가야 했다. 대화는 여러
 * 방을 오가며 하는 일이라 그 왕복이 계속 생긴다.
 *
 * 이제 두 라우트가 같은 껍데기를 그리고 오른쪽 칸만 바뀐다. 라우트를 유지하는 이유는
 * 알림 딥링크(`related_route: /chat-rooms/<id>`)와 새로고침·뒤로가기가 그대로 동작해야
 * 하기 때문이다 — 상태를 컴포넌트 안에 들면 그 셋이 전부 깨진다.
 *
 * 좁은 화면(md 미만)에서는 두 칸을 나란히 둘 수 없으므로 예전처럼 하나만 보여준다:
 * 방을 고르기 전에는 목록, 고른 뒤에는 대화(+ 목록으로 버튼). */
export function ChatRooms() {
  const nav = useNavigate();
  const { id: activeId } = useParams();
  const [groupOpen, setGroupOpen] = React.useState(false);
  const [directOpen, setDirectOpen] = React.useState(false);
  /* 방 검색 — 기준 목업의 `채팅방 검색`. 우리에겐 없었다. 목록은 마지막 대화 시각 순이라
     방이 열 개를 넘으면 **찾던 방이 아래로 밀려 스크롤로만 찾을 수 있다**. 서버를 부르지
     않는다: 이 목록은 이미 전부 와 있고(5초 폴링), 요청을 더 만들면 PF1 을 되풀이한다. */
  const [roomQuery, setRoomQuery] = React.useState("");
  const q = useQuery({
    queryKey: ["team-chat-rooms"],
    queryFn: () => api("/api/team-chat/rooms"),
    refetchInterval: 5000,
  });

  // 합계 안읽음(전체 채팅 포함)은 서버가 같은 응답(unread_total)에 실어 준다 — 배지 하나
  // 때문에 폴링을 하나 더 만들지 않는다. 사이드바 '채팅방' 항목 배지도 이 값을 쓴다.
  const unreadTotal = (q.data && q.data.unread_total) || 0;
  const team = q.data && q.data.team;      // 내 팀 방(Q6) — 서버가 부서 기준으로 보장한다
  const glob = q.data && q.data.global;
  const allItems = (q.data && q.data.items) || [];
  const needle = roomQuery.trim().toLowerCase();
  /* 거르는 값은 **행에 실제로 그려지는 값**이어야 한다(RoomRow 의 `room.title`).
     예전에는 `r.name` 을 봤는데 서버 응답에 그런 키가 없다(router.py 의 `_room_title` 이
     `title` 로 내려 준다) — 한 글자만 쳐도 모든 방이 undefined 와 비교돼 목록이 통째로
     비었고, 화면에는 이름이 멀쩡히 보이던 터라 "채팅방이 깨졌다" 로 읽혔다. */
  const matches = (r) => !needle || ((r && r.title) || "").toLowerCase().includes(needle);
  const items = needle ? allItems.filter(matches) : allItems;
  const open = (rid) => nav(`/chat-rooms/${rid}`);

  /* 방을 안 고르고 들어오면 **내 팀 방**을 연다 — 사용자 지적 Q6
   * ("기본으로 만들어진 방은 기본적으로 내 팀임"). 부서가 없으면 전체 채팅으로 떨어진다.
   * `replace` 로 바꾸는 이유: 뒤로가기를 눌렀을 때 빈 목록 화면으로 돌아가 다시 여기로
   * 튕기는 고리가 생기지 않게 한다. */
  React.useEffect(() => {
    if (activeId) return;
    const fallback = (team && team.id) || (glob && glob.id);
    if (fallback) nav(`/chat-rooms/${fallback}`, { replace: true });
  }, [activeId, team && team.id, glob && glob.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const listPanel = (
    // 헤더(제목줄) · 검색줄 · 목록, 자식 셋이 항상 그려지는데 트랙을 "auto 1fr" 둘만 주면
    // grid가 검색줄을 1fr(남는 세로 공간 전부)에 놓고 목록은 암시 행(auto, 내용 높이만)으로
    // 밀려나 방 목록이 패널 맨 아래에서부터 쌓이고 그 위는 통째로 빈다(사용자 지적: "채팅방이
    // 아래부터 만들어짐"). 트랙을 자식 수만큼(auto auto 1fr) 줘 목록이 1fr(남는 공간)을 갖는다.
    <Box data-testid="chatroom-list-grid" sx={{ display: "grid", gridTemplateRows: "auto auto 1fr", minHeight: 0, minWidth: 0 }}>
      <Box sx={{
        display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap",
        px: 2, py: 1.75, borderBottom: 1, borderColor: "divider",
      }}>
        <Typography component="h2" sx={{ fontWeight: 750, fontSize: FONT_SIZE.sectionTitle }}>대화</Typography>
        {unreadTotal > 0 ? (
          <Chip size="small" color="primary" label={unreadTotal > 99 ? "99+" : unreadTotal}
            sx={{ height: "1.375rem", fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold }} />
        ) : null}
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={() => setDirectOpen(true)}>1:1</Button>
        <Button size="small" variant="primary" onClick={() => setGroupOpen(true)}>새 그룹</Button>
      </Box>
      <Box sx={{ px: 2, py: 1.25, borderBottom: 1, borderColor: "divider" }}>
        <TextField
          size="small" fullWidth value={roomQuery}
          onChange={(e) => setRoomQuery(e.target.value)}
          placeholder="채팅방 검색"
          inputProps={{ "aria-label": "채팅방 이름으로 거르기" }}
        />
      </Box>
      {/* 목록은 **자기 안에서** 스크롤한다 — 페이지가 통째로 스크롤되면 대화창이 같이 밀린다. */}
      <Box data-testid="chatroom-list-rows" sx={{ minHeight: 0, overflowY: "auto" }}>
        {q.isPending ? <Box sx={{ p: 2 }}><Skeleton lines={6} /></Box>
          : q.isError ? <Box sx={{ p: 2 }}><ErrorState error={q.error} onRetry={() => q.refetch()} /></Box>
          : (
            <>
              {/* 내 팀 → 전체 채팅 → 나머지. 팀 방이 맨 위다 — 매일 쓰는 단위가 회사 전체가
                  아니라 팀이기 때문이고, 목록 안에 섞이면 마지막 대화 시각 순으로 밀린다. */}
              {team && matches(team) ? <RoomRow room={team} onOpen={open} active={activeId === team.id} /> : null}
              {glob && matches(glob) ? <RoomRow room={glob} onOpen={open} active={activeId === glob.id} /> : null}
              {items.length === 0 && !(team && matches(team)) && !(glob && matches(glob)) ? (
                /* 검색 때문에 없는 것과 정말 없는 것을 구분한다 — 같은 빈 화면에 같은 말을
                   쓰면 "채팅방이 하나도 없네" 로 읽힌다(E계열 지적). */
                needle ? (
                  <EmptyState title="검색과 맞는 채팅방이 없습니다"
                    help={`'${roomQuery.trim()}' 으로 찾은 결과가 없습니다. 검색어를 지우면 전체 목록이 보입니다.`} />
                ) : (
                  <EmptyState title="참여 중인 채팅방이 없습니다"
                    help="위의 '새 그룹' 또는 '1:1'로 대화를 시작하세요. 전체 채팅은 누구나 참여할 수 있습니다." />
                )
              ) : items.map((r) => (
                <RoomRow key={r.id} room={r} onOpen={open} active={activeId === r.id} />
              ))}
            </>
          )}
      </Box>
    </Box>
  );

  const detailPanel = activeId ? <RoomDetailPanel key={activeId} id={activeId} /> : (
    <Box sx={{ display: "grid", placeItems: "center", p: 4, minHeight: 0 }}>
      <EmptyState title="대화를 고르세요" help="왼쪽에서 방을 고르면 여기에 대화가 열립니다." />
    </Box>
  );

  return (
    <Box className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="채팅방" title="채팅방" />
      <Card
        sx={{
          p: 0, overflow: "hidden",
          display: "grid",
          // 좁은 화면에서는 한 칸만. 고른 방이 있으면 대화를, 없으면 목록을 보여준다.
          gridTemplateColumns: { xs: "1fr", md: "20rem minmax(0, 1fr)", xxl: "22.5rem minmax(0, 1fr)" },
          // 화면 아래까지 채운다. 대화창이 자기 안에서 스크롤되려면 껍데기에 높이가 있어야 한다.
          height: { xs: "auto", md: "calc(100vh - 13rem)" },
          minHeight: { xs: 0, md: "28rem" },
        }}
      >
        <Box sx={{
          display: { xs: activeId ? "none" : "grid", md: "grid" },
          borderRight: { md: 1 }, borderColor: { md: "divider" }, minHeight: 0, minWidth: 0,
        }}>
          {listPanel}
        </Box>
        <Box sx={{ display: { xs: activeId ? "grid" : "none", md: "grid" }, minHeight: 0, minWidth: 0 }}>
          {/* 좁은 화면에서만 되돌아갈 길을 준다 — 넓은 화면에서는 목록이 옆에 있다. */}
          {activeId ? (
            <Box sx={{ display: { xs: "block", md: "none" }, px: 2, pt: 1.5 }}>
              <Button size="small" onClick={() => nav("/chat-rooms")}>목록</Button>
            </Box>
          ) : null}
          {detailPanel}
        </Box>
      </Card>
      <GroupModal open={groupOpen} onClose={() => setGroupOpen(false)} />
      <DirectModal open={directOpen} onClose={() => setDirectOpen(false)} />
    </Box>
  );
}
