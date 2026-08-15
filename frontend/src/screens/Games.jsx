import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Radio from "@mui/material/Radio";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Badge, Button, Callout, Card, EmptyState, ErrorState, Modal, ModalFooter, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { FONT_WEIGHT, PROSE_MAX_WIDTH } from "../ui/theme.js";

/* 팀 공간 > 놀이 (§5). 한 페이지에서 모든 게임방을 보고, 여기서 방을 만든다(별도 페이지 분리
 * 안 함). 목록은 3초 폴링으로 새 방을 실시간처럼 보여준다. 첫 게임=랜덤 추첨.
 *
 * 2026-08 MUI 재설계: 방 만들기 폼이 손으로 쓴 .k-input 마크업이었는데 kit.css가 걷히면서
 * 규칙이 전부 사라져 브라우저 기본 입력 상자로 떠 있었다(라벨·도움말 간격도 무너졌다).
 * MUI 폼 컨트롤로 옮겨 테마 하나를 따르게 한다. 카드 격자는 auto-fill이라 4K에서 열이 늘어난다. */

export const GAME_LABELS = { random_draw: "랜덤 추첨", quick_vote: "빠른 투표", team_split: "랜덤 팀 나누기", number: "숫자 눈치", ladder: "사다리타기", rps: "가위바위보", quiz: "실시간 퀴즈" };
const STATUS_LABELS = { waiting: "대기 중", playing: "진행 중", finished: "결과 확인 중" };
const STATUS_KIND = { waiting: "info", playing: "warn", finished: "ok" };

const MAX_OPTIONS = 8;
const MAX_QUESTIONS = 20;
const EMPTY_Q = { q: "", options: ["", ""], answer: 0 };

/* fullWidth 입력 옆에 놓이는 버튼 — 플렉스 줄에서 먼저 눌려 글자가 두 줄로 깨지지 않게 한다. */
const NOSHRINK = { flexShrink: 0, whiteSpace: "nowrap" };

