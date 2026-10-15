import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { FONT_SIZE, FONT_WEIGHT, NUMERIC, RADIUS } from "../../ui/theme.js";
import { GAME_LABELS } from "../Games.jsx";
import { personOf } from "./people.js";
import { LadderBoard } from "./LadderBoard.jsx";
import { RpsTournamentResult } from "./RpsViews.jsx";
import { Scoreboard } from "./Scoreboard.jsx";
import { drawPool } from "./boards/DrawBoard.jsx";
import { TeamColumns } from "./boards/TeamBoard.jsx";
import { VoteBars, voteWinnerIndexes } from "./boards/VoteBoard.jsx";
import { NumberPicks } from "./boards/NumberBoard.jsx";
import { RpsHands } from "./boards/RpsBoard.jsx";
import { quizRows, quizWinnerIds } from "./boards/QuizBoard.jsx";
import { marbleColor } from "./marble/render/theme.js";

/* 결과 대화 상자의 내용 (D-576) — 게임마다 다른 결과를 한 모양으로 옮긴다. 순수하게 `c`(컨트롤러 값)에서 만든다.
 *
 *   { gameType, game, mood: win|calm, heroTitle, headline, sentence, note, winners[], ranked, winnerLabel,
 *     detail(노드), detailLabel, detailDefaultOpen, copyText, size: md|lg }
 *
 * 당첨자 수 · 순위의 뜻 · 고유 정보(사다리 경로 · 득표 · 점수 · 대진 · 완주 순위)는 게임마다 다르고, 승자가 없는 결과(팀 나누기 ·
 * 사다리 · 무승부)는 `calm` 이다(제목과 설명만, 축포 없음). 승자 · 선택지는 **id** 로 가른다(옛 상태 행만 라벨로). 순위가 없는 추첨에
 * 1 · 2 · 3등을 만들지 않는다(`ranked` 는 구슬 레이스의 여러 당첨자만). 결과가 아직 없거나 발표할 수 없으면(구슬의 `disputed`) null. */

export const INTEGRITY_NOTES = {
  confirmed: (n) => `참가자 ${n}명의 화면과 일치한 결과입니다.`,
  host_only: () => "방장 화면의 결과입니다. 대조할 참가자 화면이 없었습니다.",
  host_absent: () => "방장 없이 참가자 다수의 화면이 낸 결과입니다.",
};

/** 숫자 뒤 목적격 조사 — 끝자리 읽기(영 · 일 · 이 · 삼 …)의 받침으로 「을/를」을 고른다. 10 · 100 처럼 0 으로 끝나면 「십 · 백」이라 「을」. */
export function objectParticle(value) {
  const digits = String(Math.abs(Math.trunc(Number(value) || 0)));
  const last = digits[digits.length - 1];
  return ["2", "4", "5", "9"].includes(last) ? "를" : "을";
}

function stepsToSeconds(steps) {
  return `${(Number(steps) * 0.01).toFixed(1)}초`;
}

function heroTitleFor(label) {
  if (label === "우승") return "우승을 축하합니다!";
  if (label === "승리") return "승리를 축하합니다!";
  return "당첨을 축하합니다!";
}

function people(c, userId, name) {
  return personOf(c.people, userId) || (userId ? { user_id: userId, name } : null);
}

function drawModel(c) {
  const pool = drawPool(c);
  const winners = c.drawWinners.map((w) => ({ id: w.user_id, name: w.name, user_id: w.user_id, person: people(c, w.user_id, w.name), kind: "person" }));
  return {
    mood: "win", winnerLabel: "당첨", heroTitle: "당첨을 축하합니다!", headline: "당첨자를 발표합니다",
    sentence: `${pool.length}명 중 ${winners.length}명을 뽑았습니다.`,
    winners, size: winners.length > 6 ? "lg" : "md",
    copyText: `랜덤 추첨 결과\n당첨: ${winners.map((w) => w.name).join(", ")}`,
  };
}

