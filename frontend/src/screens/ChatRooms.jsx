import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { failureText } from "../lib/failure.js";
import { Button, Callout, Card, FieldLabel, ListEmptyState, PageHeader, Skeleton, ErrorState, EmptyState, Modal, useConfirm, CountChip, DotLabel } from "../ui/kit.jsx";
import { SearchBox } from "../ui/filters.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { GRID_GAP } from "../ui/density.js";
import { CHAT } from "../ui/chat.js";
import { fmtRelative } from "../lib/format.js";
import { PeopleFilter, PersonPickRow, filterPeople } from "./chat/peoplePicker.jsx";
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
        // 지금 보고 있는 방을 목록에서 표시한다 — 두 판이 나란히 있으니 "어느 것을 보고
        // 있는지" 가 목록에도 보여야 한다. 사이드바 활성 항목과 같은 어휘다: 함몰면 + 왼쪽 레일(핸드오프 계획 E).
        // 색만으로 알리지 않는다(`aria-current`).
        borderLeft: 3, borderLeftStyle: "solid",
        borderLeftColor: active ? "primary.main" : "transparent",
        bgcolor: active ? "background.inset" : "transparent",
        "&:last-of-type": { borderBottom: 0 },
        "&:hover": { bgcolor: active ? "background.inset" : "action.hover" },
        "&:focus-visible": { outline: (t) => `2px solid ${t.palette.focusRing}`, outlineOffset: "-2px" },
      }}
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25, minWidth: 0, flex: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.bold, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: FONT_SIZE.body }}>
            {room.title}
          </Typography>
          {/* 목록 행 안의 방 종류는 점 + 낱말이다(핸드오프 RULES §2) — 면 칩이 행마다 서면 제목보다 먼저 읽힌다. */}
          <DotLabel label={tag} size="caption" sx={{ flexShrink: 0, color: "text.secondary" }} />
        </Box>
        <Typography sx={{ color: "text.secondary", fontSize: FONT_SIZE.bodySm, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {room.last_preview || "새 채팅방"}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 0.5, flexShrink: 0 }}>
        {room.last_at ? <Typography sx={{ color: "text.secondary", fontSize: FONT_SIZE.caption }}>{fmtRelative(room.last_at)}</Typography> : null}
        {room.unread > 0 ? (
          <CountChip unread value={room.unread > 99 ? "99+" : room.unread} ariaLabel={`안 읽음 ${room.unread}`} />
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
  const confirm = useConfirm();
  const dir = useDirectory(open);
  const [title, setTitle] = React.useState("");
  /* 사람 고르기의 «좁히기» 조건. 서버 질의가 아니라 **이미 받은 후보를 거르는** 것이라
     디바운스가 필요 없다 — 네트워크가 안 간다(C7 의 클라이언트 필터와 같은 부류다). */
  const [pick_q, setPickQ] = React.useState("");
  const [picked, setPicked] = React.useState({});
  // 열 때 초기화한다 — 지난 실패도 걷는다(창은 닫혀도 요청 상태가 남는다).
  React.useEffect(() => { if (open) { setTitle(""); setPicked({}); create.reset(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const create = useMutation({
    mutationFn: () => api("/api/team-chat/rooms", {
      method: "POST",
      body: { title: title.trim(), member_user_ids: Object.keys(picked).filter((k) => picked[k]) },
    }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["team-chat-rooms"] }); onClose(); nav(`/chat-rooms/${r.room.id}`); },
  });
  /* 만들기 실패는 창 발 바로 위 메시지 박스다(핸드오프 RULES §1 — 토스트였다). 쓰던 이름 · 고른 사람은 그대로다. */
  const createFailure = failureText([create, "방을 추가하지 못했습니다. 다시 시도해 주세요."]);

  const users = (dir.data && dir.data.users) || [];

  const shownUsers = React.useMemo(() => filterPeople(users, pick_q), [users, pick_q]);
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
      {/* 라벨도 입력도 kit 계약을 쓴다 (W5 · F-W5D-132/143).
          예전에는 라벨을 손으로 그리고(필수는 `*` 하나) 입력을 `Box component="input"` 으로
          만들면서 `&:focus { outline: none }` 을 줬다 — emotion 의 `.css-x:focus` 는 특이도가
          전역 `:focus-visible` 보다 높고 시트에서 더 뒤라, **키보드 포커스 링이 지워졌다.** */}
      <Box sx={{ mb: 2.5 }}>
        <FieldLabel htmlFor="tc-gtitle" required>방 이름</FieldLabel>
        {/* maxLength는 서버(app/team_chat/schemas.py::MAX_TITLE)와 같은 값이어야 한다 — 여기가
            더 짧으면 서버는 받아 줄 이름을 화면이 미리 못 치게 막는 것이 된다. */}
        <TextField
          id="tc-gtitle" size="small" fullWidth value={title} placeholder="예: 프로젝트 A 팀"
          onChange={(e) => setTitle(e.target.value)}
          inputProps={{ maxLength: 200, "aria-required": "true" }}
        />
      </Box>
      <Box>
        <FieldLabel>초대할 사람 (선택)</FieldLabel>
        {dir.isPending ? <Skeleton lines={4} />
          : dir.isError ? <ErrorState layout="region" error={dir.error} onRetry={() => dir.refetch()} />
          : users.length === 0 ? <EmptyState size="compact" title="초대할 다른 사용자가 없습니다" />
          : (
            <>
            <PeopleFilter value={pick_q} onChange={setPickQ} count={shownUsers.length} total={users.length} />
            {shownUsers.length === 0 ? (
              /* 「사람이 없다」와 「조건 때문에 0명」은 다른 사실이다(C1). */
              <EmptyState size="compact" title="조건에 맞는 사람이 없습니다" help="이름이나 이메일 일부로 다시 찾아보세요." />
            ) : (
            <Box sx={PICKER_SX}>
              {/* 체크박스도 제품의 것을 쓴다 — 맨 `<input type=checkbox>` 는 테마의 높이·
                  포커스 링·색을 하나도 받지 않는다(F-W5D-143 ④: 체크박스가 네 종류였다). */}
              {shownUsers.map((u) => (
                <PersonPickRow
                  key={u.user_id} person={u} checked={!!picked[u.user_id]}
                  onToggle={(on) => setPicked((p) => ({ ...p, [u.user_id]: on }))}
                />
              ))}
            </Box>
            )}
            </>
          )}
      </Box>
      {createFailure ? <Callout tone="danger" compact sx={{ mt: 2.5 }}>{createFailure}</Callout> : null}
    </Modal>
  );
}

function DirectModal({ open, onClose }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const dir = useDirectory(open);
  const start = useMutation({
    mutationFn: (userId) => api("/api/team-chat/rooms/direct", { method: "POST", body: { user_id: userId } }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["team-chat-rooms"] }); onClose(); nav(`/chat-rooms/${r.room.id}`); },
  });
  // 열 때 지난 실패를 걷는다.
  React.useEffect(() => { if (open) start.reset(); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  /* 대화 시작 실패는 창 안 메시지 박스다(토스트였다). 다른 사람을 누르거나 다시 누르면 걷힌다. */
  const startFailure = failureText([start, "대화를 시작하지 못했습니다. 다시 시도해 주세요."]);
  const users = (dir.data && dir.data.users) || [];
  /* 같은 이유로 여기도 좁힐 수 있어야 한다 — 1:1 상대를 고르는 목록이 그룹 초대 목록보다
     짧을 이유가 없다(같은 디렉터리다). */
  const [pick_q, setPickQ] = React.useState("");
  const shownUsers = React.useMemo(() => filterPeople(users, pick_q), [users, pick_q]);
  return (
    <Modal open={open} onClose={onClose} title="1:1 대화 시작" footer={<Button onClick={onClose}>닫기</Button>}>
      {dir.isPending ? <Skeleton lines={5} />
        : dir.isError ? <ErrorState layout="region" error={dir.error} onRetry={() => dir.refetch()} />
        : users.length === 0 ? <EmptyState size="compact" title="대화할 다른 사용자가 없습니다" />
        : (
          <>
          <PeopleFilter value={pick_q} onChange={setPickQ} count={shownUsers.length} total={users.length} />
          {shownUsers.length === 0 ? (
            <EmptyState size="compact" title="조건에 맞는 사람이 없습니다" help="이름이나 이메일 일부로 다시 찾아보세요." />
          ) : (
          <Box sx={PICKER_SX}>
            {shownUsers.map((u) => (
              <PersonPickRow
                key={u.user_id} person={u}
                disabled={start.isPending} onPick={() => start.mutate(u.user_id)}
              />
            ))}
          </Box>
          )}
          </>
        )}
      {startFailure ? <Callout tone="danger" compact sx={{ mt: 2.5 }}>{startFailure}</Callout> : null}
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
        {/* 판 제목 글자 갈래(1.0625rem/700) — 이름 옆에 건수 칩과 동작이 붙는 판 머리는 `SectionTitle` 대신 글자 갈래만 쓴다
            (대장 §0-13). 예전 `FONT_SIZE.sectionTitle` 은 `title`(1.1875rem)의 옛 별칭이라 판 제목보다 한 단 컸다. */}
        <Typography variant="sectionTitle" component="h2">대화</Typography>
        {unreadTotal > 0 ? (
          <CountChip unread value={unreadTotal > 99 ? "99+" : unreadTotal} ariaLabel={`안 읽음 ${unreadTotal}`} />
        ) : null}
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={() => setDirectOpen(true)}>1:1</Button>
        <Button size="small" variant="primary" onClick={() => setGroupOpen(true)}>새 그룹</Button>
      </Box>
      <Box sx={{ px: 2, py: 1.25, borderBottom: 1, borderColor: "divider" }}>
        {/* 좁은 목록(296)의 검색은 부모 폭을 그대로 쓰는 검색 칸이다(`layout="fill"` — 320 슬롯은 필터 바의
            규칙이다). 목록을 글자마다 바로 거르므로 디바운스하지 않는다(`immediate`). */}
        <SearchBox
          layout="fill" immediate value={roomQuery} onSearch={setRoomQuery}
          placeholder="채팅방 검색" ariaLabel="채팅방 이름으로 거르기"
        />
      </Box>
      {/* 목록은 **자기 안에서** 스크롤한다 — 페이지가 통째로 스크롤되면 대화창이 같이 밀린다. */}
      <Box data-testid="chatroom-list-rows" sx={{ minHeight: 0, overflowY: "auto" }}>
        {q.isPending ? <Box sx={{ p: 2 }}><Skeleton lines={6} /></Box>
          : q.isError ? <Box sx={{ p: 2 }}><ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} /></Box>
          : (
            <>
              {/* 내 팀 → 전체 채팅 → 나머지. 팀 방이 맨 위다 — 매일 쓰는 단위가 회사 전체가
                  아니라 팀이기 때문이고, 목록 안에 섞이면 마지막 대화 시각 순으로 밀린다. */}
              {team && matches(team) ? <RoomRow room={team} onOpen={open} active={activeId === team.id} /> : null}
              {glob && matches(glob) ? <RoomRow room={glob} onOpen={open} active={activeId === glob.id} /> : null}
              {items.length === 0 && !(team && matches(team)) && !(glob && matches(glob)) ? (
                /* 검색 때문에 없는 것과 정말 없는 것을 구분한다 — 같은 빈 화면에 같은 말을
                   쓰면 "채팅방이 하나도 없네" 로 읽힌다(E계열 지적). */
                /* 조건을 푸는 **버튼**이 있어야 한다 (C1 · W5). 예전에는 "검색어를 지우면
                   전체 목록이 보입니다" 라고 말만 하고 지울 길을 주지 않았다. */
                <ListEmptyState
                  filtered={!!needle}
                  onClear={() => setRoomQuery("")}
                  clearLabel="검색어 지우기"
                  filteredTitle="검색과 맞는 채팅방이 없습니다"
                  filteredHelp={`'${roomQuery.trim()}' 으로 찾은 결과가 없습니다.`}
                  title="참여 중인 채팅방이 없습니다"
                  help="위의 ‘새 그룹’ 또는 ‘1:1’로 대화를 시작하세요. 전체 채팅은 누구나 참여할 수 있습니다."
                />
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
      {/* 목록과 대화는 **두 판**이다(핸드오프 RULES §9 · README §C) — 목록 296(`CHAT.listWidth`) / 대화 나머지, 사이는 판 틈.
          좁은 화면에서는 한 판만. 고른 방이 있으면 대화를, 없으면 목록을 보여준다. 화면 아래까지 채운다 — 대화창이 자기
          안에서 스크롤되려면 판에 높이가 있어야 한다. */}
      <Box
        data-chat-layout=""
        sx={{
          display: "grid", gap: GRID_GAP,
          gridTemplateColumns: { xs: "minmax(0, 1fr)", md: `${CHAT.listWidth} minmax(0, 1fr)` },
          height: { xs: "auto", md: "calc(100vh - 13rem)" },
          minHeight: { xs: 0, md: "28rem" },
        }}
      >
        <Card sx={{ p: 0, overflow: "hidden", display: { xs: activeId ? "none" : "grid", md: "grid" }, minHeight: 0, minWidth: 0 }}>
          {listPanel}
        </Card>
        <Card
          sx={{
            p: 0, overflow: "hidden", display: { xs: activeId ? "grid" : "none", md: "grid" },
            gridTemplateRows: activeId ? { xs: "auto minmax(0, 1fr)", md: "minmax(0, 1fr)" } : "minmax(0, 1fr)",
            minHeight: 0, minWidth: 0,
          }}
        >
          {/* 좁은 화면에서만 되돌아갈 길을 준다 — 넓은 화면에서는 목록이 옆에 있다. */}
          {activeId ? (
            <Box sx={{ display: { xs: "block", md: "none" }, px: 2, pt: 1.5 }}>
              <Button size="small" onClick={() => nav("/chat-rooms")}>목록</Button>
            </Box>
          ) : null}
          {detailPanel}
        </Card>
      </Box>
      <GroupModal open={groupOpen} onClose={() => setGroupOpen(false)} />
      <DirectModal open={directOpen} onClose={() => setDirectOpen(false)} />
    </Box>
  );
}
