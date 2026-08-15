import { useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Badge, Button, Card, ErrorState, PageHeader, Skeleton } from "../ui/kit.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";
import { prefersReducedMotion } from "../ui/motion.js";
import { GAME_LABELS } from "./Games.jsx";
import { STATUS_LABELS, STATUS_KIND } from "./game-room/constants.js";
import { useGameRoomController } from "./game-room/useGameRoomController.js";
import { Countdown } from "./game-room/StageShared.jsx";
import { GameStage } from "./game-room/GameStage.jsx";
import { RoomSidebar } from "./game-room/RoomSidebar.jsx";

/* 게임방(§5·§6·§13·§16.2). 폴링(1.2초)으로 방 상태·참여자·이벤트를 실시간처럼 흐르게 한다.
 * 결과(당첨자)는 서버가 확정해 내려준다(§13.1) — 클라이언트는 표현만 한다. 게임방 채팅은
 * 순수 내부 DB(n8n 안 거침, §13.2). 방에 들어오면 한 번 자동 입장(가득/진행 중이면 서버가 관전).
 *
 * 2026-08 구조 분리: 원래 1,132줄이던 이 화면을 game-room/ 아래 여러 작은 파일로 나눴다
 * (게임 진행 상태 관리 훅 · 무대 렌더링 · 참여자/채팅 레일 · 게임 종류별 소품 컴포넌트).
 * 로직·마크업은 옮기기만 했고 바꾸지 않았다 — 이 파일은 그 조각들을 조립하는 얇은 껍데기다.
 *
 * 2026-08 MUI 재설계: screens.css의 .game-* 규칙 169줄을 화면 안 sx로 옮겼다. 이 화면은 업무
 * 위험이 가장 낮은 화면이라 연출을 조금 더 얹는다 — 승자 확정 순간에 축포 + 축하 일러스트 +
 * 마스코트(love/success)를 함께 띄운다. 다만 **동작 최소화(prefers-reduced-motion)** 를 켠
 * 사용자에게는 JS로 쏘는 축포를 아예 발사하지 않는다(CSS 애니메이션은 theme.js의 전역 규칙이 끈다). */

/* 사용자가 OS에서 '동작 최소화'를 켰는지. matchMedia가 없는 환경(jsdom 등)에서는 false로 본다 —
 * 없다고 예외를 던지면 결과 화면 전체가 렌더되지 않는다.
 *
 * 구현은 ui/motion.js 로 옮겼다. 로그인 인계 연출(app/LoginHandoff.jsx)이 같은 판정을 쓰는데
 * 그 코드는 초기 로드에 들어간다 — 여기서 가져가면 게임방 화면 전체가 지연 청크에서 초기
 * 번들로 끌려 들어온다. 이 화면과 테스트의 호출부는 그대로 두려고 재수출한다. */
export { prefersReducedMotion };

export function GameRoom() {
  const { id } = useParams();
  const c = useGameRoomController(id);

  if (c.phase === "error") return <div className="c-screen"><ErrorState error={c.error} onRetry={c.refetch} /></div>;
  if (c.phase === "pending") return <div className="c-screen"><Card><Skeleton lines={6} /></Card></div>;

  const {
    room, you, submissionActive, remaining, activePlayers, submittedCount, waitingNames,
    canReady, isHost, isVote, isTeam, isNumber, isLadder, isRps, isQuiz, isTournament,
    quizPlaying, mutations,
  } = c;
  const { ready, start, finish, reveal, nextQ, reset, disband, leave } = mutations;

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="놀이" title={room.title}
        actions={<Button onClick={() => leave.mutate()} disabled={leave.isPending}>나가기</Button>} />

      {/* 무대(왼쪽) + 참여자·채팅 레일(오른쪽). 좁은 화면에서는 한 열로 흐른다. */}
      <Box sx={{
        display: "grid", gap: 2, alignItems: "start",
        gridTemplateColumns: { xs: "1fr", md: "minmax(0,1fr) 22rem", xxl: "minmax(0,1fr) 26rem" },
      }}>
        <Box component="section" sx={{ display: "grid", gap: 2, minWidth: 0 }}>
          <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
            <Badge value={GAME_LABELS[room.game_type] || room.game_type} kind="neutral" />
            <Badge value={STATUS_LABELS[room.status] || room.status} kind={STATUS_KIND[room.status] || "neutral"} />
            <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
              참여 {room.player_count}/{room.max_players}
            </Typography>
            {you.role === "spectator" ? <Typography variant="body2" color="text.secondary">관전 중</Typography> : null}
          </Stack>

          {/* 진행 현황: 카운트다운 + 제출/대기(모든 제출형 게임 공통) */}
          {submissionActive || remaining != null ? (
            <Paper variant="outlined" sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", px: 1.5, py: 1.25 }}>
              <Countdown remaining={remaining} />
              {submissionActive ? (
                <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
                  <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, fontVariantNumeric: "tabular-nums" }}>
                    제출 {submittedCount}/{activePlayers.length}
                  </Typography>
                  {waitingNames.length > 0
                    ? <Typography variant="body2" color="text.secondary">대기 {waitingNames.join(", ")}</Typography>
                    : <Typography variant="body2" color="success.main" sx={{ fontWeight: FONT_WEIGHT.semibold }}>모두 제출했습니다</Typography>}
                </Stack>
              ) : null}
            </Paper>
          ) : null}

          <GameStage c={c} />

          <Stack direction="row" gap={1} flexWrap="wrap">
            {canReady ? (
              <Button variant={you.ready ? "default" : "primary"} onClick={() => ready.mutate(!you.ready)} disabled={ready.isPending}>
                {you.ready ? "준비 해제" : "준비"}
              </Button>
            ) : null}
            {isHost && room.status === "waiting" ? (
              <Button variant="primary" onClick={() => start.mutate()} disabled={start.isPending}>{isVote ? "투표 시작" : isTeam ? "팀 나누기" : isNumber ? "숫자 눈치 시작" : isLadder ? "사다리 타기" : isRps ? "가위바위보 시작" : isQuiz ? "퀴즈 시작" : "추첨 시작"}</Button>
            ) : null}
            {isHost && (isVote || isNumber || isRps) && room.status === "playing" ? (
              <Button variant="primary" onClick={() => finish.mutate()} disabled={finish.isPending}>{isVote ? "투표 종료" : isTournament ? "이 라운드 마감" : "결과 공개"}</Button>
            ) : null}
            {isHost && isQuiz && room.status === "playing" && quizPlaying?.phase === "answering" ? (
              <Button variant="primary" onClick={() => reveal.mutate()} disabled={reveal.isPending}>정답 공개</Button>
            ) : null}
            {isHost && isQuiz && room.status === "playing" && quizPlaying?.phase === "revealed" ? (
              <Button variant="primary" onClick={() => nextQ.mutate()} disabled={nextQ.isPending}>
                {(quizPlaying.round || 0) + 1 >= quizPlaying.total ? "결과 보기" : "다음 문제"}
              </Button>
            ) : null}
            {isHost && room.status === "finished" ? (
              <Button variant="primary" onClick={() => reset.mutate()} disabled={reset.isPending}>다시 하기</Button>
            ) : null}
            {isHost ? (
              <Button variant="danger" disabled={disband.isPending} onClick={c.disbandWithConfirm}>방 파하기</Button>
            ) : null}
          </Stack>
        </Box>

        <RoomSidebar c={c} />
      </Box>
    </div>
  );
}
