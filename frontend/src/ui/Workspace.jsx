import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { StateRegion, Surface } from "./kit.jsx";
import { HeadRow } from "./layout.jsx";
import { ScrollRootContext } from "./scrollRoot.js";
import { WorkspaceModeContext } from "./workspaceMode.js";
import { WORKSPACE_TRACKS } from "./density.js";
import { BREAKPOINTS, SCROLL_BOX_STICKY_TOP } from "./theme.js";

/* 관리 작업 공간 — 「채움 모드」 (F5 · D-531).
 *
 * 앱 틀은 창 하나가 굴러간다(`AppShell` 의 main 은 흐름이다). 그래서 조직 관리처럼 왼쪽 트리와 오른쪽 목록을 함께 쓰는 화면은
 * 구성원 수만큼 페이지가 길어졌고, 트리 판만 `position: sticky` + 계산값 높이로 붙어 있었다. 화면 높이 판은 `PAGE_FILL_HEIGHT`
 * (`calc(100vh - 12rem)`) 계산값뿐이라 배너 · 범위 줄이 서면 판이 넘쳤다.
 *
 * 채움 모드는 **고른 화면에서**, 창이 폭 1200 이상 **이고** 높이 600 이상일 때만 켜진다(`WORKSPACE_FILL_QUERY`). 그때 앱 틀의 main 이
 * 창 높이에 서고(`100dvh`, 넘침 숨김) 본문 상자(`.c-content`)가 남은 높이를 받는 세로 묶음이 된다 — 배너 · 범위 줄은 높이를 먹는
 * 형제라 작업 공간은 남은 높이를 정확히 받는다(계산값 없음). 판마다 머리 · 도구 줄 · 발은 고정이고 몸만 굴러간다. 두 판의 굴림은
 * 서로 독립이다(`overscroll-behavior: contain` — 한 판 끝에서 휠을 더 굴려도 다른 판 · 문서가 움직이지 않는다). 그보다 작은 창은
 * 흐름 모드다 — 한 열, 문서가 굴러가고, 고른 판의 몸만 높이 상한이 있는 스크롤 상자다.
 *
 *   useWorkspaceShellState()   앱 틀이 쓴다 — 채움을 원하는 화면이 하나라도 있고 창이 기준을 넘는가
 *   useWorkspaceFill()         화면이 쓴다 — 앱 틀에 「채움을 원한다」를 등록하고(첫 그림 전에, 깜빡임 없이) 지금 채움인가를 돌려준다
 *   <Workspace>                페이지 머리 → 간격 16 → 판 격자(남은 높이 · 간격 24)
 *   <WorkspacePane>            판 하나 — head · toolbar(고정) · 몸(굴러간다) · foot(고정)
 *   <PaneHead> · <PaneToolbar> 판 머리 줄과 도구 줄의 모양 */

export const WORKSPACE_FILL_QUERY = `(min-width:${BREAKPOINTS.lg}px) and (min-height:600px)`;

/** 앱 틀이 깔아 두는 등록 창구(`{ register() → 해제 함수 }`). 없으면(시험 · 단독 임베드) 채움은 늘 꺼져 있다. */
export const WorkspaceShellContext = React.createContext(null);
/* 지금 판 격자가 채움인가는 `workspaceMode.js` 의 문맥이 든다 — 판이 몸을 스크롤 상자로 만들지 정하고, 표(`DataTable fill`)가
   채움일 때만 직접 굴린다. */

/** 앱 틀의 상태 — 채움을 원하는 화면 수와 창의 기준. `fill` 이 참이면 main · 본문 상자가 창 높이 묶음이 된다. */
export function useWorkspaceShellState() {
  const [count, setCount] = React.useState(0);
  const api = React.useMemo(() => ({
    register() {
      setCount((n) => n + 1);
      return () => setCount((n) => Math.max(0, n - 1));
    },
  }), []);
  const media = useMediaQuery(WORKSPACE_FILL_QUERY, { noSsr: true });
  return { api, fill: count > 0 && media };
}

