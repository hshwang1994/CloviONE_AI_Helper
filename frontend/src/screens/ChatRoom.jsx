import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Button, ErrorState, Skeleton, useToast, useConfirm } from "../ui/kit.jsx";
import { ChatPane } from "./ChatPane.jsx";
import { ManageRoomModal, MemberStrip } from "./ChatRoomMembers.jsx";

/* 채팅방 페이지 — 헤더(방 이름·나가기·파하기·숨기기) + 폴링 채팅창(ChatPane). 방 메타는
 * 메시지 조회와 같은 쿼리 키를 써 한 번만 불러온다(react-query 중복 제거).
 *
 * 버튼 노출은 서버가 준 you.can_disband / you.can_hide 를 그대로 따른다 — 여기서 규칙을
 * 다시 쓰면(방장인가? 1:1인가? 전체인가?) 서버와 어긋나는 순간 '눌렀는데 403'이 된다.
 * 프런트 게이팅은 UX 일 뿐이고 판단은 서버가 다시 한다(불변 §5).
 *
 * '파하기'와 '숨기기'는 다른 일이다. 그룹은 방장이 파하면 모두에게서 사라지고(soft delete),
 * 1:1 은 파할 수 없어서 — dm_key 가 unique 라 soft-delete 하면 그 사람과 다시 대화를 시작할
 * 수 없다 — 내 목록에서만 숨긴다. 서버도 1:1 disband 를 409 로 막는다. */

/* '나가기' 확인 문구 — 방장이 나가면 결과가 방장이 아닐 때와 다르다(app/team_chat/
 * service.py::leave_room). 예전엔 누가 나가든 "계속할까요?" 한 문장이었는데, 방장이면
 * 남은 사람이 없을 때 **방이 사라진다**(파하기와 같은 결과) — 바로 옆 파하기 버튼만
 * "되돌릴 수 없습니다"라고 경고해, 결과가 같은 두 버튼이 다른 무게로 보였다. 문구를 갈라
 * 쓸 재료(you.role, room.member_count)는 이미 응답에 있다 — 새로 물을 것이 없다. */
export function leaveRoomConfirmMessage(you, room) {
  if (you.role !== "owner") return "이 채팅방을 나갑니다. 계속할까요?";
  if ((room.member_count || 0) <= 1) {
    return "이 채팅방을 나갑니다. 남은 참여자가 없어 방이 사라지며 되돌릴 수 없습니다.";
  }
  return "이 채팅방을 나갑니다. 방장 권한은 가장 먼저 들어온 다른 참여자에게 자동으로 넘어갑니다.";
}

/* 오른쪽 칸에 그려지는 대화 본문. 라우트 파라미터가 아니라 **prop 으로 id 를 받는다** —
 * 통합 껍데기(ChatRooms)가 왼쪽 목록과 나란히 이걸 그리기 때문이다.
 * 목록으로 돌아가는 버튼은 없다. 목록이 옆에 계속 떠 있으므로 돌아갈 곳이 없다. */
