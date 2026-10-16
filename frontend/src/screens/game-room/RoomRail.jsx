import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Card, Segmented } from "../../ui/kit.jsx";
import { FONT_WEIGHT } from "../../ui/theme.js";
import { GAME_RAIL_BUDGET } from "../../ui/density.js";
import { useGameRoomLayout } from "./GameRoomLayout.jsx";
import { MembersRows } from "./MembersList.jsx";
import { ChatPanel } from "./ChatPanel.jsx";

/* 오른쪽 레일 (게임 공통 G1 · D-575) — 위 판(참여자, 구슬 방은 「참여자 | 순위」) + 아래 채팅.
 *
 * 채움 모드에서는 세로 묶음이다: 위 판은 자기 내용만큼 서되 13rem 까지만(`GAME_RAIL_BUDGET.members`, 그 위는 안에서 굴린다),
 * 채팅이 남는 높이를 다 받는다 — 참여자가 마흔 명이어도 채팅 입력창은 판 바닥에 있다. 흐름 모드에서는 참가자 | 채팅 두 열이
 * 판 아래에 서고 각각 22rem 안에서 굴러간다. 모바일은 세그먼티드로 하나씩 보이되 모두 마운트를 유지한다(채팅 초안 · 스크롤 위치가
 * 탭을 오가도 남는다).
 *
 * `panes` — 위 판의 보기들 `[{ key, label, node }]`. 둘 이상이면 판 머리가 「참여자 | 순위」 전환이다. `defaultPane` 은 사용자가
 * 고르기 전의 보기(구슬 방: 대기 중 참여자, 경주가 시작되면 순위). */

export function RoomRail({ c, panes, defaultPane }) {
  const { mode } = useGameRoomLayout();
  const [picked, setPicked] = React.useState(null);
  const [mobileTab, setMobileTab] = React.useState(null);
  const membersNode = (
    <MembersRows
      members={c.members} room={c.room} you={c.you} submissionActive={c.submissionActive} submittedSet={c.submittedSet}
      maxHeight={mode === "fill" ? GAME_RAIL_BUDGET.members : "none"}
    />
  );
  const top = (panes && panes.length ? panes : [{ key: "members", label: "참여자" }])
    .map((p) => ({ ...p, node: p.key === "members" && !p.node ? membersNode : p.node }));
  const currentKey = picked && top.some((p) => p.key === picked) ? picked : (defaultPane && top.some((p) => p.key === defaultPane) ? defaultPane : top[0].key);
  const current = top.find((p) => p.key === currentKey) || top[0];

  const head = top.length > 1 ? (
    <Segmented ariaLabel="참여자와 순위 보기" value={current.key} onChange={setPicked}
      options={top.map((p) => ({ value: p.key, label: p.label }))} sx={{ alignSelf: "flex-start", mb: 1.25, flexShrink: 0 }} />
  ) : (
    <Typography component="h2" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 1, flexShrink: 0 }}>{current.label}</Typography>
  );
  const topCard = (
    <Card data-rail-top={current.key} sx={{ display: "flex", flexDirection: "column", minHeight: 0, minWidth: 0, flex: mode === "flow" ? "1 1 auto" : "0 1 auto" }}>
      {head}
      <Box sx={{ minHeight: 0, minWidth: 0, display: "flex", flexDirection: "column", flex: "1 1 auto", overflow: mode === "flow" ? "auto" : "visible" }}>
        {current.node}
      </Box>
    </Card>
  );
  const chat = (
    <ChatPanel
      chatLogRef={c.chatLogRef} chatMsgs={c.chatMsgs} you={c.you} people={c.people}
      draft={c.draft} setDraft={c.setDraft} sendChat={c.sendChat}
      chatPending={c.mutations.chat.isPending} chatFailure={c.chatFailure}
    />
  );

  if (mode === "mobile") {
    const tabs = [...top.map((p) => ({ value: p.key, label: p.label })), { value: "chat", label: "채팅" }];
    const tab = mobileTab && tabs.some((t) => t.value === mobileTab) ? mobileTab : current.key;
    return (
      <Box component="aside" aria-label="참여자와 채팅" data-room-rail={mode} sx={{ display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0 }}>
        <Segmented ariaLabel="참여자 또는 채팅" value={tab} onChange={setMobileTab} options={tabs} sx={{ alignSelf: "flex-start" }} />
        {top.map((p) => (
          <Box key={p.key} hidden={tab !== p.key} data-rail-pane={p.key} sx={{ display: tab === p.key ? "flex" : "none", flexDirection: "column", minWidth: 0 }}>
            <Card sx={{ minWidth: 0 }}>{p.node}</Card>
          </Box>
        ))}
        <Box hidden={tab !== "chat"} data-rail-pane="chat" sx={{ display: tab === "chat" ? "flex" : "none", flexDirection: "column", minWidth: 0 }}>
          {chat}
        </Box>
      </Box>
    );
  }
  if (mode === "flow") {
    return (
      <Box component="aside" aria-label="참여자와 채팅" data-room-rail={mode} sx={{
        display: "grid", gap: 2, minWidth: 0, alignItems: "stretch",
        gridTemplateColumns: { xs: "minmax(0, 1fr)", sm: "minmax(0, 1fr) minmax(0, 1fr)" },
      }}>
        <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, height: GAME_RAIL_BUDGET.flowChat }}>
          {topCard}
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, height: GAME_RAIL_BUDGET.flowChat }}>
          {chat}
        </Box>
      </Box>
    );
  }
  return (
    <Box component="aside" aria-label="참여자와 채팅" data-room-rail={mode} sx={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, minHeight: 0, flex: "1 1 auto" }}>
      {topCard}
      <Box sx={{ flex: "1 1 auto", minHeight: 0, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {chat}
      </Box>
    </Box>
  );
}