function teamModel(c) {
  const total = c.teams.reduce((n, t) => n + t.length, 0);
  return {
    mood: "calm", headline: "팀을 나눴습니다", sentence: `${total}명을 ${c.teams.length}팀으로 나눴습니다.`,
    detail: <TeamColumns teams={c.teams} people={c.people} youId={c.you.user_id} maxWidth="none" />,
    detailLabel: "팀 구성", detailDefaultOpen: true, size: c.teams.length > 3 ? "lg" : "md",
    copyText: c.teams.map((team, ti) => `${ti + 1}팀: ${team.map((m) => m.name).join(", ")}`).join("\n"),
  };
}

function ladderModel(c) {
  const result = c.gstate.result || {};
  const mine = c.ladderAssignments.find((a) => a.user_id === c.you.user_id);
  return {
    mood: "calm", headline: "사다리 결과",
    sentence: mine ? `내 결과는 「${mine.outcome}」입니다.` : "참여자마다 도착한 결과입니다.",
    detail: result.columns ? <LadderBoard key={c.room.id} result={result} highlightUserId={c.you.user_id} people={c.people} /> : (
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
        {c.ladderAssignments.map((a) => <li key={a.user_id}>{a.name} → {a.outcome}</li>)}
      </Box>
    ),
    detailLabel: "사다리", detailDefaultOpen: true, size: (result.columns || []).length > 6 ? "lg" : "md",
    copyText: c.ladderAssignments.map((a) => `${a.name} → ${a.outcome}`).join("\n"),
  };
}

function voteModel(c) {
  const vr = c.voteResult;
  const options = vr.options || [];
  const counts = vr.counts || [];
  const total = counts.reduce((n, x) => n + (Number(x) || 0), 0);
  const idx = voteWinnerIndexes(vr);
  const winners = idx.map((i) => ({ id: `o${i}`, name: options[i], note: `${counts[i] || 0}표`, kind: "option" }));
  const question = vr.question || c.gstate.question || c.room.title;
  const top = idx.length ? counts[idx[0]] || 0 : 0;
  const base = {
    detail: <VoteBars voteResult={vr} maxCount={c.maxCount} />, detailLabel: "전체 집계", detailDefaultOpen: true,
    copyText: [question, ...options.map((opt, i) => `${opt}: ${counts[i] || 0}표`)].join("\n"),
    size: options.length > 6 ? "lg" : "md", question,
  };
  if (!winners.length || total === 0) {
    return { ...base, mood: "calm", winners: [], headline: "투표 결과", sentence: "투표한 사람이 없습니다." };
  }
  return {
    ...base, mood: "win", winners, winnerLabel: "선택됨",
    heroTitle: "투표 결과가 나왔습니다",
    headline: winners.length > 1 ? "같은 표를 받은 보기가 여럿입니다" : "투표 결과가 나왔습니다",
    sentence: winners.length > 1 ? `${total}표 중 ${top}표씩 받았습니다.` : `${total}표 중 ${top}표를 받았습니다.`,
  };
}

function numberModel(c) {
  const r = c.numResult;
  const w = r.winner;
  const n = (r.picks || []).length;
  const detail = <NumberPicks numResult={r} people={c.people} youId={c.you.user_id} />;
  const copyText = (r.picks || []).map((p) => `${p.name}: ${p.number}`).join("\n");
  if (!w) return { mood: "calm", winners: [], headline: "승자가 없습니다", sentence: "유일한 숫자가 없어 승자가 없습니다.", detail, detailLabel: "공개된 숫자", detailDefaultOpen: true, copyText, size: n > 8 ? "lg" : "md" };
  return {
    mood: "win", winnerLabel: "승리", heroTitle: "승리를 축하합니다!", headline: "가장 낮은 유일한 숫자",
    winners: [{ id: w.user_id, name: w.name, user_id: w.user_id, person: people(c, w.user_id, w.name), note: `낸 숫자 ${w.number}`, kind: "person" }],
    sentence: `${n}명 중 가장 낮은 유일한 숫자 ${w.number}${objectParticle(w.number)} 냈습니다.`,
    detail, detailLabel: "공개된 숫자", detailDefaultOpen: false, copyText, size: n > 8 ? "lg" : "md",
  };
}

