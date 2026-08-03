import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import ForumRoundedIcon from "@mui/icons-material/ForumRounded";
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
    <Card sx={{ mt: 2, p: { xs: 1.5, sm: 2.5 } }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5, minWidth: 0 }}>
        <ForumRoundedIcon aria-hidden="true" sx={{ fontSize: "1.25rem", color: "primary.main" }} />
        <Typography component="h3" sx={{ flex: 1, minWidth: 0, fontSize: "1rem", fontWeight: 750 }}>팀 채팅</Typography>
        <Link href="#/chat-rooms" underline="hover" sx={{ fontSize: "0.8125rem", fontWeight: 700, flexShrink: 0 }}>
          채팅방 전체 보기
        </Link>
      </Box>
      <ChatPane roomId={glob.id} compact interval={3000} />
    </Card>
  );
}
