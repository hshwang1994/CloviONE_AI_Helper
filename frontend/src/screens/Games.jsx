import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { Badge, Button, EmptyState, ErrorState, Modal, ModalFooter, PageHeader, Skeleton, useToast } from "../ui/kit.jsx";

/* 팀 공간 > 놀이 (§5). 한 페이지에서 모든 게임방을 보고, 여기서 방을 만든다(별도 페이지 분리
 * 안 함). 목록은 3초 폴링으로 새 방을 실시간처럼 보여준다. 첫 게임=랜덤 추첨. */

export const GAME_LABELS = { random_draw: "랜덤 추첨", quick_vote: "빠른 투표", team_split: "랜덤 팀 나누기", number: "숫자 눈치", ladder: "사다리타기", rps: "가위바위보", quiz: "실시간 퀴즈" };
const STATUS_LABELS = { waiting: "대기 중", playing: "진행 중", finished: "결과 확인 중" };
const STATUS_KIND = { waiting: "info", playing: "warn", finished: "ok" };

const MAX_OPTIONS = 8;
const MAX_QUESTIONS = 20;
const EMPTY_Q = { q: "", options: ["", ""], answer: 0 };

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
    const answer = q.answer >= options.length ? options.length - 1 : q.answer;
    patch(i, { ...q, options, answer });
  };
  const setAnswer = (i, oi) => patch(i, { ...questions[i], answer: oi });
  const addQuestion = () => setQuestions((prev) => (prev.length >= MAX_QUESTIONS ? prev : [...prev, { q: "", options: ["", ""], answer: 0 }]));
  const removeQuestion = (i) => setQuestions((prev) => (prev.length <= 1 ? prev : prev.filter((_, x) => x !== i)));

  return (
    <div className="quiz-editor">
      {questions.map((q, i) => (
        <div className="quiz-q" key={i}>
          <div className="quiz-q-head">
            <span className="quiz-q-no">문제 {i + 1}</span>
            {questions.length > 1 ? <Button size="sm" onClick={() => removeQuestion(i)}>문제 삭제</Button> : null}
          </div>
          <input className="k-input" maxLength={200} value={q.q} placeholder="질문을 입력하세요" onChange={(e) => setText(i, e.target.value)} />
          <div className="quiz-opts">
            {q.options.map((o, oi) => (
              <div className="quiz-opt-row" key={oi}>
                <label className="quiz-opt-radio" title="정답으로 지정">
                  <input type="radio" name={"quiz-ans-" + i} checked={q.answer === oi} onChange={() => setAnswer(i, oi)} />
                  <span className="quiz-opt-radio-label">정답</span>
                </label>
                <input className="k-input" maxLength={80} value={o} placeholder={"보기 " + (oi + 1)} onChange={(e) => setOpt(i, oi, e.target.value)} />
                {q.options.length > 2 ? <Button size="sm" onClick={() => removeOpt(i, oi)}>삭제</Button> : null}
              </div>
            ))}
            {q.options.length < 6 ? <Button size="sm" onClick={() => addOpt(i)}>보기 추가</Button> : null}
          </div>
        </div>
      ))}
      {questions.length < MAX_QUESTIONS ? <Button size="sm" onClick={addQuestion}>문제 추가</Button> : null}
    </div>
  );
}