function rpsModel(c) {
  const r = c.rpsResult;
  if (r.mode === "tournament") {
    const champ = r.champion;
    const rounds = (r.rounds || []).length;
    const detail = <RpsTournamentResult result={r} people={c.people} />;
    const copyText = champ ? `가위바위보 토너먼트 우승: ${champ.name}` : "우승자 없음";
    if (!champ) return { mood: "calm", winners: [], headline: "우승자가 없습니다", sentence: "대진이 남지 않았습니다.", detail, detailLabel: "대진표", detailDefaultOpen: true, copyText, size: "md" };
    return {
      mood: "win", winnerLabel: "우승", heroTitle: "우승을 축하합니다!", headline: "우승자",
      winners: [{ id: champ.user_id, name: champ.name, user_id: champ.user_id, person: people(c, champ.user_id, champ.name), kind: "person" }],
      sentence: `${rounds}라운드를 이기고 우승했습니다.`,
      detail, detailLabel: "대진표", detailDefaultOpen: false, copyText, size: "md",
    };
  }
  const n = (r.reveal || []).length;
  const detail = <RpsHands rpsResult={r} people={c.people} youId={c.you.user_id} />;
  const copyText = (r.reveal || []).map((p) => `${p.name}: ${p.choice}`).join("\n");
  if (r.outcome !== "win") return { mood: "calm", winners: [], headline: "비겼습니다", sentence: "같은 손만 나왔거나 셋이 다 나왔습니다.", detail, detailLabel: "낸 손", detailDefaultOpen: true, copyText, size: n > 8 ? "lg" : "md" };
  const winners = (r.winners || []).map((w) => ({ id: w.user_id, name: w.name, user_id: w.user_id, person: people(c, w.user_id, w.name), kind: "person" }));
  return {
    mood: "win", winnerLabel: "승리", heroTitle: "승리를 축하합니다!", headline: `${r.win_choice}를 낸 사람이 이겼습니다`,
    winners,
    sentence: winners.length > 1 ? `${n}명 중 ${winners.length}명이 ${r.win_choice}를 내서 이겼습니다.` : `${n}명 중 ${r.win_choice}를 내서 이겼습니다.`,
    detail, detailLabel: "낸 손", detailDefaultOpen: false, copyText, size: winners.length > 6 || n > 8 ? "lg" : "md",
  };
}

function quizModel(c) {
  const r = c.quizResult;
  const board = r.scoreboard || [];
  const ids = quizWinnerIds(r);
  const rows = quizRows(r, c.people);
  const detail = <Scoreboard rows={rows} maxWidth="none" />;
  const copyText = board.map((s, i) => `${i + 1}. ${s.name} ${s.score}/${r.total_rounds}`).join("\n");
  const winners = board.filter((s) => ids.has(s.user_id)).map((s) => ({ id: s.user_id, name: s.name, user_id: s.user_id, person: people(c, s.user_id, s.name), note: `${s.score}점`, kind: "person" }));
  const size = board.length > 8 ? "lg" : "md";
  if (!winners.length) return { mood: "calm", winners: [], headline: "맞힌 사람이 없습니다", sentence: `${r.total_rounds}문제 중 맞힌 문제가 없습니다.`, detail, detailLabel: "최종 순위", detailDefaultOpen: true, copyText, size };
  const score = board.find((s) => ids.has(s.user_id)).score;
  return {
    mood: "win", winnerLabel: "우승", heroTitle: "우승을 축하합니다!", headline: winners.length > 1 ? "공동 우승입니다" : "우승자",
    winners,
    sentence: winners.length > 1 ? `${r.total_rounds}문제 중 ${score}문제씩 맞혀 함께 우승했습니다.` : `${r.total_rounds}문제 중 ${score}문제를 맞혀 우승했습니다.`,
    detail, detailLabel: "최종 순위", detailDefaultOpen: false, copyText, size,
  };
}

