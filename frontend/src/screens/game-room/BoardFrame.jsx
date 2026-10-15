import React from "react";
import Box from "@mui/material/Box";
import { Surface } from "../../ui/kit.jsx";
import { RADIUS } from "../../ui/theme.js";

/* 판의 틀 (게임 공통 G1 · D-575) — 껍데기의 판 칸을 꽉 채우는 판면 하나.
 *
 * 모든 게임의 판이 이 틀 안에 선다 — 대기 중의 참가자 격자도, 진행 중의 투표 보기도, 끝난 뒤의 사다리도, 구슬 레이스의 캔버스도.
 * 틀은 `Surface tone="plate"` 에 안쪽 여백 0 · 넘침 숨김 · 모서리 `RADIUS.md`(8px — 문자열로 적는다. `sx.borderRadius` 에 숫자를
 * 넣으면 MUI 가 8 을 곱해 64px 모서리가 된다 — 예전 캔버스 상자가 그랬다) 이고, 안의 측정 상자가 틀의 크기를 `ResizeObserver` 하나로
 * 재서 문맥(`useBoardSize`)으로 준다. 캔버스 · SVG 판은 그 값으로 자기 픽셀을 정하고 DOM 판은 `BoardFrame.Centered` 로 가운데에
 * 선다(넘치면 틀 안에서 굴린다 — 틀 밖으로 자라 레일과 어긋나지 않는다).
 *
 * 판 위의 알림(확인 중 · 확정 실패 · 중단)은 `BoardFrame.Notice` 로 판 위에 뜬다 — 판 위에 줄을 끼우면 판이 밀려 대기 → 진행 →
 * 종료 동안 판의 자리가 흔들린다. */

const BoardSizeCtx = React.createContext({ width: 0, height: 0 });

/** 틀 안쪽의 픽셀 크기(정수). 아직 못 쟀으면 0 이다. */
export function useBoardSize() {
  return React.useContext(BoardSizeCtx);
}

export function BoardFrame({ children, label, sx, ...rest }) {
  const innerRef = React.useRef(null);
  const [size, setSize] = React.useState({ width: 0, height: 0 });
  React.useEffect(() => {
    const el = innerRef.current;
    if (!el) return undefined;
    const measure = () => {
      const r = el.getBoundingClientRect();
      const width = Math.max(0, Math.round(r.width));
      const height = Math.max(0, Math.round(r.height));
      setSize((prev) => (prev.width === width && prev.height === height ? prev : { width, height }));
    };
    measure();
    if (typeof ResizeObserver !== "function") return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <Surface
      tone="plate"
      component="section"
      aria-label={label}
      data-board-frame=""
      sx={(t) => ({
        p: 0, position: "relative", overflow: "hidden", minWidth: 0, minHeight: 0, flex: "1 1 auto",
        borderRadius: `${RADIUS.md}px`,
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
      {...rest}
    >
      {/* 측정 상자 — 틀을 꽉 채운다. 안의 판이 틀보다 커도 틀이 자라지 않는다(절대 배치). */}
      <Box ref={innerRef} data-board-inner="" sx={{ position: "absolute", inset: 0, minWidth: 0, minHeight: 0 }}>
        <BoardSizeCtx.Provider value={size}>{children}</BoardSizeCtx.Provider>
      </Box>
    </Surface>
  );
}

/** DOM 판의 자리 — 가운데 정렬 · 안쪽 여백 · 넘치면 틀 안에서 굴린다. 넘쳐도 위쪽이 잘리지 않게 안쪽 묶음이 `margin: auto` 로
 *  선다(공간이 남으면 가운데, 모자라면 위에서부터 — `justify-content: center` 는 넘칠 때 위를 잘라 굴려도 닿지 않는다). */
function Centered({ children, sx, ...rest }) {
  return (
    <Box
      data-board-centered=""
      sx={{ position: "absolute", inset: 0, overflowY: "auto", overflowX: "hidden", overscrollBehavior: "contain", display: "flex", p: { xs: 2, md: 3 } }}
      {...rest}
    >
      <Box
        sx={(t) => ({
          m: "auto", width: "100%", minWidth: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 2.5,
          ...(typeof sx === "function" ? sx(t) : sx),
        })}
      >
        {children}
      </Box>
    </Box>
  );
}
BoardFrame.Centered = Centered;

/** 판 위에 뜨는 알림 한 줄 — 위 가운데. 판의 자리를 밀지 않는다. */
function Notice({ children }) {
  return (
    <Box
      data-board-notice=""
      sx={{
        position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", zIndex: 3,
        width: "max-content", maxWidth: "calc(100% - 24px)", pointerEvents: "auto",
      }}
    >
      {children}
    </Box>
  );
}
BoardFrame.Notice = Notice;