/* 실시간 퀴즈 문제 편집기. 문제마다 지문 + 보기(2~6) + 정답(라디오). 정답은 서버가 채점한다. */
function QuizEditor({ questions, setQuestions }) {
  const patch = (i, next) => setQuestions((prev) => prev.map((q, idx) => (idx === i ? next : q)));
  const setText = (i, v) => patch(i, { ...questions[i], q: v });
  const setOpt = (i, oi, v) => patch(i, { ...questions[i], options: questions[i].options.map((o, x) => (x === oi ? v : o)) });
  const addOpt = (i) => questions[i].options.length < 6 && patch(i, { ...questions[i], options: [...questions[i].options, ""] });
  const removeOpt = (i, oi) => {
    const q = questions[i];
    if (q.options.length <= 2) return;
    const options = q.options.filter((_, x) => x !== oi);
    // 정답은 보기 배열의 "인덱스"로만 추적된다(보기에 안정적 id가 없다 — 아래 options.map의
    // key가 배열 인덱스 oi 그 자체). 예전 코드는 `answer >= options.length`일 때만 보정해서,
    // 정답보다 앞의 보기를 지우면 배열이 한 칸씩 당겨지는데도 정답 인덱스는 그대로 남아
    // 슬라이드해 들어온 다른 보기를 방장 모르게 "정답"으로 만들었다(방장이 C를 찍고 A를
    // 지우면 서버는 D를 정답으로 채점). 지운 인덱스가 정답보다 앞이면 정답도 한 칸 당기고,
    // 정답 그 자체를 지웠다면 새 정답을 추측하지 않고 미지정(-1)으로 되돌려 방장이 다시
    // 고르게 한다.
    const answer = oi < q.answer ? q.answer - 1 : oi === q.answer ? -1 : q.answer;
    patch(i, { ...q, options, answer });
  };
  const setAnswer = (i, oi) => patch(i, { ...questions[i], answer: oi });
  const addQuestion = () => setQuestions((prev) => (prev.length >= MAX_QUESTIONS ? prev : [...prev, { ...EMPTY_Q, options: ["", ""] }]));
  const removeQuestion = (i) => setQuestions((prev) => (prev.length <= 1 ? prev : prev.filter((_, x) => x !== i)));

  return (
    <Box sx={{ display: "grid", gap: 1.5 }}>
      {questions.map((q, i) => (
        <Paper key={i} variant="outlined" sx={{ p: 2, display: "grid", gap: 1.5 }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1}>
            <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold }}>문제 {i + 1}</Typography>
            {questions.length > 1 ? <Button size="sm" onClick={() => removeQuestion(i)}>문제 삭제</Button> : null}
          </Stack>
          <TextField
            size="small" fullWidth value={q.q} placeholder="질문을 입력하세요"
            inputProps={{ maxLength: 200, "aria-label": `문제 ${i + 1} 질문` }}
            onChange={(e) => setText(i, e.target.value)}
          />
          <Box sx={{ display: "grid", gap: 1 }}>
            {q.options.map((o, oi) => (
              <Stack key={oi} direction="row" gap={1} alignItems="center">
                <FormControlLabel
                  sx={{ m: 0, flexShrink: 0 }}
                  control={
                    <Radio
                      size="small"
                      name={"quiz-ans-" + i}
                      checked={q.answer === oi}
                      onChange={() => setAnswer(i, oi)}
                    />
                  }
                  label={<Typography variant="caption" color="text.secondary">정답</Typography>}
                />
                <TextField
                  size="small" fullWidth value={o} placeholder={"보기 " + (oi + 1)}
                  inputProps={{ maxLength: 80, "aria-label": `문제 ${i + 1} 보기 ${oi + 1}` }}
                  onChange={(e) => setOpt(i, oi, e.target.value)}
                />
                {q.options.length > 2 ? <Button size="sm" sx={NOSHRINK} onClick={() => removeOpt(i, oi)}>삭제</Button> : null}
              </Stack>
            ))}
            {q.options.length < 6 ? <Box><Button size="sm" onClick={() => addOpt(i)}>보기 추가</Button></Box> : null}
            {/* 정답으로 찍었던 보기를 지우면(removeOpt) 새 정답을 추측하지 않고 미지정(-1)으로
             * 되돌린다 — 방장이 못 보고 넘어가지 않도록 라디오가 전부 비어 보이는 것과 별개로
             * 글로 한 번 더 알린다("몰래 다른 보기가 정답이 되는" 문제의 재발 지점). */}
            {q.answer < 0 ? <Callout tone="warn">정답으로 표시했던 보기를 지웠습니다. 정답을 다시 선택해 주세요.</Callout> : null}
          </Box>
        </Paper>
      ))}
      {questions.length < MAX_QUESTIONS ? <Box><Button size="sm" onClick={addQuestion}>문제 추가</Button></Box> : null}
    </Box>
  );
}

