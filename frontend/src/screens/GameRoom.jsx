import React from "react";
import { useParams } from "react-router-dom";
import { useTheme } from "@mui/material/styles";
import { Callout, Card, ErrorState, PageHeader, Skeleton } from "../ui/kit.jsx";
import { GAME_LABELS } from "./Games.jsx";
import { useGameRoomController } from "./game-room/useGameRoomController.js";
import { GameStage } from "./game-room/GameStage.jsx";
import { GameRoomLayout, useGameRoomMode } from "./game-room/GameRoomLayout.jsx";
import { BoardFrame } from "./game-room/BoardFrame.jsx";
import { RoomRail } from "./game-room/RoomRail.jsx";
import { RoomToolbar } from "./game-room/RoomToolbar.jsx";
import { ResultDialog } from "./game-room/ResultDialog.jsx";
import { buildResultModel } from "./game-room/resultModel.jsx";
import { useFullscreen } from "./game-room/useFullscreen.js";
import { RankRail } from "./game-room/marble/RankRail.jsx";
import { MarbleSettingsModal } from "./game-room/marble/MarbleSettingsModal.jsx";
import { boardPalette } from "./game-room/marble/render/theme.js";

/* 게임방(§5·§6·§13·§16.2) — 여덟 게임이 같은 껍데기 하나에 선다 (D-575).
 *
 * 폴링(1.2초)으로 방 상태·참여자·이벤트를 실시간처럼 흐르게 하고, 결과(당첨자)는 서버가 확정해 내려준다(§13.1) — 클라이언트는
 * 표현만 한다. 게임방 채팅은 순수 내부 DB(외부로 안 나감, §13.2). 방에 들어오면 한 번 자동 입장(가득/진행 중이면 서버가 관전).
 *
 * 조립: 머리(경로 · 제목) → 툴바(상태 정본 · 동작 한 줄, `RoomToolbar`) → 판(`BoardFrame` 안의 게임별 판) | 레일(참여자 · 채팅) →
 * 결과 대화 상자(`ResultDialog`, D-576). 판은 대기 · 진행 · 종료 어느 상태에서도 같은 자리 같은 크기이고, 결과를 닫아도 마지막
 * 장면으로 남는다. 전체 화면은 방 루트(`useFullscreen`)다 — 대화 상자와 축포 캔버스가 그 루트 안에 선다(전체 화면인 요소는 그 밖을
 * 가린다). 축포는 OS·브라우저 설정과 무관하게 언제나 터진다(제품 결정 — `ui/motion.js` 머리말). */

export function GameRoom() {
  const { id } = useParams();
  const c = useGameRoomController(id);
  const rootRef = React.useRef(null);
  const fs = useFullscreen(rootRef, { resetKey: id });
  const mode = useGameRoomMode();
  const theme = useTheme();
  const palette = React.useMemo(() => boardPalette(theme), [theme]);
  const [settingsOpen, setSettingsOpen] = React.useState(false);

  if (c.phase === "error") return <div className="c-screen"><ErrorState error={c.error} onRetry={c.refetch} /></div>;
  if (c.phase === "pending") return <div className="c-screen"><Card><Skeleton lines={6} /></Card></div>;

  const { room, isMarble, marble, actionFailure, mutations, reveal, isHost } = c;
  const model = buildResultModel(c, palette);
  const game = GAME_LABELS[room.game_type] || room.game_type;
  /* 전체 화면(표준 API)이면 대화 상자를 방 루트 안에 그린다 — 문서의 포털은 전체 화면에 가려진다. 흉내 모드(iPhone)는 문서 위에
     서므로 기본 포털(1300)이 루트(1250) 위에 그대로 뜬다. */
  const dialogContainer = fs.active && !fs.pseudo ? rootRef.current : undefined;
  /* 레일이 모드에 맞춰 목록을 판에 채울지(`fill`) 정한다 — 순위도 참여자와 같은 천장 · 같은 굴림이다(D-594). */
  const panes = isMarble
    ? [{ key: "members", label: "참여자" }, { key: "rank", label: "순위", render: ({ fill }) => <RankRail c={c} fill={fill} /> }]
    : null;

  return (
    <GameRoomLayout
      ref={rootRef}
      mode={mode}
      fullscreen={fs.active}
      pseudoFullscreen={fs.pseudo}
      header={<PageHeader crumbRoot="팀 공간" area="놀이" title={room.title} />}
      toolbar={<RoomToolbar c={c} fs={fs} onOpenSettings={() => setSettingsOpen(true)} />}
      notice={actionFailure ? <Callout tone="danger" compact>{actionFailure}</Callout> : null}
      board={(
        <BoardFrame label={`${game} 판`}>
          <GameStage c={c} />
        </BoardFrame>
      )}
      rail={<RoomRail c={c} panes={panes} defaultPane={isMarble && !marble.waiting ? "rank" : "members"} />}
      overlay={fs.active ? (
        /* 축포 캔버스 — 전체 화면 동안만 루트 안에 선다(`celebrate({ canvas })`). 화면을 덮되 누르는 것은 통과시킨다. */
        <canvas
          ref={c.celebrateCanvasRef}
          data-celebrate-canvas=""
          aria-hidden="true"
          style={{ position: "fixed", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 1320 }}
        />
      ) : null}
    >
      {model ? (
        <ResultDialog
          model={model} reveal={reveal} isHost={isHost}
          onReplay={() => mutations.reset.mutate()} replayPending={mutations.reset.isPending}
          container={dialogContainer} fullscreen={fs.active}
        />
      ) : null}
      {isMarble && isHost && !fs.active ? (
        <MarbleSettingsModal
          open={settingsOpen && marble.waiting} onClose={() => setSettingsOpen(false)}
          config={marble.config} members={c.members} mutations={mutations}
        />
      ) : null}
    </GameRoomLayout>
  );
}
