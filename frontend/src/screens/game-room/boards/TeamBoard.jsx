import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Surface } from "../../../ui/kit.jsx";
import { PersonLine } from "../../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, NUMERIC } from "../../../ui/theme.js";
import { BoardFrame } from "../BoardFrame.jsx";
import { personOf } from "../people.js";
import { rise } from "../constants.js";

/* 팀 나누기 판 (D-576) — 팀마다 한 칸, 칸 안은 얼굴 + 이름 줄. 결과 대화 상자의 「팀 구성」도 같은 부품(`TeamColumns`)이다. */

export function TeamColumns({ teams, people, youId, maxWidth = "64rem" }) {
  return (
    <Box sx={{ display: "grid", gap: 1.5, width: "100%", maxWidth, gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))" }}>
      {teams.map((team, ti) => (
        <Surface key={ti} tone="inset" component="section" aria-label={`${ti + 1}팀`} sx={{ p: 1.5, minWidth: 0, animation: `${rise} .38s ${ti * 60}ms ease both` }}>
          <Typography component="h3" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body, mb: 1 }}>
            {ti + 1}팀 <Box component="span" sx={{ color: "text.secondary", fontWeight: FONT_WEIGHT.regular, fontSize: FONT_SIZE.bodySm, ...NUMERIC }}>{team.length}명</Box>
          </Typography>
          <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.75 }}>
            {team.map((m) => (
              <Box component="li" key={m.user_id} sx={{ minWidth: 0 }}>
                <PersonLine person={personOf(people, m.user_id) || m} name={m.name} size="sm" bold={m.user_id === youId} />
              </Box>
            ))}
          </Box>
        </Surface>
      ))}
    </Box>
  );
}

export function TeamBoard({ c }) {
  const total = c.teams.reduce((n, t) => n + t.length, 0);
  return (
    <BoardFrame.Centered data-team-board="">
      <TeamColumns teams={c.teams} people={c.people} youId={c.you.user_id} />
      <Box component="p" sx={{ m: 0, color: "text.secondary", fontSize: FONT_SIZE.body, textAlign: "center" }}>
        {`${total}명을 ${c.teams.length}팀으로 나눴습니다.`}
      </Box>
    </BoardFrame.Centered>
  );
}
