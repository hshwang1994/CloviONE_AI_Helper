import Box from "@mui/material/Box";
import { alpha } from "@mui/material/styles";
import { keyframes } from "@mui/system";
import { UserAvatar } from "../../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, MOTION, RADIUS } from "../../../ui/theme.js";
import { rise } from "../constants.js";
import { useBoardSize } from "../BoardFrame.jsx";

/* 사람 칸 하나 (D-577) — 판의 격자(대기 · 추첨 · 숫자 · 손)가 같은 칸을 쓴다: 얼굴 · 이름(두 줄까지) · 아래 한 줄(준비 · 숫자 · 손).
 *
 * 상태 넷: `idle` 보통 · `winner` 당첨(브랜드 테두리 + 옅은 면 + 얼굴 둘레) · `dim` 공개 뒤의 나머지(흐리게) · `sweep` 발표 중의 훑기
 * (칸마다 늦게 시작하는 하이라이트 — 「누가 뽑힐까」의 순간). 칸 폭은 격자(`PeopleGrid`)가 정하고, 칸은 자기 내용보다 줄지 않는다. */

const sweepGlow = keyframes`
  0%, 100% { box-shadow: 0 0 0 0 transparent; }
  45% { box-shadow: 0 0 0 2px var(--sweep-ring), 0 6px 18px var(--sweep-shadow); }
`;

const NAME_CLAMP = {
  ...KO_WORD_BREAK, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
  lineHeight: 1.3, maxWidth: "100%", textAlign: "center",
};

export function PersonTile({ person, name, size = "lg", sub, badge, state = "idle", delayMs = 0, sweepMs = 900, me = false, label }) {
  const winner = state === "winner";
  return (
    <Box
      component="li"
      data-person-tile={state}
      aria-label={label}
      sx={(t) => ({
        listStyle: "none", minWidth: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 0.75,
        px: 1, py: 1.25, borderRadius: `${RADIUS.md}px`, position: "relative",
        /* 상태 고리(당첨 · 나)는 안쪽 그림자 한 겹 — 테두리 네 변이면 큰 칸이 판 안의 카드 모양 상자가 된다(F7 nested_card). */
        boxShadow: winner ? `inset 0 0 0 1px ${t.palette.primary.main}` : me ? `inset 0 0 0 1px ${alpha(t.palette.primary.main, 0.45)}` : "none",
        bgcolor: winner ? alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.2 : 0.1) : "transparent",
        opacity: state === "dim" ? 0.55 : 1,
        transition: `opacity ${MOTION.base} ${MOTION.ease}, background-color ${MOTION.base} ${MOTION.ease}`,
        animation: state === "sweep" ? `${sweepGlow} ${sweepMs}ms ${delayMs}ms ease-in-out both` : winner ? `${rise} .38s ease both` : "none",
        "--sweep-ring": t.palette.primary.main,
        "--sweep-shadow": alpha(t.palette.primary.main, 0.25),
      })}
    >
      <UserAvatar
        person={person} name={name} size={size}
        sx={winner ? { boxShadow: (t) => `0 0 0 2px ${t.palette.background.paper}, 0 0 0 4px ${t.palette.primary.main}` } : undefined}
      />
      <Box component="span" title={name} sx={{ ...NAME_CLAMP, fontSize: FONT_SIZE.bodySm, fontWeight: winner ? FONT_WEIGHT.bold : FONT_WEIGHT.semibold }}>
        {name}
      </Box>
      {sub ? (
        <Box component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", textAlign: "center", ...KO_WORD_BREAK }}>{sub}</Box>
      ) : null}
      {badge ? <Box sx={{ display: "flex", justifyContent: "center" }}>{badge}</Box> : null}
    </Box>
  );
}

const SIZES = ["xl", "lg", "md"];
const REM_PX = 16;
/* 판에 맞추는 계산에만 쓰는 칸의 대략 자리(rem). 칸 수는 격자 칸의 **최대** 폭으로 센다 — `repeat(auto-fit, minmax(a, b))` 는 b 로 반복
   수를 정한다. 키는 얼굴 · 이름 한 줄 · 아래 줄(준비 · 방장)까지가 `short`, 숫자 · 손처럼 큰 아래 줄과 「승리」 표지까지가 `tall` 이다. */
const TILE_FIT = {
  xl: { track: 10, gap: 1.25, short: 9, tall: 11.5 },
  lg: { track: 8, gap: 1.25, short: 7, tall: 9.5 },
  md: { track: 6, gap: 0.75, short: 6.25, tall: 9 },
};
/** 격자 밖의 판 내용(아래 문장 한 줄과 사이)의 자리 · 판 안쪽 여백(`BoardFrame.Centered`) · 넘침 허용(추정의 오차). */
const FIT_RESERVE_PX = 40;
const FIT_SLACK = 1.05;

/** 사람 수에 맞는 얼굴 크기 — 적으면 판이 비어 보이지 않게 크게(72px), 보통은 40px, 많으면 30px.
 *
 * 판의 크기(`board` — `useBoardSize()`)를 알면 그 판에 다 들어가는 가장 큰 크기까지만 내린다. 전화(판 358 × 268)에서 두 사람이 72px
 * 칸 하나씩 세로로 서서 둘째가 판 밖으로 밀렸다(390 실측) — 이제 40px 두 칸이 한 줄에 선다. 판 밖(결과 대화 상자의 상세)은 사람 수만
 * 본다. `rows` 는 칸 키(`short` · `tall`)다. */
export function tileSize(count, board, rows = "short") {
  const base = count <= 6 ? "xl" : count <= 24 ? "lg" : "md";
  if (!board || !(board.width > 0) || !(board.height > 0) || !(count > 0)) return base;
  const pad = 2 * (board.width < 600 ? 16 : 24);
  const width = board.width - pad;
  const height = (board.height - pad - FIT_RESERVE_PX) * FIT_SLACK;
  for (let i = SIZES.indexOf(base); i < SIZES.length; i += 1) {
    const f = TILE_FIT[SIZES[i]];
    const gap = f.gap * REM_PX;
    const cols = Math.max(1, Math.floor((width + gap) / (f.track * REM_PX + gap)));
    const lines = Math.ceil(count / cols);
    if (lines * (f[rows] || f.short) * REM_PX + (lines - 1) * gap <= height) return SIZES[i];
  }
  return "md";
}

/** 판 안의 격자가 쓸 얼굴 크기 — 판 크기 문맥(`BoardFrame`)을 읽는다. 문맥 밖이면 판 크기가 0 이라 사람 수만 본다. */
export function usePeopleTileSize(count, rows = "short") {
  return tileSize(count, useBoardSize(), rows);
}

/** 사람 칸의 격자 — 칸 폭은 얼굴 크기를 따르고(넉넉 8 ~ 10rem · 보통 6.5 ~ 8rem · 촘촘 5 ~ 6rem), 남는 폭은 가운데. 크기는 칸과 같은
 *  값(`size`)을 받는다 — 없으면 사람 수로 정한다. */
export function PeopleGrid({ children, count = 0, size: sizeProp, label, sx }) {
  const size = sizeProp || tileSize(count);
  const track = size === "xl" ? "minmax(8rem, 10rem)" : size === "lg" ? "minmax(6.5rem, 8rem)" : "minmax(5rem, 6rem)";
  return (
    <Box
      component="ul"
      aria-label={label}
      sx={{
        m: 0, p: 0, width: "100%", display: "grid", gap: size === "md" ? 0.75 : 1.25, justifyContent: "center",
        gridTemplateColumns: `repeat(auto-fit, ${track})`,
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}
