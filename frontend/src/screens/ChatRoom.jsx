import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { Button, Card, ErrorState, PageHeader, Skeleton, useToast, useConfirm } from "../ui/kit.jsx";
import { ChatPane } from "./ChatPane.jsx";

/* 채팅방 페이지 — 헤더(방 이름·나가기) + 폴링 채팅창(ChatPane). 방 메타는 메시지 조회와 같은
 * 쿼리 키를 써 한 번만 불러온다(react-query 중복 제거). */

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

  const leave = useMutation({
    mutationFn: () => api(`/api/team-chat/rooms/${id}/leave`, { method: "POST" }),
    onSuccess: () => { toast("채팅방을 나갔습니다.", "info"); qc.invalidateQueries({ queryKey: ["team-chat-rooms"] }); nav("/chat-rooms"); },
    onError: (e) => toast((e && e.message) || "나가지 못했습니다.", "error"),
  });

  if (meta.isError) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="팀 공간" area="채팅방" title="채팅방" actions={<Button onClick={() => nav("/chat-rooms")}>목록</Button>} />
        <ErrorState error={meta.error} onRetry={() => meta.refetch()} />
      </div>
    );
  }
  const canLeave = room.kind === "group" && !room.is_global;
  const actions = (
    <div className="k-row-actions">
      <Button onClick={() => nav("/chat-rooms")}>목록</Button>
      {canLeave ? (
        <Button variant="danger" disabled={leave.isPending}
          onClick={async () => {
            const ok = await confirm("이 채팅방을 나갑니다. 계속할까요?", { title: "채팅방 나가기", confirmLabel: "나가기", danger: true });
            if (ok) leave.mutate();
          }}>나가기</Button>
      ) : null}
    </div>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="채팅방" title={meta.isPending ? "채팅방" : (room.title || "채팅방")} actions={actions} />
      <Card>
        {meta.isPending ? <Skeleton lines={6} /> : <ChatPane roomId={id} interval={1800} />}
      </Card>
    </div>
  );
}
