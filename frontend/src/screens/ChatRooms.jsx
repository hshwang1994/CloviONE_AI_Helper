import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { Button, Card, PageHeader, Skeleton, ErrorState, EmptyState, Modal, useToast } from "../ui/kit.jsx";
import { fmtRelative } from "../lib/format.js";

/* 채팅방 목록 — 전체 채팅(고정) + 내가 속한 그룹/1:1. 새 그룹 만들기, 1:1 시작(디렉터리에서 상대
 * 선택). 목록만 폴링(5초)해 안읽음/미리보기를 갱신하고, 실제 대화는 방 페이지(ChatRoom)에서 한다. */

function RoomRow({ room, onOpen }) {
  return (
    <button type="button" className="tc-roomrow" onClick={() => onOpen(room.id)}>
      <span className="tc-roomrow-main">
        <span className="tc-roomrow-title">
          {room.title}
          {room.is_global ? <span className="tc-roomrow-tag">전체</span>
            : room.kind === "direct" ? <span className="tc-roomrow-tag">1:1</span>
            : <span className="tc-roomrow-tag">그룹 {room.member_count}</span>}
        </span>
        <span className="tc-roomrow-preview">{room.last_preview || "새 채팅방"}</span>
      </span>
      <span className="tc-roomrow-side">
        {room.last_at ? <span className="tc-roomrow-time">{fmtRelative(room.last_at)}</span> : null}
        {room.unread > 0 ? <span className="tc-unread">{room.unread > 99 ? "99+" : room.unread}</span> : null}
      </span>
    </button>
  );
}

function useDirectory(enabled) {
  return useQuery({
    queryKey: ["team-chat-directory"],
    queryFn: () => api("/api/team-chat/directory"),
    enabled,
  });
}

function personLabel(u) {
  const meta = [u.dept, u.title].filter(Boolean).join(" ");
  return meta ? `${u.display_name} (${meta})` : u.display_name;
}

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
      <div className="k-field">
        <label className="k-field-label" htmlFor="tc-gtitle">방 이름<span className="k-req"> *</span></label>
        <input id="tc-gtitle" className="k-input" maxLength={80} value={title} placeholder="예: 프로젝트 A 팀"
          onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div className="k-field">
        <label className="k-field-label">초대할 사람 (선택)</label>
        {dir.isPending ? <Skeleton lines={4} />
          : dir.isError ? <ErrorState error={dir.error} onRetry={() => dir.refetch()} />
          : users.length === 0 ? <div className="tc-empty">초대할 다른 사용자가 없습니다.</div>
          : (
            <div className="tc-picker">
              {users.map((u) => (
                <label key={u.user_id} className="tc-picker-row">
                  <input type="checkbox" checked={!!picked[u.user_id]}
                    onChange={(e) => setPicked((p) => ({ ...p, [u.user_id]: e.target.checked }))} />
                  <span>{personLabel(u)}</span>
                </label>
              ))}
            </div>
          )}
      </div>
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
        : users.length === 0 ? <div className="tc-empty">대화할 다른 사용자가 없습니다.</div>
        : (
          <div className="tc-picker">
            {users.map((u) => (
              <button key={u.user_id} type="button" className="tc-picker-btn"
                disabled={start.isPending} onClick={() => start.mutate(u.user_id)}>
                {personLabel(u)}
              </button>
            ))}
          </div>
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

  const actions = (
    <div className="k-row-actions">
      <Button onClick={() => setDirectOpen(true)}>1:1 대화</Button>
      <Button variant="primary" onClick={() => setGroupOpen(true)}>새 그룹</Button>
    </div>
  );

  const glob = q.data && q.data.global;
  const items = (q.data && q.data.items) || [];

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="채팅방" title="채팅방" actions={actions} />
      {q.isPending ? <Card><Skeleton lines={6} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (
          <Card>
            <div className="tc-roomlist">
              {glob ? <RoomRow room={glob} onOpen={(id) => nav(`/chat-rooms/${id}`)} /> : null}
              {items.length === 0 ? (
                <EmptyState title="참여 중인 채팅방이 없습니다"
                  help="위의 '새 그룹' 또는 '1:1 대화'로 대화를 시작하세요. 전체 채팅은 누구나 참여할 수 있습니다." />
              ) : items.map((r) => <RoomRow key={r.id} room={r} onOpen={(id) => nav(`/chat-rooms/${id}`)} />)}
            </div>
          </Card>
        )}
      <GroupModal open={groupOpen} onClose={() => setGroupOpen(false)} />
      <DirectModal open={directOpen} onClose={() => setDirectOpen(false)} />
    </div>
  );
}
