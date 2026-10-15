import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { Badge, FlatBadgeSurface, Card, ScrollArea } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "../../ui/theme.js";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { GAME_RAIL_BUDGET } from "../../ui/density.js";
import { ROLE_LABELS } from "./constants.js";

/* 오른쪽 레일 위쪽 — 참여자 목록. 인원수는 툴바의 「참여 n/m」이 말하므로 머리글은 「참여자」뿐이다(같은 숫자를 두 자리에 적지
 * 않는다). 목록은 `ScrollArea`(13rem) 안이라 아무리 많아도 채팅을 밀어내지 않고, 넘칠 때만 스크롤바 · 초점을 갖는다.
 * `bare` 면 판(Card)과 머리 없이 목록만 그린다 — 레일(`RoomRail`)이 판 머리에 「참여자 | 순위」 전환을 세울 때다. */

export function MembersRows({ members, room, you, submissionActive, submittedSet, maxHeight = GAME_RAIL_BUDGET.members }) {
  return (
    /* 목록 행 안이라 배지가 면을 갖지 않는다(핸드오프 RULES §2 · ACCEPTANCE F7). */
    <FlatBadgeSurface>
      <ScrollArea maxHeight={maxHeight} ariaLabel="참여자 목록" sx={{ minHeight: 0 }}>
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
          {members.map((m) => {
            // 부서를 직책보다 먼저 그린다 — lib/people.js::affiliation / lib/format.js::affiliationOf /
            // app/core/people.py::affiliation 이 전부 "부서 직책"(예: "개발본부 팀장") 순서를 쓴다.
            const sub = [m.dept, m.title].filter(Boolean);
            const isHostRow = m.user_id === room.host_user_id;
            const isMe = m.user_id === you.user_id;
            return (
              /* 내 줄은 옅은 면 하나로 알아본다 — 줄마다 투명 테두리 네 변을 두르면 판 안의 카드 모양 상자가 된다(F7 nested_card 실측). */
              <Box component="li" key={m.user_id} data-me-row={isMe ? "" : undefined} sx={{
                display: "flex", alignItems: "center", gap: 1.25, p: 1, borderRadius: `${RADIUS.md}px`,
                bgcolor: (t) => (isMe ? alpha(t.palette.primary.main, 0.1) : "transparent"),
              }}>
                {/* 얼굴은 제품의 한 부품이다(D-556). 방장은 강조색 테두리 한 겹으로 알아본다. */}
                <UserAvatar
                  person={m} name={m.name} size="md"
                  sx={isHostRow ? { boxShadow: (t) => `0 0 0 2px ${t.palette.primary.main}` } : undefined}
                />
                <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
                  <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: FONT_WEIGHT.semibold }}>
                    {m.name}{isMe ? <Box component="span" sx={{ color: "text.secondary", fontWeight: FONT_WEIGHT.regular, fontSize: FONT_SIZE.bodySm }}> (나)</Box> : null}
                  </Box>
                  {sub.length ? (
                    <Box component="span" sx={{
                      display: "flex", gap: 1, fontSize: FONT_SIZE.caption, color: "text.secondary",
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    }}>
                      {m.dept ? <Box component="span">{m.dept}</Box> : null}
                      {m.title ? <Box component="span" sx={{ color: "primary.dark", fontWeight: FONT_WEIGHT.semibold }}>{m.title}</Box> : null}
                    </Box>
                  ) : null}
                </Box>
                <Stack direction="row" gap={0.5} alignItems="center" sx={{ ml: "auto", flexShrink: 0 }}>
                  {/* 명단엔 남아 있어도(active) 90초 넘게 폴링이 없으면 추첨·팀나누기·사다리·
                      투표 대상 풀에서는 빠진다(app/games/service.py::_present_players,
                      step 9 #7) - 그 어긋남을 결과가 나오기 전에 미리 알린다. */}
                  {m.present === false ? <Badge value="자리 비움" kind="neutral" /> : null}
                  {isHostRow
                    ? <Badge value="방장" kind="info" />
                    : <Badge value={ROLE_LABELS[m.role] || m.role} kind="neutral" />}
                  {submissionActive && m.role !== "spectator"
                    ? (submittedSet.has(m.user_id)
                      ? <Badge value="제출" kind="ok" />
                      : <Badge value="대기" kind="warn" />)
                    : (m.role === "player" && m.ready ? <Badge value="준비" kind="ok" /> : null)}
                </Stack>
              </Box>
            );
          })}
        </Box>
      </ScrollArea>
    </FlatBadgeSurface>
  );
}

export function MembersList(props) {
  return (
    <Card data-members-list="" sx={{ flexShrink: 1, minHeight: 0, display: "flex", flexDirection: "column", minWidth: 0 }}>
      <Typography component="h2" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 1, flexShrink: 0 }}>참여자</Typography>
      <MembersRows {...props} />
    </Card>
  );
}