/** 화면이 채움을 원한다고 앱 틀에 알린다. `useLayoutEffect` 라 첫 그림 전에 앱 틀이 다시 그려진다(문서가 한 번 길어졌다가
 * 줄어드는 깜빡임이 없다). 화면을 떠나면 등록이 풀려 앱 틀이 원래 흐름으로 돌아간다. */
export function useWorkspaceFill() {
  const shell = React.useContext(WorkspaceShellContext);
  const media = useMediaQuery(WORKSPACE_FILL_QUERY, { noSsr: true });
  React.useLayoutEffect(() => (shell ? shell.register() : undefined), [shell]);
  return !!shell && media;
}

/* 판 사이 간격 24, 머리와 격자 사이 16(페이지 흐름 간격 — `.c-screen` 의 row-gap). */
const PANE_GAP = 3;

export function Workspace({ header, tracks = "tree", children, sx }) {
  const fill = useWorkspaceFill();
  const track = WORKSPACE_TRACKS[tracks] || WORKSPACE_TRACKS.tree;
  return (
    <Box
      className="c-screen"
      data-workspace={fill ? "fill" : "flow"}
      sx={{ ...(fill ? { flex: "1 1 auto", minHeight: 0 } : null), ...sx }}
    >
      {header}
      <Box
        data-workspace-grid=""
        sx={{
          display: "grid",
          gap: PANE_GAP,
          minWidth: 0,
          gridTemplateColumns: fill ? { lg: track.lg, xl: track.xl } : "minmax(0, 1fr)",
          ...(fill ? { flex: "1 1 auto", minHeight: 0, gridTemplateRows: "minmax(0, 1fr)" } : null),
        }}
      >
        <WorkspaceModeContext.Provider value={fill}>{children}</WorkspaceModeContext.Provider>
      </Box>
    </Box>
  );
}

/**
 * 판 하나.
 *   label        판의 접근 이름(`section` 의 aria-label)
 *   head         머리(고정, 아래 선) — 보통 `PaneHead`
 *   toolbar      도구 줄(고정) — 검색 · 필터 · 토글
 *   foot         발(고정, 위 선)
 *   body         "scroll"(몸이 굴러간다, 기본) · "table"(몸 안의 `DataTable fill` 이 직접 굴린다)
 *   bodyLabel    몸의 접근 이름 — 몸이 키보드로 굴러가는 영역이라 이름이 있어야 한다
 *   flowMaxHeight  흐름 모드에서 몸의 높이 상한(트리처럼 길어지는 판) — 그 높이 안에서 굴러간다
 * 나머지 속성(`data-*` 등)은 판 뿌리에 붙는다.
 */
