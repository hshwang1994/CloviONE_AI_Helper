import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Badge, FlatBadgeSurface } from "../../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../../ui/theme.js";
import { BoardFrame } from "../BoardFrame.jsx";
import { personOf } from "../people.js";
import { PeopleGrid, PersonTile, usePeopleTileSize } from "./PersonTile.jsx";

/* 대기 판 (D-575) — 시작 전의 판도 온전한 판이다. 참여자 얼굴 격자와 문장 하나.
 *
 * 예전에는 점선 한 줄(「참여자가 모이면 방장이 추첨을 시작합니다.」)뿐이라 판 자리가 접혀 있었고, 시작하면 판이 튀어나와 레일 ·
 * 동작 줄이 함께 밀렸다. 이제 대기 · 진행 · 종료가 같은 틀(`BoardFrame`) 안의 같은 크기다. 관전자는 격자에 서지 않는다(참여가 아니다). */

export const WAITING_SENTENCES = {
  random_draw: "참여자가 모이면 방장이 추첨을 시작합니다.",
  team_split: "참여자가 모이면 방장이 팀을 나눕니다.",
  ladder: "참여자가 모이면 방장이 사다리를 탑니다.",
  number: "참여자가 모이면 방장이 숫자 눈치를 시작합니다.",
  rps: "참여자가 모이면 방장이 가위바위보를 시작합니다.",
  quiz: "참여자가 모이면 방장이 퀴즈를 시작합니다.",
  quick_vote: "참여자가 모이면 방장이 투표를 엽니다.",
};

export function WaitingBoard({ c, title, sentence, children }) {
  const { members, room, you, people, isDraw } = c;
  const players = (members || []).filter((m) => m.role !== "spectator");
  const size = usePeopleTileSize(players.length);
  return (
    <BoardFrame.Centered data-waiting-board="">
      {title ? (
        <Typography component="p" sx={{ fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.bold, textAlign: "center", ...KO_WORD_BREAK }}>
          {title}
        </Typography>
      ) : null}
      {children}
      <FlatBadgeSurface>
        <PeopleGrid count={players.length} size={size} label="참여자">
          {players.map((m) => {
            const host = m.user_id === room.host_user_id;
            return (
              <PersonTile size={size}
                key={m.user_id}
                person={personOf(people, m.user_id) || m}
                name={m.name}
                me={m.user_id === you.user_id}
                sub={host ? "방장" : null}
                badge={isDraw && m.role === "player" && m.ready ? <Badge value="준비" kind="ok" /> : null}
              />
            );
          })}
        </PeopleGrid>
      </FlatBadgeSurface>
      <Box component="p" sx={{ m: 0, color: "text.secondary", fontSize: FONT_SIZE.body, textAlign: "center", ...KO_WORD_BREAK }}>
        {sentence || WAITING_SENTENCES[room.game_type] || "참여자가 모이면 방장이 게임을 시작합니다."}
      </Box>
    </BoardFrame.Centered>
  );
}
