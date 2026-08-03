import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { Card } from "../ui/kit.jsx";
import { ChatPane } from "./ChatPane.jsx";

/* 홈 하단 실시간 팀 채팅 위젯 — 전체 채팅 방을 작게 띄운다. 방 목록에서 전체 채팅 id 만 얻어
 * ChatPane 에 넘긴다. 기능이 꺼져 있거나(404) 오류면 조용히 숨긴다(홈의 다른 부분 무영향). */

export function TeamChatWidget() {
  const q = useQuery({
    queryKey: ["team-chat-rooms"],
    queryFn: () => api("/api/team-chat/rooms"),
    retry: false,
  });
  if (q.isError || !q.data) return null;
  const glob = q.data.global;
  if (!glob) return null;
  return (
    <Card className="tc-widget">
      <div className="c-card-head">
        <h3>팀 채팅</h3>
        <a className="k-link" href="#/chat-rooms">채팅방 전체 보기</a>
      </div>
      <ChatPane roomId={glob.id} compact interval={3000} />
    </Card>
  );
}
