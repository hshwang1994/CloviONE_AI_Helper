import React from "react";
import Box from "@mui/material/Box";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useWorkspaceFill } from "../../ui/Workspace.jsx";
import { GAME_RAIL_BUDGET, GAME_ROOM_CONTAINER, GAME_ROOM_TRACK_MIN_REM, gameRoomColumns } from "../../ui/density.js";

/* 놀이방 껍데기 하나 — 여덟 게임이 같은 틀에 선다 (게임 공통 G1 · D-575).
 *
 * 슬롯은 다섯이다: 머리(경로 · 제목) → 툴바(상태 · 동작) → 판 | 레일(참여자 · 채팅) → 겹침(전체 화면의 축포 캔버스). 판과 레일은
 * 같은 격자의 한 줄이라 **레일 바닥이 판 바닥**이다 — 예전에는 레일이 `calc(100vh - 14rem)` 계산값으로 서고 판은 자기 비율로 서서,
 * 채팅 입력창이 판 아래로 내려가 페이지가 굴러갔다.
 *
 * 세 모드(`data-game-room-layout`):
 *   fill    창이 폭 1200 · 높이 600 이상이고 앱 틀에 채움을 등록했다(`useWorkspaceFill`, D-531). 앱 틀의 main 이 창 높이에 서고
 *           이 루트가 남은 높이를 받는다 — 판 · 레일이 뷰포트 아래 여백까지 정확히 서고 페이지는 굴러가지 않는다. 두 열은 뷰포트가
 *           아니라 **껍데기가 받은 폭**이 정한다(컨테이너 질의 56rem · 80rem · 120rem, `density.js::GAME_ROOM_TRACKS`).
 *   flow    md 이상인데 채움이 아니다(1024 · 낮은 창 · 높은 확대). 판이 전폭 16:9 로 서고(바닥 22rem · 천장 60vh), 아래에
 *           참가자 | 채팅 두 열이 각각 22rem 안에서 굴러간다. 문서가 굴러가는 것이 이 모드의 설계다.
 *   mobile  md 미만. 판은 4:3, 레일은 「참가자 | 채팅」 세그먼티드 — 모두 마운트를 유지하고 고르지 않은 쪽만 숨긴다.
 *
 * 전체 화면(`data-fullscreen="on"` · `:fullscreen`)은 루트가 창 전체다 — 머리를 숨기고, 창이 넓으면(두 열이 들어가면) 채움 기하,
 * 좁으면(전화) 모바일 기하다. 채팅은 그대로다. 겹침 슬롯에 축포 캔버스가 선다(전체 화면인 요소는 그 밖의 포털 · 캔버스를 가린다).
 * iPhone 처럼 API 가 없는 곳은 `position: fixed` 로 같은 모양을 흉내 낸다(`useFullscreen`). */

export const GAME_ROOM_MODES = ["fill", "flow", "mobile"];

const LayoutCtx = React.createContext({ mode: "flow", fullscreen: false });

/** 껍데기 안의 부품(레일 · 판 · 툴바)이 지금 모드와 전체 화면 여부를 읽는다. */
export function useGameRoomLayout() {
  return React.useContext(LayoutCtx);
}

/** 모드 판정 — 채움 등록은 이 훅이 한다(첫 그림 전에 앱 틀이 알아야 깜빡임이 없다). */
export function useGameRoomMode() {
  const theme = useTheme();
  const fill = useWorkspaceFill();
  const mobile = useMediaQuery(theme.breakpoints.down("md"), { noSsr: true });
  if (fill) return "fill";
  return mobile ? "mobile" : "flow";
}

/* 전체 화면에서 두 열이 들어가는 창 — 컨테이너 문턱(56rem)에 전체 화면의 안쪽 여백(좌우 16px)을 더한 폭. */
const FULLSCREEN_TWO_COLUMNS = `(min-width:${GAME_ROOM_TRACK_MIN_REM.two + 2}rem)`;

export const GameRoomLayout = React.forwardRef(function GameRoomLayout(
  { mode, fullscreen = false, pseudoFullscreen = false, header, toolbar, notice, board, rail, overlay, children },
  ref,
) {
  const wide = useMediaQuery(FULLSCREEN_TWO_COLUMNS, { noSsr: true });
  /* 전체 화면이면 창 전체가 이 루트다 — 넓으면 채움 기하, 좁으면 모바일 기하. */
  const effective = fullscreen ? (wide ? "fill" : "mobile") : mode;
  const ctx = React.useMemo(() => ({ mode: effective, fullscreen, baseMode: mode }), [effective, fullscreen, mode]);
  const stretch = effective === "fill";
  return (
    <LayoutCtx.Provider value={ctx}>
      <Box
        ref={ref}
        className="c-screen"
        data-game-room-layout={effective}
        data-fullscreen={fullscreen ? "on" : "off"}
        data-fullscreen-mode={fullscreen ? (pseudoFullscreen ? "pseudo" : "native") : undefined}
        sx={(t) => ({
          ...GAME_ROOM_CONTAINER,
          ...(stretch && !fullscreen ? { flex: "1 1 auto", minHeight: 0 } : null),
          /* 전체 화면 — 루트가 창 전체다. 앱 틀의 바탕색을 그대로 깔아 캔버스 밖이 검게 비치지 않는다. */
          "&:fullscreen, &[data-fullscreen='on']": {
            p: 2, width: "100%", height: "100%", boxSizing: "border-box", display: "flex", flexDirection: "column",
            bgcolor: t.palette.background.default, overflowX: "hidden", overflowY: stretch ? "hidden" : "auto",
            "& [data-game-room-header]": { display: "none" },
          },
          "&::backdrop": { backgroundColor: t.palette.background.default },
          ...(pseudoFullscreen ? { position: "fixed", inset: 0, zIndex: 1250 } : null),
        })}
      >
        {header ? <Box data-game-room-header="" sx={{ minWidth: 0 }}>{header}</Box> : null}
        {toolbar}
        {notice}
        <Box
          data-game-room-grid=""
          sx={{
            display: "grid",
            gap: 2,
            minWidth: 0,
            alignItems: "stretch",
            ...(stretch
              ? { flex: "1 1 auto", minHeight: 0, gridTemplateRows: "minmax(0, 1fr)", gridAutoRows: "minmax(0, 1fr)", ...gameRoomColumns() }
              : { gridTemplateColumns: "minmax(0, 1fr)" }),
          }}
        >
          <Box
            data-game-room-board=""
            sx={{
              minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column",
              /* 흐름 · 모바일 — 폭이 정본이고 높이는 비율에서 나온다. 🔴 비율이 있는 격자 항목은 `justify-self` 기본값이 start 라
                 최소 높이에서 폭을 끌어내 칸을 넘친다(390 에서 판이 26px 넘쳤다) — 폭을 칸에 못박는다. */
              ...(stretch ? null : {
                width: "100%", justifySelf: "stretch",
                aspectRatio: effective === "mobile" ? "4 / 3" : "16 / 9",
                minHeight: effective === "mobile" ? "16rem" : GAME_RAIL_BUDGET.flowBoardMin,
                maxHeight: effective === "mobile" ? "none" : GAME_RAIL_BUDGET.flowBoardMax,
              }),
            }}
          >
            {board}
          </Box>
          <Box data-game-room-rail="" sx={{ minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column" }}>
            {rail}
          </Box>
        </Box>
        {overlay}
        {children}
      </Box>
    </LayoutCtx.Provider>
  );
});
