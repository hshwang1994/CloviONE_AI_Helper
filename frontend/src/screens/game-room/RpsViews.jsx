import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { Badge } from "../../ui/kit.jsx";
import { RPS_LABELS, RPS_EMOJI, bracketListSx, rise } from "./constants.js";
import { ResultStage, StageHint, WinnerName } from "./StageShared.jsx";

/* 가위바위보 대진표(진행/토너먼트 결과) 컴포넌트 — GameRoom.jsx 구조 분리(2026-08)로 값 변경
 * 없이 이 파일로 옮겼다. 원래 이름이 T_RPS_LABELS/T_RPS_EMOJI였던 배열은 GameRoom() 안의
 * RPS_LABELS/RPS_EMOJI와 완전히 같은 값이라 constants.js의 공용 상수로 합쳤다. */

function MatchTag({ done, winner, submitted, bye }) {
  if (bye) return <Badge value="부전승" kind="info" />;
  if (done) return winner ? <Badge value="승" kind="ok" /> : <Badge value="패" kind="neutral" />;
  return submitted ? <Badge value="제출" kind="ok" /> : <Badge value="대기" kind="warn" />;
}

/* 가위바위보 선택 버튼(손 이모지 + 라벨). */
export function RpsChoices({ labels, emojis, chosen, disabled, onPick }) {
  return (
    <Stack direction="row" gap={1} justifyContent="center" flexWrap="wrap">
      {labels.map((label, i) => (
        <Box
          key={i} component="button" type="button"
          aria-pressed={chosen === i}
          disabled={disabled}
          onClick={() => onPick(i)}
          sx={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 0.5,
            px: 2, py: 1, minWidth: "5.25rem", borderRadius: 2, cursor: "pointer",
            border: 1, borderColor: chosen === i ? "primary.main" : "divider",
            bgcolor: (t) => (chosen === i ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
            color: "text.primary", font: "inherit",
            transition: "transform .12s ease, border-color .12s ease",
            "&:hover:not(:disabled)": { borderColor: "primary.main", transform: "translateY(-2px)" },
            "&:disabled": { cursor: "default", opacity: 0.6 },
          }}
        >
          <Box component="span" aria-hidden="true" sx={{ fontSize: "2.125rem", lineHeight: 1 }}>{emojis[i]}</Box>
          <Box component="span" sx={{ fontSize: "0.8125rem", fontWeight: 600 }}>{label}</Box>
        </Box>
      ))}
    </Stack>
  );
}

/* 가위바위보 토너먼트 진행 화면: 라운드 대진표 + (내 대진이면) 선택 버튼. 상대 선택은 감춘다. */
export function RpsTournamentLive({ gstate, onPick, pending, canPlay }) {
  const ym = gstate.your_match;
  return (
    <Box sx={{ display: "grid", gap: 1.5, justifyItems: "center", width: "100%" }}>
      <Typography variant="body2" color="text.secondary">라운드 {(gstate.round_idx || 0) + 1}</Typography>
      <Box component="ul" sx={bracketListSx}>
        {(gstate.matches || []).map((m, i) => (
          <Paper component="li" key={i} variant="outlined" sx={{
            display: "grid", gridTemplateColumns: "minmax(0,1fr) auto minmax(0,1fr)", alignItems: "center", gap: 1,
            px: 1.5, py: 1, bgcolor: m.done ? "action.hover" : "background.paper",
            animation: `${rise} .35s ease both`,
          }}>
            <Stack direction="row" gap={0.75} alignItems="center" minWidth={0}>
              <Box component="span" sx={{
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                fontWeight: m.done && m.winner_name === m.a_name ? 700 : 400,
                color: m.done && m.winner_name === m.a_name ? "primary.main" : "inherit",
              }}>{m.a_name}</Box>
              <MatchTag done={m.done} winner={m.winner_name === m.a_name} submitted={m.a_submitted} />
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ px: 0.5 }}>{m.bye ? "부전승" : "vs"}</Typography>
            <Stack direction="row" gap={0.75} alignItems="center" minWidth={0} justifyContent="flex-end">
              <Box component="span" sx={{
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                fontWeight: m.done && m.winner_name === m.b_name ? 700 : 400,
                color: m.done && m.winner_name === m.b_name ? "primary.main" : "inherit",
              }}>{m.b_name || "-"}</Box>
              {!m.bye ? <MatchTag done={m.done} winner={m.winner_name === m.b_name} submitted={m.b_submitted} /> : null}
            </Stack>
          </Paper>
        ))}
      </Box>
      {ym ? (
        <Box sx={{ display: "grid", gap: 1, justifyItems: "center", width: "100%", pt: 1, borderTop: 1, borderStyle: "dashed", borderColor: "divider" }}>
          <Typography sx={{ fontWeight: 700, fontSize: "1.0625rem" }}>내 상대: {ym.opponent}</Typography>
          {canPlay ? (
            <RpsChoices labels={RPS_LABELS} emojis={RPS_EMOJI} chosen={ym.your_choice} disabled={pending} onPick={onPick} />
          ) : null}
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
            {ym.you_submitted
              ? `낸 것 ${RPS_LABELS[ym.your_choice]} (다시 누르면 변경). 상대가 내면 바로 판정됩니다.`
              : "가위, 바위, 보 중 하나를 내세요."}
          </Typography>
        </Box>
      ) : (
        <StageHint>이번 라운드 대진에 없습니다. 다음 라운드를 기다려 주세요.</StageHint>
      )}
    </Box>
  );
}

/* 토너먼트 최종 결과: 우승자 + 라운드별 대진 히스토리. */
export function RpsTournamentResult({ result }) {
  return (
    <Box sx={{ display: "grid", gap: 2, justifyItems: "center", width: "100%" }}>
      <ResultStage mood={result.champion ? "win" : "calm"} label="우승">
        {result.champion
          ? <WinnerName>🏆 {result.champion.name}</WinnerName>
          : <Typography color="text.secondary">우승자가 없습니다.</Typography>}
      </ResultStage>
      <Box sx={{ display: "grid", gap: 1.5, width: "100%", maxWidth: "30rem" }}>
        {(result.rounds || []).map((rnd, ri) => (
          <Box key={ri} sx={{ display: "grid", gap: 0.5 }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>라운드 {ri + 1}</Typography>
            <Box component="ul" sx={bracketListSx}>
              {rnd.map((m, i) => (
                <Paper component="li" key={i} variant="outlined" sx={{
                  display: "grid", gridTemplateColumns: "minmax(0,1fr) auto minmax(0,1fr)", alignItems: "center", gap: 1,
                  px: 1.5, py: 1, bgcolor: "action.hover",
                }}>
                  <Box component="span" sx={{
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    fontWeight: m.winner_name === m.a_name ? 700 : 400,
                    color: m.winner_name === m.a_name ? "primary.main" : "inherit",
                  }}>{m.a_name}</Box>
                  <Typography variant="caption" color="text.secondary">{m.b_name ? "vs" : "부전승"}</Typography>
                  <Box component="span" sx={{
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "right",
                    fontWeight: m.winner_name === m.b_name ? 700 : 400,
                    color: m.winner_name === m.b_name ? "primary.main" : "inherit",
                  }}>{m.b_name || "-"}</Box>
                </Paper>
              ))}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
