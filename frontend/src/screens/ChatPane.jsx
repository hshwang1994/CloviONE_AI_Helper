import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { Button } from "../ui/kit.jsx";
import { fmtTimeShort } from "../lib/format.js";

/* 팀 채팅 핵심 창(폴링 로그 + 입력). 방 페이지와 홈 위젯이 공유한다. 놀이(GameRoom) 폴링 패턴 이식:
 * since=0 로 최근 메시지를 받아 seq 커서로 따라오고, 내 메시지는 오른쪽 말풍선. 탭이 숨으면 폴링을
 * 늦춰(위젯이 모든 페이지에서 도는 부담 완화) SQLite 쓰기/읽기 압박을 줄인다. */

let _cseq = 0;

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

  return (
    <div className={"tc-pane" + (compact ? " tc-pane--compact" : "")}>
      <div className="tc-log" ref={logRef}>
        {q.isPending ? <div className="tc-empty">불러오는 중…</div>
          : q.isError ? <div className="tc-empty">불러오지 못했습니다.</div>
          : msgs.length === 0 ? <div className="tc-empty">아직 메시지가 없습니다. 먼저 인사해 보세요.</div>
          : msgs.map((m) => {
            if (m.kind === "system") return <div key={m.seq} className="tc-sys">{m.body}</div>;
            const mine = m.sender_user_id === you.user_id;
            return (
              <div key={m.seq} className={"tc-msg" + (mine ? " is-mine" : "")}>
                {!mine ? <span className="tc-who">{m.sender_name || "알 수 없음"}</span> : null}
                <span className="tc-row">
                  <span className="tc-bubble">{m.body}</span>
                  <span className="tc-time">{fmtTimeShort(m.created_at)}</span>
                </span>
              </div>
            );
          })}
      </div>
      <div className="tc-input">
        <input className="k-input" maxLength={2000} value={draft} placeholder="메시지 입력"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); doSend(); } }} />
        <Button variant="primary" onClick={doSend} disabled={send.isPending}>보내기</Button>
      </div>
    </div>
  );
}