function CreateRoomModal({ open, onClose, onCreated, aiEnabled }) {
  const toast = useToast();
  const [gameType, setGameType] = useState("random_draw");
  const [title, setTitle] = useState("");
  const [maxPlayers, setMaxPlayers] = useState(8);
  const [winners, setWinners] = useState(1);
  const [teams, setTeams] = useState(2);
  const [numMax, setNumMax] = useState(10);
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
      setAiTopic(""); setAiCount(5); setSpectators(true);
    }
  }, [open]);

  // AI 퀴즈 생성: 러너(Claude)가 만든 문제로 quizQs를 채운다. 결과는 아래 QuizEditor에서 검토·수정.
  const genAi = useMutation({
    mutationFn: () => api("/api/games/quiz/generate", { method: "POST", body: { topic: aiTopic.trim(), count: Number(aiCount) || 5 } }),
    onSuccess: (res) => {
      const qs = (res.questions || []).map((q) => ({ q: q.q, options: q.options, answer: q.answer }));
      if (qs.length) { setQuizQs(qs); toast(`문제 ${qs.length}개를 만들었어요. 검토하고 수정한 뒤 방을 만드세요.`, "success"); }
      else toast("생성된 문제가 없습니다. 주제를 더 구체적으로 적어 보세요.", "error");
    },
    onError: (e) => toast((e && e.message) || "AI 생성에 실패했습니다.", "error"),
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
  const config = isVote
    ? { question: question.trim(), options: cleanOptions }
    : isLadder
      ? { options: cleanOptions }
      : isTeam
        ? { teams: Number(teams) || 2 }
        : isNumber
          ? { min: 1, max: Number(numMax) || 10 }
          : isRps
            ? {}
            : isQuiz
              ? { questions: cleanQuiz }
              : { winners: Number(winners) || 1 };

  const create = useMutation({
    mutationFn: () => api("/api/games/rooms", {
      method: "POST",
      body: { title, game_type: gameType, max_players: Number(maxPlayers) || 8, allow_spectators: spectators, config },
    }),
    onSuccess: (res) => { toast("게임방을 만들었습니다.", "success"); onCreated && onCreated(res.room); },
    onError: (e) => toast((e && e.message) || "게임방을 만들지 못했습니다.", "error"),
  });
  const canSave = title.trim().length > 0 && optionsReady && questionReady && quizReady && !create.isPending;

  return (
    <Modal open={open} onClose={onClose} title="게임방 만들기" size="md"
      footer={<ModalFooter onCancel={onClose} onSubmit={() => canSave && create.mutate()} submitLabel="만들기" busy={create.isPending} />}>
      <div className="k-field">
        <label className="k-field-label" htmlFor="gr-game">게임</label>
        <select id="gr-game" className="k-input" value={gameType} onChange={(e) => setGameType(e.target.value)}>
          <option value="random_draw">랜덤 추첨</option>
          <option value="quick_vote">빠른 투표</option>
          <option value="team_split">랜덤 팀 나누기</option>
          <option value="number">숫자 눈치</option>
          <option value="ladder">사다리타기</option>
          <option value="rps">가위바위보</option>
          <option value="quiz">실시간 퀴즈</option>
        </select>
      </div>
      <div className="k-field">
        <label className="k-field-label" htmlFor="gr-title">방 제목<span className="k-req"> *</span></label>
        <input id="gr-title" className="k-input" maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder={isVote ? "예: 오늘 점심 정하기" : isTeam ? "예: 축구 팀 나누기" : isLadder ? "예: 청소 당번 사다리" : isQuiz ? "예: 사내 상식 퀴즈" : "예: 점심 커피 추첨"} />
      </div>

      {needsOptions ? (
        <>
          {isVote ? (
            <div className="k-field">
              <label className="k-field-label" htmlFor="gr-q">질문<span className="k-req"> *</span></label>
              <input id="gr-q" className="k-input" maxLength={120} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="예: 점심 뭐 먹을까요?" />
            </div>
          ) : null}
          <div className="k-field">
            <label className="k-field-label">{isLadder ? "결과 (사다리 도착지)" : "선택지"}<span className="k-req"> *</span></label>
            <div className="games-options">
              {options.map((o, i) => (
                <div className="games-option-row" key={i}>
                  <input className="k-input" maxLength={40} value={o} onChange={(e) => setOption(i, e.target.value)}
                    placeholder={(isLadder ? "결과 " : "선택지 ") + (i + 1)} />
                  {options.length > 2 ? <Button size="sm" onClick={() => removeOption(i)}>삭제</Button> : null}
                </div>
              ))}
              {options.length < MAX_OPTIONS ? <Button size="sm" onClick={addOption}>{isLadder ? "결과 추가" : "선택지 추가"}</Button> : null}
            </div>
            {isLadder ? <p className="k-field-help">참여자보다 결과가 적으면 나머지는 ‘꽝’으로 채워집니다.</p> : null}
          </div>
        </>
      ) : isTeam ? (
        <div className="k-field">
          <label className="k-field-label" htmlFor="gr-teams">팀 수</label>
          <input id="gr-teams" className="k-input" type="number" min={2} max={8} value={teams} onChange={(e) => setTeams(e.target.value)} />
        </div>
      ) : isNumber ? (
        <div className="k-field">
          <label className="k-field-label" htmlFor="gr-nummax">숫자 범위 (1 ~ ?)</label>
          <input id="gr-nummax" className="k-input" type="number" min={2} max={100} value={numMax} onChange={(e) => setNumMax(e.target.value)} />
          <p className="k-field-help">참여자가 1~{Number(numMax) || 10} 중 하나를 몰래 냅니다. 가장 낮은 ‘유일한’ 숫자를 낸 사람이 승리해요.</p>
        </div>
      ) : isRps ? (
        <div className="k-field">
          <p className="k-field-help">참여자가 몰래 가위, 바위, 보 중 하나를 냅니다. 방장이 공개하면 서버가 판정해요. (두 종류만 나오면 이기는 쪽 승리, 아니면 무승부)</p>
        </div>
      ) : isQuiz ? (
        <div className="k-field">
          <label className="k-field-label">문제<span className="k-req"> *</span></label>
          {aiEnabled ? (
            <div className="quiz-ai">
              <div className="quiz-ai-row">
                <input className="k-input" maxLength={200} value={aiTopic} placeholder="예: 사내 보안 상식"
                  onChange={(e) => setAiTopic(e.target.value)} />
                <input className="k-input quiz-ai-count" type="number" min={1} max={20} value={aiCount}
                  aria-label="문항 수" onChange={(e) => setAiCount(e.target.value)} />
                <Button size="sm" variant="primary" disabled={genAi.isPending || !aiTopic.trim()}
                  onClick={() => aiTopic.trim() && genAi.mutate()}>{genAi.isPending ? "생성 중…" : "AI로 문제 생성"}</Button>
              </div>
              <p className="k-field-help">주제를 적고 생성하면 아래 문제가 채워집니다. 그대로 쓰거나 수정하세요.</p>
            </div>
          ) : null}
          <QuizEditor questions={quizQs} setQuestions={setQuizQs} />
          <p className="k-field-help">라운드마다 참여자가 몰래 답하고, 방장이 정답을 공개하면 서버가 채점합니다.</p>
        </div>
      ) : (
        <div className="k-field">
          <label className="k-field-label" htmlFor="gr-winners">당첨 인원</label>
          <input id="gr-winners" className="k-input" type="number" min={1} max={20} value={winners} onChange={(e) => setWinners(e.target.value)} />
        </div>
      )}

      <div className="k-field">
        <label className="k-field-label" htmlFor="gr-max">최대 참여 인원</label>
        <input id="gr-max" className="k-input" type="number" min={2} max={50} value={maxPlayers} onChange={(e) => setMaxPlayers(e.target.value)} />
      </div>
      <div className="k-field">
        <label className="k-check">
          <input type="checkbox" checked={spectators} onChange={(e) => setSpectators(e.target.checked)} /> 관전 허용
        </label>
      </div>
    </Modal>
  );
}

export function Games() {
  const nav = useNavigate();
  const [composing, setComposing] = useState(false);
  const list = useQuery({ queryKey: ["games-rooms"], queryFn: () => api("/api/games/rooms"), refetchInterval: 3000 });

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="놀이" title="놀이"
        actions={<Button variant="primary" onClick={() => setComposing(true)}>게임방 만들기</Button>} />
      <p className="k-page-help">팀원과 함께 실시간으로 즐기는 놀이 공간입니다.</p>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending ? (
        <Skeleton lines={5} />
      ) : (list.data.items || []).length === 0 ? (
        <EmptyState title="열린 게임방이 없습니다" help="위 ‘게임방 만들기’로 첫 방을 열어 팀원과 함께 시작해 보세요." />
      ) : (
        <div className="games-grid">
          {list.data.items.map((r) => (
            <button type="button" key={r.id} className="game-card" onClick={() => nav("/games/" + r.id)}>
              <div className="game-card-top">
                <Badge value={STATUS_LABELS[r.status] || r.status} kind={STATUS_KIND[r.status] || "neutral"} />
                <span className="game-card-type">{GAME_LABELS[r.game_type] || r.game_type}</span>
              </div>
              <div className="game-card-title">{r.title}</div>
              <div className="game-card-meta">참여 {r.player_count}/{r.max_players}{r.allow_spectators ? ", 관전 가능" : ""}</div>
            </button>
          ))}
        </div>
      )}

      <CreateRoomModal open={composing} onClose={() => setComposing(false)}
        aiEnabled={!!(list.data && list.data.game_ai_enabled)}
        onCreated={(room) => { setComposing(false); nav("/games/" + room.id); }} />
    </div>
  );
}