/* 구슬의 완주 순위 — 색 점 · 이름 · 걸린 시간(물리 스텝 × 10ms). */
function MarbleRanking({ ranking, finishSteps, byKey, winnerKeys, palette }) {
  return (
    <Box component="ol" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
      {ranking.map((key, i) => {
        const p = byKey.get(key);
        const won = winnerKeys.has(key);
        return (
          <Box component="li" key={key} sx={(t) => ({ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, borderRadius: `${RADIUS.sm}px`, bgcolor: won ? alpha(t.palette.primary.main, 0.1) : "transparent" })}>
            <Box component="span" sx={{ width: "1.75rem", flexShrink: 0, color: "text.secondary", ...NUMERIC, fontSize: FONT_SIZE.bodySm }}>{i + 1}</Box>
            <Box component="span" aria-hidden="true" sx={{ width: 12, height: 12, borderRadius: "50%", flexShrink: 0, bgcolor: p && palette ? marbleColor(p.hue, palette) : "divider" }} />
            <Box component="span" sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: won ? FONT_WEIGHT.bold : FONT_WEIGHT.regular }}>{p ? p.name : key}</Box>
            <Typography variant="caption" color="text.secondary" sx={NUMERIC}>{stepsToSeconds(finishSteps[i])}</Typography>
          </Box>
        );
      })}
    </Box>
  );
}

function marbleModel(c, palette) {
  const m = c.marble;
  const res = m.serverResult;
  const ranking = res.ranking || [];
  const finishSteps = res.finish_steps || [];
  const n = m.participants.length;
  const winners = (res.winners || []).map((key, i) => {
    const p = m.byKey.get(key);
    return {
      id: key, name: p ? p.name : key, user_id: p ? p.user_id : null,
      person: p && p.user_id ? people(c, p.user_id, p.name) : null,
      color: p && palette ? marbleColor(p.hue, palette) : undefined, rank: i + 1, kind: p && p.user_id ? "person" : "marble",
    };
  });
  const k = winners.length;
  let sentence;
  if (m.pickLast) sentence = k > 1 ? `${n}명 중 ${k}명이 가장 늦게 들어왔습니다.` : `${n}명 중 가장 늦게 들어왔습니다.`;
  else sentence = k > 1 ? `${n}명 중 ${k}명이 먼저 결승선을 통과했습니다.` : `${n}명 중 가장 먼저 결승선을 통과했습니다.`;
  const noteOf = INTEGRITY_NOTES[m.integrity.status];
  return {
    mood: "win", winnerLabel: "당첨", heroTitle: "당첨을 축하합니다!", headline: "당첨자를 발표합니다",
    winners, ranked: k > 1, sentence, note: noteOf ? noteOf(m.integrity.agree || 0) : null,
    detail: <MarbleRanking ranking={ranking} finishSteps={finishSteps} byKey={m.byKey} winnerKeys={m.winnerKeys} palette={palette} />,
    detailLabel: "전체 순위", detailDefaultOpen: false, size: k > 6 ? "lg" : "md",
    copyText: ["구슬 레이스 결과", `당첨: ${winners.map((w) => w.name).join(", ")}`,
      ...ranking.map((key, i) => `${i + 1}. ${m.byKey.get(key) ? m.byKey.get(key).name : key} (${stepsToSeconds(finishSteps[i])})`)].join("\n"),
  };
}

/** 결과 대화 상자의 모델. 발표할 결과가 없으면 null. `palette` 는 구슬 색(판 팔레트)이다. */
export function buildResultModel(c, palette) {
  if (!c || c.room.status !== "finished") return null;
  let m = null;
  if (c.isMarble) m = c.marble && c.marble.announceable ? marbleModel(c, palette) : null;
  else if (c.isDraw) m = c.drawWinners.length ? drawModel(c) : null;
  else if (c.isTeam) m = c.teams.length ? teamModel(c) : null;
  else if (c.isLadder) m = c.ladderAssignments.length ? ladderModel(c) : null;
  else if (c.isVote) m = c.voteResult ? voteModel(c) : null;
  else if (c.isNumber) m = c.numResult ? numberModel(c) : null;
  else if (c.isRps) m = c.rpsResult ? rpsModel(c) : null;
  else if (c.isQuiz) m = c.quizResult ? quizModel(c) : null;
  if (!m) return null;
  const game = c.isRps && c.rpsResult && c.rpsResult.mode === "tournament" ? "가위바위보 토너먼트" : (GAME_LABELS[c.room.game_type] || c.room.game_type);
  return {
    gameType: c.room.game_type, game, ranked: false, winners: [], note: null, detail: null, detailLabel: "전체 결과",
    detailDefaultOpen: false, ...m,
    heroTitle: m.heroTitle || heroTitleFor(m.winnerLabel),
  };
}
