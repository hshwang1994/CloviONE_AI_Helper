import React from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import BlockRoundedIcon from "@mui/icons-material/BlockRounded";
import ScheduleRoundedIcon from "@mui/icons-material/ScheduleRounded";
import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";

import { DotLabel, EXTRA_TONE_VARS } from "./kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "./theme.js";
import { SIGNALS } from "../lib/ticketSignals.js";

/* Signal 표시 — **상태 옆에 서지만 상태가 아니다** (D-349).
 *
 * ## 왜 밀도가 둘인가
 *
 * 같은 의미는 제품 전체에서 같은 색과 같은 모양이어야 한다. 그런데 이 신호가 서는
 * 자리는 밀도가 다르다: 목록의 한 칸은 7rem 이고 상세 화면의 머리글은 한 줄이 통째로
 * 비어 있다. 한쪽에 맞추면 다른 쪽이 깨진다 — 목록에 글자 알약 셋을 넣으면 열이
 * 가로로 밀리고, 상세에 점 셋만 찍으면 아무도 그것이 무슨 뜻인지 모른다.
 *
 * 그래서 **밀도만 둘이고 어휘는 하나다.** 색·아이콘·이름이 전부 `lib/ticketSignals.js`
 * 의 같은 표에서 나오고, 좁은 쪽에서도 접근 이름은 온전한 낱말이다 — 화면을 읽어
 * 주는 사람에게는 두 밀도가 같은 말을 한다.
 *
 *   variant="dot"   점 + 낱말 **(기본)**. 표 · 칸반 카드 · 목록 행 — 핸드오프 D-14 · D-21 의 어휘
 *   variant="pill"  아이콘 + 낱말 + 옅은 면. 상세 화면 머리처럼 목록 **밖**에서만
 *   variant="mark"  아이콘만. 폭이 정말 없는 표 칸(백로그 줄 · 좁은 목록)에 딸려 선다(P-5)
 *
 * 색만으로 전달하지 않는다(WCAG 1.4.1): 아이콘 **모양**이 셋 다 다르고
 * (막음 · 시계 · 느낌표) 낱말이 항상 접근 이름에 있다.
 */

const ICON = {
  blocked: BlockRoundedIcon,
  overdue: ScheduleRoundedIcon,
  issue: ErrorOutlineRoundedIcon,
};

const TONE_PALETTE = {
  danger: { ink: "error.strong", bg: "error.bg", dot: "error.main" },
  warn: { ink: "warning.strong", bg: "warning.bg", dot: "warning.main" },
  info: { ink: "info.strong", bg: "info.bg", dot: "info.main" },
};
/* 분류 톤의 색은 키트의 표 한 벌이다(`kit.jsx::EXTRA_TONE_VARS`) — 여기 사본이 있던 동안
   두 표가 따로 고쳐질 수 있었다. */
function toneColors(tone) {
  if (TONE_PALETTE[tone]) return TONE_PALETTE[tone];
  const extra = EXTRA_TONE_VARS[tone];
  return extra ? { ink: extra.fg, bg: extra.bg, dot: extra.fg } : TONE_PALETTE.warn;
}

/* REAUDIT A8 — `blocked_reason` 은 API 가 이미 실었는데 어느 화면도 안 읽었다(차단됐다는
 * 사실만 보이고 왜인지는 안 보였다). `signal.reason` 이 있을 때만(차단 신호 · 사연이 실제로
 * 있을 때) Tooltip 으로 감싼다 — 나머지 신호(지연·이슈)와 사연 없는 차단은 지금과 똑같다. */
function SignalPill({ signal }) {
  const Icon = ICON[signal.key];
  const tone = toneColors(signal.tone);
  const body = (
    <Box
      component="span"
      className="k-signal"
      data-signal={signal.key}
      data-tone={signal.tone}
      sx={{
        display: "inline-flex", alignItems: "center", gap: 0.5,
        px: 0.75, py: 0.125, borderRadius: `${RADIUS.sm}px`,
        maxWidth: "100%", minWidth: 0, whiteSpace: "nowrap",
        fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, lineHeight: 1.4,
        bgcolor: tone.bg, color: tone.ink,
      }}
    >
      <Icon aria-hidden="true" fontSize="inherit" />
      <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
        {signal.label}
      </Box>
    </Box>
  );
  return signal.reason ? <Tooltip title={signal.reason}>{body}</Tooltip> : body;
}

