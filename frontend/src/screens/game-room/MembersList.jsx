import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { Badge, FlatBadgeSurface, Card, ScrollArea } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "../../ui/theme.js";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { personLabel } from "../../lib/people.js";
import { ROLE_LABELS } from "./constants.js";

/* 오른쪽 레일 위쪽 — 참여자 목록. 인원수는 툴바의 「참여 n/m」이 말하므로 머리글은 「참여자」뿐이다(같은 숫자를 두 자리에 적지
 * 않는다).
 *
 * 줄은 한 줄이다(D-594) — 얼굴 · 이름 · 소속(부서 직책)이 한 줄에 서고, 넘치면 말줄임표로 자르며 전체 글은 `title` 이 든다. 예전의
 * 두 줄(이름 / 소속) 줄은 61px 라 레일에 세 명 남짓만 보였다. 줄의 기하는 구슬 순위(`marble/RankRail.jsx`)와 같아 「참여자 | 순위」를
 * 오가도 판의 결이 같다.
 *
 * `fill` 이면 목록이 판(Card)이 준 높이를 채우고 그 안에서 굴린다 — 레일(`RoomRail`)이 판의 천장(채움: 레일의 55% · 흐름: 22rem 칸)을
 * 정한다. 아니면(모바일 탭) 내용만큼 선다. `MembersList` 는 판(Card)과 머리까지 그린 단독 모양이다. */

export function MembersRows({ members, room, you, submissionActive, submittedSet, fill = false }) {
  return (
    /* 목록 행 안이라 배지가 면을 갖지 않는다(핸드오프 RULES §2 · ACCEPTANCE F7). */
    <FlatBadgeSurface>
      <ScrollArea maxHeight="none" ariaLabel="참여자 목록" sx={{ minHeight: 0, ...(fill ? { flex: "1 1 auto" } : null) }}>
        <Box component="ul" data-members-rows="" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.25 }}>
          {members.map((m) => {
            const isHostRow = m.user_id === room.host_user_id;
            const isMe = m.user_id === you.user_id;
            return (
              /* 내 줄은 옅은 면 하나로 알아본다 — 줄마다 투명 테두리 네 변을 두르면 판 안의 카드 모양 상자가 된다(F7 nested_card 실측). */
              <Box component="li" key={m.user_id} data-me-row={isMe ? "" : undefined} sx={{
                display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, minWidth: 0, borderRadius: `${RADIUS.md}px`,
                bgcolor: (t) => (isMe ? alpha(t.palette.primary.main, 0.1) : "transparent"),
              }}>
                {/* 얼굴은 제품의 한 부품이다(D-556). 방장은 강조색 테두리 한 겹으로 알아본다. */}
                <UserAvatar
                  person={m} name={m.name} size="sm"
                  sx={isHostRow ? { boxShadow: (t) => `0 0 0 2px ${t.palette.primary.main}` } : undefined}
                />
                {/* 이름 · (나) · 부서 · 직책이 글 한 줄이다. 말줄임표는 글 상자 하나가 자른다(안쪽은 인라인). 부서를 직책보다 먼저 그린다 —
                    lib/people.js::affiliation / lib/format.js::affiliationOf / app/core/people.py::affiliation 이 전부 "부서 직책"
                    (예: "개발본부 팀장") 순서를 쓰고, `title` 도 같은 규칙(`personLabel` — "김하나 (개발본부 팀장)")이다. */}
                <Box component="span" title={personLabel(m)} sx={{
                  display: "block", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                  <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold }}>{m.name}</Box>
                  {isMe ? <Box component="span" sx={{ color: "text.secondary", fontSize: FONT_SIZE.bodySm }}> (나)</Box> : null}
                  {m.dept ? <Box component="span" sx={{ ml: 1, fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{m.dept}</Box> : null}
                  {m.title ? <Box component="span" sx={{ ml: 1, fontSize: FONT_SIZE.caption, color: "primary.dark", fontWeight: FONT_WEIGHT.semibold }}>{m.title}</Box> : null}
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
      <MembersRows fill {...props} />
    </Card>
  );
}