export function RoomDetailPanel({ id }) {
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [manageOpen, setManageOpen] = React.useState(false);

  const meta = useQuery({
    queryKey: ["team-chat-msgs", id],
    queryFn: () => api(`/api/team-chat/rooms/${id}/messages?since=0`),
    retry: false,
  });
  const room = (meta.data && meta.data.room) || {};
  const you = (meta.data && meta.data.you) || {};
  const members = (meta.data && meta.data.members) || [];

  // 방을 떠나면 그 방은 더 이상 볼 수 없다. 목록은 옆에 그대로 있으므로 선택만 푼다.
  const backToList = (msg) => {
    toast(msg, "info");
    qc.invalidateQueries({ queryKey: ["team-chat-rooms"] });
    nav("/chat-rooms");
  };
  const leave = useMutation({
    mutationFn: () => api(`/api/team-chat/rooms/${id}/leave`, { method: "POST" }),
    onSuccess: () => backToList("채팅방을 나갔습니다."),
    onError: (e) => toast((e && e.message) || "나가지 못했습니다.", "error"),
  });
  const disband = useMutation({
    mutationFn: () => api(`/api/team-chat/rooms/${id}/disband`, { method: "POST" }),
    onSuccess: () => backToList("채팅방을 파했습니다."),
    onError: (e) => toast((e && e.message) || "채팅방을 파하지 못했습니다.", "error"),
  });
  const hide = useMutation({
    mutationFn: () => api(`/api/team-chat/rooms/${id}/hide`, { method: "POST" }),
    onSuccess: () => backToList("내 목록에서 숨겼습니다. 새 메시지가 오면 다시 나타납니다."),
    onError: (e) => toast((e && e.message) || "숨기지 못했습니다.", "error"),
  });

  if (meta.isError) {
    return <Box sx={{ p: 3 }}><ErrorState error={meta.error} onRetry={() => meta.refetch()} /></Box>;
  }
  const canLeave = room.kind === "group" && !room.is_global;
  const busy = leave.isPending || disband.isPending || hide.isPending;
  // 방 종류(전체/내 팀/1:1/그룹)는 목록 행(ChatRooms.jsx RoomRow)과 같은 태그 어휘를 쓴다 —
  // 목록에서 보던 표식이 방에 들어오면 사라지면, 지금 어떤 방에 있는지(나갈 수 있는 방인지)를
  // 제목만으로 되짚어야 한다. department_id 분기가 빠져 있어 팀 방에 들어가면 목록에서 본
  // "내 팀"이 "그룹 N"으로 바뀌는 자기모순이 났다 — RoomRow와 같은 순서로 판정한다.
  const tag = meta.isPending ? null
    : room.is_global ? "전체" : room.department_id ? "내 팀" : room.kind === "direct" ? "1:1" : (room.member_count ? "그룹 " + room.member_count : "그룹");
  const actions = (
    <>
      {tag ? <Chip size="small" label={tag} sx={{ height: "1.5rem", fontSize: "0.75rem", alignSelf: "center" }} /> : null}
      {/* 관리(이름 변경·초대·내보내기·방장 넘기기)는 서버가 준 한 플래그로만 판단한다.
          네 동작의 조건이 모두 같으므로 버튼도 하나다 — 여기서 규칙을 다시 쓰면 어긋난다. */}
      {you.can_manage ? <Button onClick={() => setManageOpen(true)}>관리</Button> : null}
      {you.can_hide ? (
        <Button disabled={busy}
          onClick={async () => {
            const ok = await confirm("이 대화를 내 목록에서만 숨깁니다. 상대에게는 그대로 보이고, 새 메시지가 오면 다시 나타납니다.",
              { title: "대화 숨기기", confirmLabel: "숨기기" });
            if (ok) hide.mutate();
          }}>숨기기</Button>
      ) : null}
      {canLeave ? (
        <Button variant="danger" disabled={busy}
          onClick={async () => {
            const ok = await confirm(leaveRoomConfirmMessage(you, room), { title: "채팅방 나가기", confirmLabel: "나가기", danger: true });
            if (ok) leave.mutate();
          }}>나가기</Button>
      ) : null}
      {you.can_disband ? (
        <Button variant="danger" disabled={busy}
          onClick={async () => {
            const ok = await confirm("이 채팅방을 파합니다. 모든 참여자의 목록에서 사라지며 되돌릴 수 없습니다.",
              { title: "채팅방 파하기", confirmLabel: "파하기", danger: true });
            if (ok) disband.mutate();
          }}>방 파하기</Button>
      ) : null}
    </>
  );

  return (
    /* 래퍼는 flex 컬럼이다 — grid("auto 1fr")로 두면 아래 본문 칸이 자기 높이를 못 정해
       ChatPane 의 height:100% 가 MemberStrip 높이를 못 빼고 계산되고, 예전처럼 이 래퍼에
       overflowY:auto 를 얹으면 ChatPane 자신의 로그 상자와 스크롤이 두 겹으로 생긴다
       (안쪽은 이미 맨 아래로 스크롤돼 있는데 바깥은 scrollTop:0 에서 시작 — 대화가 위로
       밀려 보이는 원인). 스크롤은 ChatPane 혼자 갖는다: 헤더는 고정, 본문 칸은
       flex:"1 1 auto" 로 나머지 공간만 차지하고 그 안에서 MemberStrip 은 고정, ChatPane 을
       감싼 자리만 다시 flex:"1 1 auto" 로 남는 높이를 ChatPane 에 넘긴다. */
    <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, height: "100%" }}>
      {/* 방 머리 — 화면 제목(PageHeader)이 아니라 **칸 안의 머리**다. 왼쪽 목록과 같은 높이에서
          시작해야 두 칸이 한 판으로 읽힌다. */}
      <Box sx={{ flexShrink: 0 }}>
        <Box sx={{
          display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap",
          px: 2.5, py: 1.75, minWidth: 0,
        }}>
          <Typography component="h2" sx={{ fontWeight: 750, fontSize: "1.0625rem", minWidth: 0,
                                           overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {meta.isPending ? "채팅방" : (room.title || "채팅방")}
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>{actions}</Box>
        </Box>
        {/* 방 목록 헤더(ChatRooms.jsx listPanel)는 제목줄 + 검색줄, 2행이다. 대화창엔 검색이
            없어 한 줄뿐이지만, 그 차이만큼 빈 자리를 안 주면 두 칸의 헤더/본문 경계선이
            어긋나 한 판처럼 읽히지 않는다. 검색줄과 세로 치수를 맞춘다: py:1.25 로 감싼
            자리에 기본 컨트롤 높이 2.5rem(MuiButton.styleOverrides.root.minHeight:40 /
            design/baseline .field·.btn 의 min-height:40px 과 같은 값 — TextField(size="small")도
            이 높이로 맞춰진다)짜리 빈 칸을 두고, 그 자리 아래에 구분선을 그린다. */}
        <Box
          data-testid="chatroom-header-spacer" aria-hidden="true"
          sx={{ px: 2.5, py: 1.25, borderBottom: 1, borderColor: "divider" }}
        >
          <Box sx={{ height: "2.5rem" }} />
        </Box>
      </Box>
      <Box sx={{ display: "flex", flexDirection: "column", flex: "1 1 auto", minHeight: 0, p: { xs: 1.5, sm: 2.5 } }}>
        {meta.isPending ? <Skeleton lines={6} /> : (
          <>
            {/* 누가 지금 이 대화를 보고 있는지. 전체 채팅은 참여자 행이 없어 아무것도 그리지 않는다. */}
            <MemberStrip members={members} />
            {/* ChatPane 은 height:"100%" 로 자기 몫을 채우는 컴포넌트라, 그 100% 를 계산할
                기준(정해진 높이를 가진 부모)이 있어야 한다. flex:"1 1 auto" + minHeight:0 로
                이 자리를 만들어 준다 — 부모(위 Box)가 flex 컬럼이라 MemberStrip 이 먼저
                자기 높이를 차지하고 남는 만큼만 이 자리로 온다. */}
            <Box sx={{ flex: "1 1 auto", minHeight: 0 }}>
              <ChatPane roomId={id} interval={1800} />
            </Box>
          </>
        )}
      </Box>
      <ManageRoomModal
        open={manageOpen} onClose={() => setManageOpen(false)}
        roomId={id} title={room.title} members={members} meId={you.user_id}
      />
    </Box>
  );
}