function CreateRoomModal({ open, onClose, onCreated, aiEnabled }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [gameType, setGameType] = useState("random_draw");
  const [title, setTitle] = useState("");
  const [maxPlayers, setMaxPlayers] = useState(8);
  const [winners, setWinners] = useState(1);
  const [teams, setTeams] = useState(2);
  const [numMax, setNumMax] = useState(10);
  const [timer, setTimer] = useState(15);
  const [rpsMode, setRpsMode] = useState("single");
  const [question, setQuestion] = useState("");
  const [options, setOptions] = useState(["", ""]);
  const [quizQs, setQuizQs] = useState([{ q: "", options: ["", ""], answer: 0 }]);
  const [aiTopic, setAiTopic] = useState("");
  const [aiCount, setAiCount] = useState(5);
  const [spectators, setSpectators] = useState(true);
  React.useEffect(() => {
    if (open) {
      setGameType("random_draw"); setTitle(""); setMaxPlayers(8); setWinners(1); setTeams(2); setNumMax(10);
      setQuestion(""); setOptions(["", ""]); setQuizQs([{ q: "", options: ["", ""], answer: 0 }]);
      // 제한 시간은 "random_draw"(제한 시간 없음)의 기본값(0)으로 리셋한다 - 아래 [gameType]
      // effect와 같은 공식을 써야 한다. 여기서 gameType과 다른 값(예: 15)을 박아 두면, gameType이
      // 이미 "random_draw"라 값이 그대로라 아래 effect가 다시 돌지 않고(React가 동일값 setState는
      // 재실행을 건너뛴다) timer가 잘못된 값으로 굳어, 아무것도 안 바꾸고 열자마자 닫아도
      // dirty가 거짓으로 true가 되어 확인 대화상자가 새로 열 때마다 떴다.
      setAiTopic(""); setAiCount(5); setSpectators(true); setTimer(0); setRpsMode("single");
    }
  }, [open]);
  // 게임을 바꾸면 그 게임에 맞는 제한 시간 기본값으로(가위바위보 15초, 퀴즈 25초, 그 외 무제한).
  React.useEffect(() => {
    setTimer(gameType === "rps" ? 15 : gameType === "quiz" ? 25 : 0);
  }, [gameType]);

  // AI 퀴즈 생성: 러너(Claude)가 만든 문제로 quizQs를 채운다. 결과는 아래 QuizEditor에서 검토·수정.
  const genAi = useMutation({
    mutationFn: () => api("/api/games/quiz/generate", { method: "POST", body: { topic: aiTopic.trim(), count: Number(aiCount) || 5 } }),
    onSuccess: (res) => {
      const qs = (res.questions || []).map((q) => ({ q: q.q, options: q.options, answer: q.answer }));
      if (qs.length) { setQuizQs(qs); toast(`문제 ${qs.length}개를 만들었어요. 검토하고 수정한 뒤 방을 추가하세요.`, "success"); }
      else toast("생성된 문제가 없습니다. 주제를 더 구체적으로 적어 보세요.", "error");
    },
    onError: (e) => toast((e && e.message) || "AI 생성에 실패했습니다. 다시 시도해 주세요.", "error"),
  });

  const setOption = (i, v) => setOptions((prev) => prev.map((o, idx) => (idx === i ? v : o)));
  const addOption = () => setOptions((prev) => (prev.length >= MAX_OPTIONS ? prev : [...prev, ""]));
  const removeOption = (i) => setOptions((prev) => (prev.length <= 2 ? prev : prev.filter((_, idx) => idx !== i)));

  const cleanOptions = options.map((o) => o.trim()).filter(Boolean);
  const isVote = gameType === "quick_vote";
  const isTeam = gameType === "team_split";
  const isNumber = gameType === "number";
  const isLadder = gameType === "ladder";
  const isRps = gameType === "rps";
  const isQuiz = gameType === "quiz";
  const needsOptions = isVote || isLadder;  // 선택지/결과 목록을 쓰는 게임
  const optionsReady = !needsOptions || cleanOptions.length >= 2;
  const questionReady = !isVote || question.trim().length > 0;
  const cleanQuiz = quizQs
    .map((q) => ({ q: q.q.trim(), options: q.options.map((o) => o.trim()), answer: q.answer }))
    .filter((q) => q.q && q.options.length >= 2 && q.options.every(Boolean) && q.answer >= 0 && q.answer < q.options.length);
  const quizReady = !isQuiz || cleanQuiz.length >= 1;
  const timed = isVote || isNumber || isRps || isQuiz;
  const timerVal = Math.max(0, Math.min(Number(timer) || 0, 300));
  const config = isVote
    ? { question: question.trim(), options: cleanOptions, timer_seconds: timerVal }
    : isLadder
      ? { options: cleanOptions }
      : isTeam
        ? { teams: Number(teams) || 2 }
        : isNumber
          ? { min: 1, max: Number(numMax) || 10, timer_seconds: timerVal }
          : isRps
            ? { timer_seconds: timerVal, mode: rpsMode }
            : isQuiz
              ? { questions: cleanQuiz, timer_seconds: timerVal }
              : { winners: Number(winners) || 1 };

  const create = useMutation({
    mutationFn: () => api("/api/games/rooms", {
      method: "POST",
      body: { title, game_type: gameType, max_players: Number(maxPlayers) || 8, allow_spectators: spectators, config },
    }),
    onSuccess: (res) => { toast("게임방을 만들었습니다.", "success"); onCreated && onCreated(res.room); },
    onError: (e) => toast((e && e.message) || "게임방을 만들지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const canSave = title.trim().length > 0 && optionsReady && questionReady && quizReady && !create.isPending;

  // 뭔가 입력했으면 Esc·바깥 클릭에 그냥 닫히지 않게 한다 (E11). 퀴즈는 최대 20문항이라
  // 한 번의 실수로 사라지는 양이 크다 - 그리고 되돌릴 방법이 없다.
  // 열 때 초기화하는 값들과 **같은 기준**으로 본다(위 useEffect 참조). 판정이 갈리면
  // "안 바꿨는데 물어본다"(성가심)거나 "바꿨는데 안 물어본다"(데이터 손실)가 된다.
  // 텍스트 필드(제목/질문/선택지/AI 주제/퀴즈)만 보고 있었다 — 당첨 인원·팀 수·숫자 범위·
  // 제한 시간·가위바위보 방식·관전 허용처럼 숫자/셀렉트로 바꾼 값은 판정에서 빠져 있어
  // 그 값만 바꾸고 닫으면 확인 없이 그대로 사라졌다. 열 때 리셋하는 기본값과 비교해 채운다.
  const defaultTimer = gameType === "rps" ? 15 : gameType === "quiz" ? 25 : 0;
  const dirty =
    title.trim().length > 0 ||
    question.trim().length > 0 ||
    options.some((o) => o.trim().length > 0) ||
    aiTopic.trim().length > 0 ||
    quizQs.some((q) => q.q.trim().length > 0 || q.options.some((o) => o.trim().length > 0)) ||
    Number(maxPlayers) !== 8 ||
    Number(winners) !== 1 ||
    Number(teams) !== 2 ||
    Number(numMax) !== 10 ||
    Number(timer) !== defaultTimer ||
    Number(aiCount) !== 5 ||
    rpsMode !== "single" ||
    !spectators;

  // 하단 '취소' 버튼 전용 닫기 경로. `Modal`의 `dirty` prop은 X 아이콘·Esc·바깥 클릭에서
  // 오는 내부 onClose만 지킨다 — 이 모달이 footer로 넘기는 `ModalFooter`의 onCancel은 Modal을
  // 거치지 않고 곧장 CreateRoomModal이 받은 onClose를 불렀다. 그래서 다른 경로는 전부 확인을
  // 받으면서 '취소' 버튼만 확인 없이 바로 닫혔다. 문구는 Modal 내부·FormModal과 같게 맞춘다
  // (같은 상황에 다른 말이 나오면 사용자는 다른 일이 일어난다고 읽는다).
  const requestClose = async () => {
    if (!dirty) { onClose(); return; }
    const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?",
      { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
    if (ok) onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title="게임방 추가" size="md" dirty={dirty}
      footer={<ModalFooter onCancel={requestClose} onSubmit={() => canSave && create.mutate()} submitLabel="추가" busy={create.isPending} />}>
      <Box sx={{ display: "grid", gap: 2.5 }}>
        <TextField
          id="gr-game" select size="small" fullWidth label="게임"
          value={gameType} onChange={(e) => setGameType(e.target.value)}
        >
          <MenuItem value="random_draw">랜덤 추첨</MenuItem>
          <MenuItem value="quick_vote">빠른 투표</MenuItem>
          <MenuItem value="team_split">랜덤 팀 나누기</MenuItem>
          <MenuItem value="number">숫자 눈치</MenuItem>
          <MenuItem value="ladder">사다리타기</MenuItem>
          <MenuItem value="rps">가위바위보</MenuItem>
          <MenuItem value="quiz">실시간 퀴즈</MenuItem>
        </TextField>

        <TextField
          id="gr-title" size="small" fullWidth required label="방 제목"
          inputProps={{ maxLength: 120 }} value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder={isVote ? "예: 오늘 점심 정하기" : isTeam ? "예: 축구 팀 나누기" : isLadder ? "예: 청소 당번 사다리" : isQuiz ? "예: 사내 상식 퀴즈" : "예: 점심 커피 추첨"}
        />

        {needsOptions ? (
          <>
            {isVote ? (
              <TextField
                id="gr-q" size="small" fullWidth required label="질문"
                inputProps={{ maxLength: 120 }} value={question} onChange={(e) => setQuestion(e.target.value)}
                placeholder="예: 점심 뭐 먹을까요?"
              />
            ) : null}
            <Box>
              <Typography variant="body2" color="text.secondary" id="gr-opts-label" sx={{ mb: 1 }}>
                {isLadder ? "결과 (사다리 도착지)" : "선택지"}
                <Box component="span" sx={{ color: "error.main" }}> *</Box>
              </Typography>
              <Box role="group" aria-labelledby="gr-opts-label" sx={{ display: "grid", gap: 1 }}>
                {options.map((o, i) => (
                  <Stack key={i} direction="row" gap={1} alignItems="center">
                    <TextField
                      size="small" fullWidth value={o}
                      inputProps={{ maxLength: 40, "aria-label": (isLadder ? "결과 " : "선택지 ") + (i + 1) }}
                      onChange={(e) => setOption(i, e.target.value)}
                      placeholder={(isLadder ? "결과 " : "선택지 ") + (i + 1)}
                    />
                    {options.length > 2 ? <Button size="sm" sx={NOSHRINK} onClick={() => removeOption(i)}>삭제</Button> : null}
                  </Stack>
                ))}
                {options.length < MAX_OPTIONS ? (
                  <Box><Button size="sm" onClick={addOption}>{isLadder ? "결과 추가" : "선택지 추가"}</Button></Box>
                ) : null}
              </Box>
              {isLadder ? (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                  참여자보다 결과가 적으면 나머지는 ‘꽝’으로 채워집니다.
                </Typography>
              ) : null}
            </Box>
          </>
        ) : isTeam ? (
          <TextField
            id="gr-teams" type="number" size="small" fullWidth label="팀 수"
            inputProps={{ min: 2, max: 8 }} value={teams} onChange={(e) => setTeams(e.target.value)}
          />
        ) : isNumber ? (
          <TextField
            id="gr-nummax" type="number" size="small" fullWidth label="숫자 범위 (1 ~ ?)"
            inputProps={{ min: 2, max: 100 }} value={numMax} onChange={(e) => setNumMax(e.target.value)}
            helperText={`참여자가 1~${Number(numMax) || 10} 중 하나를 몰래 냅니다. 가장 낮은 ‘유일한’ 숫자를 낸 사람이 승리해요.`}
          />
        ) : isRps ? (
          <TextField
            id="gr-rpsmode" select size="small" fullWidth label="방식"
            value={rpsMode} onChange={(e) => setRpsMode(e.target.value)}
            helperText={rpsMode === "tournament"
              ? "참여자를 무작위로 짝지어 1:1로 붙고, 이긴 사람이 다음 라운드로 올라가 마지막 한 명이 챔피언이 됩니다. 비기면 그 대진만 다시 냅니다."
              : "참여자가 몰래 가위, 바위, 보 중 하나를 냅니다. 방장이 공개하면 서버가 판정해요 (두 종류만 나오면 이기는 쪽 승리, 아니면 무승부)."}
          >
            <MenuItem value="single">한 판 (다 같이 한 번에)</MenuItem>
            <MenuItem value="tournament">토너먼트 (짝지어 이긴 사람이 올라감)</MenuItem>
          </TextField>
        ) : isQuiz ? (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              문제<Box component="span" sx={{ color: "error.main" }}> *</Box>
            </Typography>
            {aiEnabled ? (
              <Paper variant="outlined" sx={{ p: 2, mb: 1.5, bgcolor: "action.hover" }}>
                <Stack direction={{ xs: "column", sm: "row" }} gap={1} alignItems={{ sm: "center" }}>
                  <TextField
                    size="small" fullWidth value={aiTopic} placeholder="예: 사내 보안 상식"
                    inputProps={{ maxLength: 200, "aria-label": "퀴즈 주제" }}
                    onChange={(e) => setAiTopic(e.target.value)}
                  />
                  <TextField
                    size="small" type="number" value={aiCount}
                    inputProps={{ min: 1, max: 20, "aria-label": "문항 수" }}
                    onChange={(e) => setAiCount(e.target.value)}
                    sx={{ width: { xs: "100%", sm: "6rem" }, flexShrink: 0 }}
                  />
                  {/* fullWidth 입력 옆의 버튼은 먼저 눌려 글자가 두 줄로 깨진다 — 양보하지 않게 못 박는다. */}
                  <Button size="sm" variant="primary" disabled={genAi.isPending || !aiTopic.trim()}
                    sx={NOSHRINK}
                    onClick={() => aiTopic.trim() && genAi.mutate()}>{genAi.isPending ? "생성 중…" : "AI로 문제 생성"}</Button>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                  주제를 적고 생성하면 아래 문제가 채워집니다. 그대로 쓰거나 수정하세요.
                </Typography>
              </Paper>
            ) : null}
            <QuizEditor questions={quizQs} setQuestions={setQuizQs} />
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              라운드마다 참여자가 몰래 답하고, 방장이 정답을 공개하면 서버가 채점합니다.
            </Typography>
          </Box>
        ) : (
          <TextField
            id="gr-winners" type="number" size="small" fullWidth label="당첨 인원"
            inputProps={{ min: 1, max: 20 }} value={winners} onChange={(e) => setWinners(e.target.value)}
          />
        )}

        {timed ? (
          <TextField
            id="gr-timer" type="number" size="small" fullWidth label="제한 시간 (초)"
            inputProps={{ min: 0, max: 300 }} value={timer} onChange={(e) => setTimer(e.target.value)}
            helperText={`${isQuiz ? "문제마다" : "라운드마다"} 남은 시간이 카운트다운으로 보입니다. 시간이 끝나면 자동으로 다음 단계로 넘어갑니다${isRps ? " (안 낸 사람은 무작위로 처리)" : ""}. 0이면 시간 제한이 없습니다.`}
          />
        ) : null}
        <TextField
          id="gr-max" type="number" size="small" fullWidth label="최대 참여 인원"
          inputProps={{ min: 2, max: 50 }} value={maxPlayers} onChange={(e) => setMaxPlayers(e.target.value)}
        />
        <FormControlLabel
          control={<Checkbox checked={spectators} onChange={(e) => setSpectators(e.target.checked)} />}
          label="관전 허용"
        />
      </Box>
    </Modal>
  );
}

export function Games() {
  const nav = useNavigate();
  const [composing, setComposing] = useState(false);
  const list = useQuery({ queryKey: ["games-rooms"], queryFn: () => api("/api/games/rooms"), refetchInterval: 3000 });

  const createBtn = <Button variant="primary" onClick={() => setComposing(true)}>게임방 추가</Button>;

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="놀이" title="놀이" spot="games" actions={createBtn} />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: PROSE_MAX_WIDTH }}>
        팀원과 함께 실시간으로 즐기는 놀이 공간입니다.
      </Typography>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending ? (
        <Card><Skeleton lines={5} /></Card>
      ) : (list.data.items || []).length === 0 ? (
        <EmptyState
          icon="🎲"
          title="열린 게임방이 없습니다"
          help="위 ‘게임방 추가’로 첫 방을 열어 팀원과 함께 시작해 보세요."
          action={createBtn}
        />
      ) : (
        /* auto-fill 격자 — 방이 몇 개든, 화면이 얼마나 넓든 카드 폭이 일정하게 유지된다.
         * 4K에서는 열 수가 늘어 남는 폭이 그냥 비지 않는다(카드 하나가 1,500px로 늘어나지도 않는다). */
        <Box sx={{
          display: "grid", gap: 2,
          gridTemplateColumns: {
            xs: "repeat(auto-fill, minmax(15rem, 1fr))",
            xxl: "repeat(auto-fill, minmax(17rem, 1fr))",
          },
        }}>
          {list.data.items.map((r) => (
            <Paper
              key={r.id}
              component="button"
              type="button"
              variant="outlined"
              onClick={() => nav("/games/" + r.id)}
              sx={{
                p: 2.5, textAlign: "left", font: "inherit", color: "inherit", cursor: "pointer",
                display: "grid", gap: 1, alignContent: "start", minWidth: 0,
                transition: "border-color .15s, transform .15s",
                "&:hover": { borderColor: "primary.main", transform: "translateY(-2px)" },
              }}
            >
              <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
                <Badge value={STATUS_LABELS[r.status] || r.status} kind={STATUS_KIND[r.status] || "neutral"} />
                <Typography variant="caption" color="text.secondary">{GAME_LABELS[r.game_type] || r.game_type}</Typography>
              </Stack>
              <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: "1rem", overflowWrap: "anywhere" }}>{r.title}</Typography>
              <Typography variant="body2" color="text.secondary">
                참여 {r.player_count}/{r.max_players}{r.allow_spectators ? ", 관전 가능" : ""}
              </Typography>
            </Paper>
          ))}
        </Box>
      )}

      <CreateRoomModal open={composing} onClose={() => setComposing(false)}
        aiEnabled={!!(list.data && list.data.game_ai_enabled)}
        onCreated={(room) => { setComposing(false); nav("/games/" + room.id); }} />
    </div>
  );
}