export function WorkspacePane({ label, head, toolbar, foot, children, body = "scroll", bodyLabel, flowMaxHeight, sx, ...rest }) {
  const fill = React.useContext(WorkspaceModeContext);
  const scrolls = fill ? body === "scroll" : !!flowMaxHeight;
  const bodySx = fill
    ? (body === "table"
      ? { flex: "1 1 auto", minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }
      : { flex: "1 1 auto", minHeight: 0 })
    : (flowMaxHeight ? { maxHeight: flowMaxHeight } : null);
  return (
    <Surface
      tone="plate"
      component="section"
      aria-label={label}
      data-workspace-pane=""
      {...rest}
      sx={{
        p: 0, minWidth: 0, display: "flex", flexDirection: "column",
        /* 채움이면 판이 자기 모서리로 안을 자른다(굴러가는 몸이 둥근 모서리 밖으로 비치지 않게). 흐름이면 자르지 않는다 — 판이
           `overflow: hidden` 이면 안의 고정 열 이름(sticky)이 판에 붙박인다(`kit.jsx::ListCard` 머리말). */
        overflow: fill ? "hidden" : "visible",
        ...(fill ? { minHeight: 0 } : null),
        ...sx,
      }}
    >
      {head ? (
        <Box data-pane-head="" sx={{ flexShrink: 0, pt: 2, pb: 1.5, px: 2.5, borderBottom: 1, borderColor: "divider" }}>{head}</Box>
      ) : null}
      {toolbar ? (
        <Box data-pane-toolbar="" sx={{ flexShrink: 0, py: 1.5, px: 2.5 }}>{toolbar}</Box>
      ) : null}
      <Box
        data-pane-body={body}
        /* 굴러가는 몸은 키보드로 굴릴 수 있다 — 초점을 받고 이름이 있는 영역이다. */
        tabIndex={scrolls ? 0 : undefined}
        role={scrolls ? "region" : undefined}
        aria-label={scrolls ? (bodyLabel || label) : undefined}
        sx={{
          minWidth: 0,
          ...bodySx,
          ...(scrolls ? {
            overflow: "auto",
            scrollbarGutter: "stable",
            overscrollBehavior: "contain",
            /* 이 상자가 스크롤 창이라고 안쪽에 알린다 — 안의 고정 열 이름이 상단바 높이(52)를 피하지 않고 상자 위에 붙는다. */
            ...SCROLL_BOX_STICKY_TOP,
            "&:focus-visible": (t) => ({ outline: `2px solid var(--clovir-focus-ring, ${t.palette.focusRing})`, outlineOffset: -2 }),
          } : null),
        }}
      >
        <ScrollRootContext.Provider value={scrolls || (fill && body === "table") ? "auto" : null}>
          <StateRegion>{children}</StateRegion>
        </ScrollRootContext.Provider>
      </Box>
      {foot ? (
        <Box data-pane-foot="" sx={{ flexShrink: 0, borderTop: 1, borderColor: "divider", px: 2.5, py: 1.25 }}>{foot}</Box>
      ) : null}
    </Surface>
  );
}

/** 판 머리 — 위에 작은 경로 줄(선택), 그 아래 [앞 아이콘] [제목 · 상태 …] [동작] 한 줄(`HeadRow`, 첫 줄 가운데선).
 *
 *   titleRef  제목에 초점을 옮겨야 하는 화면(한 열 배치에서 고른 결과로 옮겨 가기)이 준다 — 주면 제목이 `tabIndex=-1` 이다
 *   meta      제목 바로 옆의 짧은 상태(정상이 아닐 때만 서는 점 + 낱말). 제목이 말줄임이 되어도 상태는 잘리지 않는다 */
export function PaneHead({ above, lead, title, titleAs = "h2", titleRef, meta, action, children }) {
  return (
    <Box data-pane-head-row="" sx={{ minWidth: 0, display: "grid", rowGap: 0.5 }}>
      {above ? <Box sx={{ minWidth: 0 }}>{above}</Box> : null}
      <HeadRow lead={lead} action={action}>
        <Box sx={{ display: "flex", alignItems: "center", columnGap: 1, minWidth: 0 }}>
          <Typography
            component={titleAs}
            variant="sectionTitle"
            ref={titleRef}
            tabIndex={titleRef ? -1 : undefined}
            title={typeof title === "string" ? title : undefined}
            sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {title}
          </Typography>
          {meta ? <Box sx={{ flexShrink: 0, display: "inline-flex", alignItems: "center" }}>{meta}</Box> : null}
        </Box>
        {children}
      </HeadRow>
    </Box>
  );
}

/** 판 도구 줄 — 왼쪽부터 흐르는 칸들, 좁으면 줄바꿈. 높이 34 의 칸이 한 줄에 선다. */
export function PaneToolbar({ children, sx }) {
  return (
    <Box data-pane-toolbar-row="" sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1.5, minWidth: 0, ...sx }}>
      {children}
    </Box>
  );
}

export default Workspace;