function SignalMark({ signal }) {
  const Icon = ICON[signal.key];
  const tone = toneColors(signal.tone);
  // `title` 은 브라우저 기본 툴팁이다 — 사연이 있으면 그 자리에 이어 붙인다(좁은 목록은
  // MUI Tooltip 을 안 쓴다, 위 밀도 설명 참고).
  const title = signal.reason ? `${signal.label}: ${signal.reason}` : signal.label;
  return (
    <Box
      component="span"
      className="k-signal-mark"
      data-signal={signal.key}
      data-tone={signal.tone}
      role="img"
      aria-label={title}
      title={title}
      sx={{
        display: "inline-flex", alignItems: "center", flexShrink: 0,
        fontSize: FONT_SIZE.bodySm, lineHeight: 1,
        color: tone.dot,
      }}
    >
      <Icon aria-hidden="true" fontSize="inherit" />
    </Box>
  );
}

function SignalDot({ signal }) {
  const body = (
    <DotLabel
      label={signal.label}
      tone={signal.tone}
      strong={signal.tone === "danger"}
      /* 신호 표지를 짚는 손잡이는 밀도와 무관하게 같다 — 시험과 프로브가 `data-signal` 로 찾는다. */
      data-signal={signal.key}
      data-tone={signal.tone}
      /* 사연이 있으면 MUI Tooltip 이 말한다(A8) — 브라우저 기본 툴팁과 둘이 겹쳐 뜨지 않게
         그때는 `title` 을 비운다. */
      title={signal.reason ? "" : signal.label}
      sx={{ fontSize: FONT_SIZE.caption }}
    />
  );
  /* Tooltip 은 ref 를 받는 자식이 필요하다 — 점+낱말을 span 하나로 감싼다.
     사연은 **읽어 주는 글자로도** 붙인다. 예전 칸반 카드의 표지(`mark`)는 `role="img"` 의 이름이
     「차단됨: 사연」이었는데, 점+낱말로 바뀌면서 사연이 마우스를 올려야만 뜨는 Tooltip 에만 남았다
     — 낭독기와 키보드 사용자에게서 사연이 사라진 셈이다. `describeChild` 는 Tooltip 이 감싼 span 에
     `aria-label` 을 덮어 보이는 낱말을 가리지 않게 한다. */
  return signal.reason
    ? (
      <Tooltip title={signal.reason} describeChild>
        <Box component="span" sx={{ display: "inline-flex", minWidth: 0 }}>
          {body}
          <span className="sr-only">{`: ${signal.reason}`}</span>
        </Box>
      </Tooltip>
    )
    : body;
}

/** 켜져 있는 신호를 그린다. 하나도 없으면 **아무것도 그리지 않는다.**
 *
 * 빈 자리에 «-» 를 찍지 않는 이유: 「신호가 없다」는 값이 빠진 것이 아니라 정상이고,
 * 목록의 대부분이 그 상태다. 대시를 찍으면 화면이 없는 데이터로 가득 찬 것처럼 보인다.
 */
export function TicketSignals({ signals, variant = "dot", sx }) {
  const list = Array.isArray(signals) ? signals : [];
  if (!list.length) return null;
  const Item = variant === "mark" ? SignalMark : variant === "pill" ? SignalPill : SignalDot;
  return (
    <Box
      component="span"
      data-signal-variant={variant}
      sx={{
        display: "inline-flex", alignItems: "center", minWidth: 0, flexWrap: variant === "dot" ? "wrap" : "nowrap",
        columnGap: variant === "mark" ? 0.375 : variant === "dot" ? 1 : 0.5, rowGap: 0.25,
        ...sx,
      }}
    >
      {list.map((s) => <Item key={s.key} signal={s} />)}
    </Box>
  );
}

/** 어휘 표를 그대로 다시 내보낸다 — 화면이 두 곳을 import 하지 않게. */
export { SIGNALS };
