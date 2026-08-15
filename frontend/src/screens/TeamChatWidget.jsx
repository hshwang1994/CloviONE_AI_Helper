import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import ForumRoundedIcon from "@mui/icons-material/ForumRounded";
import { api } from "../lib/api.js";
import { Card, ErrorState, Skeleton } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { ChatPane } from "./ChatPane.jsx";

/* 홈 하단 실시간 팀 채팅 위젯 — 전체 채팅 방을 작게 띄운다. 방 목록에서 전체 채팅 id 만 얻어
 * ChatPane 에 넘긴다.
 *
 * **오류를 조용히 숨기지 않는다** (E-4). 예전에는 `q.isError || !q.data` 한 줄로 위젯이
 * 통째로 사라졌다 — 서버가 500 을 줘도, 아직 불러오는 중이어도, 정말로 기능이 없어도
 * 화면에는 똑같이 **아무것도 없었다.** 사용자는 "팀 채팅이 없어졌다" 고 읽는다.
 * 이제 셋을 가른다:
 *   - 불러오는 중 → 스켈레톤(자리를 잡아 둔다, 레이아웃이 나중에 튀지 않게)
 *   - 기능 없음(404) 또는 볼 권한 없음(403) → 그때만 숨긴다. 없는 기능의 오류 상자는 소음이다
 *   - 그 밖의 실패 → 이유와 '다시 시도'
 *
 * **이 위젯은 홈에서 가장 비싼 부품이었다** (PF1). 재 보니 홈의 분당 24요청 중 20이 여기서
 * 나갔다 — 아무도 말하지 않는 방을 3초마다 물었기 때문이다. 대화 중에는 여전히 3초지만,
 * 응답이 그대로면 최대 30초까지 물러난다(규칙은 teamchat-poll.js). 홈은 '오늘 할 일'을
 * 보는 화면이지 채팅을 하는 화면이 아니다 — 채팅을 하러 온 사람은 채팅방 화면으로 간다.
 */
const IDLE_MAX_MS = 30000;

export function TeamChatWidget() {
  const q = useQuery({
    queryKey: ["team-chat-rooms"],
    queryFn: () => api("/api/team-chat/rooms"),
    retry: false,
  });
  // 머리글은 어느 상태에서나 같은 자리에 있다 — 상태에 따라 제목까지 사라지면 사용자는
  // "어느 카드가 실패한 것인가" 를 알 수 없다.
  const header = (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5, minWidth: 0 }}>
      <ForumRoundedIcon aria-hidden="true" sx={{ fontSize: FONT_SIZE.pageTitle, color: "primary.main" }} />
      <Typography component="h3" sx={{ flex: 1, minWidth: 0, fontSize: "1rem", fontWeight: 750 }}>팀 채팅</Typography>
      <Link href="#/chat-rooms" underline="hover" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold, flexShrink: 0 }}>
        채팅방 전체 보기
      </Link>
    </Box>
  );
  const shell = (children) => (
    <Card sx={{ mt: 2, p: { xs: 1.5, sm: 2.5 } }}>{header}{children}</Card>
  );

  if (q.isPending) return shell(<Skeleton lines={4} />);
  if (q.isError) {
    // 기능이 아예 없거나(404) 볼 권한이 없는(403) 것은 '고장' 이 아니다 — 그때만 숨긴다.
    const status = q.error && q.error.status;
    if (status === 404 || status === 403) return null;
    return shell(<ErrorState error={q.error} onRetry={() => q.refetch()} />);
  }
  const glob = q.data && q.data.global;
  // 전체 채팅 방이 없는 것은 성공한 응답의 정상적인 결과다(기능 미구성) — 조용히 숨긴다.
  if (!glob) return null;
  return shell(<ChatPane roomId={glob.id} compact interval={3000} idleMax={IDLE_MAX_MS} />);
}
