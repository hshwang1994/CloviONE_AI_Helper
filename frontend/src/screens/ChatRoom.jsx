import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import { api } from "../lib/api.js";
import { Button, Card, ErrorState, PageHeader, Skeleton, useToast, useConfirm } from "../ui/kit.jsx";
import { ChatPane } from "./ChatPane.jsx";

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

export function ChatRoom() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();

  const meta = useQuery({
    queryKey: ["team-chat-msgs", id],
    queryFn: () => api(`/api/team-chat/rooms/${id}/messages?since=0`),
    retry: false,
  });
  const room = (meta.data && meta.data.room) || {};
  const you = (meta.data && meta.data.you) || {};

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
    return (
      <Box className="c-screen">
        <PageHeader crumbRoot="팀 공간" area="채팅방" title="채팅방" actions={<Button onClick={() => nav("/chat-rooms")}>목록</Button>} />
        <ErrorState error={meta.error} onRetry={() => meta.refetch()} />
      </Box>
    );
  }
  const canLeave = room.kind === "group" && !room.is_global;
  const busy = leave.isPending || disband.isPending || hide.isPending;
  // 방 종류(전체/1:1/그룹)는 목록 행과 같은 태그 어휘를 쓴다 — 목록에서 보던 표식이 방에 들어오면
  // 사라지면, 지금 어떤 방에 있는지(나갈 수 있는 방인지)를 제목만으로 되짚어야 한다.
  const tag = meta.isPending ? null
    : room.is_global ? "전체" : room.kind === "direct" ? "1:1" : (room.member_count ? "그룹 " + room.member_count : "그룹");
  const actions = (
    <>
      {tag ? <Chip size="small" label={tag} sx={{ height: "1.5rem", fontSize: "0.75rem", alignSelf: "center" }} /> : null}
      <Button onClick={() => nav("/chat-rooms")}>목록</Button>
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
            const ok = await confirm("이 채팅방을 나갑니다. 계속할까요?", { title: "채팅방 나가기", confirmLabel: "나가기", danger: true });
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
    <Box className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="채팅방" title={meta.isPending ? "채팅방" : (room.title || "채팅방")} actions={actions} />
      <Card sx={{ p: { xs: 1.5, sm: 2.5 } }}>
        {meta.isPending ? <Skeleton lines={6} /> : <ChatPane roomId={id} interval={1800} />}
      </Card>
    </Box>
  );
}
