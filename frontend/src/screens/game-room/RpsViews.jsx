import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { Badge, FlatBadgeSurface } from "../../ui/kit.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "../../ui/theme.js";
import { RPS_LABELS, RPS_EMOJI, bracketListSx, rise } from "./constants.js";
import { StageHint } from "./StageShared.jsx";
import { personOf } from "./people.js";

/* 가위바위보 선택 단추와 토너먼트 대진표(진행 · 결과).
 *
 * 대진 한 줄은 「얼굴 — vs — 얼굴」 마주 보기다(D-577) — 이긴 쪽이 브랜드색 이름과 테두리 얼굴로 선다. 얼굴은 신원 지도(`people`)로
 * 풀어 진행 중에 나간 사람도 남는다. */

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
            px: 2, py: 1, minWidth: "5.25rem", borderRadius: `${RADIUS.md}px`, cursor: "pointer",
            border: 1, borderColor: chosen === i ? "primary.main" : "divider",
            bgcolor: (t) => (chosen === i ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
            color: "text.primary", font: "inherit",
            transition: "transform .12s ease, border-color .12s ease",
            "&:hover:not(:disabled)": { borderColor: "primary.main", transform: "translateY(-2px)" },
            "&:disabled": { cursor: "default", opacity: 0.6 },
          }}
        >
          <Box component="span" aria-hidden="true" sx={{ fontSize: "2.125rem", lineHeight: 1 }}>{emojis[i]}</Box>
          <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold }}>{label}</Box>
        </Box>
      ))}
    </Stack>
  );
}

/* 승자는 **id** 로 가른다(P5 ②) — 동명이인이면 이름으로는 알 수 없다. id 가 없는 옛 상태 행만 이름으로 본다. */
function wonBy(m, side) {
  if (m.winner != null && (m.a != null || m.b != null)) return m.winner === m[side];
  return !!m.winner_name && m.winner_name === m[side + "_name"];
}

/* 대진의 한쪽 — 얼굴 + 이름. 오른쪽은 거울처럼 이름이 얼굴 앞에 선다. */
function Side({ id, name, won, done, mirror, people, tag }) {
  const face = id ? <UserAvatar person={personOf(people, id) || { user_id: id, name }} name={name} size="md"
    sx={won && done ? { boxShadow: (t) => `0 0 0 2px ${t.palette.background.paper}, 0 0 0 4px ${t.palette.primary.main}` } : undefined} /> : null;
  return (
    <Stack direction={mirror ? "row-reverse" : "row"} gap={0.75} alignItems="center" minWidth={0} sx={{ justifyContent: "flex-start" }}>
      {face}
      <Box component="span" title={name || ""} sx={{
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0,
        fontWeight: done && won ? FONT_WEIGHT.bold : FONT_WEIGHT.regular,
        color: done && won ? "primary.main" : "inherit",
      }}>{name || "-"}</Box>
      {tag}
    </Stack>
  );
}

function MatchRow({ m, people, live }) {
  const bye = !!m.bye || !m.b_name;
  return (
    <Paper component="li" variant="outlined" sx={{
      display: "grid", gridTemplateColumns: "minmax(0,1fr) auto minmax(0,1fr)", alignItems: "center", gap: 1,
      px: 1.5, py: 1, bgcolor: m.done ? "action.hover" : "background.paper", animation: `${rise} .35s ease both`,
    }}>
      <Side id={m.a} name={m.a_name} won={wonBy(m, "a")} done={m.done} people={people}
        tag={live ? <MatchTag done={m.done} winner={wonBy(m, "a")} submitted={m.a_submitted} /> : null} />
      <Typography variant="caption" color="text.secondary" sx={{ px: 0.5 }}>{bye ? "부전승" : "vs"}</Typography>
      {bye ? <Box /> : (
        <Side id={m.b} name={m.b_name} won={wonBy(m, "b")} done={m.done} mirror people={people}
          tag={live ? <MatchTag done={m.done} winner={wonBy(m, "b")} submitted={m.b_submitted} /> : null} />
      )}
    </Paper>
  );
}

/* 가위바위보 토너먼트 진행 화면: 라운드 대진표 + (내 대진이면) 선택 버튼. 상대 선택은 감춘다. */
export function RpsTournamentLive({ gstate, onPick, pending, canPlay, people }) {
  const ym = gstate.your_match;
  return (
    <Box sx={{ display: "grid", gap: 1.5, justifyItems: "center", width: "100%" }}>
      <Typography variant="body2" color="text.secondary">라운드 {(gstate.round_idx || 0) + 1}</Typography>
      {/* 목록 행 안이라 배지가 면을 갖지 않는다(핸드오프 RULES §2 · ACCEPTANCE F7). */}
      <FlatBadgeSurface>
        <Box component="ul" sx={bracketListSx}>
          {(gstate.matches || []).map((m, i) => <MatchRow key={i} m={m} people={people} live />)}
        </Box>
      </FlatBadgeSurface>
      {ym ? (
        <Box sx={{ display: "grid", gap: 1, justifyItems: "center", width: "100%", pt: 1.5, borderTop: 1, borderColor: "divider" }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.title }}>내 상대는 {ym.opponent}입니다.</Typography>
          {canPlay ? (
            <RpsChoices labels={RPS_LABELS} emojis={RPS_EMOJI} chosen={ym.your_choice} disabled={pending} onPick={onPick} />
          ) : null}
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
            {ym.you_submitted
              ? `${RPS_LABELS[ym.your_choice]}를 냈습니다. 다시 누르면 바뀌고, 상대가 내면 바로 판정합니다.`
              : "가위, 바위, 보 중 하나를 내세요."}
          </Typography>
        </Box>
      ) : (
        <StageHint>이번 라운드 대진에 없습니다. 다음 라운드를 기다려 주세요.</StageHint>
      )}
    </Box>
  );
}

/* 토너먼트 대진 히스토리 — 우승자는 결과 대화 상자(D-576)가 발표한다. */
export function RpsTournamentResult({ result, people }) {
  return (
    <Box sx={{ display: "grid", gap: 2, justifyItems: "center", width: "100%" }}>
      <Box sx={{ display: "grid", gap: 1.5, width: "100%", maxWidth: "30rem" }}>
        {(result.rounds || []).map((rnd, ri) => (
          <Box key={ri} sx={{ display: "grid", gap: 0.5 }}>
            <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold }}>라운드 {ri + 1}</Typography>
            <Box component="ul" sx={bracketListSx}>
              {rnd.map((m, i) => <MatchRow key={i} m={{ ...m, done: true }} people={people} />)}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
